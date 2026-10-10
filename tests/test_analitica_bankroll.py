import json
from pathlib import Path
from unittest import TestCase
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.analitica_bankroll import balance_curve, exposure
from core import bankroll as bank


class AnalyticsTests(TestCase):
    def ledger(self):
        frame=pd.DataFrame([
            dict(fecha='2026-10-01',estado='Ganada',monto=100,ganancia_neta=100),
            dict(fecha='2026-10-02',estado='Perdida',monto=300,ganancia_neta=-300),
            dict(fecha='2026-10-03',estado='Push',monto=100,ganancia_neta=0),
            dict(fecha='2026-10-04',estado='Pendiente',monto=200,ganancia_neta=0),
            dict(fecha='2026-10-05',estado='Anulada',monto=900,ganancia_neta=0)])
        frame['deporte']='NFL';frame['partido']='A @ B';frame['seleccion']='OVER 45.5'
        frame['casa']='DraftKings';frame['cuota']=2.0;frame['probabilidad']=.6
        frame['origen']='nfl_total'
        frame['referencia']=json.dumps({'game_id':'g1'})
        return frame

    def test_curve_matches_balance_and_excludes_pending_void(self):
        frame=self.ledger();curve=balance_curve(frame,1000)
        self.assertEqual(curve.Saldo.tolist(),[1000,1100,800,800])
        self.assertEqual(curve.iloc[-1].Saldo,bank.metrics(frame,1000)['saldo'])
        self.assertEqual(curve['Caída (MXN)'].max(),300)
        self.assertAlmostEqual(curve['Caída (%)'].max(),100*300/1100)
        self.assertEqual(curve.iloc[-1].Fecha,pd.Timestamp('2026-10-03'))
        self.assertEqual(frame.iloc[0].ganancia_neta,100)

    def test_daily_grouping_and_corrections_rebuild_the_curve(self):
        frame=self.ledger();frame.loc[1,'fecha']='2026-10-01'
        self.assertEqual(balance_curve(frame,1000).Saldo.tolist(),[1000,800,800])
        frame.loc[1,['estado','ganancia_neta']]=['Ganada',300]
        self.assertEqual(balance_curve(frame,1000).Saldo.tolist(),[1000,1400,1400])
        self.assertEqual(balance_curve(frame,2000).Saldo.tolist(),[2000,2400,2400])

    def test_empty_and_zero_capital_do_not_fabricate_returns(self):
        frame=self.ledger()
        self.assertTrue(balance_curve(frame[frame.estado.eq('Pendiente')],1000).empty)
        loss=frame[frame.estado.eq('Perdida')]
        curve=balance_curve(loss,0)
        self.assertEqual(curve['Caída (MXN)'].max(),300)
        self.assertTrue(curve['Caída (%)'].isna().all())
        with self.assertRaises(ValueError): balance_curve(frame,-1)

    def test_exposure_merges_nfl_markets_and_keeps_mlb_doubleheaders_distinct(self):
        frame=self.ledger().iloc[[3]].copy()
        second=frame.copy();second['origen']='nfl_prop';second['monto']=100
        mlb=frame.copy();mlb['deporte']='MLB';mlb['origen']='mlb_total';mlb['monto']=50
        mlb['referencia']=json.dumps({'game_id':'m1'})
        double=mlb.copy();double['referencia']=json.dumps({'game_id':'m2'})
        manual=frame.copy();manual['origen']='manual';manual['referencia']='{}';manual['monto']=20
        settled=self.ledger().iloc[[0]]
        source=pd.concat([frame,second,mlb,double,manual,settled],ignore_index=True)
        sports,games=exposure(source,1000)
        self.assertEqual(sports['Comprometido (MXN)'].sum(),420)
        self.assertAlmostEqual(sports['% del pendiente'].sum(),100)
        self.assertAlmostEqual(games['% del saldo'].sum(),42)
        self.assertEqual(len(games),4)
        self.assertEqual(games.iloc[0]['Comprometido (MXN)'],300)
        self.assertEqual(games.iloc[0]['Apuestas'],2)
        self.assertEqual(len(games[games.Deporte.eq('MLB')]),2)
        self.assertTrue(any('Sin identificador' in x for x in games.Agrupación))
        _,zero=exposure(source,0)
        self.assertTrue(zero['% del saldo'].isna().all())

    def test_empty_exposure_and_invalid_pending_amount(self):
        frame=self.ledger();a,b=exposure(frame[frame.estado.ne('Pendiente')],1000)
        self.assertTrue(a.empty and b.empty)
        frame.loc[frame.estado.eq('Pendiente'),'monto']=float('nan')
        with self.assertRaises(ValueError): exposure(frame,1000)

    def app(self):
        return AppTest.from_string('''
from tests.test_analitica_bankroll import AnalyticsTests
from core.ui_bankroll import render_analytics, render_history
from core.ui_movil import apply_mobile_layout
apply_mobile_layout()
ledger=AnalyticsTests().ledger()
render_analytics(ledger,1000)
render_history(ledger)
''').run()

    def test_charts_history_and_column_selection_preserve_all_rows(self):
        app=self.app()
        self.assertFalse(app.exception)
        self.assertTrue(any(m.label=='Caída máxima desde un pico' and '$300.00' in m.value for m in app.metric))
        self.assertEqual(len([n for n in app if 'vega_lite_chart' in n.type]),2)
        self.assertTrue(any('5 de 5 apuestas' in c.value for c in app.caption))
        self.assertFalse(any(b.label=='Registrar en bankroll' for b in app.button))
        app.radio(key='bank_history_view').set_value('Tabla').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[-1].value),5)
        app.multiselect(key='bank_history_columns').set_value([]).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Selecciona al menos' in i.value for i in app.info))


class UnitsTests(TestCase):
    def test_conversion_preserves_pesos_and_roi_at_different_unit_values(self):
        frame=AnalyticsTests().ledger()
        original=frame.copy(deep=True)
        for unit in (100,250):
            result=bank.with_units(frame,unit)
            self.assertEqual(result['Monto (u)'].tolist(),(frame.monto/unit).tolist())
            self.assertEqual(result['Beneficio (u)'].tolist(),(frame.ganancia_neta/unit).tolist())
            self.assertEqual(bank.metrics(result,1000),bank.metrics(frame,1000))
            self.assertTrue(result['Valor unidad (MXN)'].eq(unit).all())
            pd.testing.assert_frame_equal(frame,original)
        empty=bank.with_units(frame.iloc[:0],100)
        self.assertTrue(empty.empty)
        for invalid in (0,-100,float('nan'),float('inf'),.001):
            with self.assertRaises(ValueError):bank.with_units(frame,invalid)

    def test_cards_and_table_show_actual_mxn_and_configured_units(self):
        at=AppTest.from_string('''
from tests.test_analitica_bankroll import AnalyticsTests
from core.ui_bankroll import render_history
render_history(AnalyticsTests().ledger(),250)
''').run()
        self.assertFalse(at.exception)
        cards=[m.value for m in at.markdown if '<div class="oracle-pick ' in m.value]
        self.assertTrue(any('$100.00 MXN · 0.40 u' in card for card in cards))
        self.assertTrue(any('$-300.00 MXN · -1.20 u' in card for card in cards))
        self.assertTrue(any('Pendiente' in card for card in cards))
        at.radio(key='bank_history_view').set_value('Tabla').run()
        self.assertFalse(at.exception)
        table=at.dataframe[-1].value
        self.assertIn('Monto (u)',table)
        self.assertEqual(table['Monto (MXN)'].tolist(),[900,200,100,300,100])
        self.assertEqual(table['Monto (u)'].tolist(),[3.6,.8,.4,1.2,.4])

    def test_model_equivalence_uses_shared_value_and_does_not_invent_offline_amounts(self):
        from unittest.mock import patch
        from core.ui_unidades import load_unit
        load_unit.clear()
        source='from core.ui_unidades import render_model_equivalence\nrender_model_equivalence(2,.91)'
        with patch('core.ui_unidades.load_unit',return_value=250):
            at=AppTest.from_string(source).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.metric[0].value,'$500.00 MXN')
        self.assertEqual(at.metric[1].value,'$+227.50 MXN')
        with patch('core.ui_unidades.load_unit',return_value=None):
            at=AppTest.from_string(source).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.metric),0)
        self.assertTrue(any('Bankroll → Portafolio' in c.value for c in at.caption))

    def test_read_only_unit_lookup_closes_connection_on_failure(self):
        from unittest.mock import Mock,patch
        from core.ui_unidades import load_unit
        load_unit.clear()
        conn=Mock()
        with patch('core.ui_unidades.get_db_connection',return_value=conn), \
             patch.object(bank,'unit_value',side_effect=RuntimeError('private-detail')):
            self.assertIsNone(load_unit())
        conn.close.assert_called_once()
        load_unit.clear()
