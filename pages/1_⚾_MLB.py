"""Página interactiva del Oráculo AI para la MLB en Streamlit con interfaz distintiva Diamond Cyan."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="MLB Oráculo AI",
    page_icon="⚾",
    layout="wide",
)

from core.ui_diseno import apply_design
apply_design()

from core.ui_navegacion_movil import install_navigation
install_navigation()

from core.constants import ZONA_CDMX
from core.ui_actualizacion import render_update_button
from core.ui_historial_publicado import render_history
from core.ui_picks_guardados import render_mlb_today
from core.ui_trabajos import render_generate_mlb

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")

# Encabezado principal de la marca MLB
st.markdown(
    '<div class="mlb-shell">'
    '<div class="mlb-brand">'
    '<span class="mlb-logo">⚾</span>'
    '<div>'
    '<div>ORÁCULO <span class="mlb-accent">MLB AI</span></div>'
    '<div class="mlb-status">DraftKings Live Odds · Sabermetrics FIP/ERA & Bullpen · Base de Datos</div>'
    '</div>'
    '</div>'
    f'<div style="text-align:right;">'
    f'<span style="background:#0e1d32;color:#00e5ff;padding:.3rem .75rem;border-radius:8px;font-size:.78rem;font-weight:800;border:1px solid #1c2b42;">'
    f'🕒 {hora_actual_cdmx} CDMX'
    f'</span>'
    '</div>'
    '</div>',
    unsafe_allow_html=True
)

# Hero Banner descriptivo
st.markdown(
    '<div class="mlb-view-hero">'
    '<div>'
    '<div class="mlb-eyebrow">BÉISBOL DE GRANDES LIGAS · MLB ANALYTICS</div>'
    '<h1 style="margin:.25rem 0 .2rem;color:#f0f7ff;">Pronósticos y Métricas Sabermétricas</h1>'
    '<div class="mlb-subtitle">Modelado cuantitativo para líneas de Moneyline y Totales de Carreras (O/U).</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True
)

# Toolbar de acciones compacta en la parte superior
c_desc, c_btn1, c_btn2 = st.columns([2.5, 1, 1], gap="small")
with c_desc:
    st.caption("⚡ Actualización de cuotas DraftKings y liquidación oficial de partidos")
with c_btn1:
    render_update_button("mlb", compact=True)
with c_btn2:
    render_generate_mlb()

st.markdown("<div style='margin-bottom: 0.75rem;'></div>", unsafe_allow_html=True)

# Navegación estandarizada
seccion_guardada = st.session_state.get("mlb_section", "Picks de hoy")
idx_defecto = 1 if seccion_guardada == "Rendimiento" else 0

view = st.radio(
    "Sección MLB",
    ["Picks de hoy", "Rendimiento"],
    index=idx_defecto,
    horizontal=True,
    label_visibility="collapsed",
    key="mlb_section",
)

if view == "Rendimiento":
    col_sub1, col_sub2 = st.columns([1, 3])
    with col_sub1:
        mercado_hist = st.radio(
            "Mercado de rendimiento",
            ["Moneyline", "Totales"],
            horizontal=True,
            key="mlb_hist_market_sel",
        )
    render_history("MLB", mercado_hist, key=f"mlb_{mercado_hist.lower()}_perf")
else:
    col_sub1, col_sub2 = st.columns([1, 3])
    with col_sub1:
        mercado_hoy = st.radio(
            "Mercado",
            ["Moneyline", "Totales"],
            horizontal=True,
            key="mlb_today_market_sel",
        )
    render_mlb_today(mercado_hoy)
