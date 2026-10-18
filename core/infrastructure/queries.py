"""Consultas tabulares independientes de funciones de producto."""
import pandas as pd

def rows(conn, sql, params=()):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return pd.DataFrame(cursor.fetchall())
    finally:
        cursor.close()
