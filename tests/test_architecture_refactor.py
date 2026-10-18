"""Regresiones de contratos, vigencia, vistas y límites de infraestructura."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import ast
import unittest
from unittest.mock import patch, Mock
import pandas as pd
from core.domain.contracts import Prediction, probabilities
from core.domain.quotes import fresh_quotes
from nfl.services.eligibility import upcoming
from core.infrastructure.migrations import ensure_schema

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,18,15,30,tzinfo=timezone.utc)


class ContractTests(unittest.TestCase):
    def test_scales_are_explicit_including_low_percentages(self):
        self.assertEqual(probabilities(pd.Series([.5,50]),scale=100).tolist(),[.005,.5])
        self.assertTrue(pd.isna(probabilities(pd.Series([50]),scale=1).iloc[0]))
        with self.assertRaises(ValueError):probabilities(pd.Series([1]),scale=10)

    def test_prediction_rejects_naive_time_invalid_odds_and_post_start(self):
        args=dict(game_id='g',market='Totales',selection='OVER',probability=.6,model='v',
                  start_utc=NOW+timedelta(hours=1),generated_utc=NOW,provider='nflverse')
        self.assertEqual(Prediction(**args).probability,.6)
        for change in [dict(generated_utc=NOW.replace(tzinfo=None)),dict(probability=60),
                       dict(decimal_odds=1),dict(generated_utc=NOW+timedelta(hours=2))]:
            with self.assertRaises(ValueError):Prediction(**(args|change))

    def test_quotes_expire_and_future_unknown_captures_are_rejected(self):
        f=pd.DataFrame(dict(id=['fresh','old','future','missing'],timestamp_captura=[
            NOW-timedelta(minutes=10),NOW-timedelta(minutes=121),NOW+timedelta(minutes=1),None]))
        self.assertEqual(fresh_quotes(f,NOW).id.tolist(),['fresh'])

    def test_started_games_disappear_even_before_the_result_arrives(self):
        f=pd.DataFrame(dict(id_juego=['future','live','unknown','settled'],resultado_pick=['PENDIENTE']*3+['GANADA'],
            inicio_utc=[NOW+timedelta(minutes=30),NOW-timedelta(minutes=1),None,NOW+timedelta(minutes=30)]))
        with patch('nfl.services.eligibility.nfl_starts',return_value={}):
            self.assertEqual(upcoming(f,NOW).id_juego.tolist(),['future'])

    def test_domain_and_view_imports_do_not_depend_on_retired_features(self):
        for f in ['core/ui_tarjetas.py','core/comparador.py','nfl/publicaciones_totales.py']:
            s=(ROOT/f).read_text()
            self.assertNotIn('core.bankroll import',s)
            self.assertNotIn('core.combinadas_datos import',s)
        for f in ['dashboard.py','pages/2_🏈_NFL.py','pages/4_📊_Rendimiento.py']:
            self.assertNotIn('runpy',(ROOT/f).read_text())
        import subprocess
        files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        self.assertFalse(any('.venv' in f for f in files))

    def test_process_executor_does_not_pass_credentials_in_command_arguments(self):
        from core.application.jobs import ProcessExecutor
        with patch('core.application.jobs.subprocess.Popen') as child,patch.dict('os.environ',{'ORACLE_WORKER_MODE':'process'}):
            ProcessExecutor().submit(None,'job','mlb',None,{'password':'private'})
        args=child.call_args.args[0]
        self.assertNotIn('private',' '.join(args))
        self.assertTrue(child.call_args.kwargs['start_new_session'])
        self.assertIn('ORACLE_WORKER_DB',child.call_args.kwargs['env'])

    def test_external_worker_mode_only_enqueues(self):
        from core.application.jobs import ProcessExecutor
        with patch('core.application.jobs.subprocess.Popen') as child,patch.dict('os.environ',{'ORACLE_WORKER_MODE':'external'}):
            ProcessExecutor().submit(None,'job','mlb',None,{})
        child.assert_not_called()

    def test_migration_releases_lock_on_failure(self):
        conn=Mock();cursor=conn.cursor.return_value
        cursor.fetchone.side_effect=[(1,),None,None]
        def execute(sql,*args):
            if sql.startswith('CREATE TABLE IF NOT EXISTS nfl_capturas'):raise RuntimeError('DDL failure')
        cursor.execute.side_effect=execute
        with self.assertRaises(RuntimeError):ensure_schema(conn,'captures')
        self.assertTrue(any('RELEASE_LOCK' in c.args[0] for c in cursor.execute.call_args_list))
        cursor.close.assert_called_once()

    def test_same_price_new_capture_keeps_a_new_auditable_snapshot(self):
        from nfl import actualizar_lineas_props as capture
        old=dict(id_juego='g',id_jugador='p',casa_apuestas='DraftKings',tipo_prop='receptions',
                 linea=4.5,cuota_over=-110,cuota_under=-110,timestamp_captura='2026-10-18T12:00:00Z')
        key=('g','p','DraftKings','receptions')
        conn=Mock()
        with patch.object(capture,'cargar_ultimas_lineas',return_value={key:old}):
            self.assertEqual(capture.guardar_lineas(conn,[old]),0)
            self.assertEqual(capture.guardar_lineas(conn,[old|{'timestamp_captura':'2026-10-18T15:00:00Z'}]),1)
            self.assertEqual(capture.guardar_lineas(conn,[old|{'timestamp_captura':None}]),0)
        self.assertIsNone(capture.convertir_timestamp('sin hora'))
        self.assertIsNone(capture.convertir_timestamp('2026-10-18T15:00:00'))

    def test_one_nfl_scheduled_owner(self):
        import yaml
        for f in ['nfl_props.yml','nfl_predicciones.yml']:
            doc=yaml.safe_load((ROOT/'.github/workflows'/f).read_text())
            triggers=doc.get('on',doc.get(True,{}))
            self.assertNotIn('schedule',triggers)
        doc=yaml.safe_load((ROOT/'.github/workflows/bot_nfl_props.yml').read_text())
        self.assertIn('schedule',doc.get('on',doc.get(True,{})))
