"""Prueba transaccional contra MySQL real, solo en la base desechable del CI."""
import os
import unittest
import uuid
from core.db import get_db_connection
from core import bankroll as bank

@unittest.skipUnless(os.environ.get('BANKROLL_MYSQL_TEST')=='1','Requiere MySQL de pruebas')
class TestRealMySQL(unittest.TestCase):
    def test_jobs_persist_across_connections_and_exclude_duplicate_active_requests(self):
        from unittest.mock import patch
        from core import trabajos
        from core import permisos
        self.assertEqual(os.environ.get('DB_NAME'),'bankroll_ci')
        with patch.object(permisos,'configured_password',return_value='integration'),patch.object(trabajos.EXECUTOR,'submit') as worker:
            first=trabajos.submit('mlb',token='integration')
            self.assertEqual(trabajos.submit('mlb',token='integration'),first)
            worker.assert_called_once()
            read=trabajos.latest('mlb')
            self.assertEqual(read['id'],first);self.assertEqual(read['estado'],'en_cola')
            conn=get_db_connection()
            try:
                cur=conn.cursor()
                cur.execute('UPDATE oracle_trabajos SET creado_utc=UTC_TIMESTAMP(6)-INTERVAL 6 MINUTE WHERE id=%s',(first,));conn.commit()
                cur.execute("SELECT GET_LOCK('oracle-job-mlb',0)");self.assertEqual(cur.fetchone()[0],1)
                self.assertEqual(trabajos.latest('mlb')['estado'],'en_cola')
                cur.execute("SELECT RELEASE_LOCK('oracle-job-mlb')");cur.fetchone()
                self.assertEqual(trabajos.latest('mlb')['estado'],'interrumpida')
                cur.close()
                trabajos.update(conn,first,'ejecutando',step='Resultados')
                trabajos.update(conn,first,'completada',result={'detalle':'2 resultados guardados'})
                read=trabajos.latest('mlb')
                self.assertEqual(read['estado'],'completada');self.assertIsNone(read['activo'])
                self.assertNotIn('integration',str(read['resultado']))
                second=trabajos.submit('mlb',token='integration')
                self.assertNotEqual(first,second)
                trabajos.update(conn,second,'fallida',result={'detalle':'Prueba finalizada'})
            finally:conn.close()

    def test_nfl_total_original_is_immutable_and_never_backfills_a_past_start(self):
        from unittest.mock import patch
        import pandas as pd
        from nfl import publicaciones_totales as pub
        game='totals-'+str(uuid.uuid4())
        frame=pd.DataFrame([dict(game_id=game,estado='PICK',pick='OVER',total_line=45.5,prob_pick=.6,odds_pick=-110)])
        conn=get_db_connection()
        try:
            with patch.object(pub,'nfl_starts',return_value={game:pd.Timestamp('2099-10-01T20:00Z')}):
                pub.save(conn,frame,'v1',None)
                frame['total_line']=55.5;frame['prob_pick']=.9
                pub.save(conn,frame,'v1',None)
            cur=conn.cursor()
            cur.execute('SELECT linea,probabilidad FROM nfl_publicaciones_totales WHERE id_juego=%s',(game,))
            self.assertEqual(cur.fetchone(),(45.5,.6))
            with patch.object(pub,'nfl_starts',return_value={game:pd.Timestamp('2020-10-01T20:00Z')}):pub.save(conn,frame,'past',None)
            cur.execute('SELECT COUNT(*) FROM nfl_publicaciones_totales WHERE id_juego=%s',(game,))
            self.assertEqual(cur.fetchone()[0],1);cur.close()
        finally:conn.close()

    def test_mlb_totals_retry_keeps_original_and_settlement_is_one_row_per_game(self):
        import pandas as pd
        from datetime import datetime
        from mlb_totales import registro
        from mlb_totales.test_integracion import TestIntegration
        self.assertEqual(os.environ.get('DB_NAME'),'bankroll_ci')
        conn=get_db_connection()
        try:
            registro.prepare(conn)
            row=TestIntegration().snapshot()
            row['game_id']=int(uuid.uuid4().hex[:12],16)
            model=uuid.uuid4().hex*2
            self.assertEqual(registro.save_snapshots(conn,pd.DataFrame([row]),model,now='2026-09-30T18:00:00Z'),1)
            changed={**row,'linea':7.5,'p_over':.8,'p_under':.2,'cuota_over':2.2}
            self.assertEqual(registro.save_snapshots(conn,pd.DataFrame([changed]),model,now='2026-09-30T18:10:00Z'),0)
            cur=conn.cursor(dictionary=True)
            cur.execute('SELECT linea,confianza,cuota_seleccion FROM mlb_totales_predicciones WHERE game_pk=%s AND model_id=%s',(row['game_id'],model))
            self.assertEqual(cur.fetchone(),dict(linea=8.5,confianza=.6,cuota_seleccion=1.91))
            cur.close();cur=conn.cursor()
            for _ in range(2):cur.execute(registro.RESULT_SQL,(row['game_id'],5,4,9,0,datetime(2026,10,1)))
            conn.commit()
            cur.execute('SELECT COUNT(*) FROM mlb_totales_resultados WHERE game_pk=%s',(row['game_id'],))
            self.assertEqual(cur.fetchone()[0],1)
            frame=registro.settle(registro.history(conn))
            pick=frame[(frame.game_pk==row['game_id']) & frame.model_id.eq(model)]
            self.assertEqual(len(pick),1)
            self.assertAlmostEqual(pick.iloc[0].unidades,.91)
            cur.close()
        finally:conn.close()

    def test_favorites_persist_update_and_delete_without_touching_bankroll(self):
        from core import preferencias
        self.assertEqual(os.environ.get('DB_NAME'),'bankroll_ci')
        scope='test-'+str(uuid.uuid4())
        preferencias.save(scope,'Recepciones',{'period':'Últimos 7 días','market':'receptions','confidence':60})
        self.assertEqual(preferencias.load(scope)['Recepciones']['confidence'],60)
        preferencias.save(scope,'Recepciones',{'period':'Todo el historial','confidence':65})
        self.assertEqual(len(preferencias.load(scope)),1)
        self.assertEqual(preferencias.load(scope)['Recepciones']['confidence'],65)
        self.assertEqual(preferencias.load(scope+'other'),{})
        preferencias.delete(scope,'Recepciones')
        self.assertEqual(preferencias.load(scope),{})

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

    def test_mlb_join_handles_legacy_collations_and_settles_exact_event(self):
        from datetime import date
        from mlb import publicaciones_moneyline as pub
        conn=get_db_connection()
        try:
            pub.prepare(conn);cur=conn.cursor()
            # Legacy y tablas nuevas tienen distintas reglas para comparar texto.
            cur.execute("CREATE TABLE IF NOT EXISTS juegos (id_juego VARCHAR(128) PRIMARY KEY, fecha DATETIME, equipo_local VARCHAR(128), equipo_visitante VARCHAR(128), marcador_local INT NULL, marcador_visitante INT NULL) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute("ALTER TABLE mlb_moneyline_mercado CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            cur.execute("ALTER TABLE mlb_publicaciones_moneyline CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            game='join-'+str(uuid.uuid4())
            cur.execute("INSERT INTO juegos VALUES (%s,'2099-01-01 19:00:00','A','B',NULL,NULL)",(game,))
            cur.execute(pub.MARKET_SQL,(game,'2099-01-02 01:00:00','A','B',1.9,2.1,'2020-01-01 00:00:00'));conn.commit()
            import mysql.connector
            with self.assertRaises(mysql.connector.Error) as incompatible:
                cur.execute("SELECT j.id_juego FROM juegos j JOIN mlb_moneyline_mercado m ON j.id_juego=m.id_juego")
            self.assertEqual(incompatible.exception.errno,1267)
            conn.rollback()
            cur.execute(pub.TODAY_SQL,(date(2099,1,1),))
            self.assertIn(game,[r[0] for r in cur.fetchall()]);conn.commit()
            pub.save(conn,game_id=game,model_id='a'*64,day=date(2099,1,1),home='A',away='B',pick='B',confidence=70,home_odds=1.9,away_odds=2.1)
            cur.execute('UPDATE juegos SET marcador_local=2,marcador_visitante=4 WHERE id_juego=%s',(game,));conn.commit()
            cur.execute(pub.HISTORY_SQL);columns=[r[0] for r in cur.description]
            saved=[dict(zip(columns,r)) for r in cur.fetchall()]
            self.assertEqual(next(r for r in saved if r['id_juego']==game)['resultado'],'GANADA')
            cur.execute(pub.TODAY_SQL,(date(2099,1,1),));self.assertNotIn(game,[r[0] for r in cur.fetchall()])
            cur.close()
        finally:conn.close()

    def test_mlb_original_publication_is_immutable_and_rejects_started_games(self):
        from datetime import date
        from mlb import publicaciones_moneyline as pub
        conn=get_db_connection()
        try:
            pub.prepare(conn);game='mlb-'+str(uuid.uuid4());cur=conn.cursor()
            cur.execute(pub.MARKET_SQL,(game,'2099-01-02 01:00:00','A','B',1.9,2.1,'2020-01-01 00:00:00'))
            conn.commit()
            args=dict(game_id=game,model_id='a'*64,day=date(2099,1,1),home='A',away='B',pick='A',
                      confidence=70,home_odds=1.9,away_odds=2.1)
            self.assertTrue(pub.save(conn,**args))
            self.assertFalse(pub.save(conn,**{**args,'confidence':99,'pick':'B'}))
            cur.execute('SELECT probabilidad,pick_ia,publicada_utc,start_utc FROM mlb_publicaciones_moneyline WHERE id_juego=%s',(game,))
            original=cur.fetchone();conn.commit()
            self.assertEqual(original[:2],(.7,'A'));self.assertLess(original[2],original[3])
            # Otra versión conserva su propia primera publicación.
            self.assertTrue(pub.save(conn,**{**args,'model_id':'b'*64}))
            # Una captura que cambia durante el cálculo no se certifica.
            cur.execute('UPDATE mlb_moneyline_mercado SET cuota_local=1.8 WHERE id_juego=%s',(game,));conn.commit()
            self.assertFalse(pub.save(conn,**{**args,'model_id':'c'*64}))
            cur.execute('UPDATE mlb_moneyline_mercado SET start_utc=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE id_juego=%s',(game,));conn.commit()
            self.assertFalse(pub.save(conn,**{**args,'model_id':'d'*64,'home_odds':1.8}))
            cur.execute('SELECT COUNT(*) FROM mlb_publicaciones_moneyline WHERE id_juego=%s',(game,))
            self.assertEqual(cur.fetchone()[0],2);cur.close()
        finally:conn.close()

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
            bank.unit_value(conn,250)
            bank.prepare(conn)  # no restablece la unidad ni reescribe las apuestas
            self.assertEqual(bank.unit_value(conn),250)
            units=bank.with_units(bank.load_ledger(conn),bank.unit_value(conn))
            self.assertEqual(units.iloc[0]['Monto (u)'],.4)
            self.assertAlmostEqual(units.iloc[0]['Beneficio (u)'],.364)
            self.assertEqual(units.iloc[0].monto,100)
            self.assertEqual(units.iloc[0].ganancia_neta,91)
            self.assertEqual(bank.metrics(units,1000),stats)
            second=get_db_connection()
            try:self.assertEqual(bank.unit_value(second),250)
            finally:second.close()
            events=bank.load_audit(conn);events=events[events.apuesta_id.eq(receipt)]
            self.assertEqual(list(events.accion),['estado','registro'])
            self.assertEqual(events.iloc[0].motivo,'Resultado comprobado')
            import io,zipfile
            with zipfile.ZipFile(io.BytesIO(bank.export_bundle(conn))) as archive:
                self.assertEqual(set(archive.namelist()),{'apuestas.csv','auditoria.csv','recibos.csv','config.json'})
                import json
                self.assertEqual(json.loads(archive.read('config.json'))['valor_unidad_mxn'],250)
            self.assertEqual(len(bank.load_audit(conn).query("accion == 'unidad'")),1)
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

    def test_receiving_publication_is_immutable_across_connections(self):
        import json
        import pandas as pd
        from datetime import datetime,timezone
        from nfl.publicaciones_props import save_publications,attach_publications
        self.assertEqual(os.environ.get('DB_NAME'),'bankroll_ci')
        game='test-'+str(uuid.uuid4())
        frame=pd.DataFrame([dict(game_id=game,player_id='p',tipo_prop='receiving_yards',
            id_linea=123,linea=60.5,proyeccion=85,seleccion='OVER',probabilidad_pick=.65,
            cuota_pick=-110,estado_pick='REVISAR LESION',dependencia_lesion=True)])
        games=pd.DataFrame([dict(game_id=game,gameday='2099-10-11',gametime='13:00')])
        conn=get_db_connection()
        try:
            save_publications(conn,frame,games,'v')
            frame['proyeccion']=30
            save_publications(conn,frame,games,'v')
        finally:conn.close()
        conn=get_db_connection()
        try:
            record=dict(id_juego=game,id_jugador='p',tipo_prop='receiving_yards',modelo_version='v',id_linea=123)
            saved=attach_publications(conn,[record])[0]
            self.assertEqual(json.loads(saved['auditoria_payload'])['proyeccion'],85)
            # Otra línea o modelo no reutilizan el registro anterior.
            self.assertIsNone(attach_publications(conn,[dict(record,id_linea=999)])[0]['auditoria_payload'])
            self.assertIsNone(attach_publications(conn,[dict(record,modelo_version='other')])[0]['auditoria_payload'])
            frame['id_linea']=124
            save_publications(conn,frame,games,'v')
            self.assertEqual(json.loads(attach_publications(conn,[dict(record,id_linea=124)])[0]['auditoria_payload'])['proyeccion'],30)
        finally:conn.close()

if __name__=='__main__':unittest.main()
