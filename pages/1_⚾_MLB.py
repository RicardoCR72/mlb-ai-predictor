"""Página interactiva del Oráculo AI para la MLB en Streamlit con diseño simétrico a NFL y paleta Diamond Cyan."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="MLB · OVERDOG AI",
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
    '<div>OVERDOG <span class="mlb-accent">MLB AI V5</span></div>'
    '<div class="mlb-status">Modo Offseason · Ensamble V5 (LightGBM + DNN) · Regresamos en Spring Training 2027</div>'
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

# Selector de sección MLB: Resumen Ejecutivo Offseason 2026 vs Rendimiento Histórico
seccion_guardada = st.session_state.get("mlb_section", "Picks de hoy")
idx_defecto = 1 if seccion_guardada == "Rendimiento" else 0

view = st.radio(
    "Sección MLB",
    ["Picks de hoy", "Rendimiento"],
    format_func=lambda x: "❄️ Resumen Ejecutivo Offseason 2026" if x == "Picks de hoy" else "📈 Auditoría y Rendimiento",
    index=idx_defecto,
    horizontal=True,
    label_visibility="collapsed",
    key="mlb_section",
)

if view == "Rendimiento":
    mercado = st.radio(
        "Mercado MLB",
        ["Moneyline (Ganador Directo)", "Totales de Carreras"],
        horizontal=True,
        label_visibility="collapsed",
        key="mlb_mercado_principal",
    )
    mercado_tipo = "Totales" if "Totales" in mercado else "Moneyline"
    render_history("MLB", mercado_tipo, key=f"mlb_{mercado_tipo.lower()}_perf")
else:
    render_mlb_today("Moneyline")
