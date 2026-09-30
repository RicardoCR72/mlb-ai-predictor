"""Registro inmutable de la primera predicción por juego/casa/modelo y liquidación 1u."""
from datetime import datetime,timezone
import math
import numpy as np
import pandas as pd
from mlb_totales.mercado import utc
from mlb_totales.descargar_pitcheo import fetch_json,TYPES

DDL=["""
CREATE TABLE IF NOT EXISTS mlb_totales_predicciones (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 game_pk BIGINT NOT NULL, odds_game_id VARCHAR(128) NOT NULL,
 model_id CHAR(64) NOT NULL, model_name VARCHAR(64) NOT NULL,
 fecha_oficial DATE NOT NULL, start_utc DATETIME NOT NULL,
 equipo_local VARCHAR(128) NOT NULL,equipo_visitante VARCHAR(128) NOT NULL,
 game_type CHAR(1) NOT NULL,casa_apuestas VARCHAR(128) NOT NULL,
 linea DOUBLE NOT NULL,cuota_over DOUBLE NOT NULL,cuota_under DOUBLE NOT NULL,
 seleccion VARCHAR(5) NOT NULL,total_pred DOUBLE NOT NULL,
 p_over DOUBLE NOT NULL,p_under DOUBLE NOT NULL,p_push DOUBLE NOT NULL,
 confianza DOUBLE NOT NULL,cuota_seleccion DOUBLE NOT NULL,ev DOUBLE NOT NULL,
 edge_carreras DOUBLE NOT NULL,home_pitcher_id BIGINT NOT NULL,away_pitcher_id BIGINT NOT NULL,
 quote_captured_utc DATETIME NOT NULL,recorded_utc DATETIME(6) NOT NULL,
 estado_modelo VARCHAR(64) NOT NULL,candidato TINYINT NOT NULL,
 UNIQUE KEY uq_mlb_total_snapshot (game_pk,casa_apuestas,model_id),
 KEY ix_mlb_total_fecha (fecha_oficial)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""","""
CREATE TABLE IF NOT EXISTS mlb_totales_resultados (
 game_pk BIGINT NOT NULL PRIMARY KEY,home_runs INT NOT NULL,away_runs INT NOT NULL,
 innings_final INT NULL,revision_reglas TINYINT NOT NULL DEFAULT 0,
 updated_utc DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""]

LATEST_QUOTES="""
 SELECT j.id_juego,j.fecha,j.equipo_local,j.equipo_visitante,
        p.casa_apuestas,p.linea,p.cuota_over,p.cuota_under,p.timestamp_captura
 FROM juegos j JOIN lineas_props p ON p.id_juego=j.id_juego
 WHERE p.tipo_prop='totales_carreras' AND j.fecha>=%s AND j.fecha<%s
"""


def prepare(connection):
    cursor=connection.cursor()
    try:
        for statement in DDL:cursor.execute(statement)
        connection.commit()
    finally:cursor.close()


def read_rows(connection,query,params=()):
    cursor=connection.cursor(dictionary=True)
    try:
        cursor.execute(query,params)
        return pd.DataFrame(cursor.fetchall())
    finally:cursor.close()


def tables_ready(connection):
    c=connection.cursor()
    try:
        for name in ('mlb_totales_predicciones','mlb_totales_resultados'):
            c.execute('SHOW TABLES LIKE %s',(name,))
            if c.fetchone() is None:return False
        return True
    finally:c.close()


def quote_rows(connection,day):
    date=pd.Timestamp(day).normalize()
    # El matching posterior verifica equipo/hora; jamás une solo por fecha y pareja.
    return read_rows(connection,LATEST_QUOTES,
        ((date-pd.Timedelta(days=1)).to_pydatetime(),(date+pd.Timedelta(days=2)).to_pydatetime()))


def snapshot_values(row,model_id,now=None):
    now=utc(now if now is not None else datetime.now(timezone.utc))
    if (utc(row['start_utc'])<=now or row.get('estado_mercado')!='OK'
        or row.get('estado') in ('ABRIDOR_PENDIENTE','ACTUALIZAR_HISTORIAL')
        or row.get('seleccion') not in ('OVER','UNDER')):
        return None
    p=[float(row.get(k,np.nan)) for k in ('p_over','p_under','p_push')]
    if not all(math.isfinite(x) and 0<=x<=1 for x in p) or abs(sum(p)-1)>1e-8:
        return None
    pick=row['seleccion'];side=pick.lower()
    confidence=float(row['p_'+side]);odds=float(row['cuota_'+side]);ev=float(row['ev_'+side])
    if not math.isfinite(odds) or odds<=1 or not math.isfinite(ev):return None
    return (int(row['game_id']),str(row['odds_game_id']),model_id,str(row['modelo']),
        pd.Timestamp(row['fecha']).date(),utc(row['start_utc']).tz_localize(None).to_pydatetime(),
        str(row['local']),str(row['visitante']),str(row['game_type']),str(row['casa_apuestas']),
        float(row['linea']),float(row['cuota_over']),float(row['cuota_under']),pick,
        float(row['total_proyectado']),*p,confidence,odds,ev,float(row['edge_carreras']),
        int(row['home_pitcher_id']),int(row['away_pitcher_id']),
        utc(row['captured_utc']).tz_localize(None).to_pydatetime(),now.tz_localize(None).to_pydatetime(),
        str(row['estado']),int(ev>0))


SNAPSHOT_SQL="""
 INSERT INTO mlb_totales_predicciones
 (game_pk,odds_game_id,model_id,model_name,fecha_oficial,start_utc,equipo_local,equipo_visitante,
 game_type,casa_apuestas,linea,cuota_over,cuota_under,seleccion,total_pred,p_over,p_under,p_push,
 confianza,cuota_seleccion,ev,edge_carreras,home_pitcher_id,away_pitcher_id,
 quote_captured_utc,recorded_utc,estado_modelo,candidato)
 VALUES ("""+','.join(['%s']*28)+""")
 ON DUPLICATE KEY UPDATE id=mlb_totales_predicciones.id
"""


def save_snapshots(connection,frame,model_id,now=None):
    cursor=connection.cursor();count=0
    try:
        for _,row in frame.iterrows():
            values=snapshot_values(row,model_id,now)
            if values is not None:
                cursor.execute(SNAPSHOT_SQL,values)
                if cursor.rowcount==1:count+=1
        connection.commit()
        return count
    except Exception:
        connection.rollback();raise
    finally:cursor.close()


def parse_results(data):
    rows=[]
    for day in data.get('dates',[]):
        for game in day['games']:
            if game['status'].get('abstractGameState')!='Final':continue
            h,a=game['teams']['home'],game['teams']['away']
            if 'score' not in h or 'score' not in a:continue
            innings=game.get('linescore',{}).get('currentInning')
            # Un final anticipado/reanudado exige revisar las reglas de la casa.
            review=(innings is None or int(innings)<9 or game.get('scheduledInnings',9)!=9
                or any(game.get(k) for k in ('resumeDate','resumedFrom','resumedFromDate'))
                or 'forfeit' in game['status'].get('detailedState','').lower())
            rows.append((int(game['gamePk']),int(h['score']),int(a['score']),
                         None if innings is None else int(innings),int(review)))
    return rows


RESULT_SQL="""
 INSERT INTO mlb_totales_resultados
 (game_pk,home_runs,away_runs,innings_final,revision_reglas,updated_utc)
 VALUES (%s,%s,%s,%s,%s,%s)
 ON DUPLICATE KEY UPDATE home_runs=VALUES(home_runs),away_runs=VALUES(away_runs),
 innings_final=VALUES(innings_final),revision_reglas=VALUES(revision_reglas),updated_utc=VALUES(updated_utc)
"""


def refresh_results(connection,max_days=15):
    pending=read_rows(connection,"""
      SELECT DISTINCT p.fecha_oficial FROM mlb_totales_predicciones p
      LEFT JOIN mlb_totales_resultados r ON r.game_pk=p.game_pk
      WHERE (r.game_pk IS NULL OR p.fecha_oficial>=UTC_DATE()-INTERVAL 2 DAY)
      ORDER BY p.fecha_oficial DESC LIMIT %s
    """,(max_days,))
    if pending.empty:return 0
    cursor=connection.cursor();n=0
    try:
        for day in pending.fecha_oficial:
            data=fetch_json('schedule',{'sportId':1,'date':str(pd.Timestamp(day).date()),
                                       'gameType':TYPES,'hydrate':'linescore'})
            for result in parse_results(data):
                cursor.execute(RESULT_SQL,(*result,datetime.now(timezone.utc).replace(tzinfo=None)))
                n+=1
        connection.commit()
    except Exception:
        connection.rollback();raise
    finally:cursor.close()
    return n


def history(connection):
    return read_rows(connection,"""
      SELECT p.*,r.home_runs,r.away_runs,r.innings_final,r.revision_reglas
      FROM mlb_totales_predicciones p
      LEFT JOIN mlb_totales_resultados r ON r.game_pk=p.game_pk
      ORDER BY p.fecha_oficial DESC,p.id DESC
    """)


def settle(frame):
    result=frame.copy()
    if result.empty:return result
    states=[];profits=[]
    for _,r in result.iterrows():
        if pd.isna(r.home_runs) or pd.isna(r.away_runs):
            states.append('PENDIENTE');profits.append(np.nan);continue
        if pd.notna(r.revision_reglas) and bool(r.revision_reglas):
            states.append('REVISAR_REGLAS');profits.append(np.nan);continue
        total=float(r.home_runs)+float(r.away_runs);line=float(r.linea)
        if total==line:states.append('PUSH');profits.append(0.0);continue
        won=(total>line) if r.seleccion=='OVER' else (total<line)
        states.append('GANADA' if won else 'PERDIDA')
        profits.append(float(r.cuota_seleccion)-1 if won else -1.0)
    result['resultado']=states;result['unidades']=profits
    result['confianza_pct']=pd.to_numeric(result.confianza)*100
    result['total_real']=pd.to_numeric(result.home_runs)+pd.to_numeric(result.away_runs)
    return result


def summary(frame):
    settled=frame[frame.resultado.isin(['GANADA','PERDIDA','PUSH'])] if not frame.empty else frame
    n=len(settled)
    won=int((settled.resultado=='GANADA').sum()) if n else 0
    lost=int((settled.resultado=='PERDIDA').sum()) if n else 0
    push=int((settled.resultado=='PUSH').sum()) if n else 0
    units=float(settled.unidades.sum()) if n else 0
    return dict(apuestas=n,ganadas=won,perdidas=lost,push=push,unidades=units,
                roi=100*units/n if n else 0,acierto=100*won/(won+lost) if won+lost else 0)
