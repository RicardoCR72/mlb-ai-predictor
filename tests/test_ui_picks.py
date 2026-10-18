from datetime import date
import ast
import textwrap
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.ui_filtros import filter_frame
from core.ui_tarjetas import nfl_pick, mlb_total_pick, liga_pick, card_html, pick_key
from core import bankroll


class PickTests(TestCase):
    def test_liga_nine_games_have_nine_cards_without_registration_controls(self):
        with patch('core.ui_tarjetas.get_db_connection') as connect:
            at=AppTest.from_string('''
import pandas as pd
from core.ui_tarjetas import render_liga_matches
render_liga_matches(pd.DataFrame([dict(fecha='2099-10-10',inicio_utc='2099-10-11T01:00:00Z',
 visitante=f'Visitante {i}',local=f'Local {i}',p_over25=.58,p_under25=.42) for i in range(9)]))
''').run()
            self.assertFalse(at.exception)
            cards=lambda: [m.value for m in at.markdown if '<div class="oracle-pick ' in m.value]
            self.assertEqual(len(cards()),9)
            self.assertFalse(at.button)
            self.assertFalse(at.selectbox)
            self.assertTrue(all('58.0%' in card and '42.0%' in card for card in cards()))
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
from core.ui_tarjetas import render_pick
pick = dict(fecha='2099-10-10',deporte='NFL',partido='A @ B',seleccion='OVER 45.5',
    casa='DraftKings',cuota=1.95,probabilidad=.61,origen='nfl_total',
    referencia=dict(game_id='g1',side='OVER',line=45.5))
render_pick(pick, market='Total', state='PICK')
''').run()

    def test_cards_no_longer_offer_bankroll_registration(self):
        with patch('core.ui_tarjetas.get_db_connection') as connect, patch.object(bankroll,'save_bet') as save:
            at=self.app()
            self.assertFalse(at.exception)
            self.assertFalse(at.button)
            self.assertFalse(at.number_input)
            self.assertFalse(at.checkbox)
            self.assertFalse(at.get('form'))
            connect.assert_not_called();save.assert_not_called()



class FilterTests(TestCase):
    def test_week_market_and_result_combine_without_changing_input(self):
        frame=pd.DataFrame(dict(fecha=['2026-09-10']*4,week=[1,1,2,2],pick=['OVER','UNDER','UNDER','OVER'],
            resultado=['GANADA','PERDIDA','GANADA','PUSH']))
        got=filter_frame(frame,'fecha',week_col='week',week='1',market_col='pick',market='UNDER',
                         result_col='resultado',result='PERDIDA')
        self.assertEqual(got.index.tolist(),[1])
        self.assertEqual(len(frame),4)

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
from core.ui_filtros import performance_filters,safe_select
frame=pd.DataFrame(dict(fecha=['2026-10-01','2026-10-02'],prob=[.55,.7],estado=['Ganada','Perdida']))
filtered=performance_filters(frame,'fecha','test',probability_col='prob',probability_scale=100,result_col='estado')
st.metric('Muestra',len(filtered))
''').run()
        self.assertFalse(at.exception)
        at.slider[0].set_value(60).run()
        self.assertEqual(at.metric[0].value,'1')
        at.selectbox[1].select('Ganada').run()
        self.assertEqual(at.metric[0].value,'0')


class NFLTotalsFiltersTests(TestCase):
    def app(self):
        from core.comparador import normalize
        rows=[]
        for i,(week,pick,result,odds,p) in enumerate([(1,'OVER','GANADA',1.9,.6),
            (1,'UNDER','PERDIDA',1.9,.61),(2,'UNDER','GANADA',2.2,.7),(2,'OVER','PUSH',1.9,.55)]):
            rows.append(dict(id=f'g{i}',fecha=pd.Timestamp('2026-09-10')+pd.Timedelta(days=i),modelo='v1',
                seleccion=pick,linea=45.5,resultado=result,cuota=odds,probabilidad=p))
        f=normalize(pd.DataFrame(rows),sport='NFL',market='Totales',identity=['id'])
        f['Semana']=['1','1','2','2']
        self.enterContext(patch('core.ui_historial_publicado.load_history',return_value=(f,[])))
        return AppTest.from_string("from core.ui_historial_publicado import render_history\nrender_history('NFL','Totales',key='nfl_totals_test')").run()

    def test_real_totals_filters_update_metrics_market_comparison_and_cards(self):
        at=self.app()
        self.assertFalse(at.exception)
        self.assertFalse(next(e for e in at.expander if e.label=='Filtros de rendimiento').proto.expanded)
        def select(label,value):
            next(s for s in at.selectbox if s.label==label).select(value).run()
            self.assertFalse(at.exception)
        self.assertEqual(at.metric[0].value,'4')
        self.assertFalse(any(e.label in ('Balance y equivalencia en pesos','Análisis por mercado y semana','Comparar mercados') for e in at.expander))
        self.assertFalse(at.get('vega_lite_chart'))
        select('Mercado','UNDER')
        self.assertEqual(at.metric[0].value,'2')
        self.assertEqual(at.metric[3].value,'+10.0%')
        select('Semana','1')
        self.assertEqual(at.metric[0].value,'1')
        self.assertEqual(at.metric[3].value,'-100.0%')
        self.assertEqual(at.metric[0].value,'1')
        cards=[m.value for m in at.markdown if '<div class="oracle-pick ' in m.value]
        self.assertEqual(len(cards),1)
        self.assertIn('UNDER 45.5',cards[0])
        self.assertIn('❌ Perdida',cards[0])
        select('Resultado','PERDIDA')
        self.assertEqual(at.metric[0].value,'1')
        select('Resultado','GANADA')
        self.assertEqual(len(at.metric),0)
        self.assertEqual(len(at.metric),0)
        self.assertTrue(any('No hay registros para estos filtros' in m.value for m in at.markdown))


class PerformanceSummaryTests(TestCase):
    def test_more_cards_never_truncates_metrics_and_filter_change_resets_limit(self):
        app=AppTest.from_string('''
import pandas as pd
import streamlit as st
from core.ui_rendimiento_resumen import history_window,render_performance_charts
frame=pd.DataFrame([dict(id=i,fecha='2099-10-10',estado='GANADA',profit=1) for i in range(25)])
if st.checkbox('Solo cinco'):frame=frame.head(5)
st.metric('Picks evaluados',len(frame))
render_performance_charts(frame,date_col='fecha',profit_col='profit',result_col='estado')
visible=history_window(frame,'summary_test')
st.session_state['cards']=len(visible)
''').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['cards'],10)
        self.assertEqual(app.metric[0].value,'25')
        self.assertFalse(next(e for e in app.expander if e.label=='Comparar mercados').proto.expanded)
        app.button(key='summary_test_more').click().run()
        self.assertEqual(app.session_state['cards'],20)
        self.assertEqual(app.metric[0].value,'25')
        app.button(key='summary_test_more').click().run()
        self.assertEqual(app.session_state['cards'],25)
        app.checkbox[0].check().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['cards'],5)
        self.assertEqual(app.metric[0].value,'5')
        self.assertFalse(app.button)


class MLBTodayFiltersTests(TestCase):
    def test_totals_starts_at_fifty_and_only_exposes_confidence_filter(self):
        import mlb_totales.ui_totales_mlb as ui
        ready=pd.DataFrame([dict(casa_apuestas='DraftKings',odds_game_id=str(i),
            start_utc='2099-10-11T23:00:00Z',captured_utc='2099-10-11T22:00:00Z',
            estado_mercado='OK',abridor_local='A',abridor_visitante='B',age_minutes=10) for i in range(2)])
        pred=pd.DataFrame([dict(estado='EXPERIMENTAL',p_over=p,prob_seleccion=p,
            estado_valor='SIN VALOR',historial_hasta='2099-10-10',seleccion='OVER',
            ev_over=-.1,ev_under=-.2) for p in [.5,.74]])
        shown=[]
        with patch.object(ui,'cached_calendar',return_value=ready),patch.object(ui.registro,'quote_rows',return_value=ready), \
             patch.object(ui,'match',return_value=ready),patch.object(ui,'cached_predict',side_effect=lambda *a:pred.copy()), \
             patch.object(ui,'stamp',return_value=()),patch.object(ui.registro,'tables_ready',return_value=False), \
             patch.object(ui,'render_cards',side_effect=lambda f:shown.append(f.copy())),patch('streamlit.secrets',{}):
            at=AppTest.from_string('from unittest.mock import Mock\nfrom mlb_totales.ui_totales_mlb import render_picks\nrender_picks(Mock())').run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.slider),1)
            self.assertEqual(at.slider[0].value,50)
            self.assertFalse(at.date_input)
            self.assertFalse(at.number_input)
            self.assertFalse(at.checkbox)
            self.assertFalse(at.selectbox)
            self.assertEqual(len(shown[-1]),2)  # Sin exigir EV positivo.
            at.slider[0].set_value(60).run()
            self.assertFalse(at.exception)
            self.assertEqual(shown[-1].prob_seleccion.tolist(),[.74])


class MLBHistoryVisibilityTests(TestCase):
    def app(self,view,historical=True,reconstructed=False):
        from core.comparador import normalize
        f=normalize(pd.DataFrame([
            dict(id='g1',fecha='2026-09-01',modelo='MLB V4',seleccion='A',resultado='GANADA',cuota=1.9,probabilidad=.7),
            dict(id='g2',fecha='2026-09-02',modelo='MLB V4',seleccion='C',resultado='PERDIDA',cuota=1.8,probabilidad=.68)]),
            sport='MLB',market='Moneyline',identity=['id'])
        if not historical:f=f.iloc[:0]
        if reconstructed:f.loc[1,'procedencia']='Reconstruido'
        self.enterContext(patch('core.ui_historial_publicado.load_history',return_value=(f,[])))
        self.enterContext(patch('core.ui_trabajos.latest',return_value=None))
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'pages/1_⚾_MLB.py'))
        app.session_state['mlb_section']='Rendimiento' if 'Rendimiento' in view else 'Picks de hoy'
        return app.run()

    def test_history_renders_cards_and_metrics_without_querying_today(self):
        at=self.app('Rendimiento')
        self.assertFalse(at.exception)
        self.assertEqual([m.value for m in at.metric],['2','50.0%','-0.10 u','-5.0%'])
        cards=[m.value for m in at.markdown if '<div class="oracle-pick ' in m.value]
        self.assertEqual(len(cards),2)

    def test_empty_today_uses_neutral_mlb_style_and_preserves_history_navigation(self):
        at=self.app('Picks de hoy')
        self.assertFalse(at.exception);self.assertFalse(at.error)
        self.assertTrue(any('No hay publicaciones con inicio verificable' in m.value for m in at.markdown))
        next(r for r in at.radio if r.label=='Sección MLB').set_value('Rendimiento').run()
        self.assertEqual(at.metric[0].value,'2')

    def test_truly_empty_history_shows_its_own_message(self):
        at=self.app('Rendimiento',historical=False)
        self.assertFalse(at.exception);self.assertFalse(at.metric)
        self.assertTrue(any('No hay publicaciones disponibles' in m.value for m in at.markdown))

    def test_reconstructed_and_saved_picks_are_visible_and_filterable_separately(self):
        at=self.app('Rendimiento',reconstructed=True)
        next(w for w in at.selectbox if w.label=='Procedencia').select('Reconstruido').run()
        self.assertFalse(at.exception);self.assertEqual(at.metric[0].value,'1')
        cards=[m.value for m in at.markdown if '<div class="oracle-pick ' in m.value]
        self.assertTrue(all('Reconstruido' in c for c in cards))
