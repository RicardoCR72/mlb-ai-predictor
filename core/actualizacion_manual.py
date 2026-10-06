"""Actualización solicitada desde la app: resultados oficiales, sin cuotas ni mensajes."""
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import os
import re
import subprocess
import sys
import threading
from zoneinfo import ZoneInfo
import pandas as pd
from core.db import get_db_connection, get_db_credentials
from core import bankroll as bank

SERVICES = ('mlb','nfl_totales','nfl_props','liga_mx','bankroll')
LOCKS = {service:threading.Lock() for service in SERVICES}
SCRIPTS = {'nfl_totales':'nfl/evaluar_resultados.py','nfl_props':'nfl/evaluar_resultados_props.py'}


def child_environment():
    config=get_db_credentials()
    env=os.environ.copy()
    for key,field in {'DB_HOST':'host','DB_PORT':'port','DB_USER':'user','DB_PASSWORD':'password',
                      'DB_PASS':'password','DB_NAME':'database','DB_SSL_CA':'ssl_ca'}.items():
        if field in config:env[key]=str(config[field])
    # Las actualizaciones manuales no envían notificaciones ni consumen odds.
    env['TELEGRAM_REPORTE_UNIFICADO']='1'
    for key in ('TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','ODDS_API_KEY','THE_ODDS_API_KEY'):
        env.pop(key,None)
    return env


def run_script(service,root):
    if service not in SCRIPTS:raise ValueError('Proceso manual no permitido.')
    result=subprocess.run([sys.executable,str(Path(root)/SCRIPTS[service])],cwd=str(root),
                          env=child_environment(),capture_output=True,text=True,timeout=240)
    if result.returncode:
        # No mostrar stderr/tracebacks que podrían contener información de conexión.
        raise RuntimeError(f'El evaluador terminó con código {result.returncode}; revisa la conexión y las dependencias NFL.')
    output=result.stdout if isinstance(result.stdout,str) else ''
    match=re.search(r'(?:Predicciones|Proyecciones) evaluadas:\s*(\d+)',output)
    return f"{match.group(1) if match else '0'} resultados NFL evaluados. Los partidos sin resultado oficial siguen pendientes."


def refresh_mlb_games(conn,now=None):
    from mlb_totales.descargar_pitcheo import fetch_json,TYPES
    now=now or datetime.now(ZoneInfo('America/Mexico_City'))
    pending=bank.rows(conn,"""SELECT id_juego,fecha,equipo_local,equipo_visitante FROM juegos
        WHERE LOWER(estado)='programado' AND DATE(fecha)<=%s
        ORDER BY fecha DESC""",(now.date(),))
    if pending.empty:return 'Sin partidos MLB pendientes de resultados.'
    pending['dia']=pd.to_datetime(pending.fecha).dt.date
    days=sorted(set(pending.dia),reverse=True)[:15]
    changed,ambiguous=0,0
    cursor=conn.cursor()
    try:
        for day in days:
            data=fetch_json('schedule',{'sportId':1,'date':str(day),'gameType':TYPES,'hydrate':'linescore'})
            games=[g for d in data.get('dates',[]) for g in d.get('games',[])]
            def pair(game):
                names=[game['teams'][side]['team']['name'] for side in ('home','away')]
                return tuple('Athletics' if n=='Oakland Athletics' else n for n in names)
            counts=Counter(pair(game) for game in games)
            for game in games:
                if game.get('status',{}).get('abstractGameState')!='Final':continue
                home,away=pair(game)
                matching=pending[(pending.dia==day)&pending.equipo_local.eq(home)&pending.equipo_visitante.eq(away)]
                if counts[(home,away)]!=1 or len(matching)>1:
                    ambiguous+=1;continue  # no liquidar ambos juegos de una doble cartelera con el mismo marcador
                if matching.empty:continue
                h,a=game['teams']['home'],game['teams']['away']
                if 'score' not in h or 'score' not in a:continue
                cursor.execute("""UPDATE juegos SET marcador_local=%s,marcador_visitante=%s,estado='finalizado'
                    WHERE id_juego=%s AND LOWER(estado)='programado'""",
                    (int(h['score']),int(a['score']),matching.iloc[0].id_juego))
                changed+=cursor.rowcount
        conn.commit()
    except Exception:
        conn.rollback();raise
    finally:cursor.close()
    return f'{changed} partidos MLB actualizados. {ambiguous} coincidencias ambiguas requieren revisión. Se revisaron hasta 15 fechas pendientes.'


def mlb_totals(conn):
    from mlb_totales.registro import prepare,refresh_results
    prepare(conn)
    return f'{refresh_results(conn)} resultados MLB Totales V2 consultados y guardados.'


def refresh_liga(root):
    from futbol_liga_mx.proveedor_espn import run
    folder=Path(root)/'futbol_liga_mx/data'
    # Escaneo completo para que la evidencia de cobertura siga siendo verificable.
    past,future=run(str(folder/'partidos.csv'),str(folder/'proximos.csv'),
                    season_end=datetime.now(ZoneInfo('America/Mexico_City')).date()+timedelta(days=14),workers=4,include_today=True,strict=True)
    return f'Historial: {len(past)} partidos. Calendario: {len(future)} próximos. Modelo congelado conservado.'


def settle_bank(conn,root):
    bank.prepare(conn)
    count,errors=bank.settle_pending(conn,root)
    if errors:raise RuntimeError(f'{count} apuestas liquidadas; {len(errors)} pendientes de revisión.')
    return f'{count} apuestas realizadas liquidadas con los resultados disponibles.'


def run_update(service,root,on_step=None):
    if service not in SERVICES:raise ValueError('Servicio inválido.')
    # Mismo candado para todas las sesiones de este proceso Streamlit.
    if not LOCKS[service].acquire(blocking=False):
        return {'busy':True,'steps':[], 'at':datetime.now(ZoneInfo('America/Mexico_City')).isoformat()}
    output=[];conn=None
    def step(label,fn):
        if on_step:on_step(label)
        try:
            output.append({'paso':label,'ok':True,'detalle':fn()})
            return True
        except Exception as exc:
            # Detalles propios controlados; errores externos nunca exponen secretos.
            message=str(exc) if type(exc) is RuntimeError else type(exc).__name__
            output.append({'paso':label,'ok':False,'detalle':message})
            return False
    def db():
        nonlocal conn
        if conn is None:conn=get_db_connection()
        return conn
    def sport(which):
        if which=='mlb':
            step('Marcadores MLB',lambda:refresh_mlb_games(db()))
            step('Resultados MLB Totales V2',lambda:mlb_totals(db()))
        elif which in SCRIPTS:
            step('Resultados NFL totales' if which=='nfl_totales' else 'Resultados NFL props',lambda:run_script(which,root))
        elif which=='liga_mx':
            step('Resultados y calendario Liga MX',lambda:refresh_liga(root))
    try:
        if service=='bankroll':
            try:
                bank.prepare(db())
                ledger=bank.load_ledger(db())
                pending=ledger[ledger.estado.eq('Pendiente')]
                origins=set(pending.origen)
                wanted=[]
                if origins & {'mlb_total','mlb_ml'}:wanted.append('mlb')
                if 'nfl_total' in origins:wanted.append('nfl_totales')
                if 'nfl_prop' in origins:wanted.append('nfl_props')
                if 'liga_mx' in origins:wanted.append('liga_mx')
                for which in wanted:
                    if LOCKS[which].acquire(blocking=False):
                        try:sport(which)
                        finally:LOCKS[which].release()
                    else:output.append({'paso':which,'ok':False,'detalle':'Ya hay una actualización en curso; vuelve a intentar al terminar.'})
            except Exception as exc:
                output.append({'paso':'Leer apuestas pendientes','ok':False,'detalle':type(exc).__name__})
        else:sport(service)
        step('Liquidación de bankroll',lambda:settle_bank(db(),root))
    finally:
        try:
            if conn is not None:conn.close()
        finally:LOCKS[service].release()
    return {'busy':False,'steps':output,'at':datetime.now(ZoneInfo('America/Mexico_City')).isoformat()}
