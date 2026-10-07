"""Resumen de solo lectura; una fuente fallida no oculta las demás."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import pandas as pd
from core import bankroll as bank

LABELS = {'mlb':'MLB · Moneyline', 'mlb_total':'MLB · Totales V2',
          'nfl_totales':'NFL · Totales', 'nfl_props':'NFL · Props', 'liga_mx':'Liga MX', 'bankroll':'Bankroll'}


def empty(service):
    return dict(service=service,label=LABELS[service],games_today=None,picks_today=None,
        pending=None,last_data=None,last_result=None,games=[],pending_items=[],detail='',errors=[])


def mx_date(value, utc=False):
    stamp = pd.to_datetime(value, errors='coerce')
    if pd.isna(stamp): return None
    if utc and stamp.tzinfo is None: stamp = stamp.tz_localize('UTC')
    if stamp.tzinfo is not None: stamp = stamp.tz_convert('America/Mexico_City')
    return stamp.date()


def maximum(frame, column):
    if frame.empty or column not in frame: return None
    values = pd.to_datetime(frame[column], errors='coerce').dropna()
    return str(values.max()) if len(values) else None


def game_summary(frame, now, utc=False):
    today = now.astimezone(ZoneInfo('America/Mexico_City')).date()
    future, past = [], 0
    for row in frame.to_dict('records'):
        day = mx_date(row['fecha'], utc)
        if day is None: continue
        final_flag = str(row.get('estado','')).lower().strip()=='finalizado'
        missing_scores = pd.isna(row.get('marcador_local')) or pd.isna(row.get('marcador_visitante'))
        finished = final_flag or not missing_scores
        if missing_scores and (day<today or final_flag): past += 1
        if not finished and today <= day <= today+timedelta(days=6):
            if utc:
                start = pd.Timestamp(row['fecha'])
                start = start.tz_localize('UTC') if start.tzinfo is None else start
                if start <= pd.Timestamp(now): continue
                time = start.tz_convert('America/Mexico_City').strftime('%H:%M CDMX')
            else: time = 'Hora no verificada'
            future.append(dict(Fecha=day.isoformat(),Horario=time,Partido=f"{row['visitante']} @ {row['local']}"))
    return sum(g['Fecha']==today.isoformat() for g in future),past,future


def prediction_summary(frame, now, *, keys, candidate, utc=False):
    today = now.astimezone(ZoneInfo('America/Mexico_City')).date()
    frame = frame.drop_duplicates(keys,keep='first')
    picks, pending, items = 0, 0, []
    final_states = {'GANADA','PERDIDA','PUSH','ANULADA','VOID'}
    for row in frame.to_dict('records'):
        day = mx_date(row['fecha'],utc)
        if day is None: continue
        result = str(row.get('resultado','') or '').upper().strip()
        final_game = str(row.get('estado_juego','')).lower().strip()=='finalizado'
        resolved = result in final_states or bool(row.get('resuelto',False))
        if not resolved and (day<today or final_game):
            pending += 1
            items.append({'Fecha':day.isoformat(), 'Partido':f"{row.get('visitante','')} @ {row.get('local','')}",
                'Selección':f"{row.get('jugador','')} {row.get('seleccion','')} {row.get('linea','')}".strip()})
        available = not resolved and not final_game and day==today and candidate(row)
        if utc:
            stamp=pd.Timestamp(row['fecha'])
            stamp=stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp
            available = available and stamp > pd.Timestamp(now)
        if available: picks += 1
    return picks,pending,items


def read_summary(conn, root, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None: raise ValueError('El resumen requiere una hora con zona horaria.')
    today = now.astimezone(ZoneInfo('America/Mexico_City')).date()
    horizon = (today+timedelta(days=8)).isoformat()
    output = {key:empty(key) for key in LABELS}
    calendars = {}
    for source,table in [('mlb','juegos'),('nfl_totales','nfl_juegos')]:
        item = output[source]
        try:
            if conn is None: raise ConnectionError('offline')
            frame = bank.rows(conn,f'''SELECT id_juego AS game_id,fecha,equipo_local AS local,
                equipo_visitante AS visitante,estado,marcador_local,marcador_visitante FROM {table}
                WHERE DATE(fecha)<=%s AND (DATE(fecha)>=%s OR marcador_local IS NULL OR marcador_visitante IS NULL)''',
                (horizon,today.isoformat()))
            frame=frame.drop_duplicates('game_id') if not frame.empty else frame
            if frame.empty: counts=(0,0,[])
            else: counts=game_summary(frame,now)
            item['games_today'],item['pending'],item['games']=counts
            if source=='mlb' and not frame.empty:
                for row in frame.to_dict('records'):
                    day=mx_date(row['fecha'])
                    if day is not None and (day<today or str(row['estado']).lower().strip()=='finalizado') and (pd.isna(row['marcador_local']) or pd.isna(row['marcador_visitante'])):
                        item['pending_items'].append({'Fecha':day.isoformat(),'Partido':f"{row['visitante']} @ {row['local']}",'Selección':'Marcador pendiente'})
            calendars[source]=frame
        except Exception as exc: item['errors'].append('Calendario: '+type(exc).__name__)
    output['nfl_props'].update({k:output['nfl_totales'][k] for k in ('games_today','games')})
    output['nfl_props']['errors']=list(output['nfl_totales']['errors'])

    queries = {
      'mlb': '''SELECT p.fecha,p.equipo_local AS local,p.equipo_visitante AS visitante,p.pick_ia AS seleccion,
        p.confianza,p.cuota,j.id_juego AS game_id,j.estado AS estado_juego
        FROM registro_picks_ia p JOIN juegos j ON DATE(j.fecha)=p.fecha
        AND j.equipo_local=p.equipo_local AND j.equipo_visitante=p.equipo_visitante
        WHERE p.fecha>=%s AND p.fecha<=%s''',
      'mlb_total': '''SELECT p.game_pk AS game_id,p.start_utc AS fecha,p.candidato,p.seleccion,p.linea,p.recorded_utc AS actualizado,
        p.equipo_local AS local,p.equipo_visitante AS visitante,r.home_runs,r.away_runs,r.updated_utc,
        r.revision_reglas FROM mlb_totales_predicciones p LEFT JOIN mlb_totales_resultados r ON r.game_pk=p.game_pk
        WHERE LOWER(TRIM(p.casa_apuestas))='draftkings' AND p.fecha_oficial<=%s
        AND (p.fecha_oficial>=%s OR r.game_pk IS NULL OR r.revision_reglas=1) ORDER BY p.recorded_utc ASC,p.id ASC''',
      'nfl_totales': '''SELECT p.id_juego AS game_id,j.fecha,j.equipo_local AS local,j.equipo_visitante AS visitante,
        j.estado AS estado_juego,p.estado_pick,p.seleccion,p.linea_total AS linea,p.resultado_pick AS resultado,p.actualizado_en AS actualizado
        FROM nfl_predicciones_totales p JOIN nfl_juegos j ON j.id_juego=p.id_juego
        WHERE DATE(j.fecha)<=%s AND (DATE(j.fecha)>=%s OR p.resultado_pick IS NULL OR p.resultado_pick NOT IN ('GANADA','PERDIDA','PUSH','ANULADA','VOID'))
        ORDER BY p.actualizado_en DESC,p.id_prediccion DESC''',
      'nfl_props': '''SELECT p.id_juego AS game_id,p.id_jugador,p.tipo_prop,j.fecha,j.estado AS estado_juego,
        j.equipo_local AS local,j.equipo_visitante AS visitante,u.nombre AS jugador,p.seleccion,p.linea,
        p.estado_pick,p.resultado_pick AS resultado,p.actualizado_en AS actualizado,p.evaluado_en
        FROM nfl_proyecciones_props p JOIN nfl_juegos j ON j.id_juego=p.id_juego
        JOIN nfl_lineas_props l ON l.id_linea=p.id_linea LEFT JOIN nfl_jugadores u ON u.id_jugador=p.id_jugador
        WHERE LOWER(TRIM(l.casa_apuestas))='draftkings'
        AND DATE(j.fecha)<=%s AND (DATE(j.fecha)>=%s OR p.resultado_pick IS NULL OR p.resultado_pick NOT IN ('GANADA','PERDIDA','PUSH','ANULADA','VOID'))
        ORDER BY p.actualizado_en DESC,p.id_proyeccion DESC'''}
    for source,sql in queries.items():
        item=output[source]
        try:
            if conn is None: raise ConnectionError('offline')
            params = (today.isoformat(),horizon) if source=='mlb' else (horizon,(today-timedelta(days=1)).isoformat())
            frame=bank.rows(conn,sql,params)
            if source=='mlb':
                # Un registro por pareja no identifica el juego de una doble cartelera.
                if not frame.empty: frame=frame[~frame.duplicated(['fecha','local','visitante'],keep=False)]
                item['picks_today']=prediction_summary(frame,now,keys=['game_id'],candidate=lambda r:float(r['confianza'])>=74 and float(r['cuota'])>1)[0] if not frame.empty else 0
                item['last_data']=maximum(frame,'fecha')
                item['detail']='Picks de hoy con confianza ≥74%. Fecha de picks; hora de inicio no verificada.'
            else:
                if source=='mlb_total':
                    if not frame.empty:
                        frame['resuelto']=frame.home_runs.notna() & frame.away_runs.notna() & ~frame.revision_reglas.fillna(0).astype(bool)
                        frame['estado_juego']=frame[['home_runs','away_runs']].notna().all(axis=1).map({True:'finalizado',False:''})
                        calendar=frame.rename(columns={'home_runs':'marcador_local','away_runs':'marcador_visitante'})
                        item['games_today'],_,item['games']=game_summary(calendar.drop_duplicates('game_id'),now,utc=True)
                    else: item['games_today'],item['games']=0,[]
                    item['last_result']=maximum(frame,'updated_utc')
                    candidate=lambda r:bool(r['candidato'])
                else: candidate=lambda r:r['estado_pick']==('PICK' if source=='nfl_totales' else 'CANDIDATO')
                keys=['game_id','id_jugador','tipo_prop'] if source=='nfl_props' else ['game_id']
                item['picks_today'],item['pending'],item['pending_items']=prediction_summary(frame,now,keys=keys,candidate=candidate,utc=source=='mlb_total') if not frame.empty else (0,0,[])
                item['last_data']=maximum(frame,'actualizado')
                if source=='nfl_props': item['last_result']=maximum(frame,'evaluado_en')
                item['detail']='Candidatos de hoy guardados; resultados pendientes de días anteriores o de partidos finalizados.'
                if source.startswith('nfl'): item['detail']+=' NFL no proporciona hora de inicio verificada.'
        except Exception as exc:
            item['picks_today']=None
            if source!='mlb': item['pending']=None
            item['errors'].append('Predicciones: '+type(exc).__name__)
    try:
        if conn is None: raise ConnectionError('offline')
        for source,sql in [('mlb','SELECT MAX(fecha) AS fecha FROM registro_picks_ia'),
          ('mlb_total','SELECT MAX(recorded_utc) AS fecha FROM mlb_totales_predicciones'),
          ('nfl_totales','SELECT MAX(actualizado_en) AS fecha FROM nfl_predicciones_totales'),
          ('nfl_props','SELECT MAX(actualizado_en) AS fecha FROM nfl_proyecciones_props')]:
            try: output[source]['last_data']=maximum(bank.rows(conn,sql),'fecha')
            except Exception as exc: output[source]['errors'].append('Último dato: '+type(exc).__name__)
    except ConnectionError: pass

    item=output['liga_mx']
    try:
        folder=Path(root)/'futbol_liga_mx'
        history=pd.read_csv(folder/'data/partidos.csv')
        fixtures=pd.read_csv(folder/'data/proximos.csv')
        report=json.loads((folder/'data/cobertura_actual.json').read_text())
        item['last_data']=report.get('verified_utc')
        item['last_result']=maximum(history,'fecha')
        item['pending']=int(fixtures['fecha'].map(mx_date).map(lambda d:d is not None and d<today).sum())
        for row in fixtures.to_dict('records'):
            day=mx_date(row['fecha'])
            if day is not None and day<today:
                item['pending_items'].append({'Fecha':day.isoformat(),'Partido':f"{row['visitante']} @ {row['local']}",'Selección':'Calendario pendiente de revisión'})
        from futbol_liga_mx.continuidad import frozen_model,upcoming_ready
        _,metrics=frozen_model(folder/'modelos')
        ready=upcoming_ready(history,fixtures,metrics,now)
        calendar=ready.rename(columns={'inicio_utc':'fecha_utc'}).copy()
        calendar['fecha']=calendar['fecha_utc']
        item['games_today'],_,item['games']=game_summary(calendar,now,utc=True)
        item['picks_today']=item['games_today']*2
        item['detail']='Dos selecciones O/U 2.5 por partido habilitado; cuotas por confirmar. Último dato: verificación de cobertura.'
        if report.get('partial_day'): item['detail']+=' La cobertura del día en curso es parcial.'
    except Exception as exc:
        item['errors'].append('Cobertura o calendario: '+type(exc).__name__)
        item['detail']='Revisa o actualiza el calendario y su cobertura; las predicciones se mantienen suspendidas.'

    item=output['bankroll']
    try:
        if conn is None: raise ConnectionError('offline')
        ledger=bank.load_ledger(conn)
        capital=bank.rows(conn,'SELECT capital_inicial FROM bankroll_config WHERE id=1')
        if capital.empty: raise ValueError('Sin capital configurado')
        item['finance']=bank.metrics(ledger,float(capital.iloc[0,0]))
        item['pending']=int(ledger.estado.eq('Pendiente').sum())
        item['pending_items']=ledger.loc[ledger.estado.eq('Pendiente'),['fecha','partido','seleccion']].rename(columns={'fecha':'Fecha','partido':'Partido','seleccion':'Selección'}).to_dict('records')
        item['last_data']=maximum(bank.rows(conn,'SELECT MAX(actualizado_en) AS fecha FROM bankroll_apuestas'),'fecha')
        item['detail']='Apuestas pendientes de cualquier fecha; saldo y disponible de toda la banca. No se liquida al abrir el resumen.'
    except Exception as exc: item['errors'].append('Banca: '+type(exc).__name__)
    return dict(at=now.isoformat(),today=today.isoformat(),services=output)
