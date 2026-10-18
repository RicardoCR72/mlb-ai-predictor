from core.infrastructure.migrations import ensure_schema
"""Auditoría de consultas pagadas y candado compartido entre web y Actions."""
from datetime import datetime, timezone

LOCK_NAME = 'nfl-props-cuota'


def preparar(conn):
    cursor = conn.cursor()
    try:
        ensure_schema(conn, 'captures')
        conn.commit()
    finally:
        cursor.close()


def adquirir(conn):
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT GET_LOCK(%s,0)', (LOCK_NAME,))
        row = cursor.fetchone()
        return bool(row and row[0] == 1)
    finally:
        cursor.close()


def liberar(conn):
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT RELEASE_LOCK(%s)', (LOCK_NAME,))
        cursor.fetchone()
    finally:
        cursor.close()


def iniciar(conn, game_id, event_id, day):
    cursor = conn.cursor()
    try:
        # Confirmar antes de HTTP: si la conexión se corta tras cobrar, el automático
        # no repite a ciegas una consulta cuyo cobro no pudimos verificar.
        cursor.execute('''INSERT INTO nfl_capturas_odds
            (id_juego,evento_id,fecha_mexico,solicitada_en,estado)
            VALUES (%s,%s,%s,%s,'solicitada')''',
            (game_id, event_id, day, datetime.now(timezone.utc).replace(tzinfo=None)))
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()


def terminar(conn, capture_id, cost, state='recibida'):
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE nfl_capturas_odds SET estado=%s,creditos=%s WHERE id=%s",
                       (state, cost, capture_id))
        conn.commit()
    finally:
        cursor.close()
