"""El historial permanece accesible aunque fallen las proyecciones operativas."""
import unittest
from unittest.mock import Mock, patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from tests.test_arquitectura import nfl_fixture
from nfl import repositorio


class PropsAvailabilityTests(unittest.TestCase):
    def test_performance_is_accessible_when_operational_query_fails_or_is_empty(self):
        for unavailable in (RuntimeError('fixture offline'), pd.DataFrame()):
            args={'side_effect':unavailable} if isinstance(unavailable,Exception) else {'return_value':unavailable}
            with self.subTest(unavailable=type(unavailable).__name__), \
                 patch('nfl.ui_props.cargar_props_mysql',**args) as read, \
                 patch('core.ui_historial_publicado.render_history') as history:
                app=AppTest.from_string('from nfl.ui_props import render\nrender()').run()
                self.assertFalse(app.exception)
                selector=next(r for r in app.radio if r.label=='Sección de props')
                self.assertIn('Rendimiento',selector.options)
                read.reset_mock()
                selector.set_value('📈 Rendimiento').run()
                self.assertFalse(app.exception)
                history.assert_called_once_with('NFL',None,key='nfl_prop_perf')
                read.assert_not_called()

    def test_repository_handles_settled_rows_with_missing_profit(self):
        frame=nfl_fixture(True)
        frame['beneficio_unidades']=float('nan')
        frame['resultado_pick']='GANADA'
        connection=Mock()
        connection.cursor.return_value.fetchall.return_value=frame.to_dict('records')
        repositorio.cargar_props_mysql.clear()
        try:
            with patch.object(repositorio,'get_db_connection',return_value=connection), \
                 patch('nfl.publicaciones_props.attach_publications',side_effect=lambda conn,rows:rows):
                result=repositorio.cargar_props_mysql(2099)
            self.assertAlmostEqual(result.beneficio_unidades.iloc[0],100/110)
            self.assertAlmostEqual(result.probabilidad_pick.iloc[0],.7)
            self.assertIn('WHERE j.temporada = %s',connection.cursor.return_value.execute.call_args.args[0])
        finally:repositorio.cargar_props_mysql.clear()

    def test_missing_profit_handles_every_result_and_null(self):
        for state,expected in [(' ganada ',100/110),('PERDIDA',-1),('PUSH',0)]:
            self.assertAlmostEqual(repositorio.calcular_beneficio_unidades(
                {'resultado_pick':state,'cuota_pick':-110}),expected)
        self.assertTrue(pd.isna(repositorio.calcular_beneficio_unidades({'resultado_pick':None})))
