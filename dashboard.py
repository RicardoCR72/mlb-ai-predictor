import streamlit as st
from pathlib import Path

st.set_page_config(page_title='Oráculo Sports AI', page_icon='◉', layout='wide', initial_sidebar_state='expanded')
from core.ui_navegacion_movil import install_navigation
install_navigation()
from core.ui_diseno import apply_design
apply_design()

hero_html = '''<div class="home-hero-card">
  <div class="home-hero-header">
    <div>
      <div style="display:flex; align-items:center; gap:0.55rem; margin-bottom:0.35rem;">
        <span class="home-live-badge"><span class="home-pulse-dot"></span> SISTEMA EN VIVO</span>
        <span style="font-size:0.75rem; color:#64748b; font-weight:800; letter-spacing:0.12em;">ORÁCULO SPORTS AI</span>
      </div>
      <div class="home-hero-title">Tu día deportivo</div>
      <div class="home-hero-sub">Panel unificado de inteligencia probabilística y valor matemático para apuestas deportivas.</div>
    </div>
    <div style="display:flex; gap:0.45rem; flex-wrap:wrap; align-items:center;">
      <span class="home-sport-pill" style="color:#00e5ff; border-color:rgba(0,229,255,0.3); background:rgba(0,229,255,0.08);">⚾ MLB</span>
      <span class="home-sport-pill" style="color:#b7ff3c; border-color:rgba(183,255,60,0.3); background:rgba(183,255,60,0.08);">🏈 NFL</span>
      <span class="home-sport-pill" style="color:#00e676; border-color:rgba(0,230,118,0.3); background:rgba(0,230,118,0.08);">⚽ Fútbol</span>
      <span class="home-sport-pill" style="color:#ff6b35; border-color:rgba(255,107,53,0.3); background:rgba(255,107,53,0.08);">🏀 NBA</span>
    </div>
  </div>
</div>'''
st.markdown(hero_html, unsafe_allow_html=True)

from core.ui_inicio import render_home
render_home()
with st.sidebar:
    from core.ui_boleta import render_widget_boleta
    render_widget_boleta(sidebar=True)
    st.caption('MLB, NFL, Fútbol (8 Ligas), NBA y Rendimiento')

