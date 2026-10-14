from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch,Mock
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.combinadas import prepare_candidates,recommend,combination
from core.combinadas_datos import read_candidates

NOW=datetime(2099,10,11,16,tzinfo=timezone.utc)


class ParlayTests(TestCase):
    def fixture(self):
        picks=[]
        for index,(sport,prob) in enumerate([('NFL',.8),('MLB',.75),('Liga MX',.7)]):
            picks.append(dict(deporte=sport,fecha='2099-10-11',local=f'Local {index}',visitante=f'Visitante {index}',
                origen=['nfl_prop','mlb_total','liga_mx'][index],mercado='Total',seleccion='OVER 25.5',
                probabilidad=prob,cuota=1.9 if index<2 else None,casa='DraftKings',casa_verificada=index<2,
                inicio_utc=NOW+timedelta(hours=3),cuota_capturada_utc=NOW-timedelta(minutes=5),referencia={}))
        return picks

    def test_rank_and_recommend_one_per_match_even_across_markets(self):
        options=self.fixture();other=dict(options[0],origen='nfl_total',seleccion='UNDER 50.5',probabilidad=.9)
        ranked=prepare_candidates(options+[other],NOW)
        selected=recommend(ranked,3)
        self.assertEqual([p['probabilidad'] for p in selected],[.9,.75,.7])
        self.assertEqual(len({p['event'] for p in selected}),3)
        result=combination(selected,NOW)
        self.assertAlmostEqual(result['probability'],.9*.75*.7)
        self.assertIsNone(result['odds'])

    def test_prices_only_when_same_verified_house_and_no_duplicate_event(self):
        picks=prepare_candidates(self.fixture(),NOW)[:2]
        result=combination(picks,NOW)
        self.assertAlmostEqual(result['odds'],1.9**2)
        self.assertFalse(combination([picks[0],picks[0]],NOW)['ok'])
        picks[1]['casa']='Otro';self.assertIsNone(combination(picks,NOW)['odds'])
        picks[1]['casa']='DraftKings';picks[1]['casa_verificada']=False
        self.assertIsNone(combination(picks,NOW)['odds'])

    def test_same_player_line_and_side_in_different_markets_are_distinct_picks(self):
        original=dict(self.fixture()[0],jugador_id='player',tipo_prop='receiving_yards')
        other=dict(original,tipo_prop='rushing_yards',probabilidad=.85)
        ranked=prepare_candidates([original,other],NOW)
        self.assertEqual(len(ranked),2)
        self.assertNotEqual(ranked[0]['id'],ranked[1]['id'])
        self.assertEqual(len(recommend(ranked,3)),1)

    def test_started_review_unknown_time_old_quotes_and_invalid_probabilities(self):
        original=self.fixture()[0]
        self.assertEqual(prepare_candidates([dict(original,inicio_utc=NOW)],NOW),[])
        for update in [dict(estado='REVISAR LESION'),dict(inicio_utc=None),dict(cuota_capturada_utc=NOW-timedelta(hours=25))]:
            candidates=prepare_candidates([dict(original,**update)],NOW)
            self.assertFalse(candidates[0]['automatic']);self.assertEqual(recommend(candidates,2),[])
        for p in [None,float('nan'),float('inf'),-1,72,1]:
            self.assertEqual(prepare_candidates([dict(original,probabilidad=p)],NOW),[])

    def test_current_clock_and_mexico_date_reject_rollover_and_later_start(self):
        options=self.fixture();options[0]['inicio_utc']=datetime(2099,10,12,2,tzinfo=timezone.utc)
        self.assertEqual(prepare_candidates(options,NOW)[0]['fecha'],'2099-10-11')
        self.assertFalse(combination(prepare_candidates(options,NOW)[:2],NOW+timedelta(days=1))['ok'])

    def test_source_reader_is_select_only_and_partial_failures_keep_other_sports(self):
        calls=[]
        def query(conn,sql):
            calls.append(sql);self.assertTrue(sql.strip().upper().startswith('SELECT'))
            if 'nfl_proyecciones_props' in sql:
                return pd.DataFrame([dict(game_id='g',jugador_id='p',tipo_prop='receiving_yards',fecha='2099-10-11',
                    local='A',visitante='B',jugador='Jugador',seleccion='OVER',linea=30.5,american=-110,
                    probabilidad=.7,estado='CANDIDATO',captura=NOW)])
            if 'registro_picks_ia' in sql:raise RuntimeError('secret should not display')
            return pd.DataFrame()
        with patch('core.combinadas_datos.rows',side_effect=query),patch('core.combinadas_datos.nfl_starts',return_value={'g':NOW+timedelta(hours=2)}), \
             patch('futbol_liga_mx.continuidad.frozen_model',side_effect=ValueError('blocked')):
            picks,errors=read_candidates(Mock(),'.',NOW)
        self.assertEqual(len(picks),1);self.assertNotIn('secret',str(errors));self.assertEqual(len(calls),4)
        self.assertAlmostEqual(picks[0]['cuota'],1+100/110)
        self.assertEqual(picks[0]['probabilidad'],.7)

    def test_ui_proposal_and_edit_conflicts_and_missing_quotes(self):
        options=self.fixture()
        with patch('core.ui_combinadas_diseno.load_candidates',return_value=(options,[])),patch('core.ui_combinadas_diseno.datetime') as clock:
            clock.now.return_value=NOW
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'pages/5_🎯_Combinadas.py')).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value,'3')
            self.assertEqual(app.metric[1].value,'42.0%')
            self.assertEqual(app.metric[2].value,'Por confirmar')
            app.multiselect(key='parlay_legs').set_value([]).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('al menos dos' in w.value for w in app.warning))
            app.multiselect(key='parlay_sports').set_value(['NFL']).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.info)
            self.assertTrue(any('oracle-state' in m.value and 'dos partidos' in m.value for m in app.markdown))
