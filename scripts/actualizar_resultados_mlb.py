"""Recupera resultados oficiales de moneyline y totales sin consultar cuotas."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db import get_db_connection
from core.actualizacion_manual import refresh_mlb_games, mlb_totals
from core.auditoria_mlb import capture, compare
import json


def main():
    conn = get_db_connection()
    failures = []
    try:
        before = capture(conn)
        def moneyline(connection):
            return refresh_mlb_games(connection,on_ambiguity=lambda item:
                print('Ambigüedad MLB: '+json.dumps(item,ensure_ascii=False)))
        # Los dos historiales son independientes: intentar ambos aunque falle uno.
        for label, refresh in (('Moneyline', moneyline), ('Totales', mlb_totals)):
            try:
                print(f'{label}: {refresh(conn)}')
            except Exception as exc:
                conn.rollback()
                failures.append(label)
                print(f'::error::{label}: no se completó la actualización ({type(exc).__name__}).')
        audit=compare(before,capture(conn))
        for source,result in audit.items():
            print('Auditoría MLB '+source+': '+json.dumps(result,ensure_ascii=False))
            if result['estado']!='OK':
                print('::warning::Auditoría MLB '+source+': '+result['estado'])
        if failures:
            raise RuntimeError('Resultados MLB pendientes: ' + ', '.join(failures))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
