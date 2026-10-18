"""Primera publicación de totales por juego/modelo; nunca certificar históricos."""
from pathlib import Path
import math
import pandas as pd
from core.combinadas_datos import nfl_starts

DDL='''CREATE TABLE IF NOT EXISTS nfl_publicaciones_totales (
 id_juego VARCHAR(128) NOT NULL, modelo VARCHAR(128) NOT NULL,
 seleccion VARCHAR(5) NOT NULL,linea DOUBLE NOT NULL,probabilidad DOUBLE NOT NULL,
 cuota DOUBLE NOT NULL,start_utc DATETIME(6) NOT NULL,publicada_utc DATETIME(6) NOT NULL,
 PRIMARY KEY(id_juego,modelo)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''


def save(conn,frame,model,root):
    starts=nfl_starts(root)
    cursor=conn.cursor()
    try:
        cursor.execute(DDL)
        for r in frame.to_dict('records'):
            start=starts.get(str(r['game_id']))
            p=float(r.get('prob_pick',float('nan')));line=float(r.get('total_line',float('nan')))
            odds=float(r.get('odds_pick',float('nan')))
            if start is None or r.get('estado')!='PICK' or r.get('pick') not in ('OVER','UNDER'):continue
            if not all(math.isfinite(v) for v in (p,line,odds)) or not 0<=p<=1 or abs(odds)<100:continue
            cursor.execute('''INSERT INTO nfl_publicaciones_totales
                (id_juego,modelo,seleccion,linea,probabilidad,cuota,start_utc,publicada_utc)
                SELECT %s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6)
                WHERE %s>UTC_TIMESTAMP(6)
                ON DUPLICATE KEY UPDATE id_juego=nfl_publicaciones_totales.id_juego''',
                (str(r['game_id']),model,r['pick'],line,p,odds,
                 pd.Timestamp(start).tz_convert('UTC').tz_localize(None).to_pydatetime(),
                 pd.Timestamp(start).tz_convert('UTC').tz_localize(None).to_pydatetime()))
        conn.commit()
    finally:cursor.close()
