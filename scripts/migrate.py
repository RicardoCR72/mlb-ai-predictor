"""Aplicar migraciones aditivas: python -m scripts.migrate."""
from core.db import get_db_connection
from core.infrastructure.migrations import SCHEMAS, ensure_schema


def main():
    conn=get_db_connection()
    try:
        for name in SCHEMAS:
            ensure_schema(conn,name)
            print('Esquema verificado:',name)
    finally:conn.close()


if __name__=='__main__':main()
