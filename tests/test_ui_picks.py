from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.ui_filtros import filter_frame
from core.ui_picks import nfl_pick, mlb_total_pick, liga_pick, card_html, pick_key
from core import bankroll


class PickTests(TestCase):
    def test_liga_nine_games_have_nine_cards_and_keep_selected_side_for_registration(self):
        with patch('core.ui_picks.get_db_connection') as connect:
            at=AppTest.from_string('''
import pandas as pd
from core.ui_picks import render_liga_matches
render_liga_matches(pd.DataFrame([dict(fecha='2099-10-10',inicio_utc='2099-10-11T01:00:00Z',
 visitante=f'Visitante {i}',local=f'Local {i}',p_over25=.58,p_under25=.42) for i in range(9)]))
''').run()
            self.assertFalse(at.exception)
            cards=lambda: [m.value for m in at.markdown if '<div class="oracle-pick ' in m.value]
            self.assertEqual(len(cards()),9)
            self.assertEqual(len(at.button),9)
            self.assertTrue(all('58.0%' in card and '42.0%' in card for card in cards()))
            at.selectbox[0].select('UNDER').run()
            self.assertEqual(len(cards()),9)
            at.button[0].click().run()
            draft=at.session_state['pick_draft']
            self.assertEqual(draft['seleccion'],'UNDER 2.5')
            self.assertEqual(draft['referencia']['side'],'UNDER')
            self.assertEqual(draft['referencia']['local'],'Local 0')
            self.assertEqual(draft['probabilidad'],.42)
            at.button[2].click().run()
            at.selectbox[0].select('OVER').run()
            at.button[0].click().run()
            self.assertEqual(at.session_state['pick_draft']['probabilidad'],.58)
            self.assertFalse(at.exception)
            connect.assert_not_called()

    def nfl_row(self):
        return dict(id_juego='2026_05_A_B', id_jugador='p1', tipo_prop='receiving_yards',
            gameday='2026-10-10', away_team='A', home_team='B', pick='OVER', seleccion='UNDER',
            total_line=45.5, linea=60.5, odds_pick=-110, cuota_pick=120, prob_pick=.61,
            probabilidad_pick=.57, player_name='Jugador', casa_apuestas='DraftKings')

    def test_adapters_keep_line_probability_and_settlement_identifiers(self):
        total = nfl_pick(self.nfl_row())
        prop = nfl_pick(self.nfl_row(), prop=True)
        self.assertAlmostEqual(total['cuota'], 1+100/110)
        self.assertEqual(total['probabilidad'], .61)
        self.assertEqual(prop['cuota'], 2.2)
        self.assertEqual(prop['referencia'], dict(game_id='2026_05_A_B', id_jugador='p1',
            tipo_prop='receiving_yards', side='UNDER', line=60.5))
        self.assertNotIn('inicio_utc', total['referencia'])
        row = dict(game_id=1, fecha='2026-10-10', start_utc='2026-10-10T23:00:00Z',
            visitante='A', local='B', seleccion='OVER', linea=8.5, cuota_over=1.95, prob_seleccion=.6)
        a = mlb_total_pick(row)
        b = mlb_total_pick(dict(row, game_id=2, start_utc='2026-10-11T02:00:00Z'))
        self.assertNotEqual(pick_key(a), pick_key(b))
        self.assertEqual(a['referencia']['line'],8.5)
        self.assertEqual(a['referencia']['game_id'],'1')
        liga = liga_pick(dict(fecha=pd.Timestamp('2026-10-10'),inicio_utc='2026-10-11T01:00:00Z',
            visitante='A',local='B',p_over25=.58,p_under25=.42), 'UNDER')
        self.assertEqual(liga['referencia']['fecha'],'2026-10-10')
        self.assertIsNone(liga['cuota'])
        self.assertEqual(liga['probabilidad'],.42)

    def test_card_escapes_content_and_discloses_missing_kickoff(self):
        pick = nfl_pick(self.nfl_row())
        pick['partido'] = '<script>alert(1)</script>'
        html = card_html(pick, market='Total', details=[('Edge','<b>5</b>')])
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('Hora no verificada',html)
        self.assertIn('61.0%',html)

    def app(self):
        return AppTest.from_string('''
from core.ui_picks import render_pick
pick = dict(fecha='2099-10-10',deporte='NFL',partido='A @ B',seleccion='OVER 45.5',
    casa='DraftKings',cuota=1.95,probabilidad=.61,origen='nfl_total',
    referencia=dict(game_id='g1',side='OVER',line=45.5))
render_pick(pick, market='Total', state='PICK')
''').run()

    def test_registration_requires_confirmation_and_preserves_snapshot_on_retry(self):
        conn = Mock()
        with patch('core.ui_picks.get_db_connection',return_value=conn) as connect, \
             patch.object(bankroll,'prepare'), patch.object(bankroll,'save_bet') as save:
            at=self.app()
            self.assertFalse(at.exception)
            connect.assert_not_called()
            at.button[0].click().run()
            at.number_input[0].set_value(2.1)
            at.number_input[1].set_value(250)
            at.button[1].click().run()
            self.assertTrue(at.warning)
            save.assert_not_called()
            at.checkbox[0].check()
            save.side_effect=RuntimeError('no secrets in UI')
            at.button[1].click().run()
            first_receipt=save.call_args.args[2]
            self.assertTrue(at.error)
            self.assertNotIn('no secrets',at.error[0].value)
            save.side_effect=None
            at.button[1].click().run()
            self.assertFalse(at.exception)
            self.assertEqual(save.call_args.args[2],first_receipt)
            bet=save.call_args.args[1]
            self.assertEqual((bet['cuota'],bet['monto'],bet['probabilidad']),(2.1,250,.61))
            self.assertEqual(bet['estado'],'Pendiente')
            self.assertEqual(bet['referencia']['line'],45.5)
            self.assertTrue(at.success)
            self.assertNotIn('pick_draft',at.session_state)
            self.assertEqual(conn.close.call_count,2)

    def test_cancel_and_started_game_never_write(self):
        with patch('core.ui_picks.get_db_connection') as connect:
            at=self.app();at.button[0].click().run();at.button[2].click().run()
            self.assertFalse(at.exception)
            self.assertNotIn('pick_draft',at.session_state)
            at=AppTest.from_string('''
from core.ui_picks import render_pick
render_pick(dict(fecha='2000-01-01',deporte='MLB',partido='A @ B',seleccion='OVER 8.5',
 casa='DraftKings',cuota=1.9,probabilidad=.6,origen='mlb_total',
 referencia=dict(game_id='1',side='OVER',line=8.5,inicio_utc='2000-01-01T23:00:00Z')),market='Total')
''').run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.button),0)
            connect.assert_not_called()


class FilterTests(TestCase):
    def test_cdmx_dates_and_inclusive_seven_day_window(self):
        frame=pd.DataFrame({'fecha':['2026-10-07T03:00:00Z','2026-10-01','2026-09-29',None],
            'prob':[.6,.7,.8,.9]})
        got=filter_frame(frame,'fecha',period='Hoy',today=date(2026,10,6))
        self.assertEqual(got.index.tolist(),[0])
        got=filter_frame(frame,'fecha',period='Últimos 7 días',today=date(2026,10,6))
        self.assertEqual(got.index.tolist(),[0,1])
        self.assertEqual(len(frame),4)

    def test_season_range_confidence_market_and_result_share_metrics_sample(self):
        frame=pd.DataFrame(dict(fecha=['2026-10-01','2026-10-06','2026-10-07'],
            season=[2026,2026,2025],p=[.61,.59,.8],mercado=['total','prop','total'],
            estado=['Ganada','Perdida','Ganada'],monto=[100,200,100],ganancia_neta=[95,-200,95]))
        got=filter_frame(frame,'fecha',period='Temporada',season_col='season',season='2026',
            probability_col='p',probability_scale=100,minimum=60,market_col='mercado',market='total')
        self.assertEqual(got.index.tolist(),[0])
        self.assertEqual(bankroll.metrics(got)['roi'],95)
        got=filter_frame(frame,'fecha',period='Rango personalizado',start=date(2026,10,6),end=date(2026,10,7),
            result_col='estado',result='Ganada')
        self.assertEqual(got.index.tolist(),[2])
        self.assertTrue(filter_frame(frame,'fecha',period='Rango personalizado',start=date(2026,10,7),end=date(2026,10,6)).empty)

    def test_filter_widget_recalculates_before_rendering_metrics(self):
        at=AppTest.from_string('''
import pandas as pd
import streamlit as st
from core.ui_filtros import performance_filters
frame=pd.DataFrame(dict(fecha=['2026-10-01','2026-10-02'],prob=[.55,.7],estado=['Ganada','Perdida']))
filtered=performance_filters(frame,'fecha','test',probability_col='prob',probability_scale=100,result_col='estado')
st.metric('Muestra',len(filtered))
''').run()
        self.assertFalse(at.exception)
        at.slider[0].set_value(60).run()
        self.assertEqual(at.metric[0].value,'1')
        at.selectbox[1].select('Ganada').run()
        self.assertEqual(at.metric[0].value,'0')
