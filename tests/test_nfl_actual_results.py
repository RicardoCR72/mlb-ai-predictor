"""Resultados observados conservados desde SQL hasta la tarjeta de rendimiento."""
import unittest
from unittest.mock import patch, Mock
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.comparador import normalize
from core.ui_historial_publicado import actual_result_details
from core.ui_tarjetas import card_html


class ActualResultsTests(unittest.TestCase):
    def test_all_prop_markets_show_observed_values_including_zero(self):
        for market,actual,text in [('Yardas de recepción',30,'30 yardas'),('Yardas por pase',280,'280 yardas'),
             ('Yardas terrestres',0,'0 yardas'),('Recepciones',4,'4 recepciones'),
             ('Pases de touchdown',2,'2 pases de touchdown'),('Anota touchdown',0,'0 touchdowns')]:
            row=dict(deporte='NFL',mercado=market,resultado='GANADA',valor_real=actual,linea=20,proyeccion=99)
            self.assertEqual(actual_result_details(row),[('Resultado real',text)])

    def test_totals_show_points_and_score_and_do_not_invent_pending_values(self):
        row=dict(deporte='NFL',mercado='Totales',resultado='PERDIDA',total_real=47,marcador_local=27,marcador_visitante=20)
        self.assertEqual(actual_result_details(row),[('Total real','47 puntos'),('Marcador final','20 – 27 (visitante – local)')])
        row['resultado']='PENDIENTE'
        self.assertEqual(actual_result_details(row),[('Total real','Pendiente')])
        row.update(resultado='GANADA',total_real=None)
        self.assertEqual(actual_result_details(row)[0],('Total real','47 puntos'))
        row.update(marcador_local=None,marcador_visitante=None)
        self.assertEqual(actual_result_details(row)[0],('Total real','No disponible'))

    def test_normalization_keeps_actuals_and_selection_without_changing_metrics(self):
        raw=pd.DataFrame([dict(id='g',fecha='2026-10-18',modelo='v',resultado='GANADA',
            probabilidad=.6,cuota=1.9,seleccion='OVER',linea=20,valor_real=30,total_real=47,
            marcador_local=27,marcador_visitante=20)])
        frame=normalize(raw,sport='NFL',market='Yardas de recepción',identity=['id'])
        self.assertEqual(frame.valor_real.iloc[0],30)
        self.assertEqual(frame.total_real.iloc[0],47)
        self.assertAlmostEqual(frame.unidades.iloc[0],.9)
        self.assertEqual(frame.linea.iloc[0],20)

    def test_verified_totals_keep_official_total_and_original_line(self):
        from core import confianza_datos as data
        base=normalize(pd.DataFrame(),sport='NFL',market='Totales',identity=['id'])
        official=pd.DataFrame([dict(id_juego='g',modelo='v',linea=45.5,seleccion='OVER',
            probabilidad=.6,cuota=-110,start_utc='2026-10-18T17:00Z',publicada_utc='2026-10-18T16:00Z',
            fecha='2026-10-18',equipo_local='B',equipo_visitante='A',
            marcador_local=27,marcador_visitante=20,estado='finalizado')])
        def query(conn,sql):
            return official if 'FROM nfl_publicaciones_totales' in sql else pd.DataFrame()
        with patch.object(data,'read_models',return_value=(base,[])),patch.object(data,'rows',side_effect=query), \
             patch.object(data.registro,'history',return_value=pd.DataFrame()),patch.object(data,'nfl_starts',return_value={}):
            frame,_=data.read_history(Mock(),'.',include_liga=False)
        row=frame[frame.mercado.eq('Totales')].iloc[0]
        self.assertEqual(row.total_real,47)
        self.assertEqual(row.linea,45.5)
        self.assertEqual(row.resultado,'GANADA')
        self.assertIn(('Total real','47 puntos'),actual_result_details(row))

    def test_actual_is_visible_without_opening_details(self):
        pick=dict(deporte='NFL',fecha='2026-10-18',partido='A @ B',seleccion='Jugador · OVER 20',
                  casa='DraftKings',cuota=1.9,probabilidad=.6)
        html=card_html(pick,market='Yardas de recepción',state='GANADA',details=[('Resultado real','30 yardas')])
        self.assertIn('30 yardas',html.split('<details')[0])
        self.assertIn('OVER 20',html)

    def test_performance_renders_actual_in_card_and_preserves_csv(self):
        raw=pd.DataFrame([dict(id='g',fecha='2026-10-18',modelo='v',resultado='GANADA',
            probabilidad=.6,cuota=1.9,seleccion='OVER',linea=20,valor_real=30,jugador='Jugador',
            equipo_local='B',equipo_visitante='A')])
        frame=normalize(raw,sport='NFL',market='Yardas de recepción',identity=['id'])
        with patch('core.ui_historial_publicado.load_history',return_value=(frame,[])):
            app=AppTest.from_string("from core.ui_historial_publicado import render_history\nrender_history('NFL',None,key='actuals')").run()
        self.assertFalse(app.exception)
        cards=[m.value for m in app.markdown if 'oracle-pick' in m.value and 'Jugador' in m.value]
        self.assertEqual(len(cards),1)
        self.assertIn('30 yardas',cards[0].split('<details')[0])
        self.assertEqual(next(m for m in app.metric if m.label=='Picks evaluados').value,'1')
        self.assertIn('valor_real',frame.to_csv(index=False))
