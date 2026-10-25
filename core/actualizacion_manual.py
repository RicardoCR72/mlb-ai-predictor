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

SERVICES = ('mlb','nfl_totales','nfl_props','nfl_moneyline','liga_mx','bankroll')
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


def verified_mlb_starts(pending,games):
    """Correspondencia única por horario, con hasta 90 segundos entre fuentes.

    El scraper guarda juegos.fecha como commence_time UTC menos seis horas.
    No elegir el más cercano: cada lado debe tener un único candidato posible.
    Una fecha sin hora no es evidencia suficiente para una doble cartelera.
    """
    edges=[]
    for game in games:
        try:
            start=pd.Timestamp(game['gameDate'])
            if start.tzinfo is None:continue
            for _,row in pending.iterrows():
                stamp=pd.Timestamp(row.fecha)
                if pd.isna(stamp) or stamp==stamp.normalize():continue
                if stamp.tzinfo is None:stamp=stamp.tz_localize('Etc/GMT+6')
                if abs((stamp.tz_convert('UTC')-start.tz_convert('UTC')).total_seconds())<=90:
                    edges.append((str(game['gamePk']),str(row.id_juego)))
        except (KeyError,ValueError,TypeError):continue
    official_counts=Counter(pk for pk,id in edges)
    stored_counts=Counter(id for pk,id in edges)
    return {pk:id for pk,id in edges if official_counts[pk]==1 and stored_counts[id]==1}


def refresh_mlb_games(conn,now=None,on_ambiguity=None):
    from mlb_totales.descargar_pitcheo import fetch_json,TYPES
    now=now or datetime.now(ZoneInfo('America/Mexico_City'))
    pending=bank.rows(conn,"""SELECT id_juego,fecha,equipo_local,equipo_visitante FROM juegos
        WHERE LOWER(estado)='programado' AND DATE(fecha)<=%s
        ORDER BY fecha DESC""",(now.date(),))
    if pending.empty:return 'Sin partidos MLB pendientes de resultados.'
    pending['dia']=pd.to_datetime(pending.fecha).dt.date
    days=sorted(set(pending.dia),reverse=True)[:15]
    changed,ambiguous=0,0
    refunded=0
    from core.devoluciones import mlb_refund_reason, save_refund
    reported=set()
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
                refund_reason=mlb_refund_reason(game,day)
                cancelled=refund_reason is not None
                if not cancelled and game.get('status',{}).get('abstractGameState')!='Final':continue
                home,away=pair(game)
                matching=pending[(pending.dia==day)&pending.equipo_local.eq(home)&pending.equipo_visitante.eq(away)]
                if matching.empty:continue
                h,a=game['teams']['home'],game['teams']['away']
                if not cancelled and (h.get('score') is None or a.get('score') is None):continue
                if counts[(home,away)]!=1 or len(matching)>1:
                    official=[g for g in games if pair(g)==(home,away)]
                    exact=verified_mlb_starts(matching,official)
                    identity=exact.get(str(game['gamePk']))
                    unresolved=matching[~matching.id_juego.astype(str).isin(exact.values())]
                    # Solo contar registros nuestros, una vez por pareja/fecha.
                    # Una doble cartelera ajena al historial no es un pendiente.
                    key=(day,home,away)
                    if not unresolved.empty and key not in reported:
                        reported.add(key)
                        ambiguous+=len(unresolved)
                        if on_ambiguity:on_ambiguity(dict(fecha=str(day),local=home,visitante=away,
                            pendientes=unresolved.id_juego.astype(str).tolist(),
                            horas_guardadas=unresolved.fecha.astype(str).tolist(),
                            oficiales=[dict(game_pk=g['gamePk'],inicio=g.get('gameDate')) for g in official]))
                    if identity is None:continue  # Sin evidencia, no asignar marcador.
                    matching=matching[matching.id_juego.astype(str).eq(identity)]
                if cancelled:
                    save_refund(conn,sport='MLB',game_id=str(matching.iloc[0].id_juego),
                        official_id=game['gamePk'],legacy_key=f'{day.isoformat()}|{home}|{away}',
                        reason=refund_reason,source='MLB Stats API',
                        evidence={'gamePk':game['gamePk'],'status':game['status'],'date':str(day),
                                  'rescheduleGameDate':game.get('rescheduleGameDate')})
                    refunded+=1
                    continue
                cursor.execute("""UPDATE juegos SET marcador_local=%s,marcador_visitante=%s,estado='finalizado'
                    WHERE id_juego=%s AND LOWER(estado)='programado'""",
                    (int(h['score']),int(a['score']),matching.iloc[0].id_juego))
                changed+=cursor.rowcount
        conn.commit()
    except Exception:
        conn.rollback();raise
    finally:cursor.close()
    return f'{changed} partidos MLB actualizados. {refunded} partidos con devolución confirmada. {ambiguous} coincidencias ambiguas requieren revisión. Se revisaron hasta 15 fechas pendientes.'


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
        elif which in ('nfl_totales', 'nfl_props', 'nfl_moneyline'):
            from nfl.liquidar_nfl import liquidar_todo_nfl
            step('Liquidación NFL (Totales, Moneyline y Props)', lambda: liquidar_todo_nfl().get('mensaje'))
        elif which=='liga_mx':
            step('Resultados y calendario Liga MX',lambda:refresh_liga(root))
            from futbol_liga_mx.registro import liquidar_partidos_pendientes_ligamx
            step('Liquidación Liga MX',lambda:liquidar_partidos_pendientes_ligamx().get('mensaje'))
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
                if 'nfl_moneyline' in origins:wanted.append('nfl_moneyline')
                if 'liga_mx' in origins:wanted.append('liga_mx')
                for which in wanted:
                    if LOCKS[which].acquire(blocking=False):
                        try:sport(which)
                        finally:LOCKS[which].release()
                    else:output.append({'paso':which,'ok':False,'detalle':'Ya hay una actualización en curso; vuelve a intentar al terminar.'})
            except Exception as exc:
                output.append({'paso':'Leer apuestas pendientes','ok':False,'detalle':type(exc).__name__})
        else:sport(service)
        if service=='bankroll':step('Liquidación de bankroll',lambda:settle_bank(db(),root))
    finally:
        try:
            if conn is not None:conn.close()
        finally:LOCKS[service].release()
    return {'busy':False,'steps':output,'at':datetime.now(ZoneInfo('America/Mexico_City')).isoformat()}
