"""Prueba transaccional contra MySQL real, solo en la base desechable del CI."""
import os
import unittest
import uuid
from core.db import get_db_connection
from core import bankroll as bank

@unittest.skipUnless(os.environ.get('BANKROLL_MYSQL_TEST')=='1','Requiere MySQL de pruebas')
class TestRealMySQL(unittest.TestCase):
    def test_nfl_paid_capture_audit_and_lock_between_connections(self):
        from datetime import date
        from nfl import capturas
        self.assertEqual(os.environ.get('DB_NAME'),'bankroll_ci')
        first,second=get_db_connection(),get_db_connection()
        try:
            capturas.preparar(first)
            self.assertTrue(capturas.adquirir(first))
            self.assertFalse(capturas.adquirir(second))
            game='test-'+str(uuid.uuid4())
            id=capturas.iniciar(first,game,'event-test',date(2026,10,11))
            # La reserva de consulta persiste aunque nunca llegue una respuesta HTTP.
            cur=second.cursor(dictionary=True)
            cur.execute('SELECT * FROM nfl_capturas_odds WHERE id=%s',(id,))
            row=cur.fetchone();cur.close();second.commit()
            self.assertEqual(row['estado'],'solicitada')
            self.assertIsNone(row['creditos'])
            capturas.terminar(first,id,6)
            cur=second.cursor(dictionary=True)
            cur.execute('SELECT * FROM nfl_capturas_odds WHERE id=%s',(id,))
            row=cur.fetchone();cur.close();second.commit()
            self.assertEqual(row['creditos'],6)
            self.assertEqual(row['fecha_mexico'],date(2026,10,11))
            capturas.liberar(first)
            self.assertTrue(capturas.adquirir(second))
            capturas.liberar(second)
        finally:
            first.close();second.close()

    def test_persistence_duplicate_audit_and_balance(self):
        self.assertEqual(os.environ.get('DB_NAME'),'bankroll_ci')
        conn = get_db_connection()
        try:
            bank.prepare(conn)
            bank.capital(conn,1000)
            receipt=str(uuid.uuid4())
            bet=dict(fecha='2026-10-05',deporte='NFL',partido=receipt,seleccion='OVER 45.5',
                     casa='DraftKings',cuota=1.91,monto=100,probabilidad=.58,origen='nfl_total',
                     referencia={'game_id':receipt,'side':'OVER','line':45.5,
                                 'inicio_utc':'2026-10-06T20:00:00Z'})
            bank.save_bet(conn,bet,receipt)
            bank.save_bet(conn,{**bet,'monto':900},receipt)  # receipt retry never changes snapshot
            with self.assertRaisesRegex(ValueError,'ya está registrada'):
                bank.save_bet(conn,bet,str(uuid.uuid4()))
        finally: conn.close()
        conn=get_db_connection()
        try:
            ledger=bank.load_ledger(conn);saved=ledger[ledger.id.eq(receipt)].iloc[0]
            self.assertEqual(saved.monto,100);self.assertEqual(saved.probabilidad,.58)
            self.assertEqual(bank.metrics(ledger,1000)['disponible'],900)
            self.assertEqual(bank.update_state(conn,receipt,'Ganada',reason='Resultado comprobado'),1)
            self.assertEqual(bank.update_state(conn,receipt,'Perdida',only_pending=True),0)
            ledger=bank.load_ledger(conn);stats=bank.metrics(ledger,1000)
            self.assertEqual(stats['saldo'],1091);self.assertEqual(stats['disponible'],1091)
            self.assertEqual(stats['roi'],91)
            events=bank.load_audit(conn);events=events[events.apuesta_id.eq(receipt)]
            self.assertEqual(list(events.accion),['estado','registro'])
            self.assertEqual(events.iloc[0].motivo,'Resultado comprobado')
            import io,zipfile
            with zipfile.ZipFile(io.BytesIO(bank.export_bundle(conn))) as archive:
                self.assertEqual(set(archive.namelist()),{'apuestas.csv','auditoria.csv','recibos.csv','config.json'})
            # A distinct bookmaker ticket permits a second real identical wager.
            bank.save_bet(conn,{**bet,'ticket':'second-ticket'},str(uuid.uuid4()))
            self.assertEqual(len(bank.load_ledger(conn)),2)
            # A transaction failure must not leave an orphan receipt or audit event.
            failing={**bet,'ticket':'failure','partido':'x'*300}
            with self.assertRaises(Exception):bank.save_bet(conn,failing,str(uuid.uuid4()))
            self.assertEqual(len(bank.rows(conn,'SELECT * FROM bankroll_recibos')),2)
            # Simular los registros anteriores a la tabla de recibos, incluidos duplicados históricos.
            audit_count=len(bank.load_audit(conn))
            cur=conn.cursor()
            try:
                cur.execute('DELETE FROM bankroll_recibos')
                cur.execute('DELETE FROM bankroll_migraciones')
                conn.commit()
            finally:cur.close()
            bank.prepare(conn)
            self.assertEqual(len(bank.load_ledger(conn)),2)  # nunca borra apuestas previas
            self.assertEqual(len(bank.rows(conn,'SELECT * FROM bankroll_recibos')),1)
            self.assertEqual(len(bank.load_audit(conn)),audit_count)
            bank.prepare(conn)  # migración idempotente
            with self.assertRaisesRegex(ValueError,'ya está registrada'):
                bank.save_bet(conn,bet,str(uuid.uuid4()))
        finally:conn.close()

if __name__=='__main__':unittest.main()
