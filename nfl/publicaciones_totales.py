"""Primera publicación de totales por juego/modelo; nunca certificar históricos."""
from pathlib import Path
import math
from datetime import datetime, timezone
from core.domain.contracts import Prediction
from core.domain.odds import decimal_odds
import pandas as pd
from nfl.persistence.calendar import nfl_starts

from core.infrastructure.migrations import SCHEMAS, ensure_schema
DDL = SCHEMAS['total_publications']


def save(conn,frame,model,root):
    starts=nfl_starts(root)
    cursor=conn.cursor()
    try:
        ensure_schema(conn, 'total_publications')
        for r in frame.to_dict('records'):
            start=starts.get(str(r['game_id']))
            p=float(r.get('prob_pick',float('nan')));line=float(r.get('total_line',float('nan')))
            odds=float(r.get('odds_pick',float('nan')))
            if start is None or r.get('estado')!='PICK' or r.get('pick') not in ('OVER','UNDER'):continue
            if not all(math.isfinite(v) for v in (p,line,odds)) or not 0<=p<=1 or abs(odds)<100:continue
            try:
                Prediction(game_id=str(r['game_id']), market='Totales', selection=r['pick'],
                           probability=p, model=model, start_utc=pd.Timestamp(start).to_pydatetime(),
                           generated_utc=datetime.now(timezone.utc), provider='nflverse',
                           line=line, decimal_odds=decimal_odds(odds))
            except (ValueError, TypeError):
                continue
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
