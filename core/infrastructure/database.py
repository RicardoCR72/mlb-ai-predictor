"""Manejador unificado de conexión y consultas para base de datos MySQL (Aiven / XAMPP)."""
from __future__ import annotations

import os
import tempfile
import threading
from contextlib import contextmanager
from typing import Any, Generator, Optional
import mysql.connector
import mysql.connector.pooling
import pandas as pd

# Pool de conexiones reutilizable (lazy, thread-safe)
_pool: Optional[mysql.connector.pooling.MySQLConnectionPool] = None
_pool_lock = threading.Lock()


def get_db_credentials() -> dict[str, Any]:
    """Obtiene las credenciales de conexión resolviendo Streamlit secrets o variables de entorno."""
    creds: dict[str, Any] = {}
    aliases = {'DB_HOST': ('MYSQL_HOST', 'host'), 'DB_USER': ('MYSQL_USER', 'user'),
               'DB_PASSWORD': ('MYSQL_PASSWORD', 'password'), 'DB_NAME': ('MYSQL_DATABASE', 'database'),
               'DB_PORT': ('MYSQL_PORT', 'port'), 'DB_SSL_CA': ('MYSQL_SSL_CA', 'ssl_ca')}
    # No modificar os.environ: resolver aliases sin efectos globales.
    env = dict(os.environ)
    for target, names in aliases.items():
        if not env.get(target):
            for name in names:
                if env.get(name):
                    env[target] = env[name]
                    break

    # 1. Intentar leer desde Streamlit secrets si está disponible
    try:
        import streamlit as st
        section = st.secrets.get("mysql", st.secrets)
        if "host" in section:
            creds["host"] = section["host"]
            creds["port"] = int(section.get("port", 3306))
            creds["user"] = section["user"]
            creds["password"] = section["password"]
            creds["database"] = section["database"]
            for key in ("ssl_ca", "ssl_verify_cert", "ssl_verify_identity"):
                if key in section: creds[key] = section[key]
    except Exception:
        pass

    # 2. Si falta algún valor, complementar desde os.environ (GitHub Actions o local)
    if "host" not in creds:
        creds["host"] = env.get("NFL_DB_HOST") or env.get("DB_HOST", "localhost")
        creds["port"] = int(env.get("NFL_DB_PORT") or env.get("DB_PORT", 3306))
        creds["user"] = env.get("NFL_DB_USER") or env.get("DB_USER", "root")
        creds["password"] = (
            env.get("NFL_DB_PASSWORD")
            or env.get("DB_PASSWORD")
            or env.get("DB_PASS", "")
        )
        creds["database"] = env.get("NFL_DB_NAME") or env.get("DB_NAME", "deportes")

    # 3. Soporte para certificados SSL de Aiven
    ca_content = env.get("NFL_DB_SSL_CA_CERT") or env.get("DB_SSL_CA_CERT")
    if ca_content:
        # Guardar en archivo temporal si viene como string en variables de entorno
        temp_cert = os.path.join(tempfile.gettempdir(), "aiven_ca.pem")
        with open(temp_cert, "w", encoding="utf-8") as f:
            f.write(ca_content)
        creds["ssl_ca"] = temp_cert
    elif env.get("DB_SSL_CA"):
        creds["ssl_ca"] = env["DB_SSL_CA"]
    elif os.path.exists("aiven_ca.pem"):
        creds["ssl_ca"] = "aiven_ca.pem"

    if creds.get("ssl_ca"):
        creds["ssl_verify_cert"] = True
    creds["connection_timeout"] = 25
    return creds


def get_pool(pool_size: int = 5) -> mysql.connector.pooling.MySQLConnectionPool:
    """Retorna el pool de conexiones compartido, creándolo de forma lazy y thread-safe.

    El pool elimina el overhead de handshake TLS por conexión (~150ms en Aiven).
    Se comparte entre todos los módulos del proceso via este módulo.
    """
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:  # double-checked locking
            creds = get_db_credentials()
            # MySQLConnectionPool no acepta 'connection_timeout' directamente
            pool_creds = {k: v for k, v in creds.items() if k != 'connection_timeout'}
            _pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="oraculo_pool",
                pool_size=pool_size,
                pool_reset_session=True,
                **pool_creds,
            )
    return _pool


def get_db_connection(dictionary: bool = False) -> mysql.connector.MySQLConnection:
    """Retorna una conexión del pool compartido (o una nueva conexión directa como fallback).

    Compatible con el uso anterior: el llamador sigue siendo responsable de cerrarla
    con conn.close() — devuelve la conexión al pool en lugar de destruirla.
    """
    try:
        conn = get_pool().get_connection()
        return conn
    except Exception:
        # Fallback: conexión directa si el pool no está disponible (tests, CI, etc.)
        creds = get_db_credentials()
        return mysql.connector.connect(**creds)


@contextmanager
def db_session(dictionary: bool = False) -> Generator[tuple[Any, Any], None, None]:
    """Context manager que maneja apertura, commit/rollback y cierre automático de conexión y cursor."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def query_df(sql: str, params: Optional[dict[str, Any] | tuple[Any, ...]] = None) -> pd.DataFrame:
    """Ejecuta una consulta SELECT y retorna un DataFrame de Pandas directamente."""
    conn = get_db_connection()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def execute_statement(sql: str, params: Optional[dict[str, Any] | tuple[Any, ...]] = None) -> int:
    """Ejecuta una instrucción INSERT, UPDATE o DELETE y retorna el número de filas afectadas."""
    with db_session() as (conn, cursor):
        cursor.execute(sql, params or ())
        return cursor.rowcount

