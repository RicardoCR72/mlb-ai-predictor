from datetime import date
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.contexto_confianza import context,text
from core.confianza import VERIFIED
from core.comparacion_periodos import compare_periods,pool
from core.comparador import normalize


class UsageTests(TestCase):
    def history(self):
        return pd.DataFrame([dict(fecha=date(2026,10,1),deporte='NFL',mercado='Recepciones',modelo='v1',procedencia=VERIFIED,
            probabilidad=.75,y=i%2,evento=f'g{i//4}',identidad=f'g{i//4}|p{i}|receptions',apto_ajuste=True) for i in range(200)])

    def pick(self):
        return dict(fecha='2026-10-10',deporte='NFL',modelo='v1',mercado_confianza='receptions',probabilidad=.75,
            origen='nfl_prop',referencia={'game_id':'current'})

    def test_context_excludes_future_other_versions_unverified_and_current_game(self):
        f=self.history();extra=f.copy();extra['fecha']=date(2026,10,10)
        unknown=f.copy();unknown['procedencia']='Guardado · hora no verificable'
        other=f.copy();other['modelo']='v2'
        result=context(self.pick(),pd.concat([f,extra,unknown,other],ignore_index=True))
        self.assertEqual(result['n'],200);self.assertEqual(result['games'],50)
        self.assertEqual(result['rate'],.5);self.assertEqual(result['status'],'disponible')
        self.assertIn('50.0%',text(result))
        p=self.pick();p['referencia']['game_id']='g0'
        self.assertEqual(context(p,f)['n'],196)
        self.assertEqual(self.pick()['probabilidad'],.75)

    def test_insufficient_context_never_presents_empirical_rate_as_probability(self):
        result=context(self.pick(),self.history().iloc[:20])
        self.assertEqual(result['status'],'insuficiente');self.assertIn('Muestra insuficiente',text(result))
        self.assertNotIn('% de acierto',text(result))
        self.assertEqual(context({**self.pick(),'probabilidad':75},self.history())['n'],0)
        f=self.history();f['apto_ajuste']=False
        self.assertEqual(context(self.pick(),f)['n'],0)

    def test_mlb_conditional_context_preserves_published_probability(self):
        f=self.history();f['deporte']='MLB';f['mercado']='Totales';f['probabilidad']=.65
        p={**self.pick(),'deporte':'MLB','mercado_confianza':'Totales','origen':'mlb_total','probabilidad':.54,'p_push':.1}
        result=context(p,f)
        self.assertEqual(result['band'],'60–70%');self.assertTrue(result['conditional'])
        self.assertEqual(p['probabilidad'],.54)

    def test_windows_do_not_overlap_and_missing_prior_is_not_zero_return(self):
        rows=[dict(id=str(i),fecha=day,modelo='v1',resultado=result,probabilidad=.7,cuota=1.9) for i,(day,result) in enumerate(
            [('2026-10-01','GANADA'),('2026-10-07','PERDIDA'),('2026-10-08','GANADA'),('2026-10-14','GANADA'),('2026-10-15','PERDIDA')])]
        f=normalize(pd.DataFrame(rows),sport='NFL',market='Recepciones',identity=['id'])
        result,limits=compare_periods(f,date(2026,10,14),7)
        self.assertEqual(limits['start'],date(2026,10,8));self.assertEqual(limits['previous_end'],date(2026,10,7))
        self.assertEqual(result['Picks evaluados · actual'].iloc[0],2)
        self.assertAlmostEqual(result['ROI (%) · actual'].iloc[0],90)
        self.assertAlmostEqual(result['Cambio ROI (pp)'].iloc[0],95)
        missing,_=compare_periods(f.iloc[2:4],date(2026,10,14),7)
        self.assertTrue(pd.isna(missing['Cambio ROI (pp)'].iloc[0]))
        self.assertTrue(pd.isna(missing['ROI (%) · anterior'].iloc[0]))
        self.assertEqual(len(pool(f,{'period':'Hoy','confidence':60})),5)

    def test_update_status_survives_rerun_and_interrupted_state_is_not_forever_running(self):
        result=dict(busy=False,steps=[dict(paso='Resultados',ok=True,detalle='2 resultados')],at='2026-10-10T00:00Z')
        job=dict(id='demo',estado='completada',creado_utc='2026-10-10 00:00:00',iniciado_utc=None,terminado_utc='2026-10-10 00:00:01',resultado=result)
        with patch('core.ui_trabajos.latest',return_value=job),patch('core.ui_trabajos.invalidate_readers'):
            app=AppTest.from_string("from core.ui_actualizacion import render_update_button\nrender_update_button('mlb')").run()
            app.run();self.assertFalse(app.exception)
            captions=' '.join(c.value for c in app.caption)
            self.assertIn('completada',captions);self.assertIn('CDMX',captions)
        app=AppTest.from_string('''
import streamlit as st
from core.ui_estado_actualizacion import save_status,render_status
if 'interrupted_status' not in st.session_state:save_status('interrupted','running','En proceso')
render_status('interrupted',previous=True)
''').run()
        self.assertFalse(app.exception)
        self.assertIn('Estado por confirmar',' '.join(m.value for m in app.markdown))

    def test_mobile_anchor_is_installed_once_per_page(self):
        root=Path(__file__).resolve().parents[1]
        for p in [root/'dashboard.py',*sorted((root/'pages').glob('*.py'))]:
            source=p.read_text(encoding='utf-8', errors='replace')
            self.assertEqual(source.count('install_navigation()'),1,str(p))

    def test_period_comparison_chart_renders_when_both_periods_have_results(self):
        source='''
from datetime import date
import pandas as pd
import streamlit as st
from core.comparador import normalize
from core.comparacion_periodos import render
st.session_state['period_compare_end']=date(2026,10,14)
f=normalize(pd.DataFrame([dict(id='a',fecha='2026-10-07',modelo='v1',resultado='PERDIDA',probabilidad=.7,cuota=1.9),
 dict(id='b',fecha='2026-10-14',modelo='v1',resultado='GANADA',probabilidad=.7,cuota=1.9)]),
 sport='NFL',market='Recepciones',identity=['id'])
f['modelo_visible']='Props NFL · V1'
render(f)
'''
        app=AppTest.from_string(source,default_timeout=10).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value['Modelo'].iloc[0],'Props NFL · V1')
        self.assertAlmostEqual(app.dataframe[0].value['Cambio ROI (pp)'].iloc[0],190)
