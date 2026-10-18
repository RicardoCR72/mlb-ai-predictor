"""Generación explícita usando cuotas guardadas, sin consumir The Odds API."""
from pathlib import Path
import sys
import json
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from mlb.moneyline_service import generate
from mlb_totales.automatizar import predict_today
from mlb_totales import registro
from core.db import get_db_connection


def main():
    conn=get_db_connection();cur=conn.cursor();steps=[]
    try:
        cur.execute("SELECT GET_LOCK('oracle-mlb-publish',0)")
        if cur.fetchone()[0]!=1:
            print('MLB_REPORT='+json.dumps(dict(steps=[],detalle='Ya hay una generación MLB en curso.')))
            return 1
        for label,fn in [('Moneyline',generate),('Totales',lambda:predict_today(conn))]:
            try:
                if label=='Totales':registro.prepare(conn)
                n=fn()
                steps.append(dict(paso=label,ok=True,detalle=f'{n} pronósticos procesados.'))
            except Exception:
                conn.rollback()
                steps.append(dict(paso=label,ok=False,detalle='No se pudo completar; revisa datos y modelos.'))
        report=dict(steps=steps,detalle='Predicciones MLB procesadas.' if all(s['ok'] for s in steps) else 'Generación MLB parcial; revisa el historial antes de reintentar.')
        print('MLB_REPORT='+json.dumps(report,ensure_ascii=False))
        return 0 if all(s['ok'] for s in steps) else 1
    finally:
        try:cur.execute("SELECT RELEASE_LOCK('oracle-mlb-publish')");cur.fetchone()
        finally:cur.close();conn.close()


if __name__=='__main__':sys.exit(main())
