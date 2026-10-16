from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import ast
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.comparador import normalize
from core.ui_rendimiento_centro import weekly_summary

ROOT=Path(__file__).resolve().parents[1]


class PerformanceCenterTests(TestCase):
    def frame(self):
        return normalize(pd.DataFrame([dict(id=str(i),fecha='2026-10-01',modelo='v1',resultado=result,
            probabilidad=p,cuota=1.9) for i,(result,p) in enumerate([('GANADA',.6),('PERDIDA',.8),('PUSH',.7)])]),
            sport='MLB',market='Moneyline',identity=['id'])

    def test_center_filters_drive_metrics_graphs_and_download_sample(self):
        f=self.frame()
        with patch('core.ui_rendimiento_centro.load_comparison',return_value=(f,[])), \
             patch('core.ui_rendimiento_centro.nfl_games',return_value=pd.DataFrame()):
            app=AppTest.from_string('from core.ui_rendimiento_centro import render_center\nrender_center()').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value,'3')
            self.assertEqual(app.metric[2].value,'-0.10 u')
            self.assertTrue(any(e.value=='Unidades acumuladas' for e in app.subheader))
            next(s for s in app.slider if s.label=='Confianza mínima (%)').set_value(75).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value,'1')
            self.assertEqual(app.metric[2].value,'-1.00 u')
            table=next(d.value for d in app.dataframe if 'identidad' in d.value)
            self.assertEqual(table.identidad.tolist(),['1'])
            next(s for s in app.selectbox if s.label=='Resultado').select('GANADA').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('No hay registros para estos filtros' in m.value for m in app.markdown))

    def test_center_other_views_use_saved_data_and_do_not_require_bankroll(self):
        f=self.frame()
        from tests.test_auditoria_nfl import AuditTests
        history=AuditTests().fixture();history['modelo_version']='v1';history['gameday']=pd.Timestamp('2026-10-01')
        history['actualizado_en']=pd.Timestamp('2026-10-01')
        with patch('core.ui_comparador.load_comparison',return_value=(f,[])), \
             patch('core.ui_rendimiento_centro.load_comparison',return_value=(f,[])), \
             patch('core.ui_rendimiento_centro.nfl_games',return_value=pd.DataFrame()), \
             patch('core.ui_rendimiento_centro.audit_history',return_value=history):
            app=AppTest.from_string('from core.ui_rendimiento_centro import render_center\nrender_center()').run()
            app.radio(key='center_view').set_value('Comparación').run();self.assertFalse(app.exception)
            self.assertTrue(any('Picks evaluados' in d.value for d in app.dataframe))
            app.radio(key='center_view').set_value('Auditoría NFL').run();self.assertFalse(app.exception)
            self.assertTrue(any(e.label=='Auditoría de yardas de recepción' for e in app.expander))
            app.radio(key='center_view').set_value('Validación Liga MX').run();self.assertFalse(app.exception)
            self.assertTrue(any('Brier' in d.value for d in app.dataframe))

    def test_weekly_uses_official_nfl_week_and_keeps_unknown_profit_missing(self):
        f=self.frame();f['deporte']='NFL';f['modelo_visible']='v1';f['semana_nfl']='2026 · NFL 05'
        f['unidades']=float('nan')
        stats=weekly_summary(f)
        self.assertEqual(stats.Semana.tolist(),['2026 · NFL 05'])
        self.assertEqual(stats.Muestra_ROI.iloc[0],0)
        self.assertTrue(pd.isna(stats.Unidades.iloc[0]))
        self.assertTrue(pd.isna(stats['ROI (%)'].iloc[0]))

    def test_sport_views_share_confidence_slider_and_no_advanced_panels(self):
        blocked={'Balance y equivalencia en pesos','Comparar mercados','Análisis por mercado y semana',
                 'Explorar umbrales históricos','Auditoría de yardas de recepción','Partidos pendientes de datos o revisión'}
        for name in ['nfl/ui_props.py','nfl/ui_totales.py','mlb_totales/ui_totales_mlb.py','pages/1_⚾_MLB.py','pages/3_⚽_Liga_MX.py']:
            source=(ROOT/name).read_text();tree=ast.parse(source)
            labels=[n.args[0].value for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                    and n.func.attr=='expander' and n.args and isinstance(n.args[0],ast.Constant)]
            self.assertFalse(blocked.intersection(labels),name)
            calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='performance_filters']
            self.assertTrue(calls,name)
            self.assertTrue(all(any(k.arg=='probability_col' for k in n.keywords) for n in calls),name)
        self.assertFalse((ROOT/'pages/0_💼_Bankroll.py').exists())
        self.assertFalse((ROOT/'pages/4_📊_Comparador.py').exists())
        self.assertTrue((ROOT/'pages/4_📊_Rendimiento.py').exists())

    def test_empty_sources_remain_usable(self):
        with patch('core.ui_rendimiento_centro.load_comparison',return_value=(self.frame().iloc[:0],['offline'])):
            app=AppTest.from_string('from core.ui_rendimiento_centro import render_center\nrender_center()').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Aún no hay picks guardados' in m.value for m in app.markdown))
