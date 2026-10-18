"""Ejecuciones manuales persistentes con exclusión MySQL entre procesos.

Los workers son procesos independientes con cola persistida. Una captura
pagada interrumpida nunca se reintenta automáticamente. El estado interrumpido requiere revisión explícita.
"""
import os
import subprocess
import sys
from pathlib import Path
import json
import uuid
import time
import mysql.connector
from core.db import get_db_connection,get_db_credentials

ROOT=Path(__file__).resolve().parents[2]
SERVICES={'mlb','nfl_props','nfl_totales','liga_mx','nfl_predictions','mlb_predictions'}
# Cada servicio obtiene su candado aun cuando espera capacidad de cómputo.
class ProcessExecutor:
    def submit(self, fn, id, service, payload, config):
        if os.environ.get('ORACLE_WORKER_MODE') == 'external':
            return None  # A separately supervised worker drains the durable queue.
        from core.actualizacion_manual import child_environment
        env = child_environment()
        if service == 'nfl_predictions':
            from core.nfl_creditos import api_key
            env['ODDS_API_KEY'] = api_key()
        env['ORACLE_WORKER_DB'] = json.dumps(config)
        subprocess.Popen([sys.executable, '-m', 'core.application.job_worker', '--job', id],
                         cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

EXECUTOR=ProcessExecutor()
from core.infrastructure.migrations import SCHEMAS, ensure_schema
DDL = SCHEMAS['jobs']


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


def worker(id,service,payload,config):
    conn=None;cur=None;slot=None;owns_service=False
    try:
        conn=mysql.connector.connect(**config);cur=conn.cursor()
        cur.execute('SELECT GET_LOCK(%s,0)',('oracle-job-'+service,))
        if cur.fetchone()[0]!=1:
            return
        owns_service=True
        cur.execute('SELECT estado FROM oracle_trabajos WHERE id=%s',(id,))
        record=cur.fetchone()
        if not record or record[0]!='en_cola':return
        for attempt in range(150):
            for number in range(3):
                name='oracle-worker-slot-'+str(number)
                cur.execute('SELECT GET_LOCK(%s,0)',(name,))
                if cur.fetchone()[0]==1:
                    slot=name
                    break
            if slot:break
            time.sleep(2)
        if slot is None:
            update(conn,id,'fallida',result={'detalle':'No hubo capacidad disponible; no se inició el trabajo.'})
            return
        if not update(conn,id,'ejecutando',step='Preparando actualización'):return
        def progress(label):update(conn,id,'ejecutando',step=label)
        if service=='nfl_predictions':
            from core.nfl_creditos import run_predictions
            result=run_predictions(ROOT,payload,on_step=progress)
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
            result=run_update(service,ROOT,on_step=progress)
            flags=[s['ok'] for s in result['steps']]
            state='fallida' if result.get('busy') or not any(flags) else 'completada' if all(flags) else 'parcial'
        update(conn,id,state,result=result)
    except Exception:
        if conn is not None:
            try:update(conn,id,'fallida',result={'detalle':'La ejecución no pudo completarse. Revisa resultados antes de reintentar; pudo haber consumo si solicitaste cuotas.'})
            except Exception:pass
    finally:
        if slot and cur is not None:
            try:cur.execute('SELECT RELEASE_LOCK(%s)',(slot,));cur.fetchone()
            except Exception:pass
        if cur is not None:
            try:
                if owns_service:
                    cur.execute('SELECT RELEASE_LOCK(%s)',('oracle-job-'+service,));cur.fetchone()
                cur.close()
            except Exception:pass
        if conn is not None:conn.close()


def submit(service,*,payload=None):
    if service not in SERVICES:raise ValueError('Servicio no permitido.')
    config=get_db_credentials();conn=get_db_connection();cur=conn.cursor()
    try:
        ensure_schema(conn, 'jobs')
        # Recuperar solo jobs huérfanos, sin volver a ejecutar cuotas automáticamente.
        cur.execute('''UPDATE oracle_trabajos SET estado='interrumpida',activo=NULL,terminado_utc=UTC_TIMESTAMP(6)
            WHERE activo=%s AND estado='ejecutando' AND creado_utc<UTC_TIMESTAMP(6)-INTERVAL 5 MINUTE
            AND IS_USED_LOCK(%s) IS NULL''',(service,'oracle-job-'+service))
        id=str(uuid.uuid4())
        try:
            cur.execute("INSERT INTO oracle_trabajos(id,servicio,activo,estado,creado_utc) VALUES (%s,%s,%s,'en_cola',UTC_TIMESTAMP(6))",(id,service,service))
            cur.execute('UPDATE oracle_trabajos SET payload=%s WHERE id=%s',(json.dumps(payload,ensure_ascii=False),id))
            conn.commit()
        except mysql.connector.IntegrityError:
            conn.rollback()
            cur.execute('SELECT id FROM oracle_trabajos WHERE activo=%s',(service,))
            row=cur.fetchone()
            if row:return row[0]
            raise
        try:EXECUTOR.submit(worker,id,service,payload,config)
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
        if row and row['estado']=='ejecutando' and row['viejo'] and row['lock_owner'] is None:row['estado']='interrumpida'
        if row and isinstance(row.get('resultado'),str):row['resultado']=json.loads(row['resultado'])
        return row
    except mysql.connector.Error as exc:
        if exc.errno==1146:return None
        raise
    finally:
        if cur is not None:cur.close()
        if conn is not None:conn.close()
