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
from tests.test_analitica_bankroll import AnalyticsTests
from core.ui_bankroll import render_analytics,render_history
from core.ui_movil import apply_mobile_layout
from core.ui_filtros import performance_filters
from core.ui_picks import render_liga_matches
import pandas as pd
st.set_page_config(layout='wide')
apply_mobile_layout()
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
                    liga=page.locator('.oracle-pick').filter(has_text='Liga MX')
                    liga.nth(8).wait_for(timeout=30000)
                    assert liga.count()==9,liga.count()
                    controls=page.locator('[data-testid="stButton"] button,[data-testid="stDownloadButton"] button,[data-testid="stFormSubmitButton"] button,[data-testid="stPageLink"] a')
                    styles=controls.evaluate_all('(nodes)=>nodes.map(n=>{const s=getComputedStyle(n);return {border:s.borderTopColor,width:s.borderTopWidth,radius:s.borderTopLeftRadius,color:s.color}})')
                    assert len(styles)>=13,styles
                    assert all(s['border']=='rgb(183, 255, 60)' and s['width']=='1px' and s['radius']=='9px' and s['color']=='rgb(183, 255, 60)' for s in styles),styles
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    mobile=page.locator('.oracle-pick').evaluate_all('(cards)=>cards.map(c=>{const r=c.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,right:r.right}})')
                    assert all(c['x']>=0 and c['right']<=392 and c['w']>300 for c in mobile),mobile
                    assert mobile[1]['y']>mobile[0]['y'],mobile[:2]
                    page.set_viewport_size({'width':1280,'height':900})
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    page.wait_for_function("(()=>{const c=document.querySelectorAll('.oracle-pick');return c.length>1 && Math.abs(c[0].getBoundingClientRect().y-c[1].getBoundingClientRect().y)<2})()")
                    page.set_viewport_size({'width':390,'height':844})
                    page.get_by_text('Tabla',exact=True).click()
                    page.get_by_text('Columnas visibles',exact=True).wait_for()
                    page.wait_for_function('document.body.scrollWidth <= innerWidth+2')
                    assert page.locator('[data-testid="stDataFrame"]:visible').count()>=1
                    assert page.locator('[data-testid="stException"]').count()==0
                    browser.close()
                print('Responsive OK: una columna a 390 px, dos a 1280 px, tabla sin desbordamiento, nueve tarjetas Liga MX y botones/enlaces con contorno MLB.')
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)


if __name__=='__main__': main()
