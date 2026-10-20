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

# Estilos CSS específicos de la NFL con acentos Turf Neon y Vegas Gold
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 85% 0%, rgba(183, 255, 60, 0.08), transparent 30rem),
            radial-gradient(circle at 15% 90%, rgba(255, 214, 0, 0.05), transparent 28rem),
            #07140e;
        color: #eef3f8;
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container {
        max-width: 1480px;
        padding-top: 1.15rem;
        padding-bottom: 2.5rem;
    }
    [data-testid="stSidebar"] {
        background: #091a13;
        border-right: 1px solid #1a382a;
    }
    .nfl-shell {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #1a382a;
        border-radius: 13px;
        background: #0d2118;
        margin-bottom: .75rem;
    }
    .nfl-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .nfl-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #b7ff3c;
        color: #071006;
        font-weight: 900;
        font-size: 1.15rem;
    }
    .nfl-accent { color: #b7ff3c; }
    .nfl-status { color: #8fa899; font-size: .78rem; font-weight: 700; }
    .nfl-view-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: .9rem 0 1.25rem;
        padding: 1.15rem;
        border: 1px solid #1a382a;
        border-radius: 14px;
        background: #0d2118;
    }
    .nfl-eyebrow {
        color: #b7ff3c;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .12em;
    }
    .nfl-view-hero h1 {
        margin: .22rem 0 .15rem;
        color: #f5f8fb;
        font-size: clamp(1.75rem, 3vw, 2.45rem);
    }
    .nfl-subtitle { color: #8fa899; font-size: .88rem; }
    
    div[data-testid="stMetric"] {
        background: #0d2118;
        border: 1px solid #1a382a;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8fa899; }
    div[data-testid="stMetricValue"] { color: #b7ff3c; }

    /* Acento Turf Neon para radio activo */
    [data-testid="stRadio"] [role="radiogroup"] {
        background: #091a13 !important;
        border: 1px solid #1a382a !important;
    }
    [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
        background: #b7ff3c !important;
        color: #071006 !important;
        font-weight: 850 !important;
    }

    /* Acentos Turf para botones y controles */
    [data-testid="stButton"] button:hover {
        background: #b7ff3c !important;
        color: #071006 !important;
        border-color: #b7ff3c !important;
    }
    [data-testid="stButton"] button[kind="primary"] {
        background: #b7ff3c !important;
        color: #071006 !important;
        border-color: #b7ff3c !important;
    }

    /* Personalización de tarjetas Oracle Pick para NFL */
    .stApp .oracle-pick {
        background: #0d2118 !important;
        border: 1px solid #1a382a !important;
        border-top: 3px solid #b7ff3c !important;
    }
    .stApp .oracle-bar i {
        background: #b7ff3c !important;
    }
    .stApp .oracle-details summary {
        color: #b7ff3c !important;
    }
    .stApp .oracle-odds {
        background: #152d21 !important;
        color: #b7ff3c !important;
        font-weight: 750;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Encabezado principal de la marca NFL
st.markdown(
    """
    <div class="nfl-shell">
        <div class="nfl-brand">
            <span class="nfl-logo">🏈</span>
            <div>
                <div>ORÁCULO <span class="nfl-accent">NFL AI</span></div>
                <div class="nfl-status">nflverse Data Pipeline · EPA/Play & Expected Yards Projections · Base de Datos</div>
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
    <div class="nfl-view-hero">
        <div>
            <div class="nfl-eyebrow">FÚTBOL AMERICANO PROFESIONAL · NFL AI</div>
            <h1 style="margin:.25rem 0 .2rem;color:#f0fdf4;">Totales & Props de Jugadores</h1>
            <div class="nfl-subtitle">Modelos cuantitativos de totales de puntos, valor esperado (EV) y props individuales.</div>
        </div>
        <div style="text-align:right;">
            <span style="background:#112a1f;color:#b7ff3c;padding:.3rem .75rem;border-radius:8px;font-size:.78rem;font-weight:800;border:1px solid #1a382a;">
                🕒 {hora_actual_cdmx} CDMX
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Selector de navegación interna
vista = st.radio(
    "Sección NFL",
    ["🏈 Totales de Partido", "📊 Props de Jugadores"],
    horizontal=True,
    label_visibility="collapsed",
    key="nfl_vista_principal_v2",
)

# Barra de acciones (actualizaciones y generación)
st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
col_act1, col_act2 = st.columns([1, 1], gap="medium")
with col_act1:
    render_update_button("nfl_totales" if "Totales" in vista else "nfl_props", compact=True)
with col_act2:
    render_prediction_button()

st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

# Renderizado de la sección correspondiente
if "Totales" in vista:
    from nfl.ui_totales import render
else:
    from nfl.ui_props import render
render()
