"""Worker separado de Streamlit. No reintenta tareas pagadas interrumpidas."""
import argparse
import json
import os
import time
from core.db import get_db_connection, get_db_credentials
from core.application.jobs import worker, SERVICES
from core.infrastructure.migrations import ensure_schema


def run_pending(job_id=None):
    import mysql.connector
    config = json.loads(os.environ['ORACLE_WORKER_DB']) if os.environ.get('ORACLE_WORKER_DB') else get_db_credentials()
    conn = mysql.connector.connect(**config)
    try:
        ensure_schema(conn, 'jobs')
        cursor = conn.cursor(dictionary=True)
        query = "SELECT id,servicio,payload FROM oracle_trabajos WHERE estado='en_cola'"
        args = ()
        if job_id:
            query += ' AND id=%s'
            args = (job_id,)
        query += ' ORDER BY creado_utc LIMIT 20'
        cursor.execute(query,args)
        jobs = cursor.fetchall()
        cursor.close()
    finally:
        conn.close()
    for job in jobs:
        if job['servicio'] not in SERVICES:
            continue
        payload = job['payload']
        if isinstance(payload,str):payload=json.loads(payload)
        worker(job['id'],job['servicio'],payload,config)
    return len(jobs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job')
    parser.add_argument('--once',action='store_true')
    args = parser.parse_args()
    while True:
        run_pending(args.job)
        if args.job or args.once:return
        time.sleep(4)


if __name__ == '__main__':
    main()
