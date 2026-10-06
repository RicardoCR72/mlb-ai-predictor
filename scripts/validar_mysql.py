"""Diagnóstico de producción de solo lectura. Nunca imprime credenciales."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.db import get_db_connection

def main():
    conn=None
    try:
        conn=get_db_connection()
        cur=conn.cursor()
        try:
            cur.execute('SELECT VERSION()');version=cur.fetchone()[0]
            cur.execute("SHOW STATUS LIKE 'Ssl_cipher'");tls=cur.fetchone()
            cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('bankroll_apuestas','bankroll_config','bankroll_recibos','bankroll_auditoria','bankroll_migraciones')")
            tables={r[0] for r in cur.fetchall()}
            print('Conexión MySQL real: OK. Versión:',version)
            print('TLS activo:',bool(tls and tls[1]))
            expected={'bankroll_apuestas','bankroll_config','bankroll_recibos','bankroll_auditoria','bankroll_migraciones'}
            print('Tablas de bankroll:',len(tables),'de',len(expected))
            if tables != expected:
                print('::warning::Abre Bankroll para aplicar la preparación aditiva de tablas. No se modificó la base en este diagnóstico.')
            if 'bankroll_apuestas' in tables:
                cur.execute('SELECT COUNT(*) FROM bankroll_apuestas');print('Apuestas persistidas:',cur.fetchone()[0])
        finally:cur.close()
    except Exception as exc:
        print('::error::Diagnóstico MySQL falló:',type(exc).__name__)
        return 1
    finally:
        if conn is not None:conn.close()
    return 0

if __name__=='__main__':sys.exit(main())
