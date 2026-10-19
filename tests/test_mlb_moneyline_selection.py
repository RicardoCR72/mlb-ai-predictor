"""La selección Moneyline original llega a las tarjetas y exportaciones."""
from unittest import TestCase
from unittest.mock import Mock, patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.comparador import normalize
from core import confianza_datos as data


class MoneylineSelectionTests(TestCase):
    def fixture(self, result='PERDIDA'):
        return pd.DataFrame([dict(id_juego='g',fecha='2026-10-18',modelo='v',
            equipo_local='Los Angeles Dodgers',equipo_visitante='New York Yankees',
            pick_ia='New York Yankees',probabilidad=.6,cuota=1.9,resultado=result,
            start_utc='2026-10-18T20:00Z',quote_utc='2026-10-18T18:00Z',
            captured_utc='2026-10-18T18:01Z',publicada_utc='2026-10-18T19:00Z')])

    def test_stored_pick_survives_both_won_and_lost_results(self):
        for result in ('GANADA','PERDIDA'):
            frame=normalize(self.fixture(result),sport='MLB',market='Moneyline',identity=['id_juego'],verified=True)
            self.assertEqual(frame.seleccion.iloc[0],'New York Yankees')
            self.assertEqual(frame.resultado.iloc[0],result)
            self.assertIn('New York Yankees',frame.to_csv(index=False))

    def test_existing_selection_is_preserved_and_missing_selection_uses_saved_pick(self):
        raw=pd.concat([self.fixture().assign(id_juego=str(i),seleccion=value)
                       for i,value in enumerate(['Los Angeles Dodgers',None,''])],ignore_index=True)
        frame=normalize(raw,sport='MLB',market='Moneyline',identity=['id_juego'])
        self.assertEqual(frame.seleccion.tolist(),['Los Angeles Dodgers','New York Yankees','New York Yankees'])

    def test_original_history_and_card_show_chosen_team_for_lost_pick(self):
        empty=normalize(pd.DataFrame(),sport='MLB',market='Moneyline',identity=['id_juego'])
        def query(conn,sql):
            return self.fixture() if 'FROM mlb_publicaciones_moneyline' in sql else pd.DataFrame()
        with patch.object(data,'read_models',return_value=(empty,[])),patch.object(data,'rows',side_effect=query), \
             patch.object(data.registro,'history',return_value=pd.DataFrame()),patch.object(data,'nfl_starts',return_value={}):
            frame,_=data.read_history(Mock(),'.',include_liga=False)
        mlb=frame[frame.deporte.eq('MLB') & frame.mercado.eq('Moneyline')]
        self.assertEqual(mlb.seleccion.tolist(),['New York Yankees'])
        with patch('core.ui_historial_publicado.load_history',return_value=(mlb,[])):
            app=AppTest.from_string("from core.ui_historial_publicado import render_history\nrender_history('MLB','Moneyline',key='saved_team')").run()
        self.assertFalse(app.exception)
        cards=[m.value for m in app.markdown if '<div class="oracle-selection">' in m.value]
        self.assertEqual(len(cards),1)
        selection=cards[0].split('<div class="oracle-selection">',1)[1].split('</div>',1)[0]
        self.assertIn('New York Yankees',selection)
        self.assertNotIn('Selección guardada',selection)
        self.assertIn('Perdida',cards[0])
