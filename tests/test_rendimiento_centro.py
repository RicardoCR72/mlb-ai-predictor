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


class ClearChartsTests(TestCase):
    def frame(self):
        return pd.DataFrame(dict(fecha=['2026-10-01']*6,
            resultado=['GANADA','PERDIDA','PUSH','GANADA','PENDIENTE','ANULADA'],
            unidades=[.9,-1,0,float('nan'),99,99],mercado=['A']*6))

    def test_donut_counts_results_while_roi_requires_known_profit(self):
        from core.ui_graficas_claras import visual_data
        f=self.frame()
        data=visual_data(f,date_col='fecha',profit_col='unidades',result_col='resultado',group_cols=['mercado'])
        self.assertEqual(data['total'],4)
        self.assertEqual(data['distribution'].Picks.tolist(),[2,1,1])
        self.assertAlmostEqual(data['distribution'].Porcentaje.sum(),1)
        self.assertEqual(data['roi'].Muestra.iloc[0],3)
        self.assertAlmostEqual(data['roi']['ROI (%)'].iloc[0],-100/30)
        self.assertAlmostEqual(data['curve']['Unidades acumuladas'].iloc[-1],-.1)
        self.assertTrue((data['distribution'].Picks>=0).all())

    def test_no_date_still_counts_in_roi_and_sources_are_not_merged(self):
        from core.ui_graficas_claras import visual_data
        f=self.frame().iloc[:2].copy();f['modelo']=['v1','v2'];f.loc[0,'fecha']='invalid'
        data=visual_data(f,date_col='fecha',profit_col='unidades',result_col='resultado',group_cols=['mercado','modelo'])
        self.assertEqual(data['missing'],1)
        self.assertEqual(len(data['roi']),2)
        self.assertEqual(data['roi'].Muestra.sum(),2)
        self.assertEqual(data['curve']['Unidades acumuladas'].tolist(),[-1])

    def test_weekly_roi_weights_by_stakes_not_mean_of_percentages(self):
        from core.ui_graficas_claras import weekly_roi
        week=pd.DataFrame(dict(Semana=['2026 · NFL 05']*3,Muestra_ROI=[10,100,0],Unidades=[5,10,float('nan')]))
        table=weekly_roi(week)
        self.assertEqual(table['Picks con beneficio'].iloc[0],110)
        self.assertAlmostEqual(table['ROI (%)'].iloc[0],1500/110)
        week['Muestra_ROI']=0;week['Unidades']=float('nan')
        self.assertTrue(pd.isna(weekly_roi(week)['ROI (%)'].iloc[0]))

    def test_empty_visuals_and_removed_combined_page(self):
        from core.ui_graficas_claras import visual_data
        data=visual_data(self.frame().iloc[:0],date_col='fecha',profit_col='unidades',result_col='resultado')
        self.assertEqual(data['total'],0)
        self.assertTrue(data['roi'].empty)
        self.assertFalse((ROOT/'pages/5_🎯_Combinadas.py').exists())
