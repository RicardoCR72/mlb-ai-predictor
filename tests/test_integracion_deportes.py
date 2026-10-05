import ast
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import yaml
from core import bankroll as bank
from futbol_liga_mx import proveedor_espn as espn
from futbol_liga_mx.inferencia import historical_probabilities, upcoming_probabilities
from futbol_liga_mx.continuidad import portable_probability
from futbol_liga_mx.modelo import build_features
from futbol_liga_mx.recuperar_historial import recover

ROOT = Path(__file__).resolve().parents[1]


def extracted(path, function, context):
    node = next(n for n in ast.parse((ROOT/path).read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == function)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), context)
    return context[function]


class FakeCursor:
    rowcount = 1
    def __init__(self, conn): self.conn = conn
    def execute(self, sql, params=()): self.conn.calls.append((sql, params))
    def close(self): pass


class FakeConnection:
    def __init__(self): self.calls = [];self.commits = 0;self.rollbacks = 0
    def cursor(self, **kwargs): return FakeCursor(self)
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


class TestBankroll(unittest.TestCase):
    def test_roi_only_settled_and_available_balance(self):
        frame = pd.DataFrame([dict(estado=s, monto=m, ganancia_neta=g) for s,m,g in
                              [('Ganada',100,90),('Perdida',100,-100),('Push',100,0),
                               ('Pendiente',1000,0),('Anulada',1000,0)]])
        metrics = bank.metrics(frame, 2000)
        self.assertAlmostEqual(metrics['roi'], -10/300*100)
        self.assertEqual(metrics['saldo'],1990)
        self.assertEqual(metrics['disponible'],990)
        self.assertEqual(metrics['win_rate'],50)

    def test_save_snapshot_accepts_text_or_timestamp_date(self):
        conn = FakeConnection()
        bet = dict(fecha='2026-10-04', deporte='NFL', partido='A @ B', seleccion='OVER 45.5',
                   casa='DraftKings', cuota=1.91, monto=100, probabilidad=.58,
                   origen='nfl_total', referencia={'game_id':'g','line':45.5,'side':'OVER'})
        bank.save_bet(conn, bet, 'receipt')
        params = conn.calls[0][1]
        self.assertEqual(params[1], date(2026,10,4))
        self.assertEqual(params[8], 'Pendiente')
        self.assertEqual(params[9],0)
        self.assertEqual(params[10],.58)
        self.assertIn('ON DUPLICATE KEY UPDATE id=id',conn.calls[0][0])
        bet['fecha'] = pd.Timestamp('2026-10-04')
        bank.save_bet(conn, bet, 'receipt')
        self.assertEqual(conn.calls[1][1][1],date(2026,10,4))

    def test_invalid_price_does_not_write(self):
        with self.assertRaises(ValueError): bank.decimal_odds(0)
        conn=FakeConnection()
        with self.assertRaises(ValueError): bank.save_bet(conn, {'cuota':float('nan'),'monto':10})
        self.assertEqual(conn.calls,[])

    def test_settlement_uses_original_bet_line_and_price(self):
        conn=FakeConnection()
        bet = dict(id='receipt',estado='Pendiente',origen='nfl_total',partido='A @ B',
                   cuota=2.0,monto=150,referencia=json.dumps({'game_id':'g','line':40.5,'side':'OVER'}))
        ledger=pd.DataFrame([bet])
        def query(conn, sql, params=()):
            if 'FROM nfl_juegos' in sql:
                return pd.DataFrame([dict(marcador_local=21,marcador_visitante=21,
                                          equipo_local='B',equipo_visitante='A')])
            return pd.DataFrame([dict(monto=150,cuota=2.0,estado='Pendiente')])
        with patch.object(bank,'load_ledger',return_value=ledger), patch.object(bank,'rows',side_effect=query):
            changed, errors=bank.settle_pending(conn, ROOT)
        self.assertEqual(changed,1);self.assertEqual(errors,[])
        sql,params=conn.calls[0]
        self.assertEqual(params,('Ganada',150.0,'receipt'))
        self.assertIn("AND estado='Pendiente'",sql)

    def test_manual_or_already_settled_bets_are_not_overwritten(self):
        ledger=pd.DataFrame([dict(estado='Ganada',origen='nfl_total'),
                             dict(estado='Pendiente',origen='manual')])
        with patch.object(bank,'load_ledger',return_value=ledger), patch.object(bank,'rows') as query:
            self.assertEqual(bank.settle_pending(FakeConnection(),ROOT),(0,[]))
        query.assert_not_called()

    def test_early_mlb_final_requires_manual_review(self):
        bet=dict(id='receipt',estado='Pendiente',origen='mlb_total',partido='A @ B',
                 referencia=json.dumps({'game_id':'g','line':8.5,'side':'OVER'}))
        with patch.object(bank,'load_ledger',return_value=pd.DataFrame([bet])), patch.object(bank,'rows',return_value=pd.DataFrame([dict(home_runs=8,away_runs=3,revision_reglas=1)])):
            self.assertEqual(bank.settle_pending(FakeConnection(),ROOT),(0,[]))


class TestNFLIntegration(unittest.TestCase):
    def test_all_month_ranges_are_valid(self):
        workflow=yaml.safe_load((ROOT/'.github/workflows/bot_nfl_props.yml').read_text())
        for event in workflow[True]['schedule']:
            for interval in event['cron'].split()[3].split(','):
                lo,hi=map(int,interval.split('-'))
                self.assertLessEqual(lo,hi)
        self.assertEqual(workflow['jobs']['props']['env']['DB_SSL_CA'],'${{ runner.temp }}/aiven-ca.pem')

    def test_manual_odds_download_is_unique_and_opt_in(self):
        w=yaml.safe_load((ROOT/'.github/workflows/nfl_props.yml').read_text())
        steps=[s for s in w['jobs']['props-nfl']['steps'] if 'actualizar_lineas_props.py' in s.get('run','')]
        self.assertEqual(len(steps),1)
        self.assertIn('inputs.actualizar_odds == true',steps[0]['if'])
        self.assertIn('--solo-draftkings',steps[0]['run'])
        self.assertEqual(w['concurrency']['group'],'nfl-props-cuota')

    def test_cached_odds_never_fall_back_to_other_book(self):
        fn=extracted(Path('nfl/actualizar_lineas_props.py'),'seleccionar_casas',{'CASAS_PREFERIDAS':{'draftkings'}})
        self.assertEqual(fn([{'key':'fanduel'}]),[])
        self.assertEqual(fn([{'key':'fanduel'},{'key':'draftkings'}]),[{'key':'draftkings'}])

    def test_projection_query_requires_draftkings(self):
        conn=FakeConnection()
        FakeCursor.fetchall=lambda self: []
        fn=extracted(Path('nfl/predecir_props_semana_actual.py'),'cargar_lineas',{'pd':pd,'np':np})
        self.assertTrue(fn(conn,['g']).empty)
        self.assertIn("LOWER(TRIM(casa_apuestas)) = 'draftkings'",conn.calls[0][0])


class TestLigaMXIntegration(unittest.TestCase):
    def event(self, eid='1', status='STATUS_SCHEDULED'):
        return dict(id=eid,date='2026-07-03T01:00:00Z',season={'year':2026},
                    status={'type':{'name':status}}, competitions=[{'competitors':[
                        {'homeAway':'home','team':{'displayName':'América'},'score':'2'},
                        {'homeAway':'away','team':{'displayName':'Chivas'},'score':'1'}]}])

    def test_cached_scheduled_event_is_refreshed_and_partial_scan_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'cache').mkdir()
            games=pd.read_csv(ROOT/'futbol_liga_mx/data/partidos.csv')
            original=len(games)
            games.to_csv(root/'partidos.csv',index=False)
            (root/'cache/espn_events.json').write_text(json.dumps({'20260703':[self.event()]}))
            with patch.object(espn,'get_scoreboard',return_value=[self.event(status='STATUS_FINAL')]) as getter:
                past,_=espn.run(str(root/'partidos.csv'),str(root/'proximos.csv'),
                    cutoff=date(2026,10,4),season_start=date(2026,7,3),season_end=date(2026,7,3))
            getter.assert_called_once()
            self.assertGreaterEqual(len(past),original)
            self.assertTrue(set(games[games.season=='2024-25'].fecha).issubset(set(past.fecha)))

    def test_screen_reproduces_confirmation_and_future_results_cannot_change_past(self):
        games=pd.read_csv(ROOT/'futbol_liga_mx/data/partidos.csv')
        games=games[games.season<='2024-25'].copy()
        params=json.loads((ROOT/'futbol_liga_mx/modelos/modelo_portable.json').read_text())
        actual=historical_probabilities(games,params)
        expected=portable_probability(build_features(games),params)
        np.testing.assert_allclose(actual.p_over25,expected,rtol=1e-12)
        changed=games.copy();changed.loc[changed.fecha>'2024-10-27','goles_local']+=20
        mutated=historical_probabilities(changed,params)
        np.testing.assert_allclose(actual.loc[actual.fecha<=pd.Timestamp('2024-10-27'),'p_over25'],
                                   mutated.loc[mutated.fecha<=pd.Timestamp('2024-10-27'),'p_over25'])

    def test_missing_season_blocks_screen_before_odds(self):
        games=pd.read_csv(ROOT/'futbol_liga_mx/data/partidos.csv')
        fixtures=pd.read_csv(ROOT/'futbol_liga_mx/data/proximos.csv')
        with self.assertRaisesRegex(ValueError,'2025-26 incompleta'):
            upcoming_probabilities(games,fixtures,{}, {'seasons':{'confirmacion':'2024-25'}})

    def test_failed_backfill_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'partidos.csv'
            path.write_bytes((ROOT/'futbol_liga_mx/data/partidos.csv').read_bytes())
            original=path.read_bytes()
            with patch('futbol_liga_mx.recuperar_historial.fetch',return_value=None),patch('futbol_liga_mx.recuperar_historial.fetch_csv',return_value=None):
                self.assertFalse(recover(path,Path(tmp)/'cache'))
            self.assertEqual(path.read_bytes(),original)


class TestBankrollUI(unittest.TestCase):
    def context(self):
        from contextlib import ExitStack
        stack = ExitStack()
        conn = FakeConnection()
        conn.close = lambda: None
        stack.enter_context(patch('core.db.get_db_connection', return_value=conn))
        stack.enter_context(patch.object(bank, 'prepare'))
        stack.enter_context(patch.object(bank, 'settle_pending', return_value=(0, [])))
        stack.enter_context(patch.object(bank, 'load_ledger', return_value=pd.DataFrame(columns=bank.COLUMNS)))
        stack.enter_context(patch.object(bank, 'capital', return_value=1000.0))
        return stack, conn

    def test_manual_save_from_form_has_valid_date(self):
        from streamlit.testing.v1 import AppTest
        context, conn = self.context()
        with context:
            app = AppTest.from_file(str(ROOT/'pages/0_💼_Bankroll.py')).run(timeout=10)
            fields = {widget.label: widget for widget in app.text_input}
            fields['Partido'].set_value('A @ B')
            fields['Selección'].set_value('OVER 45.5')
            next(widget for widget in app.button if widget.label == 'Guardar apuesta realizada').click().run(timeout=10)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(conn.calls), 1)
        self.assertIsInstance(conn.calls[0][1][1], date)
        self.assertEqual(conn.calls[0][1][9], 0.0)

    def test_model_form_keeps_snapshot_when_predictions_update(self):
        from streamlit.testing.v1 import AppTest
        context, conn = self.context()
        option = dict(fecha='2026-10-04', deporte='NFL', partido='A @ B', seleccion='OVER 40.5',
                      casa='DraftKings', cuota=1.91, probabilidad=.58, origen='nfl_total',
                      referencia={'game_id':'g','side':'OVER','line':40.5})
        with context, patch.object(bank, 'model_options', return_value=([option], [])) as load:
            app = AppTest.from_file(str(ROOT/'pages/0_💼_Bankroll.py')).run(timeout=10)
            app.radio[0].set_value('Predicción del modelo').run(timeout=10)
            load.return_value = ([{**option, 'probabilidad':.8, 'seleccion':'UNDER 50.5'}], [])
            next(widget for widget in app.button if widget.label == 'Guardar apuesta realizada').click().run(timeout=10)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(load.call_count, 1)
        params = conn.calls[0][1]
        self.assertEqual(params[4], 'OVER 40.5')
        self.assertEqual(params[10], .58)
        self.assertEqual(json.loads(params[12])['line'],40.5)

    def test_offline_keeps_calculator_without_saving(self):
        from streamlit.testing.v1 import AppTest
        with patch('core.db.get_db_connection', side_effect=RuntimeError('offline')):
            app = AppTest.from_file(str(ROOT/'pages/0_💼_Bankroll.py')).run(timeout=10)
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('MySQL' in warning.value for warning in app.warning))


if __name__=='__main__': unittest.main()
