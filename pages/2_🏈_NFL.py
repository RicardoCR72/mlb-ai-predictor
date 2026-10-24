"""Página interactiva del Oráculo AI para la NFL en Streamlit con interfaz distintiva Gridiron Turf Neon."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import streamlit as st

st.set_page_config(
    page_title="NFL Oráculo AI",
    page_icon="🏈",
    layout="wide",
)

from core.ui_diseno import apply_design
apply_design()

from core.ui_navegacion_movil import install_navigation
install_navigation()

from core.constants import ZONA_CDMX
from core.ui_actualizacion import render_update_button
from core.ui_nfl_creditos import render_prediction_button

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")

# Encabezado principal de la marca NFL
st.markdown(
    '<div class="nfl-shell">'
    '<div class="nfl-brand">'
    '<span class="nfl-logo">🏈</span>'
    '<div>'
    '<div>ORÁCULO <span class="nfl-accent">NFL AI</span></div>'
    '<div class="nfl-status">nflverse Data Pipeline · EPA/Play & Expected Yards Projections · Base de Datos</div>'
    '</div>'
    '</div>'
    f'<div style="text-align:right;">'
    f'<span style="background:#112a1f;color:#b7ff3c;padding:.3rem .75rem;border-radius:8px;font-size:.78rem;font-weight:800;border:1px solid #1a382a;">'
    f'🕒 {hora_actual_cdmx} CDMX'
    f'</span>'
    '</div>'
    '</div>',
    unsafe_allow_html=True
)

# Hero Banner descriptivo
st.markdown(
    '<div class="nfl-view-hero">'
    '<div>'
    '<div class="nfl-eyebrow">FÚTBOL AMERICANO PROFESIONAL · NFL AI</div>'
    '<h1 style="margin:.25rem 0 .2rem;color:#f0fdf4;">Moneylines, Totales & Props</h1>'
    '<div class="nfl-subtitle">Modelos cuantitativos de ganador directo (Moneyline), totales de puntos y props individuales con cuotas DraftKings.</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True
)

# Selector de navegación interna compatible con suite de pruebas y responsive
vista = st.radio(
    "Sección NFL",
    ["Totales de Partido", "Moneyline (Ganador Directo)", "📊 Props de jugadores"],
    horizontal=True,
    label_visibility="collapsed",
    key="nfl_vista_principal",
)

if vista == "Moneyline (Ganador Directo)":
    from nfl.ui_moneyline import render
    render()
elif "Totales" in vista:
    # Toolbar de acciones con ancho suficiente para evitar truncamiento
    col_btn1, col_btn2, col_info = st.columns([1.2, 1.2, 1.6], gap="small")
    with col_btn1:
        render_update_button("nfl_totales", compact=True)
    with col_btn2:
        render_prediction_button()
    with col_info:
        st.caption("⚡ Sincronización oficial de líneas de totales DraftKings.")
    st.markdown("<div style='margin-bottom: 0.65rem;'></div>", unsafe_allow_html=True)

    from nfl.ui_totales import render
    render()
else:
    # Toolbar de acciones con ancho suficiente para evitar truncamiento
    col_btn1, col_btn2, col_info = st.columns([1.2, 1.2, 1.6], gap="small")
    with col_btn1:
        render_update_button("nfl_props", compact=True)
    with col_btn2:
        render_prediction_button()
    with col_info:
        st.caption("⚡ Proyecciones individuales de props y análisis de lesiones.")
    st.markdown("<div style='margin-bottom: 0.65rem;'></div>", unsafe_allow_html=True)

    from nfl.ui_props import render
    render()
