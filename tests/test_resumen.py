from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
import json
import pandas as pd
from streamlit.testing.v1 import AppTest
from core import bankroll as bank
from core.resumen import read_summary, prediction_summary, game_summary, empty

NOW=datetime(2026,10,7,3,tzinfo=timezone.utc) # 6 de octubre, 21:00 CDMX
ROOT=Path(__file__).resolve().parents[1]


class SummaryTests(TestCase):
    def test_dates_pending_and_final_today_are_separate(self):
        frame=pd.DataFrame([
            dict(game_id='today',fecha='2026-10-06',estado_pick='PICK',resultado='PENDIENTE',estado_juego='programado'),
            dict(game_id='old',fecha='2026-10-05',estado_pick='PICK',resultado=None,estado_juego='programado'),
            dict(game_id='final',fecha='2026-10-06',estado_pick='PICK',resultado=None,estado_juego='finalizado'),
            dict(game_id='settled',fecha='2026-10-05',estado_pick='PICK',resultado='GANADA',estado_juego='finalizado')])
        picks,pending,items=prediction_summary(frame,NOW,keys=['game_id'],candidate=lambda r:r['estado_pick']=='PICK')
        self.assertEqual((picks,pending),(1,2))
        self.assertEqual(len(items),2)
        utc=frame.iloc[[0,1]].copy()
        utc['fecha']=['2026-10-07T04:00:00Z','2026-10-07T01:00:00Z']
        self.assertEqual(prediction_summary(utc,NOW,keys=['game_id'],candidate=lambda r:True,utc=True)[:2],(1,0))

    def test_calendar_uses_verified_utc_hours_and_seven_calendar_days(self):
        frame=pd.DataFrame([dict(fecha=d,local='A',visitante='B') for d in
            ['2026-10-07T04:00:00Z','2026-10-13T04:00:00Z','2026-10-14T04:00:00Z','2026-10-07T01:00:00Z']])
        today,pending,games=game_summary(frame,NOW,utc=True)
        self.assertEqual((today,pending),(1,0))
        self.assertEqual(len(games),2)
        self.assertEqual(games[0]['Horario'],'22:00 CDMX')
        finished=pd.DataFrame([dict(fecha='2026-10-06',local='A',visitante='B',estado='finalizado',marcador_local=None,marcador_visitante=None)])
        self.assertEqual(game_summary(finished,NOW)[:2],(0,1))

    def setup_files(self,folder):
        data=Path(folder)/'futbol_liga_mx/data';data.mkdir(parents=True)
        pd.DataFrame([dict(fecha='2026-10-05',local='A',visitante='B',season='2026-27',goles_local=1,goles_visitante=0)]).to_csv(data/'partidos.csv',index=False)
        fixtures=pd.DataFrame([dict(fecha='2026-10-06',local='A',visitante='B',inicio_utc='2026-10-07T04:00:00Z')])
        fixtures.to_csv(data/'proximos.csv',index=False)
        (data/'cobertura_actual.json').write_text(json.dumps({'verified_utc':NOW.isoformat()}))
        return fixtures

    def test_read_only_partial_source_failure_and_actual_bankroll(self):
        calls=[]
        games=pd.DataFrame([dict(game_id='g',fecha='2026-10-06',local='A',visitante='B',estado='programado',marcador_local=None,marcador_visitante=None)])
        ledger=pd.DataFrame([dict(fecha=pd.Timestamp('2026-10-05'),partido='A @ B',seleccion='OVER',estado='Pendiente',monto=200,ganancia_neta=0)])
        def query(conn,sql,params=()):
            calls.append(sql)
            self.assertTrue(sql.lstrip().startswith('SELECT'))
            if 'FROM juegos' in sql or 'FROM nfl_juegos' in sql: return games
            if 'FROM nfl_proyecciones_props p' in sql: raise RuntimeError('do not disclose this')
            if 'MAX(' in sql: return pd.DataFrame({'fecha':['2026-10-06T21:00:00Z']})
            if 'capital_inicial' in sql: return pd.DataFrame({'capital_inicial':[1000]})
            return pd.DataFrame()
        with TemporaryDirectory() as folder:
            fixtures=self.setup_files(folder)
            with patch.object(bank,'rows',side_effect=query),patch.object(bank,'load_ledger',return_value=ledger), \
                 patch.object(bank,'prepare') as prepare,patch.object(bank,'settle_pending') as settle, \
                 patch('futbol_liga_mx.continuidad.frozen_model',return_value=({},{})), \
                 patch('futbol_liga_mx.continuidad.upcoming_ready',return_value=fixtures):
                data=read_summary(Mock(),folder,NOW)['services']
            self.assertEqual(data['bankroll']['finance']['disponible'],800)
            self.assertEqual(data['bankroll']['pending'],1)
            self.assertEqual(data['liga_mx']['picks_today'],2)
            self.assertEqual(data['mlb']['games_today'],1)
            self.assertIsNone(data['nfl_props']['picks_today'])
            self.assertIsNone(data['nfl_props']['pending'])
            self.assertTrue(data['nfl_props']['errors'])
            self.assertNotIn('do not disclose',str(data))
            prepare.assert_not_called();settle.assert_not_called()
            self.assertTrue(calls)

    def test_offline_preserves_local_liga_and_never_invents_capital(self):
        with TemporaryDirectory() as folder:
            fixtures=self.setup_files(folder)
            with patch('futbol_liga_mx.continuidad.frozen_model',return_value=({},{})), \
                 patch('futbol_liga_mx.continuidad.upcoming_ready',return_value=fixtures):
                data=read_summary(None,folder,NOW)['services']
            self.assertEqual(data['liga_mx']['picks_today'],2)
            self.assertIsNone(data['mlb']['picks_today'])
            self.assertIsNone(data['nfl_totales']['pending'])
            self.assertNotIn('finance',data['bankroll'])

    def test_old_dates_are_not_a_failed_update_and_blocked_liga_is_unknown(self):
        with TemporaryDirectory() as folder:
            self.setup_files(folder)
            with patch('futbol_liga_mx.continuidad.frozen_model',side_effect=ValueError('blocked')):
                data=read_summary(None,folder,NOW)['services']['liga_mx']
            self.assertIsNone(data['games_today'])
            self.assertIsNone(data['picks_today'])
            self.assertTrue(data['errors'])

    def fixture(self):
        services={k:empty(k) for k in ['mlb','mlb_total','nfl_totales','nfl_props','liga_mx','bankroll']}
        services['liga_mx'].update(games_today=1,picks_today=2,pending=0,last_data=NOW.isoformat(),
            games=[dict(Fecha='2026-10-06',Horario='22:00 CDMX',Partido='A @ B')])
        return dict(today='2026-10-06',at=NOW.isoformat(),services=services)

    def test_home_and_service_ui_continue_with_partial_data(self):
        data=self.fixture()
        with patch('core.ui_resumen.snapshot',return_value=data):
            app=AppTest.from_file(str(ROOT/'dashboard.py')).run(timeout=10)
            self.assertFalse(app.exception)
            self.assertTrue(any('parcial' in metric.value for metric in app.metric))
            self.assertTrue(any(metric.value=='No disponible' for metric in app.metric))
            self.assertGreaterEqual(len(app.dataframe),2)
            app=AppTest.from_string("from core.ui_resumen import render_service_status\nrender_service_status('mlb')").run()
            self.assertFalse(app.exception)
            self.assertTrue(any('No disponible' in c.value for c in app.caption))

    def test_connection_is_closed_and_refresh_only_clears_summary(self):
        from core import ui_resumen as ui
        self.assertIn('zona no verificada',ui.timestamp('2026-10-06 18:00:00',assume_utc=False))
        ui.load_snapshot.clear()
        conn=Mock()
        with patch.object(ui,'get_db_connection',return_value=conn),patch.object(ui,'read_summary',return_value=self.fixture()) as read:
            self.assertEqual(ui.load_snapshot('fixture')['today'],'2026-10-06')
            conn.close.assert_called_once()
            read.assert_called_once()
        ui.load_snapshot.clear()
        with patch.object(ui,'snapshot',return_value=self.fixture()),patch.object(ui.load_snapshot,'clear') as clear:
            app=AppTest.from_file(str(ROOT/'dashboard.py')).run()
            app.button(key='home_refresh').click().run()
            self.assertFalse(app.exception)
            clear.assert_called_once()
