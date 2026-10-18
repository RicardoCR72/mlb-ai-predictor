"""Manejador unificado de conexión y consultas para base de datos MySQL (Aiven / XAMPP)."""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from typing import Any, Generator, Optional
import mysql.connector
import pandas as pd


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


def get_db_connection(dictionary: bool = False) -> mysql.connector.MySQLConnection:
    """Crea y retorna una nueva conexión abierta a la base de datos."""
    creds = get_db_credentials()
    conn = mysql.connector.connect(**creds)
    return conn


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
