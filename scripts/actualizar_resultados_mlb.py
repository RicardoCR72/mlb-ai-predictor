"""Recupera resultados oficiales de moneyline y totales sin consultar cuotas."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db import get_db_connection
from core.actualizacion_manual import refresh_mlb_games, mlb_totals


def main():
    conn = get_db_connection()
    failures = []
    try:
        # Los dos historiales son independientes: intentar ambos aunque falle uno.
        for label, refresh in (('Moneyline', refresh_mlb_games), ('Totales', mlb_totals)):
            try:
                print(f'{label}: {refresh(conn)}')
            except Exception as exc:
                conn.rollback()
                failures.append(label)
                print(f'::error::{label}: no se completó la actualización ({type(exc).__name__}).')
        if failures:
            raise RuntimeError('Resultados MLB pendientes: ' + ', '.join(failures))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
