"""Los detalles NFL se muestran por demanda; abrir controles no compra cuotas."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from tests.test_arquitectura import nfl_fixture


class CompactNFLTests(unittest.TestCase):
    def test_prediction_details_are_hidden_until_opened_and_cost_precedes_submission(self):
        plan=dict(fecha='2099-01-01',eventos=[],max_creditos=0,restantes=500,reserva=120)
        with patch('core.ui_nfl_creditos.consultar',return_value=plan) as preview, \
             patch('core.ui_trabajos.latest',return_value=None),patch('core.ui_trabajos.submit') as submit:
            app=AppTest.from_string('from core.ui_nfl_creditos import render_prediction_button\nrender_prediction_button()').run()
            self.assertFalse(app.exception)
            self.assertFalse(app.checkbox)
            self.assertFalse(app.caption)
            preview.assert_not_called();submit.assert_not_called()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.checkbox[0].label,'Todos los partidos de hoy')
            self.assertTrue(any('0 créditos' in c.value for c in app.caption))
            self.assertTrue(next(b for b in app.button if b.label=='Confirmar actualización').disabled)
            submit.assert_not_called()
            app.button[0].click().run()
            self.assertFalse(app.checkbox)

    def test_result_details_are_hidden_until_update_and_can_be_closed(self):
        with patch('core.ui_trabajos.latest',return_value=None) as latest, \
             patch('core.ui_trabajos.submit',return_value='fixture') as submit:
            app=AppTest.from_string('from core.ui_actualizacion import render_update_button\nrender_update_button("nfl_props")').run()
            self.assertFalse(app.exception)
            latest.assert_not_called()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            submit.assert_called_once()
            self.assertTrue(any(b.label=='Ocultar detalles' for b in app.button))
            next(b for b in app.button if b.label=='Ocultar detalles').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(any(b.label=='Ocultar detalles' for b in app.button))

    def test_totals_summary_keeps_only_picks(self):
        with patch('nfl.repositorio.cargar_predicciones_mysql',return_value=nfl_fixture()):
            app=AppTest.from_string('from nfl.ui_totales import render\nrender()').run()
        self.assertFalse(app.exception)
        labels=[m.label for m in app.metric]
        self.assertIn('Picks',labels)
        self.assertNotIn('Partidos',labels)
        self.assertNotIn('Con línea',labels)
