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
        background: linear-gradient(145deg, #0e2218, #07140e) !important;
        border: 1px solid #1a382a !important;
        border-radius: 12px !important;
        padding: .78rem .9rem !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
    }
    div[data-testid="stMetric"] label { color: #8fa899 !important; }
    div[data-testid="stMetricValue"] { color: #b7ff3c !important; font-weight: 850 !important; }

    /* Selector de navegación interna (radio activo en Verde Turf Neon sin círculos de radio) */
    .stApp [data-testid="stRadio"] [role="radiogroup"] {
        background: #091a13 !important;
        border: 1px solid #1a382a !important;
        border-radius: 10px !important;
        padding: 0.25rem !important;
        gap: 0.35rem !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label {
        border-radius: 8px !important;
        padding: 0.45rem 1.25rem !important;
        color: #8fa899 !important;
        font-weight: 600 !important;
        justify-content: center !important;
        text-align: center !important;
        transition: all 0.2s ease !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label div {
        justify-content: center !important;
    }
    /* Ocultar el círculo / radio indicator (para que sea una pestaña limpia tipo segmented control) */
    .stApp [data-testid="stRadio"] [role="radiogroup"] .etak9234,
    .stApp [data-testid="stRadio"] [role="radiogroup"] .etak9235,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label div:has(> [data-testid="stMarkdownContainer"]) > div:first-child,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label div:has(+ [data-testid="stMarkdownContainer"]),
    .stApp [data-testid="stRadio"] [role="radiogroup"] label [role="radio"] {
        display: none !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
        background: #b7ff3c !important;
        background-color: #b7ff3c !important;
        color: #071006 !important;
        font-weight: 850 !important;
        box-shadow: 0 0 14px rgba(183, 255, 60, 0.45) !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) p,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) span,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) div {
        color: #071006 !important;
        font-weight: 850 !important;
    }

    /* Botones de acción con bloque relleno Turf Neon */
    .stApp [data-testid="stButton"] button,
    .stApp [data-testid="stButton"] button[kind="primary"],
    .stApp [data-testid="stButton"] button[kind="secondary"],
    .stApp .st-key-nfl_predicciones_creditos button,
    .stApp [class*="st-key-actualizacion_manual_nfl"] button,
    div[data-testid="stButton"] > button {
        background: #b7ff3c !important;
        background-color: #b7ff3c !important;
        color: #071006 !important;
        border: 1px solid #b7ff3c !important;
        border-radius: 10px !important;
        font-weight: 850 !important;
        font-size: 0.95rem !important;
        height: 46px !important;
        min-height: 46px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 4px 14px rgba(183, 255, 60, 0.4) !important;
        transition: all 0.2s ease !important;
    }
    .stApp [data-testid="stButton"] button p,
    .stApp [data-testid="stButton"] button span,
    .stApp [data-testid="stButton"] button div,
    .stApp .st-key-nfl_predicciones_creditos button *,
    .stApp [class*="st-key-actualizacion_manual_nfl"] button * {
        color: #071006 !important;
        font-weight: 850 !important;
    }
    .stApp [data-testid="stButton"] button:hover,
    .stApp [data-testid="stButton"] button[kind="primary"]:hover,
    .stApp .st-key-nfl_predicciones_creditos button:hover,
    .stApp [class*="st-key-actualizacion_manual_nfl"] button:hover {
        background: #cbfd64 !important;
        background-color: #cbfd64 !important;
        border-color: #cbfd64 !important;
        color: #071006 !important;
        box-shadow: 0 6px 20px rgba(183, 255, 60, 0.6) !important;
        transform: translateY(-1px) !important;
    }
    .stApp [data-testid="stButton"] button:active {
        transform: translateY(0px) !important;
    }
    .stApp [data-testid="stButton"] button:disabled {
        background: #112217 !important;
        background-color: #112217 !important;
        border-color: #1a382a !important;
        color: #4f6859 !important;
        cursor: not-allowed !important;
        box-shadow: none !important;
        transform: none !important;
    }
    .stApp [data-testid="stButton"] button:disabled * {
        color: #4f6859 !important;
    }

    /* Tarjetas de Pronósticos y Rendimiento NFL (estilo NBA) */
    .stApp .oracle-pick,
    .stApp .oracle-pick.nfl-card {
        background: linear-gradient(145deg, #0e2218, #07140e) !important;
        border: 1px solid #1a382a !important;
        border-radius: 18px !important;
        padding: 1.5rem 1.6rem 1.8rem 1.6rem !important;
        margin-bottom: 1.5rem !important;
        box-shadow: 0 4px 22px rgba(0, 0, 0, 0.35) !important;
        transition: transform 0.15s ease, border-color 0.15s ease !important;
        box-sizing: border-box !important;
        color: #eef3f8 !important;
    }
    .stApp .oracle-pick:hover,
    .stApp .oracle-pick.nfl-card:hover {
        border-color: rgba(183, 255, 60, 0.5) !important;
        box-shadow: 0 6px 26px rgba(183, 255, 60, 0.12) !important;
    }

    .card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.8rem;
        color: #8fa899;
        margin-bottom: 0.85rem;
        border-bottom: 1px solid #1a382a;
        padding-bottom: 0.5rem;
    }
    .badge-time {
        background: #112a1f;
        color: #b7ff3c;
        border: 1px solid #1a382a;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
    }
    .badge-conf-alta {
        background: rgba(183, 255, 60, 0.18);
        color: #b7ff3c;
        border: 1px solid rgba(183, 255, 60, 0.55);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-weight: 800;
        font-size: 0.75rem;
    }
    .badge-conf-media {
        background: rgba(183, 255, 60, 0.10);
        color: #cbfd64;
        border: 1px solid rgba(183, 255, 60, 0.35);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.75rem;
    }
    .teams-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.85rem;
        padding-bottom: 0.85rem;
        border-bottom: 1px solid #1a382a;
    }
    .team-name {
        font-size: 1.25rem;
        font-weight: 800;
        color: #f5f8fb;
    }
    .team-abbr {
        color: #8fa899;
        font-size: 0.9rem;
        font-weight: 600;
    }

    .pick-box {
        background: linear-gradient(145deg, #0e261b, #081710) !important;
        border: 1px solid rgba(183, 255, 60, 0.45) !important;
        border-radius: 12px;
        padding: 0.85rem 1.15rem;
        margin-top: 1rem;
        margin-bottom: 0.6rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-sizing: border-box;
        box-shadow: 0 4px 18px rgba(183, 255, 60, 0.10) !important;
    }
    .pick-title {
        color: #b7ff3c;
        font-size: 0.72rem;
        font-weight: 850;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .pick-sel {
        color: #ffffff;
        font-size: 1.05rem;
        font-weight: 800;
    }
    .stat-pill {
        background: #0f291c;
        padding: 0.35rem 0.65rem;
        border-radius: 8px;
        font-size: 0.82rem;
        color: #b8d4c5;
        border: 1px solid #1a382a;
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
            <div class="nfl-eyebrow" style="color: #b7ff3c !important;">FÚTBOL AMERICANO PROFESIONAL · NFL AI</div>
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

# Selector de navegación interna (sin emojis)
vista = st.radio(
    "Sección NFL",
    ["Totales de Partido", "Props de Jugadores"],
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
