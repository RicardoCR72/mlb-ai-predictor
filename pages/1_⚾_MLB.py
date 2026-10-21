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
        background: linear-gradient(145deg, #0b1524, #060c18) !important;
        border: 1px solid #16263d !important;
        border-radius: 12px !important;
        padding: .78rem .9rem !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
    }
    div[data-testid="stMetric"] label { color: #8295b3 !important; }
    div[data-testid="stMetricValue"] { color: #00e5ff !important; font-weight: 850 !important; }

    /* Selector de navegación interna (radio activo en Cyan sin círculos de radio) */
    .stApp [data-testid="stRadio"] [role="radiogroup"] {
        background: #08101e !important;
        border: 1px solid #1c2b42 !important;
        border-radius: 10px !important;
        padding: 0.25rem !important;
        gap: 0.35rem !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label {
        border-radius: 8px !important;
        padding: 0.45rem 1.25rem !important;
        color: #8295b3 !important;
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
        background: #00e5ff !important;
        background-color: #00e5ff !important;
        color: #040d1a !important;
        font-weight: 850 !important;
        box-shadow: 0 0 14px rgba(0, 229, 255, 0.45) !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) p,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) span,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) div {
        color: #040d1a !important;
        font-weight: 850 !important;
    }

    /* Botones de acción con bloque relleno Diamond Cyan */
    .stApp [data-testid="stButton"] button,
    .stApp [data-testid="stButton"] button[kind="primary"],
    .stApp [data-testid="stButton"] button[kind="secondary"],
    .stApp .st-key-mlb_generate button,
    .stApp [class*="st-key-actualizacion_manual_"] button,
    div[data-testid="stButton"] > button {
        background: #00e5ff !important;
        background-color: #00e5ff !important;
        color: #040d1a !important;
        border: 1px solid #00e5ff !important;
        border-radius: 10px !important;
        font-weight: 850 !important;
        font-size: 0.95rem !important;
        height: 46px !important;
        min-height: 46px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 4px 14px rgba(0, 229, 255, 0.4) !important;
        transition: all 0.2s ease !important;
    }
    .stApp [data-testid="stButton"] button p,
    .stApp [data-testid="stButton"] button span,
    .stApp [data-testid="stButton"] button div,
    .stApp .st-key-mlb_generate button *,
    .stApp [class*="st-key-actualizacion_manual_"] button * {
        color: #040d1a !important;
        font-weight: 850 !important;
    }
    .stApp [data-testid="stButton"] button:hover,
    .stApp [data-testid="stButton"] button[kind="primary"]:hover,
    .stApp .st-key-mlb_generate button:hover,
    .stApp [class*="st-key-actualizacion_manual_"] button:hover {
        background: #33ebff !important;
        background-color: #33ebff !important;
        border-color: #33ebff !important;
        color: #040d1a !important;
        box-shadow: 0 6px 20px rgba(0, 229, 255, 0.6) !important;
        transform: translateY(-1px) !important;
    }
    .stApp [data-testid="stButton"] button:active {
        transform: translateY(0px) !important;
    }
    .stApp [data-testid="stButton"] button:disabled {
        background: #0d1a29 !important;
        background-color: #0d1a29 !important;
        border-color: #172a44 !important;
        color: #4a6282 !important;
        cursor: not-allowed !important;
        box-shadow: none !important;
        transform: none !important;
    }
    .stApp [data-testid="stButton"] button:disabled * {
        color: #4a6282 !important;
    }

    /* Tarjetas de Pronósticos y Rendimiento MLB (estilo NBA) */
    .stApp .oracle-pick,
    .stApp .oracle-pick.mlb-card {
        background: linear-gradient(145deg, #0b1524, #060c18) !important;
        border: 1px solid #16263d !important;
        border-radius: 18px !important;
        padding: 1.5rem 1.6rem 1.8rem 1.6rem !important;
        margin-bottom: 1.5rem !important;
        box-shadow: 0 4px 22px rgba(0, 0, 0, 0.35) !important;
        transition: transform 0.15s ease, border-color 0.15s ease !important;
        box-sizing: border-box !important;
        color: #eef3f8 !important;
    }
    .stApp .oracle-pick:hover,
    .stApp .oracle-pick.mlb-card:hover {
        border-color: rgba(0, 229, 255, 0.5) !important;
        box-shadow: 0 6px 26px rgba(0, 229, 255, 0.12) !important;
    }

    .card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.8rem;
        color: #8295b3;
        margin-bottom: 0.85rem;
        border-bottom: 1px solid #16263d;
        padding-bottom: 0.5rem;
    }
    .badge-time {
        background: #091728;
        color: #00e5ff;
        border: 1px solid #15324d;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
    }
    .badge-conf-alta {
        background: rgba(0, 229, 255, 0.18);
        color: #00e5ff;
        border: 1px solid rgba(0, 229, 255, 0.55);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-weight: 800;
        font-size: 0.75rem;
    }
    .badge-conf-media {
        background: rgba(0, 229, 255, 0.10);
        color: #38bdf8;
        border: 1px solid rgba(0, 229, 255, 0.35);
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
        border-bottom: 1px solid #16263d;
    }
    .team-name {
        font-size: 1.25rem;
        font-weight: 800;
        color: #f5f8fb;
    }
    .team-abbr {
        color: #8295b3;
        font-size: 0.9rem;
        font-weight: 600;
    }

    .pick-box {
        background: linear-gradient(145deg, #0a1728, #060e1a) !important;
        border: 1px solid rgba(0, 229, 255, 0.45) !important;
        border-radius: 12px;
        padding: 0.85rem 1.15rem;
        margin-top: 1rem;
        margin-bottom: 0.6rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-sizing: border-box;
        box-shadow: 0 4px 18px rgba(0, 229, 255, 0.10) !important;
    }
    .pick-title {
        color: #00e5ff;
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
        background: #091728;
        padding: 0.35rem 0.65rem;
        border-radius: 8px;
        font-size: 0.82rem;
        color: #9ab4d6;
        border: 1px solid #15324d;
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
            <div class="mlb-eyebrow" style="color: #00e5ff !important;">BÉISBOL DE GRANDES LIGAS · MLB ANALYTICS</div>
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

# Selector de navegación interna (sin emojis)
view = st.radio(
    "Sección MLB",
    ["Picks de hoy (Moneyline)", "Totales de Carreras", "Rendimiento Moneyline", "Rendimiento Totales"],
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
if view == "Rendimiento Moneyline":
    render_history("MLB", "Moneyline", key="mlb_ml_perf")
elif view == "Rendimiento Totales":
    render_history("MLB", "Totales", key="mlb_total_period")
elif view == "Totales de Carreras":
    render_mlb_today("Totales")
else:
    render_mlb_today("Moneyline")
