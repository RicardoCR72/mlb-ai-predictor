"""Liquidación sin consultar cuotas ni crear apuestas a partir de predicciones."""
from pathlib import Path
import sys
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path: sys.path.insert(0, str(RAIZ))
from core.db import get_db_connection
from core.bankroll import prepare, settle_pending


def main():
    conn = get_db_connection()
    try:
        prepare(conn)
        changed, errors = settle_pending(conn, RAIZ)
        print(f'Bankroll: {changed} apuestas realizadas liquidadas.')
        for error in errors: print('::warning::Liquidación pendiente de revisión: ' + error)
    finally:
        conn.close()


if __name__ == '__main__': main()
