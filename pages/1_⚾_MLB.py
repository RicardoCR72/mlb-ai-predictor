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

# Estilos CSS específicos de MLB con acentos Diamond Cyan y modo oscuro nocturno
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 85% 0%, rgba(0, 229, 255, 0.08), transparent 30rem),
            radial-gradient(circle at 15% 90%, rgba(0, 119, 182, 0.06), transparent 28rem),
            #060c18;
        color: #eef3f8;
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container {
        max-width: 1480px;
        padding-top: 1.15rem;
        padding-bottom: 2.5rem;
    }
    [data-testid="stSidebar"] {
        background: #08101e;
        border-right: 1px solid #1a273c;
    }
    .mlb-shell {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #1c2b42;
        border-radius: 13px;
        background: #0b1424;
        margin-bottom: .75rem;
    }
    .mlb-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .mlb-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #00e5ff;
        color: #040d1a;
        font-weight: 900;
        font-size: 1.15rem;
    }
    .mlb-accent { color: #00e5ff; }
    .mlb-status { color: #8295b3; font-size: .78rem; font-weight: 700; }
    .mlb-view-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: .9rem 0 1.25rem;
        padding: 1.15rem;
        border: 1px solid #1c2b42;
        border-radius: 14px;
        background: #0b1424;
    }
    .mlb-eyebrow {
        color: #00e5ff;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .12em;
    }
    .mlb-view-hero h1 {
        margin: .22rem 0 .15rem;
        color: #f5f8fb;
        font-size: clamp(1.75rem, 3vw, 2.45rem);
    }
    .mlb-subtitle { color: #8295b3; font-size: .88rem; }
    
    div[data-testid="stMetric"] {
        background: #0b1424;
        border: 1px solid #1c2b42;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8295b3; }
    div[data-testid="stMetricValue"] { color: #00e5ff; }

    /* Acento Cyan para radio activo */
    [data-testid="stRadio"] [role="radiogroup"] {
        background: #08101e !important;
        border: 1px solid #1c2b42 !important;
    }
    [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
        background: #00e5ff !important;
        color: #040d1a !important;
        font-weight: 850 !important;
    }

    /* Acentos Cyan para botones y controles */
    [data-testid="stButton"] button:hover {
        background: #00e5ff !important;
        color: #040d1a !important;
        border-color: #00e5ff !important;
    }
    [data-testid="stButton"] button[kind="primary"] {
        background: #00e5ff !important;
        color: #040d1a !important;
        border-color: #00e5ff !important;
    }

    /* Personalización de tarjetas Oracle Pick para MLB */
    .stApp .oracle-pick {
        background: #0b1424 !important;
        border: 1px solid #1c2b42 !important;
        border-top: 3px solid #00e5ff !important;
    }
    .stApp .oracle-bar i {
        background: #00e5ff !important;
    }
    .stApp .oracle-details summary {
        color: #00e5ff !important;
    }
    .stApp .oracle-odds {
        background: #132238 !important;
        color: #00e5ff !important;
        font-weight: 750;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Encabezado principal de la marca MLB
st.markdown(
    """
    <div class="mlb-shell">
        <div class="mlb-brand">
            <span class="mlb-logo">⚾</span>
            <div>
                <div>ORÁCULO <span class="mlb-accent">MLB AI</span></div>
                <div class="mlb-status">DraftKings Live Odds · Sabermetrics FIP/ERA & Bullpen · Base de Datos</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")

# Hero Banner descriptivo
st.markdown(
    f"""
    <div class="mlb-view-hero">
        <div>
            <div class="mlb-eyebrow">BÉISBOL DE GRANDES LIGAS · MLB ANALYTICS</div>
            <h1 style="margin:.25rem 0 .2rem;color:#f0f7ff;">Pronósticos y Métricas Sabermétricas</h1>
            <div class="mlb-subtitle">Modelado cuantitativo para líneas de Moneyline y Totales de Carreras (O/U).</div>
        </div>
        <div style="text-align:right;">
            <span style="background:#0e1d32;color:#00e5ff;padding:.3rem .75rem;border-radius:8px;font-size:.78rem;font-weight:800;border:1px solid #1c2b42;">
                🕒 {hora_actual_cdmx} CDMX
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Selector de navegación interna
view = st.radio(
    "Sección MLB",
    ["🔮 Picks de hoy (Moneyline)", "🎯 Totales de Carreras", "📈 Rendimiento Moneyline", "📊 Rendimiento Totales"],
    horizontal=True,
    label_visibility="collapsed",
    key="mlb_section_v2",
)

# Barra de acciones (actualizaciones y generación)
st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
col_act1, col_act2 = st.columns([1, 1], gap="medium")
with col_act1:
    render_update_button("mlb", compact=True)
with col_act2:
    render_generate_mlb()

st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

# Despliegue de contenido según la vista seleccionada
if view == "📈 Rendimiento Moneyline":
    render_history("MLB", "Moneyline", key="mlb_ml_perf")
elif view == "📊 Rendimiento Totales":
    render_history("MLB", "Totales", key="mlb_total_period")
elif view == "🎯 Totales de Carreras":
    render_mlb_today("Totales")
else:
    render_mlb_today("Moneyline")
