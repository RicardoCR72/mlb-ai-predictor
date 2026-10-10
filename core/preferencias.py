"""Favoritos compartidos de la aplicación; MySQL conserva las preferencias entre sesiones."""
import json
from core.db import get_db_connection

DDL='''CREATE TABLE IF NOT EXISTS oracle_filtros_favoritos (
 ambito VARCHAR(80) NOT NULL,nombre VARCHAR(80) NOT NULL,ajustes TEXT NOT NULL,
 actualizado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 PRIMARY KEY (ambito,nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''


def load(scope):
    conn=get_db_connection();cursor=conn.cursor()
    try:
        cursor.execute('SELECT nombre,ajustes FROM oracle_filtros_favoritos WHERE ambito=%s ORDER BY nombre',(scope,))
        result={}
        for name,payload in cursor.fetchall():
            try:
                values=json.loads(payload)
                if isinstance(values,dict):result[name]=values
            except (ValueError,TypeError):continue
        return result
    except Exception as exc:
        if getattr(exc,'errno',None)==1146:return {}
        raise
    finally:cursor.close();conn.close()


def save(scope,name,settings):
    name=str(name).strip()
    if not name or len(name)>80 or len(scope)>80:raise ValueError('Usa un nombre de 1 a 80 caracteres.')
    payload=json.dumps(settings,ensure_ascii=False,default=str)
    if len(payload)>16000:raise ValueError('La configuración es demasiado grande.')
    conn=get_db_connection();cursor=conn.cursor()
    try:
        cursor.execute(DDL)
        cursor.execute('INSERT INTO oracle_filtros_favoritos (ambito,nombre,ajustes) VALUES (%s,%s,%s) '
                       'ON DUPLICATE KEY UPDATE ajustes=VALUES(ajustes)',(scope,name,payload))
        conn.commit()
    except Exception:conn.rollback();raise
    finally:cursor.close();conn.close()


def delete(scope,name):
    conn=get_db_connection();cursor=conn.cursor()
    try:
        cursor.execute('DELETE FROM oracle_filtros_favoritos WHERE ambito=%s AND nombre=%s',(scope,name))
        conn.commit()
    except Exception:conn.rollback();raise
    finally:cursor.close();conn.close()
