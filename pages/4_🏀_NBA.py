"""Página interactiva del Oráculo AI para la NBA en Streamlit con módulo de Rendimiento y Base de Datos."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="NBA Oráculo AI",
    page_icon="🏀",
    layout="wide",
)

from core.ui_diseno import apply_design
apply_design()

from core.ui_navegacion_movil import install_navigation
install_navigation()

RAIZ = Path(__file__).resolve().parents[1]
RUTA_NBA = RAIZ / "nba"
RUTA_DATA_NBA = RAIZ / "data" / "nba"
RUTA_PREDICCIONES = RUTA_DATA_NBA / "predictions" / "predicciones_nba_hoy.json"

from nba.predecir_hoy import predecir_partidos_hoy
from nba.registro import cargar_historial_rendimiento, liquidar_partidos_pendientes_nba, guardar_predicciones_nba
from core.constants import ZONA_CDMX

# Estilos CSS específicos de la NBA con acentos neón y modo oscuro premium
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 85% 0%, rgba(255, 107, 0, 0.08), transparent 30rem),
            radial-gradient(circle at 15% 90%, rgba(255, 107, 0, 0.04), transparent 28rem),
            #080c13;
        color: #eef3f8;
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container {
        max-width: 1480px;
        padding-top: 1.15rem;
        padding-bottom: 2.5rem;
    }
    [data-testid="stSidebar"] {
        background: #0d131d;
        border-right: 1px solid #202938;
    }
    .nba-shell {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #332014;
        border-radius: 13px;
        background: #140e09;
        margin-bottom: .75rem;
    }
    .nba-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .nba-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #ff6b00;
        color: #ffffff;
        font-weight: 900;
        font-size: 1.1rem;
    }
    .nba-accent { color: #ff8c33; }
    .nba-status { color: #a4978e; font-size: .78rem; font-weight: 700; }
    .nba-view-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: .9rem 0 1.25rem;
        padding: 1.15rem;
        border: 1px solid #332014;
        border-radius: 14px;
        background: #140e09;
    }
    .nba-eyebrow {
        color: #ff8c33;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .12em;
    }
    .nba-view-hero h1 {
        margin: .22rem 0 .15rem;
        color: #f5f8fb;
        font-size: clamp(1.75rem, 3vw, 2.45rem);
    }
    .nba-subtitle { color: #a4978e; font-size: .88rem; }
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #17110c, #0f0a06) !important;
        border: 1px solid #352114 !important;
        border-radius: 12px !important;
        padding: .78rem .9rem !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
    }
    div[data-testid="stMetric"] label { color: #a4978e !important; }
    div[data-testid="stMetricValue"] { color: #ff8c33 !important; font-weight: 850 !important; }

    /* Selector de navegación interna (radio activo en naranja NBA sin círculos de radio) */
    .stApp [data-testid="stRadio"] [role="radiogroup"] {
        background: #0d131d !important;
        border: 1px solid #202938 !important;
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
        background: #ff6b00 !important;
        background-color: #ff6b00 !important;
        color: #ffffff !important;
        font-weight: 850 !important;
        box-shadow: 0 0 14px rgba(255, 107, 0, 0.45) !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) p,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) span,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) div {
        color: #ffffff !important;
        font-weight: 850 !important;
    }

    /* Botones de acción con bloque relleno naranja NBA (como en NFL/MLB pero en naranja) */
    .stApp [data-testid="stButton"] button,
    .stApp [data-testid="stButton"] button[kind="primary"],
    .stApp [data-testid="stButton"] button[kind="secondary"],
    .stApp .st-key-btn_act_res button,
    .stApp .st-key-btn_act_cuotas button,
    div[data-testid="stButton"] > button {
        background: #ff6b00 !important;
        background-color: #ff6b00 !important;
        color: #ffffff !important;
        border: 1px solid #ff6b00 !important;
        border-radius: 10px !important;
        font-weight: 850 !important;
        font-size: 0.95rem !important;
        height: 46px !important;
        min-height: 46px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 4px 14px rgba(255, 107, 0, 0.4) !important;
        transition: all 0.2s ease !important;
    }
    .stApp [data-testid="stButton"] button p,
    .stApp [data-testid="stButton"] button span,
    .stApp [data-testid="stButton"] button div,
    .stApp .st-key-btn_act_res button *,
    .stApp .st-key-btn_act_cuotas button * {
        color: #ffffff !important;
        font-weight: 850 !important;
    }
    .stApp [data-testid="stButton"] button:hover,
    .stApp [data-testid="stButton"] button[kind="primary"]:hover,
    .stApp .st-key-btn_act_res button:hover,
    .stApp .st-key-btn_act_cuotas button:hover {
        background: #ff851b !important;
        background-color: #ff851b !important;
        border-color: #ff851b !important;
        color: #ffffff !important;
        box-shadow: 0 6px 20px rgba(255, 107, 0, 0.6) !important;
        transform: translateY(-1px) !important;
    }
    .stApp [data-testid="stButton"] button:active,
    .stApp .st-key-btn_act_res button:active,
    .stApp .st-key-btn_act_cuotas button:active {
        transform: translateY(0px) !important;
    }
    .stApp [data-testid="stButton"] button:disabled,
    .stApp .st-key-btn_act_res button:disabled,
    .stApp .st-key-btn_act_cuotas button:disabled {
        background: #1e1610 !important;
        background-color: #1e1610 !important;
        border-color: #382518 !important;
        color: #7d6b5e !important;
        cursor: not-allowed !important;
        box-shadow: none !important;
        transform: none !important;
    }
    .stApp [data-testid="stButton"] button:disabled *,
    .stApp .st-key-btn_act_res button:disabled * {
        color: #7d6b5e !important;
    }

    /* Tarjeta contenedora única por partido con leve fondo naranja oscuro */
    [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 1.5rem 1.6rem 1.8rem 1.6rem !important;
        border: 1px solid #352114 !important;
        border-radius: 18px !important;
        background: linear-gradient(145deg, #17110c, #0e0906) !important;
        margin-bottom: 1.5rem !important;
        transition: transform 0.15s ease, border-color 0.15s ease !important;
        box-shadow: 0 4px 22px rgba(0, 0, 0, 0.3) !important;
        box-sizing: border-box !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: #55341f !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] > [data-testid="stVerticalBlock"] {
        border: none !important;
        background: transparent !important;
        padding-bottom: 0.5rem !important;
    }

    .card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.8rem;
        color: #a4978e;
        margin-bottom: 0.85rem;
        border-bottom: 1px solid #2a180e;
        padding-bottom: 0.5rem;
    }
    .badge-time {
        background: #23160e;
        color: #ff8c33;
        border: 1px solid #3d2415;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
    }
    .badge-conf-alta {
        background: rgba(255, 107, 0, 0.22);
        color: #ff8c33;
        border: 1px solid rgba(255, 107, 0, 0.6);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-weight: 800;
        font-size: 0.75rem;
    }
    .badge-conf-media {
        background: rgba(255, 140, 51, 0.14);
        color: #ffaa66;
        border: 1px solid rgba(255, 140, 51, 0.4);
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
        border-bottom: 1px solid #2a180e;
    }
    .team-name {
        font-size: 1.25rem;
        font-weight: 800;
        color: #f5f8fb;
    }
    .team-abbr {
        color: #a4978e;
        font-size: 0.9rem;
        font-weight: 600;
    }

    /* Barra de progreso de Probabilidad Ganador: fondo oscuro contrastante y relleno naranja NBA */
    div[data-testid="stProgress"] {
        --primary-color: #ff6b00 !important;
    }
    div[data-testid="stProgress"] div[data-testid="stProgressBarTrack"],
    div[data-testid="stProgressBarTrack"] {
        background-color: #1a120b !important;
        background: #1a120b !important;
        border-radius: 9999px !important;
        overflow: hidden !important;
        border: 1px solid #352114 !important;
    }
    div[data-testid="stProgress"] div[data-testid="stProgressBarTrack"] > div,
    div[data-testid="stProgressBarTrack"] > div,
    div.e1ed21rz1 {
        background-color: #ff6b00 !important;
        background: linear-gradient(90deg, #ff6b00, #ff8c33) !important;
        border-radius: 9999px !important;
    }

    .pick-box {
        background: linear-gradient(145deg, #24160c, #1a0f08) !important;
        border: 1px solid rgba(255, 140, 51, 0.55) !important;
        border-radius: 12px;
        padding: 0.85rem 1.15rem;
        margin-top: 1rem;
        margin-bottom: 0.6rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-sizing: border-box;
        box-shadow: 0 4px 18px rgba(255, 107, 0, 0.12) !important;
    }
    .pick-title {
        color: #ff8c33;
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
        background: #1b130c;
        padding: 0.35rem 0.65rem;
        border-radius: 8px;
        font-size: 0.82rem;
        color: #d8c6b8;
        border: 1px solid #352114;
    }
    </style>
    """,
    unsafe_allow_html=True
)


def cargar_predicciones(forzar: bool = False):
    """Carga las predicciones desde disco o ejecuta el pipeline si no existen o se solicita refresco."""
    if forzar or not RUTA_PREDICCIONES.exists():
        with st.spinner("Consultando DraftKings y ejecutando modelos de la NBA..."):
            preds = predecir_partidos_hoy(force_refresh=forzar)
            return preds
    try:
        with open(RUTA_PREDICCIONES, "r", encoding="utf-8") as f:
            preds = json.load(f)
            # Solo sincronizar con historial si hay picks pendientes por liquidar
            pendientes = [
                p for p in preds
                if p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"] and p.get("estado") != "STATUS_FINAL"
            ]
            if pendientes:
                try:
                    guardar_predicciones_nba(pendientes)
                except Exception:
                    pass
            return preds
    except Exception:
        return predecir_partidos_hoy(force_refresh=True)


# Encabezado principal
st.markdown(
    """
    <div class="nba-shell">
        <div class="nba-brand">
            <span class="nba-logo">🏀</span>
            <div>
                <div>ORÁCULO <span class="nba-accent">NBA AI</span></div>
                <div class="nba-status">DraftKings Odds · Four Factors Analytics · Sincronizado con Base de Datos</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")

# Selector de navegación interna (sin emojis y activo en verde)
vista = st.radio(
    "Sección NBA",
    ["Proyecciones de Hoy", "Rendimiento e Historial"],
    horizontal=True,
    label_visibility="collapsed",
    key="nba_vista_principal",
)

# Cargar estado de predicciones de hoy para determinar si los partidos ya fueron liquidados
predicciones_actuales = cargar_predicciones(forzar=False)
hay_pendientes_por_liquidar = any(
    p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"] and p.get("estado") != "STATUS_FINAL"
    for p in predicciones_actuales
)

# Barra de acciones (actualizar resultados y cuotas a la misma altura)
st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
col_act1, col_act2 = st.columns(2, gap="medium")
with col_act1:
    btn_deshabilitado = not hay_pendientes_por_liquidar
    lbl_btn_res = "Resultados Ya Registrados (Bloqueado)" if btn_deshabilitado else "Actualizar Resultados Hoy"
    help_btn_res = (
        "Los partidos ya fueron liquidados y registrados en Rendimiento e Historial. Acción bloqueada para evitar duplicados."
        if btn_deshabilitado else
        "Consulta marcadores finales de ESPN, liquida las apuestas de hoy y las pasa a Rendimiento e Historial."
    )
    if st.button(lbl_btn_res, key="btn_act_res", type="primary", disabled=btn_deshabilitado, use_container_width=True, help=help_btn_res):
        with st.spinner("Liquidando partidos y actualizando historial NBA..."):
            res = liquidar_partidos_pendientes_nba()
            if res.get("evaluados", 0) > 0:
                st.success(f"✅ {res['mensaje']}")
            else:
                st.info(f"ℹ️ {res['mensaje']}")
            st.rerun()

with col_act2:
    if st.button("Actualizar Cuotas", key="btn_act_cuotas", type="primary", use_container_width=True, help="Consulta las últimas líneas de DraftKings y actualiza las predicciones de hoy."):
        with st.spinner("Consultando DraftKings y ejecutando modelos..."):
            cargar_predicciones(forzar=True)
            st.success("✅ Cuotas y predicciones actualizadas desde DraftKings.")
            st.rerun()

st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

# ==========================================================
# VISTA 1: PROYECCIONES Y LÍNEAS DE HOY
# ==========================================================
if vista == "Proyecciones de Hoy":
    st.markdown(
        f"""
        <div class="nba-view-hero">
            <div>
                <div class="nba-eyebrow">BALONCESTO PROFESIONAL · ORÁCULO AI</div>
                <h1>Predicciones y Líneas NBA</h1>
                <div class="nba-subtitle">Modelos de Spread, Totales (Over/Under) y Moneyline sincronizados en base de datos. Hora CDMX: {hora_actual_cdmx}.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    predicciones = list(predicciones_actuales)

    if not predicciones:
        st.info("🏀 No hay partidos programados para hoy en la cartelera de la NBA. Puedes volver a consultar más tarde o forzar la actualización.")
        st.stop()

    # Partidos pendientes activos (los concluidos y liquidados pasan exclusivamente a Rendimiento e Historial)
    partidos_pendientes = [
        p for p in predicciones
        if p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"] and p.get("estado") != "STATUS_FINAL"
    ]
    partidos_liquidados = [
        p for p in predicciones
        if p.get("resultado") in ["GANADA", "PERDIDA", "PUSH"] or p.get("estado") == "STATUS_FINAL"
    ]

    total_partidos = len(predicciones)
    n_pendientes = len(partidos_pendientes)
    n_liquidados = len(partidos_liquidados)

    ganadas_hoy = sum(1 for p in predicciones if p.get("resultado") == "GANADA")
    perdidas_hoy = sum(1 for p in predicciones if p.get("resultado") == "PERDIDA")
    pushes_hoy = sum(1 for p in predicciones if p.get("resultado") == "PUSH")
    u_hoy = sum(float(p.get("unidades_ganadas") or 0.0) for p in predicciones if p.get("unidades_ganadas") is not None)

    # Tarjetas de métricas
    mcols = st.columns(4)
    mcols[0].metric("Partidos en Cartelera", f"{n_pendientes} pendientes")
    if n_liquidados > 0:
        mcols[1].metric("Picks Auditados", f"{n_liquidados} liquidados")
        mcols[2].metric("Balance Auditado", f"{u_hoy:+.2f} u", f"{ganadas_hoy}G - {perdidas_hoy}P" + (f" ({pushes_hoy} Push)" if pushes_hoy else ""))
        mcols[3].metric("Estado de Jornada", "Finalizada y Archivada")
    else:
        picks_altos = sum(1 for p in partidos_pendientes if p.get("confianza") == "ALTA")
        picks_totales = sum(1 for p in partidos_pendientes if "Totales" in p.get("pick_mercado", ""))
        picks_spread = sum(1 for p in partidos_pendientes if "Spread" in p.get("pick_mercado", ""))
        mcols[1].metric("Picks Alta Confianza", picks_altos)
        mcols[2].metric("Picks de Totales (O/U)", picks_totales)
        mcols[3].metric("Picks de Spread / ML", picks_spread + sum(1 for p in partidos_pendientes if "Moneyline" in p.get("pick_mercado", "")))

    # Si todos los partidos ya fueron liquidados, ocultar tarjetas de partidos y mostrar aviso hasta nuevo clic en Actualizar Cuotas
    if n_pendientes == 0:
        st.markdown(
            f"""
            <div style="background: linear-gradient(145deg, #18110b, #0f0a06); border: 1px solid #ff6b00; border-radius: 16px; padding: 2.2rem 2rem; text-align: center; margin-top: 1.2rem; margin-bottom: 2rem; box-shadow: 0 4px 25px rgba(255, 107, 0, 0.12);">
                <div style="font-size: 2.8rem; margin-bottom: 0.6rem;">🏀🏁</div>
                <div style="font-size: 1.35rem; font-weight: 900; color: #ff8c33; margin-bottom: 0.5rem;">
                    Partidos Concluidos y Auditados
                </div>
                <div style="color: #cbd5e1; font-size: 0.95rem; max-width: 620px; margin: 0 auto 1.2rem auto; line-height: 1.55;">
                    Los partidos de la cartelera anterior ({n_liquidados} juegos) ya finalizaron y han sido liquidados en la pestaña <b>Rendimiento e Historial</b> con sus marcadores oficiales.
                    <br><br>
                    No hay partidos pendientes por mostrar en esta sección. Para consultar y cargar la nueva cartelera de partidos y líneas de juego, haz clic en el botón superior <b>Actualizar Cuotas</b>.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.stop()

    # Controles de filtrado para partidos pendientes
    fcol1, fcol2, fcol3 = st.columns([2, 2, 2])
    with fcol1:
        filtro_mercado = st.selectbox(
            "Mercado del Pick",
            ["Todos los mercados", "Totales (Over/Under)", "Spread", "Moneyline"]
        )
    with fcol2:
        filtro_confianza = st.selectbox(
            "Nivel de Confianza",
            ["Todas las selecciones", "Solo ALTA confianza", "Solo MEDIA confianza"]
        )
    with fcol3:
        filtro_orden = st.selectbox(
            "Ordenar por",
            ["Hora (Más temprano primero)", "Confianza (ALTA primero)"]
        )

    # Aplicar filtros a los partidos pendientes
    filtrados = list(partidos_pendientes)

    if filtro_mercado == "Totales (Over/Under)":
        filtrados = [p for p in filtrados if "Totales" in p.get("pick_mercado", "")]
    elif filtro_mercado == "Spread":
        filtrados = [p for p in filtrados if "Spread" in p.get("pick_mercado", "")]
    elif filtro_mercado == "Moneyline":
        filtrados = [p for p in filtrados if "Moneyline" in p.get("pick_mercado", "")]

    if filtro_confianza == "Solo ALTA confianza":
        filtrados = [p for p in filtrados if p.get("confianza") == "ALTA"]
    elif filtro_confianza == "Solo MEDIA confianza":
        filtrados = [p for p in filtrados if p.get("confianza") == "MEDIA"]

    if filtro_orden == "Hora (Más temprano primero)":
        filtrados.sort(key=lambda x: x.get("hora_cdmx", ""))
    else:
        filtrados.sort(key=lambda x: 0 if x.get("confianza") == "ALTA" else 1)

    st.write("")
    st.subheader(f"Partidos Disponibles ({len(filtrados)})")

    # Render de tarjetas
    for p in filtrados:
        conf = p.get("confianza", "NEUTRAL")
        badge_conf = "badge-conf-alta" if conf == "ALTA" else "badge-conf-media"
        
        resultado_pick = p.get("resultado")
        u_gan = p.get("unidades_ganadas")
        m_loc = p.get("marcador_local")
        m_vis = p.get("marcador_visita")
        es_final = (p.get("estado") == "STATUS_FINAL") or (resultado_pick in ["GANADA", "PERDIDA", "PUSH"])

        # Badge de horario o estado final
        if es_final:
            badge_top_left = '<span class="badge-time" style="background: #2a180e; color: #ffaa66; border: 1px solid #ff6b00; font-weight: 800;">🏁 FINALIZADO</span><span style="margin-left: 0.6rem; color: #8e9bb0; font-size: 0.8rem;">Marcador Oficial ESPN</span>'
        else:
            badge_top_left = f'<span class="badge-time">⏰ {p.get("hora_cdmx", "TBD")} CDMX</span><span style="margin-left: 0.6rem;">{p.get("provider", "DraftKings")} Sportsbook</span>'

        # Badge de resultado o confianza
        if resultado_pick == "GANADA":
            val_u = f"+{u_gan:.2f}" if (u_gan is not None and u_gan > 0) else ("+0.91" if u_gan is None else f"{u_gan:.2f}")
            badge_top_right = f'<span style="background: rgba(34, 197, 94, 0.16); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.55); padding: 0.25rem 0.75rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem;">🏆 GANADA ({val_u} u)</span>'
        elif resultado_pick == "PERDIDA":
            badge_top_right = f'<span style="background: rgba(239, 68, 68, 0.16); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.55); padding: 0.25rem 0.75rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem;">❌ PERDIDA (-1.00 u)</span>'
        elif resultado_pick == "PUSH":
            badge_top_right = f'<span style="background: rgba(148, 163, 184, 0.16); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.55); padding: 0.25rem 0.75rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem;">🤝 PUSH (0.00 u)</span>'
        else:
            badge_top_right = f'<span class="{badge_conf}">CONFIANZA {conf}</span>'

        # Fila de equipos con o sin marcador final
        if es_final and m_vis is not None and m_loc is not None:
            teams_html = f"""
            <div class="teams-row">
                <div>
                    <div class="team-name">{p.get('equipo_visita')} <span style="color: #ff8c33; margin-left: 0.4rem; font-size: 1.4rem; font-weight: 900;">{int(m_vis)}</span></div>
                    <div class="team-abbr">Visitante ({p.get('abbr_visita')}) · ML: {p.get('ml_visita', 'N/D')}</div>
                </div>
                <div style="font-size: 1rem; color: #ff6b00; font-weight: 900; letter-spacing: 0.08em; background: #22140a; border: 1px solid #ff6b00; padding: 0.2rem 0.6rem; border-radius: 6px;">FINAL</div>
                <div style="text-align: right;">
                    <div class="team-name"><span style="color: #ff8c33; margin-right: 0.4rem; font-size: 1.4rem; font-weight: 900;">{int(m_loc)}</span> {p.get('equipo_local')}</div>
                    <div class="team-abbr">Local ({p.get('abbr_local')}) · ML: {p.get('ml_local', 'N/D')}</div>
                </div>
            </div>
            """
        else:
            teams_html = f"""
            <div class="teams-row">
                <div>
                    <div class="team-name">{p.get('equipo_visita')}</div>
                    <div class="team-abbr">Visitante ({p.get('abbr_visita')}) · ML: {p.get('ml_visita', 'N/D')}</div>
                </div>
                <div style="font-size: 1.1rem; color: #5a687d; font-weight: 800;">@</div>
                <div style="text-align: right;">
                    <div class="team-name">{p.get('equipo_local')}</div>
                    <div class="team-abbr">Local ({p.get('abbr_local')}) · ML: {p.get('ml_local', 'N/D')}</div>
                </div>
            </div>
            """

        with st.container(border=True):
            st.markdown(
                f"""
                <div class="card-top">
                    <div>
                        {badge_top_left}
                    </div>
                    <div>
                        {badge_top_right}
                    </div>
                </div>
                {teams_html}
                """,
                unsafe_allow_html=True
            )

            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                st.caption("🏀 **Probabilidad Ganador (Moneyline)**")
                p_vis = p.get("prob_visita_win", 0.5) * 100
                p_loc = p.get("prob_local_win", 0.5) * 100
                st.progress(int(p_loc), text=f"Local {p_loc:.1f}% vs Visita {p_vis:.1f}%")
                margen = p.get("margen_local_esperado", 0.0)
                signo = "+" if margen > 0 else ""
                st.markdown(f"<span class='stat-pill'>Margen modelo: <b>{signo}{margen:.1f} pts</b> local</span>", unsafe_allow_html=True)

            with col_c2:
                st.caption("🎯 **Totales (Over / Under)**")
                tot_proy = p.get("total_proyectado", 0.0)
                linea_tot = p.get("linea_total", 0.0)
                edge_tot = p.get("edge_puntos_total", 0.0)
                signo_edge = "+" if edge_tot > 0 else ""
                st.write(f"Línea Casa: **{linea_tot}** · Modelo: **{tot_proy:.1f} pts**")
                st.markdown(f"<span class='stat-pill'>Edge: <b>{signo_edge}{edge_tot:.1f} pts</b></span>", unsafe_allow_html=True)

            with col_c3:
                st.caption("⚖️ **Spread / Hándicap**")
                spread_det = p.get("spread_detalles", "N/D")
                prob_cov_loc = p.get("prob_cover_home", 0.5) * 100
                prob_cov_vis = p.get("prob_cover_away", 0.5) * 100
                st.write(f"Línea: **{spread_det}**")
                st.markdown(f"<span class='stat-pill'>Cubrir spread: Local {prob_cov_loc:.1f}% | Visita {prob_cov_vis:.1f}%</span>", unsafe_allow_html=True)

            # Caja de Recomendación Oficial con resultado si ya está liquidado
            if resultado_pick in ["GANADA", "PERDIDA", "PUSH"]:
                color_res = "#4ade80" if resultado_pick == "GANADA" else ("#f87171" if resultado_pick == "PERDIDA" else "#cbd5e1")
                val_u_box = f"+{u_gan:.2f}" if (u_gan is not None and u_gan > 0) else ("+0.91" if u_gan is None else f"{u_gan:.2f}")
                pick_res_html = f"""
                <div style="text-align: right;">
                    <div style="font-size: 0.72rem; color: #8e9bb0; font-weight: 700;">RESULTADO AUDITADO</div>
                    <div style="font-size: 1.15rem; font-weight: 900; color: {color_res};">{resultado_pick} ({val_u_box} u)</div>
                </div>
                """
            else:
                pick_res_html = f"""
                <div style="text-align: right;">
                    <div style="font-size: 0.72rem; color: #8e9bb0;">PROBABILIDAD MODELO</div>
                    <div style="font-size: 1.25rem; font-weight: 900; color: #ff8c33;">{p.get('pick_probabilidad', 0.0)*100:.1f}%</div>
                </div>
                """

            st.markdown(
                f"""
                <div class="pick-box">
                    <div>
                        <div class="pick-title">Recomendación Oficial del Oráculo AI ({p.get('pick_mercado')})</div>
                        <div class="pick-sel">{p.get('pick_seleccion')}</div>
                        <div style="font-size: 0.8rem; color: #8e9bb0; margin-top: 0.2rem;">{p.get('pick_detalle')}</div>
                    </div>
                    {pick_res_html}
                </div>
                """,
                unsafe_allow_html=True
            )

# ==========================================================
# VISTA 2: RENDIMIENTO Y AUDITORÍA DE RESULTADOS
# ==========================================================
else:
    st.markdown(
        """
        <div class="nba-view-hero">
            <div>
                <div class="nba-eyebrow">AUDITORÍA Y TRACK RECORD</div>
                <h1>Rendimiento Histórico NBA</h1>
                <div class="nba-subtitle">Historial de aciertos, simulación de unidades ganadas (+/- u) y retorno de inversión (ROI) con datos verificados.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    df_hist = cargar_historial_rendimiento()

    if df_hist.empty:
        st.info("No hay historial disponible aún.")
        st.stop()

    liquidados = df_hist[df_hist["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()

    # Asignación vectorial de Temporada NBA (Octubre año N a Junio año N+1)
    dt_serie = pd.to_datetime(liquidados["fecha"], errors="coerce")
    y_serie = dt_serie.dt.year
    m_serie = dt_serie.dt.month
    next_yy = ((y_serie + 1) % 100).astype(str).str.zfill(2)
    cur_yy = (y_serie % 100).astype(str).str.zfill(2)
    prev_y = (y_serie - 1).astype(str)
    liquidados["temporada"] = np.where(m_serie >= 10, y_serie.astype(str) + "-" + next_yy, prev_y + "-" + cur_yy)

    # Identificar temporadas ordenadas (la más reciente primero)
    temporadas_ordenadas = sorted(liquidados["temporada"].unique().tolist(), reverse=True)
    temp_actual = temporadas_ordenadas[0] if temporadas_ordenadas else "2026-27"

    # ==========================================================
    # FILA 1: FILTROS CRONOLÓGICOS Y DE PARTIDO (DATOS ACTUALES)
    # ==========================================================
    st.markdown("<div style='font-size: 0.82rem; font-weight: 800; color: #ff8c33; letter-spacing: 0.08em; margin-bottom: 0.35rem;'>FILTROS TEMPORALES Y DE PARTIDO</div>", unsafe_allow_html=True)
    tcol1, tcol2, tcol3 = st.columns(3)

    with tcol1:
        opciones_temp = ["Todas las temporadas"] + [
            f"{t} (Actual)" if t == temp_actual else t for t in temporadas_ordenadas
        ]
        sel_temp_label = st.selectbox("📅 Temporada", opciones_temp, index=0)
        sel_temp = sel_temp_label.replace(" (Actual)", "")

    # Filtrado intermedio para días disponibles según la temporada elegida
    df_para_dias = liquidados if sel_temp == "Todas las temporadas" else liquidados[liquidados["temporada"] == sel_temp]
    fechas_disp = sorted(df_para_dias["fecha"].dropna().unique().tolist(), reverse=True)

    with tcol2:
        opciones_dias = ["Todos los días"] + fechas_disp
        sel_dia = st.selectbox("📆 Día / Fecha", opciones_dias, index=0)

    # Filtrado intermedio para partidos disponibles según temporada y día
    df_para_juegos = df_para_dias if sel_dia == "Todos los días" else df_para_dias[df_para_dias["fecha"] == sel_dia]

    juegos_unicos_map = {}
    for _, row in df_para_juegos.sort_values("fecha", ascending=False).iterrows():
        id_partido = f"{row['fecha']}_{row['equipo_visitante']}_{row['equipo_local']}"
        if id_partido not in juegos_unicos_map:
            if sel_dia == "Todos los días":
                lbl_juego = f"{row['fecha']} · {row['equipo_visitante']} @ {row['equipo_local']}"
            else:
                lbl_juego = f"{row['equipo_visitante']} @ {row['equipo_local']}"
            juegos_unicos_map[id_partido] = lbl_juego

    with tcol3:
        opciones_juegos = ["Todos los juegos"] + list(juegos_unicos_map.values())
        sel_juego = st.selectbox("🏀 Juego / Partido", opciones_juegos, index=0)

    # ==========================================================
    # FILA 2: CRITERIOS DE AUDITORÍA Y APUESTA
    # ==========================================================
    st.markdown("<div style='font-size: 0.82rem; font-weight: 800; color: #ff8c33; letter-spacing: 0.08em; margin-top: 0.4rem; margin-bottom: 0.35rem;'>CRITERIOS DE AUDITORÍA</div>", unsafe_allow_html=True)
    rcol1, rcol2, rcol3 = st.columns(3)
    with rcol1:
        mercados_disp = ["Todos los mercados"] + sorted(list(liquidados["mercado"].unique()))
        sel_mercado = st.selectbox("Mercado para Auditoría", mercados_disp)
    with rcol2:
        confianzas_disp = ["Todas las confianzas", "Solo ALTA", "Solo MEDIA"]
        sel_conf = st.selectbox("Nivel de Confianza en Auditoría", confianzas_disp)
    with rcol3:
        sel_resultado = st.selectbox("Estado del Resultado", ["Todos los resultados", "Solo Ganadas", "Solo Perdidas", "Solo Pushes"])

    # Aplicar todos los filtros seleccionados
    f_liq = liquidados.copy()
    if sel_temp != "Todas las temporadas":
        f_liq = f_liq[f_liq["temporada"] == sel_temp]
    if sel_dia != "Todos los días":
        f_liq = f_liq[f_liq["fecha"] == sel_dia]
    if sel_juego != "Todos los juegos":
        for k_id, v_lbl in juegos_unicos_map.items():
            if v_lbl == sel_juego:
                parts = k_id.split("_", 2)
                f_liq = f_liq[
                    (f_liq["fecha"] == parts[0]) &
                    (f_liq["equipo_visitante"] == parts[1]) &
                    (f_liq["equipo_local"] == parts[2])
                ]
                break
    if sel_mercado != "Todos los mercados":
        f_liq = f_liq[f_liq["mercado"] == sel_mercado]
    if sel_conf == "Solo ALTA":
        f_liq = f_liq[f_liq["confianza"] == "ALTA"]
    elif sel_conf == "Solo MEDIA":
        f_liq = f_liq[f_liq["confianza"] == "MEDIA"]
    if sel_resultado == "Solo Ganadas":
        f_liq = f_liq[f_liq["resultado"] == "GANADA"]
    elif sel_resultado == "Solo Perdidas":
        f_liq = f_liq[f_liq["resultado"] == "PERDIDA"]
    elif sel_resultado == "Solo Pushes":
        f_liq = f_liq[f_liq["resultado"] == "PUSH"]

    if f_liq.empty:
        st.warning("⚠️ No se encontraron picks ni partidos liquidados para la combinación de filtros seleccionada.")
        st.stop()

    # Cálculo de métricas
    n_eval = len(f_liq)
    ganadas = int((f_liq["resultado"] == "GANADA").sum())
    perdidas = int((f_liq["resultado"] == "PERDIDA").sum())
    pushes = int((f_liq["resultado"] == "PUSH").sum())
    decididas = ganadas + perdidas
    acierto_pct = (ganadas / decididas * 100.0) if decididas else 0.0
    beneficio_u = float(f_liq["unidades_ganadas"].sum()) if n_eval else 0.0
    roi_pct = (beneficio_u / n_eval * 100.0) if n_eval else 0.0

    # Tarjetas de métricas
    rmcols = st.columns(4)
    rmcols[0].metric("Picks Evaluados", f"{n_eval:,}")
    rmcols[1].metric("Acierto", f"{acierto_pct:.1f}%", f"{ganadas}G - {perdidas}P" + (f" ({pushes} Push)" if pushes else ""))
    rmcols[2].metric("Unidades Netas", f"{beneficio_u:+.2f} u")
    rmcols[3].metric("ROI Simulado", f"{roi_pct:+.2f}%")

    # Banner informativo de filtros activos si hay alguno seleccionado
    filtros_activos_texto = []
    if sel_temp != "Todas las temporadas":
        filtros_activos_texto.append(f"Temporada: <b>{sel_temp}</b>")
    if sel_dia != "Todos los días":
        filtros_activos_texto.append(f"Día: <b>{sel_dia}</b>")
    if sel_juego != "Todos los juegos":
        filtros_activos_texto.append(f"Juego: <b>{sel_juego}</b>")
    if sel_mercado != "Todos los mercados":
        filtros_activos_texto.append(f"Mercado: <b>{sel_mercado}</b>")
    if sel_conf != "Todas las confianzas":
        filtros_activos_texto.append(f"Confianza: <b>{sel_conf}</b>")
    if sel_resultado != "Todos los resultados":
        filtros_activos_texto.append(f"Estado: <b>{sel_resultado}</b>")

    if filtros_activos_texto:
        st.markdown(
            f"""
            <div style="background: rgba(255, 107, 0, 0.09); border: 1px solid rgba(255, 107, 0, 0.35); border-radius: 8px; padding: 0.5rem 0.9rem; margin-top: 0.75rem; margin-bottom: 0.75rem; font-size: 0.85rem; color: #ffaa66;">
                🔍 <b>Filtros activos:</b> {' · '.join(filtros_activos_texto)} &nbsp;|&nbsp; <b>{n_eval}</b> pick(s) liquidados
            </div>
            """,
            unsafe_allow_html=True
        )

    st.write("")
    
    # Gráfica de evolución acumulada en el tiempo (si hay más de 1 fecha o pick)
    if len(f_liq) > 1 and f_liq["fecha"].nunique() > 1:
        st.subheader("📈 Evolución de Unidades en el Tiempo (Simulación 1 u por pick)")
        f_liq_chart = f_liq.copy()
        f_liq_chart["fecha_dt"] = pd.to_datetime(f_liq_chart["fecha"])
        evolucion = f_liq_chart.sort_values("fecha_dt").copy()
        evolucion["Unidades Acumuladas"] = evolucion["unidades_ganadas"].cumsum()
        
        chart_data = evolucion.set_index("fecha_dt")["Unidades Acumuladas"]
        st.line_chart(chart_data, use_container_width=True)

    # Desglose por mercado
    with st.expander("📊 Desglose Detallado por Mercado"):
        agrupado = []
        for m, g in f_liq.groupby("mercado"):
            g_dec = g[g["resultado"].isin(["GANADA", "PERDIDA"])]
            g_ganadas = (g["resultado"] == "GANADA").sum()
            g_perdidas = (g["resultado"] == "PERDIDA").sum()
            g_acierto = (g_ganadas / len(g_dec) * 100.0) if len(g_dec) else 0.0
            g_beneficio = g["unidades_ganadas"].sum()
            g_roi = (g_beneficio / len(g) * 100.0) if len(g) else 0.0
            agrupado.append({
                "Mercado": m,
                "Picks": len(g),
                "Ganadas": int(g_ganadas),
                "Perdidas": int(g_perdidas),
                "Acierto (%)": round(g_acierto, 1),
                "Unidades": round(g_beneficio, 2),
                "ROI (%)": round(g_roi, 1),
            })
        st.dataframe(pd.DataFrame(agrupado), hide_index=True, use_container_width=True)

    # ==========================================================
    # SECCIÓN: PARTIDOS LIQUIDADOS (TARJETAS VISUALES)
    # ==========================================================
    st.write("")
    
    partidos_grupos = []
    for (f_val, ev_val, el_val), g_df in f_liq.sort_values(["fecha", "hora_cdmx"], ascending=[False, False]).groupby(
        ["fecha", "equipo_visitante", "equipo_local"], sort=False
    ):
        h_cdmx = g_df["hora_cdmx"].iloc[0] if "hora_cdmx" in g_df.columns else "TBD"
        mv = g_df["marcador_visitante"].iloc[0] if "marcador_visitante" in g_df.columns else None
        ml = g_df["marcador_local"].iloc[0] if "marcador_local" in g_df.columns else None
        temp_val = g_df["temporada"].iloc[0] if "temporada" in g_df.columns else ""
        partidos_grupos.append({
            "fecha": f_val,
            "hora_cdmx": h_cdmx,
            "temporada": temp_val,
            "equipo_visitante": ev_val,
            "equipo_local": el_val,
            "marcador_visitante": mv,
            "marcador_local": ml,
            "picks": g_df.to_dict(orient="records"),
            "unidades_totales": float(g_df["unidades_ganadas"].sum())
        })

    total_partidos = len(partidos_grupos)
    st.subheader(f"🏀 Partidos Liquidados ({total_partidos} partido{'s' if total_partidos != 1 else ''} · {n_eval} pick{'s' if n_eval != 1 else ''})")

    # Mostrar tarjetas para los partidos (hasta 20 directamente para fluidez visual)
    max_tarjetas = 20
    partidos_a_mostrar = partidos_grupos[:max_tarjetas]

    for p_partido in partidos_a_mostrar:
        mv = p_partido["marcador_visitante"]
        ml = p_partido["marcador_local"]
        mv_str = str(int(mv)) if pd.notna(mv) else "-"
        ml_str = str(int(ml)) if pd.notna(ml) else "-"
        u_partido = p_partido["unidades_totales"]
        color_bal = "#4ade80" if u_partido > 0 else ("#f87171" if u_partido < 0 else "#cbd5e1")

        with st.container(border=True):
            st.markdown(
                f"""
                <div class="card-top">
                    <div>
                        <span class="badge-time" style="background: #2a180e; color: #ffaa66; border: 1px solid #ff6b00; font-weight: 800;">🏁 PARTIDO LIQUIDADO</span>
                        <span style="margin-left: 0.6rem; color: #8e9bb0; font-size: 0.8rem;">📅 {p_partido['fecha']} · ⏰ {p_partido['hora_cdmx']} CDMX (Temporada {p_partido['temporada']})</span>
                    </div>
                    <div>
                        <span style="font-size: 0.78rem; color: #8e9bb0; font-weight: 700; margin-right: 0.4rem;">BALANCE JUEGO:</span>
                        <span style="font-weight: 900; font-size: 1rem; color: {color_bal};">{u_partido:+.2f} u</span>
                    </div>
                </div>
                <div class="teams-row">
                    <div>
                        <div class="team-name">{p_partido['equipo_visitante']} <span style="color: #ff8c33; margin-left: 0.4rem; font-size: 1.4rem; font-weight: 900;">{mv_str}</span></div>
                        <div class="team-abbr">Visitante</div>
                    </div>
                    <div style="font-size: 1rem; color: #ff6b00; font-weight: 900; letter-spacing: 0.08em; background: #22140a; border: 1px solid #ff6b00; padding: 0.2rem 0.6rem; border-radius: 6px;">FINAL</div>
                    <div style="text-align: right;">
                        <div class="team-name"><span style="color: #ff8c33; margin-right: 0.4rem; font-size: 1.4rem; font-weight: 900;">{ml_str}</span> {p_partido['equipo_local']}</div>
                        <div class="team-abbr">Local</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # Mostrar los picks liquidados dentro de este partido
            for p in p_partido["picks"]:
                resultado_pick = p.get("resultado")
                u_gan = p.get("unidades_ganadas")
                color_res = "#4ade80" if resultado_pick == "GANADA" else ("#f87171" if resultado_pick == "PERDIDA" else "#cbd5e1")
                val_u_box = f"+{u_gan:.2f}" if (u_gan is not None and u_gan > 0) else ("+0.91" if u_gan is None else f"{u_gan:.2f}")

                linea_info = f" · Línea: <b>{p.get('linea')}</b>" if (pd.notna(p.get("linea")) and p.get("linea") != 0.0) else ""

                st.markdown(
                    f"""
                    <div class="pick-box" style="margin-bottom: 0.5rem;">
                        <div>
                            <div class="pick-title">Recomendación Auditada ({p.get('mercado')}) · Confianza {p.get('confianza', 'MEDIA')}</div>
                            <div class="pick-sel">{p.get('seleccion')}</div>
                            <div style="font-size: 0.8rem; color: #8e9bb0; margin-top: 0.2rem;">
                                Cuota: <b>{p.get('cuota', 1.91):.2f}</b> · Prob. Modelo: <b>{float(p.get('probabilidad', 0.5))*100:.1f}%</b>{linea_info}
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 0.72rem; color: #8e9bb0; font-weight: 700;">RESULTADO AUDITADO</div>
                            <div style="font-size: 1.15rem; font-weight: 900; color: {color_res};">{resultado_pick} ({val_u_box} u)</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    if total_partidos > max_tarjetas:
        st.info(f"ℹ️ Mostrando las tarjetas de los {max_tarjetas} partidos más recientes de {total_partidos}. Utiliza los filtros de Temporada o Día arriba para aislar cualquier fecha específica, o consulta la tabla completa a continuación.")

    # ==========================================================
    # TABLA COMPLETA DE AUDITORÍA
    # ==========================================================
    st.write("")
    st.subheader(f"📋 Registro Completo de Auditoría ({len(f_liq)} registros)")

    df_tabla = f_liq.sort_values(["fecha", "hora_cdmx"], ascending=[False, False]).copy()
    df_tabla["Partido"] = df_tabla["equipo_visitante"] + " @ " + df_tabla["equipo_local"]
    df_tabla["Marcador Final"] = df_tabla.apply(
        lambda r: f"{int(r['marcador_visitante'])} - {int(r['marcador_local'])}"
        if pd.notna(r.get("marcador_visitante")) and pd.notna(r.get("marcador_local"))
        else "N/D",
        axis=1
    )
    df_tabla["Cuota"] = df_tabla["cuota"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    df_tabla["Probabilidad"] = df_tabla["probabilidad"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
    df_tabla["Unidades Netas"] = df_tabla["unidades_ganadas"].apply(
        lambda x: f"+{x:.2f} u" if (pd.notna(x) and x > 0) else (f"{x:.2f} u" if pd.notna(x) else "0.00 u")
    )

    columnas_mostrar = [
        "temporada", "fecha", "hora_cdmx", "Partido", "Marcador Final",
        "mercado", "seleccion", "Cuota", "Probabilidad", "confianza", "resultado", "Unidades Netas"
    ]
    renombres = {
        "temporada": "Temporada",
        "fecha": "Fecha",
        "hora_cdmx": "Hora CDMX",
        "mercado": "Mercado",
        "seleccion": "Selección",
        "confianza": "Confianza",
        "resultado": "Resultado",
    }
    st.dataframe(
        df_tabla[columnas_mostrar].rename(columns=renombres),
        use_container_width=True,
        hide_index=True
    )
