import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.comparador import normalize,comparison,read_models,SAVED
from core.ui_controles import ordered


class ComparisonTests(TestCase):
    def frame(self):
        raw=pd.DataFrame([
            dict(id='a',fecha='2026-10-01',modelo='v1',resultado='GANADA',probabilidad=.7,cuota=-110),
            dict(id='b',fecha='2026-10-02',modelo='v1',resultado='PERDIDA',probabilidad=.8,cuota=120),
            dict(id='c',fecha='2026-10-03',modelo='v1',resultado='PUSH',probabilidad=.6,cuota=None),
            dict(id='d',fecha='2026-10-04',modelo='v1',resultado='GANADA',probabilidad=.6,cuota=None),
            dict(id='e',fecha='2026-10-05',modelo='v1',resultado='PENDIENTE',probabilidad=.9,cuota=-110),
            dict(id='a',fecha='2026-10-01',modelo='v1',resultado='PERDIDA',probabilidad=.7,cuota=-110),
            dict(id='a',fecha='2026-10-01',modelo='v2',resultado='GANADA',probabilidad=.7,cuota=120)])
        return normalize(raw,sport='NFL',market='Totales',identity=['id'],american=True)

    def test_one_unit_duplicates_models_push_missing_quote_and_pending(self):
        frame=self.frame()
        self.assertEqual(len(frame),6)
        stats=comparison(frame).set_index('Modelo')
        first=stats.loc['v1']
        self.assertEqual(first['Picks evaluados'],4)
        self.assertEqual(first['Picks con beneficio conocido'],3)
        self.assertEqual(first['Sin beneficio conocido'],1)
        self.assertAlmostEqual(first['Unidades'],100/110-1)
        self.assertAlmostEqual(first['ROI (%)'],100*(100/110-1)/3)
        self.assertAlmostEqual(stats.loc['v2']['ROI (%)'],120)
        self.assertEqual(first['Procedencia'],SAVED)

    def test_partial_failure_is_read_only_and_keeps_successful_source(self):
        calls=[]
        def query(conn,sql):
            calls.append(sql)
            self.assertTrue(sql.lstrip().startswith('SELECT'))
            if 'nfl_predicciones_totales' in sql:
                return pd.DataFrame([dict(fecha='2026-10-01',id_juego='g',modelo='v1',
                    probabilidad=.6,cuota=-110,resultado='GANADA')])
            raise RuntimeError('secret-not-for-ui')
        with patch('core.comparador.rows',side_effect=query),patch('core.comparador.registro.history',side_effect=RuntimeError):
            frame,issues=read_models(Mock())
        self.assertEqual(len(frame),1)
        self.assertEqual(set(issues),{'MLB Moneyline','MLB Totales V2','NFL Props'})
        self.assertNotIn('secret',str(issues))
        self.assertTrue(any('COUNT(*)' in sql for sql in calls))

    def test_verified_snapshots_exclude_after_start_and_non_candidates(self):
        raw=pd.DataFrame([dict(game_pk=i,model_id='v8',fecha_oficial='2026-10-01',confianza=.6,
            cuota_seleccion=1.9,seleccion='OVER',linea=8.5,home_runs=5,away_runs=4,revision_reglas=0,
            candidato=1 if i!=3 else 0,recorded_utc='2026-10-01T18:00:00Z' if i!=2 else '2026-10-01T22:00:00Z',
            quote_captured_utc='2026-10-01T17:00:00Z',start_utc='2026-10-01T20:00:00Z') for i in (1,2,3)])
        with patch('core.comparador.rows',return_value=pd.DataFrame()),patch('core.comparador.registro.history',return_value=raw):
            frame,issues=read_models(Mock())
        self.assertFalse(issues)
        self.assertEqual(len(frame),1)
        self.assertEqual(frame.iloc[0].procedencia,'Previo al inicio verificado')
        self.assertAlmostEqual(comparison(frame).iloc[0]['Unidades'],.9)

    def test_comparator_renders_filters_sample_and_safe_partial_failure(self):
        with patch('core.ui_comparador.load_comparison',return_value=(self.frame(),['NFL Props'])):
            at=AppTest.from_string('from core.ui_comparador import render_comparison\nrender_comparison()').run()
            self.assertFalse(at.exception)
            table=at.dataframe[-1].value
            self.assertIn('Picks con beneficio conocido',table)
            next(w for w in at.selectbox if w.label=='Resultado').select('GANADA').run()
            self.assertFalse(at.exception)
            self.assertTrue(at.dataframe[-1].value['Perdidas'].eq(0).all())
            self.assertTrue(any('Fuente no disponible' in m.value for m in at.markdown))


class ControlsTests(TestCase):
    def test_order_is_stable_missing_last_and_does_not_change_financial_sample(self):
        frame=pd.DataFrame(dict(fecha=['2026-10-03','2026-10-01','2026-10-02'],p=[.6,None,.8],u=[1,-1,0]))
        self.assertEqual(ordered(frame,'fecha',True).index.tolist(),[1,2,0])
        self.assertEqual(ordered(frame,'p',False).index.tolist(),[2,0,1])
        self.assertEqual(ordered(frame,'u',False).u.sum(),frame.u.sum())
        self.assertNotIn('_oracle_order',frame)

    def test_uniform_states_escape_html(self):
        at=AppTest.from_string('from core.ui_controles import state_message\nstate_message("<script>bad</script>",kind="offline")').run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        self.assertIn('&lt;script&gt;',at.markdown[0].value)
        self.assertIn('oracle-state',at.markdown[0].value)

    def source(self):
        return '''
import pandas as pd
import streamlit as st
from core.ui_filtros import performance_filters
frame=pd.DataFrame([dict(id='a',fecha='2026-10-01',p=.7,mercado='OVER',resultado='GANADA',week=1),
 dict(id='b',fecha='2026-10-02',p=.8,mercado='UNDER',resultado='PERDIDA',week=2),
 dict(id='c',fecha='2026-10-03',p=.5,mercado='UNDER',resultado='GANADA',week=2)])
f=performance_filters(frame,'fecha','favorite_test',probability_col='p',probability_scale=100,
 market_col='mercado',result_col='resultado',week_col='week')
st.session_state['visible_ids']=f.id.tolist()
'''

    def test_favorite_survives_new_session_and_reset_restores_full_sample(self):
        stored={}
        def save(scope,name,values):stored[name]=json.loads(json.dumps(values,default=str))
        with patch('core.preferencias.save',side_effect=save),patch('core.preferencias.load',side_effect=lambda scope:stored.copy()):
            at=AppTest.from_string(self.source()).run()
            at.slider[0].set_value(60).run()
            next(w for w in at.selectbox if w.label=='Mercado').select('UNDER').run()
            next(w for w in at.selectbox if w.label=='Semana').select('2').run()
            at.text_input(key='favorite_test_fav_name').set_value('NFL Under')
            at.button(key='favorite_test_fav_save').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(stored['NFL Under']['confidence'],60)
            fresh=AppTest.from_string(self.source()).run()
            self.assertEqual(fresh.session_state['visible_ids'],['a','b','c'])
            fresh.button(key='favorite_test_fav_load').click().run()
            fresh.button(key='favorite_test_fav_apply').click().run()
            self.assertFalse(fresh.exception)
            self.assertEqual(fresh.session_state['visible_ids'],['b'])
            fresh.button(key='favorite_test_reset').click().run()
            self.assertFalse(fresh.exception)
            self.assertEqual(fresh.session_state['visible_ids'],['a','b','c'])

    def test_stale_favorite_values_do_not_break_new_week_or_markets(self):
        with patch('core.preferencias.load',return_value={'Viejo':{'week':'99','market':'REMOVED','period':'Unknown'}}):
            at=AppTest.from_string(self.source()).run()
            at.button(key='favorite_test_fav_load').click().run()
            at.button(key='favorite_test_fav_apply').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['visible_ids'],['a','b','c'])


    def test_date_range_favorite_restores_date_widgets_in_new_session(self):
        from datetime import date
        stored={}
        def save(scope,name,values):stored[name]=json.loads(json.dumps(values,default=str))
        with patch('core.preferencias.save',side_effect=save),patch('core.preferencias.load',side_effect=lambda scope:stored.copy()):
            at=AppTest.from_string(self.source()).run()
            next(w for w in at.selectbox if w.label=='Periodo').select('Rango personalizado').run()
            next(w for w in at.date_input if w.label=='Desde').set_value(date(2026,10,1))
            next(w for w in at.date_input if w.label=='Hasta').set_value(date(2026,10,2))
            at.run()
            at.text_input(key='favorite_test_fav_name').set_value('Octubre')
            at.button(key='favorite_test_fav_save').click().run()
            fresh=AppTest.from_string(self.source()).run()
            fresh.button(key='favorite_test_fav_load').click().run()
            fresh.button(key='favorite_test_fav_apply').click().run()
            self.assertFalse(fresh.exception)
            self.assertEqual(fresh.session_state['visible_ids'],['a','b'])
            self.assertEqual(next(w for w in fresh.date_input if w.label=='Desde').value,date(2026,10,1))
