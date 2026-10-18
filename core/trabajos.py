"""Ejecuciones manuales persistentes con exclusión MySQL entre procesos.

Los workers viven en la app; si el proceso termina, no se reintenta una captura
pagada automáticamente. El estado interrumpido requiere revisión explícita.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import uuid
import mysql.connector
from core.db import get_db_connection,get_db_credentials
from core import permisos

ROOT=Path(__file__).resolve().parents[1]
SERVICES={'mlb','nfl_props','nfl_totales','liga_mx','nfl_predictions','mlb_predictions'}
EXECUTOR=ThreadPoolExecutor(max_workers=3,thread_name_prefix='oracle-job')
DDL='''CREATE TABLE IF NOT EXISTS oracle_trabajos (
 id CHAR(36) PRIMARY KEY,servicio VARCHAR(40) NOT NULL,
 activo VARCHAR(40) NULL UNIQUE,estado VARCHAR(24) NOT NULL,
 creado_utc DATETIME(6) NOT NULL,iniciado_utc DATETIME(6) NULL,
 terminado_utc DATETIME(6) NULL,paso VARCHAR(180) NULL,resultado JSON NULL,
 KEY ix_oracle_jobs_service(servicio,creado_utc)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''


def update(conn,id,state,step=None,result=None):
    cur=conn.cursor()
    try:
        terminal=state in ('completada','parcial','fallida','interrumpida')
        cur.execute('''UPDATE oracle_trabajos SET estado=%s,paso=%s,resultado=%s,
            iniciado_utc=IF(%s='ejecutando' AND iniciado_utc IS NULL,UTC_TIMESTAMP(6),iniciado_utc),
            terminado_utc=IF(%s,UTC_TIMESTAMP(6),terminado_utc),activo=IF(%s,NULL,activo)
            WHERE id=%s AND estado IN ('en_cola','ejecutando')''',
            (state,step,json.dumps(result,ensure_ascii=False) if result is not None else None,state,terminal,terminal,id))
        changed=cur.rowcount
        conn.commit()
        return changed
    finally:cur.close()


def worker(id,service,payload,token,config):
    conn=None;cur=None
    try:
        conn=mysql.connector.connect(**config);cur=conn.cursor()
        cur.execute('SELECT GET_LOCK(%s,0)',('oracle-job-'+service,))
        if cur.fetchone()[0]!=1:
            update(conn,id,'fallida',result={'detalle':'Servicio ocupado. No se inició otra ejecución.'});return
        if not update(conn,id,'ejecutando',step='Preparando actualización'):return
        def progress(label):update(conn,id,'ejecutando',step=label)
        permisos.require_admin(token)
        if service=='nfl_predictions':
            from core.nfl_creditos import run_predictions
            result=run_predictions(ROOT,payload,on_step=progress,admin_token=token)
            state='completada' if result['ok'] else 'parcial' if result.get('reporte') else 'fallida'
        elif service=='mlb_predictions':
            from core.actualizacion_manual import child_environment
            import subprocess,sys
            progress('Generando MLB con cuotas guardadas')
            process=subprocess.run([sys.executable,str(ROOT/'scripts/generar_mlb.py')],cwd=ROOT,
                env=child_environment(),capture_output=True,text=True,timeout=900)
            reports=[json.loads(line.split('=',1)[1]) for line in process.stdout.splitlines() if line.startswith('MLB_REPORT=')]
            result=reports[-1] if reports else {'detalle':'No se pudo confirmar la generación. Revisa los datos guardados.'}
            state='completada' if process.returncode==0 else 'parcial' if any(s['ok'] for s in result.get('steps',[])) else 'fallida'

        else:
            from core.actualizacion_manual import run_update
            result=run_update(service,ROOT,on_step=progress,admin_token=token)
            flags=[s['ok'] for s in result['steps']]
            state='fallida' if result.get('busy') or not any(flags) else 'completada' if all(flags) else 'parcial'
        update(conn,id,state,result=result)
    except Exception:
        if conn is not None:
            try:update(conn,id,'fallida',result={'detalle':'La ejecución no pudo completarse. Revisa resultados antes de reintentar; pudo haber consumo si solicitaste cuotas.'})
            except Exception:pass
    finally:
        if cur is not None:
            try:cur.execute('SELECT RELEASE_LOCK(%s)',('oracle-job-'+service,));cur.fetchone();cur.close()
            except Exception:pass
        if conn is not None:conn.close()


def submit(service,*,token,payload=None):
    permisos.require_admin(token)
    if service not in SERVICES:raise ValueError('Servicio no permitido.')
    config=get_db_credentials();conn=get_db_connection();cur=conn.cursor()
    try:
        cur.execute(DDL)
        # Recuperar solo jobs huérfanos, sin volver a ejecutar cuotas automáticamente.
        cur.execute('''UPDATE oracle_trabajos SET estado='interrumpida',activo=NULL,terminado_utc=UTC_TIMESTAMP(6)
            WHERE activo=%s AND creado_utc<UTC_TIMESTAMP(6)-INTERVAL 5 MINUTE
            AND IS_USED_LOCK(%s) IS NULL''',(service,'oracle-job-'+service))
        id=str(uuid.uuid4())
        try:
            cur.execute("INSERT INTO oracle_trabajos(id,servicio,activo,estado,creado_utc) VALUES (%s,%s,%s,'en_cola',UTC_TIMESTAMP(6))",(id,service,service))
            conn.commit()
        except mysql.connector.IntegrityError:
            conn.rollback()
            cur.execute('SELECT id FROM oracle_trabajos WHERE activo=%s',(service,))
            row=cur.fetchone()
            if row:return row[0]
            raise
        try:EXECUTOR.submit(worker,id,service,payload,token,config)
        except Exception:
            update(conn,id,'fallida',result={'detalle':'No se pudo iniciar el worker.'});raise
        return id
    finally:cur.close();conn.close()


def latest(service):
    conn=None;cur=None
    try:
        conn=get_db_connection();cur=conn.cursor(dictionary=True)
        cur.execute('''SELECT *,IS_USED_LOCK(CONCAT('oracle-job-',servicio)) AS lock_owner,
            creado_utc<UTC_TIMESTAMP(6)-INTERVAL 5 MINUTE AS viejo
            FROM oracle_trabajos WHERE servicio=%s ORDER BY creado_utc DESC LIMIT 1''',(service,))
        row=cur.fetchone()
        if row and row['estado'] in ('en_cola','ejecutando') and row['viejo'] and row['lock_owner'] is None:row['estado']='interrumpida'
        if row and isinstance(row.get('resultado'),str):row['resultado']=json.loads(row['resultado'])
        return row
    except mysql.connector.Error as exc:
        if exc.errno==1146:return None
        raise
    finally:
        if cur is not None:cur.close()
        if conn is not None:conn.close()
