"""Comprueba la presentación real a 390 y 1280 px con Chrome del runner, sin credenciales."""
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def main():
    chrome=shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
    if not chrome: raise RuntimeError('Falta Chrome en el runner de la prueba responsive.')
    with tempfile.TemporaryDirectory() as folder:
        app=Path(folder)/'app.py'
        app.write_text(f"import sys\nsys.path.insert(0,{str(ROOT)!r})\n"+'''
import streamlit as st
from core.ui_diseno import apply_design
from tests.test_analitica_bankroll import AnalyticsTests
from core.ui_bankroll_diseno import render_analytics,render_history
from core.ui_movil import apply_mobile_layout
from core.ui_filtros import performance_filters
from core.ui_tarjetas import render_liga_matches
import pandas as pd
import core.ui_comparador as comparator_ui
from core.comparador import normalize
from unittest.mock import patch
st.set_page_config(layout='wide')
apply_mobile_layout()
apply_design()
ledger=AnalyticsTests().ledger()
ledger['partido']='New England Patriots @ Jacksonville Jaguars'
render_analytics(ledger,1000)
ledger=performance_filters(ledger,'fecha','smoke',probability_col='probabilidad',probability_scale=100,result_col='estado')
render_history(ledger)
st.button('Actualizar resultados Liga MX')
st.download_button('Descargar muestra','prueba','prueba.txt')
with st.form('style_check'):
    st.form_submit_button('Guardar muestra')
st.page_link('https://github.com/RicardoCR72/mlb-ai-predictor',label='Ver proyecto')
render_liga_matches(pd.DataFrame([dict(fecha='2099-10-10',inicio_utc='2099-10-11T01:00:00Z',
 visitante=f'Visitante {i}',local=f'Local {i}',p_over25=.58,p_under25=.42) for i in range(9)]))
from core.ui_tarjetas import render_pick
render_pick(dict(fecha='2099-10-10',deporte='NFL',partido='Arizona Cardinals @ Seattle Seahawks',
 seleccion='OVER 45.5',casa='DraftKings',cuota=1.9,probabilidad=.61,cuota_capturada_utc='2026-10-10T20:30:00Z'),
 market='Total del partido',details=[('Proyección','48.5'),('EV estimado','5.1%')],allow_register=False)
import core.ui_nfl_creditos as paid_ui
paid_ui.consultar=lambda day: dict(fecha=day,eventos=[dict(id='demo',away_team='Arizona Cardinals',
 home_team='Seattle Seahawks',commence_time='2099-01-01T00:20:00Z')],max_creditos=6,restantes=500,reserva=120)
paid_ui.run_predictions=lambda root,plan: dict(ok=True,detalle='Predicciones de prueba actualizadas',
 reporte=dict(fecha=plan['fecha'],solicitados=1,creditos=6,restantes=494,insertadas=30))
paid_ui.render_prediction_button()
comparison_data=normalize(pd.DataFrame([dict(id=str(i),fecha='2026-10-01',modelo='v1',resultado=result,
 probabilidad=.6,cuota=1.9) for i,result in enumerate(['GANADA','PERDIDA','PUSH'])]),
 sport='MLB',market='Moneyline',identity=['id'])
comparator_ui.load_comparison=lambda:(comparison_data,[])
comparator_ui.render_comparison()
from core.ui_rendimiento_centro import render_center
with patch('core.ui_rendimiento_centro.load_comparison',return_value=(comparison_data,[])),patch('core.ui_rendimiento_centro.nfl_games',return_value=pd.DataFrame()):
    render_center()
from core.auditoria_nfl import render_receiving_audit
from tests.test_auditoria_nfl import AuditTests
audit_data=AuditTests().fixture()
render_receiving_audit(audit_data,audit_data)
from unittest.mock import patch
from tests.test_resumen import SummaryTests
from core.ui_inicio import render_home
real_page_link=st.page_link
home_data=SummaryTests().fixture()
home_data['services']['bankroll']['finance']=dict(saldo=10000,pendientes=0,disponible=10000)
home_data['services']['liga_mx']['games']=[dict(Fecha=f'2026-10-{6+i//2:02}',Horario='22:00 CDMX',
 Partido=f'Visitante de nombre largo {i} @ Equipo local {i}') for i in range(12)]
with patch('core.ui_resumen.snapshot',return_value=home_data),patch('streamlit.page_link',
    side_effect=lambda page,**kwargs:real_page_link('https://github.com/RicardoCR72/mlb-ai-predictor',**kwargs)):
    render_home()
from core.ui_rendimiento_resumen import history_window,render_performance_charts
with st.container(key='lean_history_smoke'):
    history=pd.DataFrame([dict(id=i,fecha='2099-10-10',estado='GANADA',profit=1) for i in range(25)])
    st.metric('Picks evaluados',len(history))
    render_performance_charts(history,date_col='fecha',profit_col='profit',result_col='estado')
    visible=history_window(history,'lean_smoke')
    st.caption(f'Vista resumida: {len(visible)} picks')
from core.ui_confianza import render as render_confidence
from tests.test_confianza import ConfidenceTests
with st.container(key='confidence_smoke'),patch('core.ui_confianza.load',return_value=(ConfidenceTests().fixture(30),[])):
    render_confidence()
''')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        with (Path(folder)/'server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(app),'--server.headless=true',
                f'--server.port={port}','--browser.gatherUsageStats=false'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            try:
                url=f'http://127.0.0.1:{port}'
                for attempt in range(100):
                    try:
                        with urlopen(url+'/_stcore/health',timeout=1) as response:
                            if response.status==200: break
                    except OSError: time.sleep(.2)
                else: raise RuntimeError('Streamlit no inició para la prueba responsive.')
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(executable_path=chrome,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
                    page=browser.new_page(viewport={'width':390,'height':844})
                    page.goto(url)
                    page.locator('.oracle-pick').first.wait_for(timeout=30000)
                    assert page.locator('[data-testid="stException"]').count()==0
                    paid_button=page.get_by_role('button',name='Actualizar predicciones NFL de hoy (hasta 6 créditos)',exact=True)
                    paid_button.wait_for(timeout=30000)
                    liga=page.locator('.oracle-pick').filter(has_text='Liga MX')
                    liga.nth(8).wait_for(timeout=30000)
                    assert liga.count()==9,liga.count()
                    visuals=page.locator('.st-key-center_visual_charts')
                    visuals.get_by_text('Cómo terminaron los picks',exact=True).wait_for()
                    visuals.get_by_text('ROI por mercado',exact=True).wait_for()
                    assert visuals.locator('[data-testid="stVegaLiteChart"]').count()==3
                    assert page.get_by_role('button',name='Descargar propuesta',exact=True).count()==0

                    controls=page.locator('[data-testid="stButton"] button,[data-testid="stDownloadButton"] button,[data-testid="stFormSubmitButton"] button,[data-testid="stPageLink"] a')
                    styles=controls.evaluate_all('(nodes)=>nodes.map(n=>{const s=getComputedStyle(n);return {border:s.borderTopColor,width:s.borderTopWidth,radius:s.borderTopLeftRadius,color:s.color}})')
                    assert len(styles)>=13,styles
                    assert all(s['border'] in ('rgb(69, 84, 106)','rgb(183, 255, 60)') and s['width']=='1px' and s['radius']=='9px' and s['color'] in ('rgb(198, 209, 223)','rgb(7, 16, 6)') for s in styles),styles
                    assert any(s['color']=='rgb(7, 16, 6)' for s in styles),styles
                    page.get_by_text('Auditoría de yardas de recepción',exact=True).click()
                    page.get_by_role('button',name='Descargar auditoría de yardas',exact=True).wait_for()
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    page.get_by_text('Tus deportes',exact=True).wait_for(timeout=30000)
                    preview=page.locator('.agenda-match:visible')
                    preview.first.wait_for(timeout=30000)
                    assert preview.count()==5
                    page.locator('.st-key-home_agenda_controls').get_by_text('10 partidos',exact=True).click()
                    page.get_by_text('10 de 12 partidos · próximos siete días.',exact=True).wait_for(timeout=30000)
                    assert preview.count()==10
                    page.locator('.st-key-home_agenda_controls').get_by_text('Todos',exact=True).click()
                    page.get_by_text('12 de 12 partidos · próximos siete días.',exact=True).wait_for(timeout=30000)
                    assert preview.count()==12
                    page.get_by_text('Ver calendario completo',exact=True).click()
                    page.locator('.st-key-home_calendar_full .agenda-day').first.wait_for()
                    assert page.locator('.st-key-home_calendar_full .agenda-match:visible').count()==12
                    page.get_by_text('Detalle de disponibilidad',exact=True).click()
                    page.locator('.availability-card').first.wait_for()
                    assert page.locator('.availability-card:visible').count()==5
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    assert page.get_by_text('Captura de cuota: Hora no disponible',exact=True).count()>=9
                    details=page.locator('.oracle-details').first
                    assert not details.evaluate('(e)=>e.open')
                    details.locator('summary').click()
                    assert details.evaluate('(e)=>e.open')
                    assert details.locator('.oracle-detail').count()>=1
                    details.locator('summary').click()
                    assert page.locator('[data-testid="stVegaLiteChart"]').count()>=2
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    mobile=page.locator('.oracle-pick').evaluate_all('(cards)=>cards.map(c=>{const r=c.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,right:r.right}})')
                    assert all(c['x']>=0 and c['right']<=392 and c['w']>300 for c in mobile),mobile
                    assert mobile[1]['y']>mobile[0]['y'],mobile[:2]
                    page.set_viewport_size({'width':1280,'height':900})
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    page.wait_for_function("(()=>{const c=document.querySelectorAll('.oracle-pick');return c.length>1 && Math.abs(c[0].getBoundingClientRect().y-c[1].getBoundingClientRect().y)<2})()")
                    first_cards=page.locator('.oracle-pick').evaluate_all('(nodes)=>nodes.slice(0,2).map(n=>n.getBoundingClientRect().height)')
                    assert abs(first_cards[0]-first_cards[1])<2,first_cards
                    # The cards follow the tallest content in each row; their links share a baseline.
                    for selector,number in [('.st-key-home_sports [class*="st-key-home_sport_"]',3),
                                            ('.st-key-home_performance_card',1)]:
                        cards=page.locator(selector)
                        assert cards.count()==number
                        page.wait_for_function("""(selector)=>{const cards=[...document.querySelectorAll(selector)];
                            const heights=cards.map(c=>c.getBoundingClientRect().height);
                            const links=cards.map(c=>c.querySelector('[data-testid="stPageLink"]').getBoundingClientRect().bottom);
                            return Math.max(...heights)-Math.min(...heights)<2 && Math.max(...links)-Math.min(...links)<2}
                            """,arg=selector)
                    assert page.locator('.st-key-home_bankroll_card').count()==0
                    assert page.get_by_role('button',name='Registrar en bankroll',exact=True).count()==0
                    assert 'Abrir Rendimiento' in page.locator('.st-key-home_performance_card').inner_text()
                    page.set_viewport_size({'width':390,'height':844})
                    page.get_by_text('Comparador de rendimiento',exact=True).wait_for()
                    assert page.get_by_text('Mínimo de picks con beneficio conocido',exact=True).count()==1
                    page.locator('[data-testid="stExpander"]').filter(has_text='Filtros de rendimiento').last.locator('summary').click()
                    page.get_by_text('Tabla',exact=True).click()
                    page.get_by_text('Columnas visibles',exact=True).wait_for()
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    assert page.locator('[data-testid="stDataFrame"]:visible').count()>=1
                    assert page.locator('[data-testid="stException"]').count()==0
                    paid_button.click()
                    page.get_by_text('Predicciones de prueba actualizadas · Consumo: 6 · Restantes: 494',exact=True).first.wait_for()
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    assert page.locator('[data-testid="stException"]').count()==0
                    lean=page.locator('.st-key-lean_history_smoke')
                    lean.get_by_text('Vista resumida: 10 picks',exact=True).wait_for()
                    assert lean.locator('[data-testid="stVegaLiteChart"]:visible').count()==1
                    lean.get_by_role('button',name='Ver 10 más',exact=True).click()
                    lean.get_by_text('Vista resumida: 20 picks',exact=True).wait_for()
                    assert lean.locator('[data-testid="stMetricValue"]').get_by_text('25',exact=True).count()==1
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    confidence=page.locator('.st-key-confidence_smoke')
                    confidence.get_by_text('Calibración de confianza',exact=True).wait_for()
                    confidence.get_by_role('button',name='Descargar diagnóstico por rangos',exact=True).wait_for()
                    confidence.get_by_text('Prueba temporal de recalibración',exact=True).click()
                    confidence.get_by_role('button',name='Descargar evaluación temporal',exact=True).wait_for()
                    assert page.locator('[data-testid="stException"]').count()==0
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    browser.close()
                print('Responsive OK: una columna a 390 px, dos a 1280 px, tabla sin desbordamiento, nueve tarjetas Liga MX y tarjetas alineadas y jerarquía visual de botones.')
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)


if __name__=='__main__': main()
