"""Página interactiva del Oráculo AI para la Liga MX en Streamlit con interfaz distintiva Emerald Pitch & Aztec Gold."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(
    page_title="Liga MX Oráculo AI",
    page_icon="⚽",
    layout="wide",
)

from core.ui_diseno import apply_design
apply_design()

from core.ui_navegacion_movil import install_navigation
install_navigation()

from core.constants import ZONA_CDMX

RAIZ = Path(__file__).resolve().parents[1]
RUTA_FUTBOL = RAIZ / "futbol_liga_mx"
RUTA_DATA = RUTA_FUTBOL / "data"
RUTA_PREDICCIONES = RUTA_DATA / "predicciones_ligamx_hoy.json"

from futbol_liga_mx.predecir_jornada import predecir_jornada_ligamx
from futbol_liga_mx.registro import (
    cargar_historial_rendimiento_ligamx,
    liquidar_partidos_pendientes_ligamx,
    guardar_predicciones_ligamx
)

# Estilos CSS específicos de la Liga MX con acentos Emerald Pitch y Mexican Gold
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 85% 0%, rgba(0, 230, 118, 0.08), transparent 30rem),
            radial-gradient(circle at 15% 90%, rgba(245, 158, 11, 0.06), transparent 28rem),
            #06140d;
        color: #eef3f8;
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container {
        max-width: 1480px;
        padding-top: 1.15rem;
        padding-bottom: 2.5rem;
    }
    [data-testid="stSidebar"] {
        background: #091710;
        border-right: 1px solid #143523;
    }
    .ligamx-shell {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #143523;
        border-radius: 13px;
        background: #0b1f15;
        margin-bottom: .75rem;
    }
    .ligamx-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .ligamx-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #00e676;
        color: #04150b;
        font-weight: 900;
        font-size: 1.15rem;
    }
    .ligamx-accent { color: #00e676; }
    .ligamx-gold { color: #f59e0b; }
    .ligamx-status { color: #8ba797; font-size: .78rem; font-weight: 700; }
    .ligamx-view-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: .9rem 0 1.25rem;
        padding: 1.15rem;
        border: 1px solid #143523;
        border-radius: 14px;
        background: #0b1f15;
    }
    .ligamx-eyebrow {
        color: #00e676;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .12em;
    }
    .ligamx-view-hero h1 {
        margin: .22rem 0 .15rem;
        color: #f5f8fb;
        font-size: clamp(1.75rem, 3vw, 2.45rem);
    }
    .ligamx-subtitle { color: #8ba797; font-size: .88rem; }
    
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #0b1f15, #06140d) !important;
        border: 1px solid #143523 !important;
        border-radius: 12px !important;
        padding: .78rem .9rem !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
    }
    div[data-testid="stMetric"] label { color: #8ba797 !important; }
    div[data-testid="stMetricValue"] { color: #00e676 !important; font-weight: 850 !important; }

    /* Selector de navegación interna */
    .stApp [data-testid="stRadio"] [role="radiogroup"] {
        background: #091710 !important;
        border: 1px solid #143523 !important;
        border-radius: 10px !important;
        padding: 0.25rem !important;
        gap: 0.35rem !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label {
        border-radius: 8px !important;
        padding: 0.45rem 1.25rem !important;
        color: #8ba797 !important;
        font-weight: 600 !important;
        justify-content: center !important;
        text-align: center !important;
        transition: all 0.2s ease !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label div {
        justify-content: center !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] .etak9234,
    .stApp [data-testid="stRadio"] [role="radiogroup"] .etak9235,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label div:has(> [data-testid="stMarkdownContainer"]) > div:first-child,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label div:has(+ [data-testid="stMarkdownContainer"]),
    .stApp [data-testid="stRadio"] [role="radiogroup"] label [role="radio"] {
        display: none !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
        background: #00e676 !important;
        background-color: #00e676 !important;
        color: #04150b !important;
        font-weight: 850 !important;
        box-shadow: 0 0 14px rgba(0, 230, 118, 0.45) !important;
    }
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) p,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) span,
    .stApp [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) div {
        color: #04150b !important;
        font-weight: 850 !important;
    }

    /* Botones de acción Esmeralda */
    .stApp [data-testid="stButton"] button,
    .stApp [data-testid="stButton"] button[kind="primary"],
    .stApp [data-testid="stButton"] button[kind="secondary"],
    .stApp .st-key-btn_act_res_liga button,
    .stApp .st-key-btn_act_cuotas_liga button,
    div[data-testid="stButton"] > button {
        background: #00e676 !important;
        background-color: #00e676 !important;
        color: #04150b !important;
        border: 1px solid #00e676 !important;
        border-radius: 10px !important;
        font-weight: 850 !important;
        font-size: 0.95rem !important;
        height: 46px !important;
        min-height: 46px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 4px 14px rgba(0, 230, 118, 0.4) !important;
        transition: all 0.2s ease !important;
    }
    .stApp [data-testid="stButton"] button p,
    .stApp [data-testid="stButton"] button span,
    .stApp [data-testid="stButton"] button div,
    .stApp .st-key-btn_act_res_liga button *,
    .stApp .st-key-btn_act_cuotas_liga button * {
        color: #04150b !important;
        font-weight: 850 !important;
    }
    .stApp [data-testid="stButton"] button:hover,
    .stApp [data-testid="stButton"] button[kind="primary"]:hover,
    .stApp .st-key-btn_act_res_liga button:hover,
    .stApp .st-key-btn_act_cuotas_liga button:hover {
        background: #26f089 !important;
        background-color: #26f089 !important;
        border-color: #26f089 !important;
        color: #04150b !important;
        box-shadow: 0 6px 20px rgba(0, 230, 118, 0.6) !important;
        transform: translateY(-1px) !important;
    }
    .stApp [data-testid="stButton"] button:disabled,
    .stApp .st-key-btn_act_res_liga button:disabled {
        background: #0f2217 !important;
        background-color: #0f2217 !important;
        border-color: #143523 !important;
        color: #446452 !important;
        cursor: not-allowed !important;
        box-shadow: none !important;
        transform: none !important;
    }

    /* Tarjetas de partidos */
    [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 1.5rem 1.6rem 1.8rem 1.6rem !important;
        border: 1px solid #143523 !important;
        border-radius: 18px !important;
        background: linear-gradient(145deg, #0b1f15, #06140d) !important;
        margin-bottom: 1.5rem !important;
        box-shadow: 0 4px 22px rgba(0, 0, 0, 0.35) !important;
        box-sizing: border-box !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(0, 230, 118, 0.5) !important;
    }

    .card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.8rem;
        color: #8ba797;
        margin-bottom: 0.85rem;
        border-bottom: 1px solid #143523;
        padding-bottom: 0.5rem;
    }
    .badge-time {
        background: #0d261a;
        color: #00e676;
        border: 1px solid #143523;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
    }
    .badge-conf-alta {
        background: rgba(0, 230, 118, 0.18);
        color: #00e676;
        border: 1px solid rgba(0, 230, 118, 0.55);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-weight: 800;
        font-size: 0.75rem;
    }
    .badge-conf-media {
        background: rgba(0, 230, 118, 0.10);
        color: #4ade80;
        border: 1px solid rgba(0, 230, 118, 0.35);
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
        border-bottom: 1px solid #143523;
    }
    .team-name {
        font-size: 1.25rem;
        font-weight: 800;
        color: #f5f8fb;
    }
    .team-abbr {
        color: #8ba797;
        font-size: 0.9rem;
        font-weight: 600;
    }

    .pick-box {
        background: linear-gradient(145deg, #0b2418, #07170f) !important;
        border: 1px solid rgba(0, 230, 118, 0.45) !important;
        border-radius: 12px;
        padding: 0.85rem 1.15rem;
        margin-top: 1rem;
        margin-bottom: 0.6rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-sizing: border-box;
        box-shadow: 0 4px 18px rgba(0, 230, 118, 0.10) !important;
    }
    .pick-title {
        color: #00e676;
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
        background: #0a2115;
        padding: 0.35rem 0.65rem;
        border-radius: 8px;
        font-size: 0.82rem;
        color: #a3c4b1;
        border: 1px solid #143523;
    }
    </style>
    """,
    unsafe_allow_html=True
)


def cargar_predicciones_ligamx(forzar: bool = False):
    """Carga las predicciones desde disco o ejecuta el pipeline si no existen o se solicita refresco."""
    hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")

    if forzar or not RUTA_PREDICCIONES.exists():
        with st.spinner("Consultando DraftKings y ejecutando modelo Bivariado Poisson..."):
            preds = predecir_jornada_ligamx(force_refresh=forzar)
            return preds
    try:
        with open(RUTA_PREDICCIONES, "r", encoding="utf-8") as f:
            preds = json.load(f)

        if not preds or not isinstance(preds, list):
            return predecir_jornada_ligamx(force_refresh=True)

        # Evitar que se queden pegados partidos pasados:
        fechas_partidos = [p.get("fecha_cdmx") for p in preds if p.get("fecha_cdmx")]
        # Si TODOS los partidos del archivo son de fechas anteriores a hoy, actualizar a la nueva jornada
        todos_pasados = all(f < hoy_cdmx for f in fechas_partidos) if fechas_partidos else False
        todos_finalizados = all(
            p.get("resultado") in ["GANADA", "PERDIDA", "PUSH"] or "FINAL" in str(p.get("estado", "")).upper()
            for p in preds
        )

        if todos_pasados or (todos_finalizados and max(fechas_partidos, default="") < hoy_cdmx):
            with st.spinner("Actualizando cartelera de la jornada activa Liga MX..."):
                return predecir_jornada_ligamx(force_refresh=True)

        # Sincronizar pendientes con la base de datos
        pendientes = [p for p in preds if p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]]
        if pendientes:
            try:
                guardar_predicciones_ligamx(pendientes)
            except Exception:
                pass
        return preds
    except Exception:
        return predecir_jornada_ligamx(force_refresh=True)


# Encabezado principal de la marca Liga MX
st.markdown(
    """
    <div class="ligamx-shell">
        <div class="ligamx-brand">
            <span class="ligamx-logo">⚽</span>
            <div>
                <div>ORÁCULO <span class="ligamx-accent">LIGA MX AI</span></div>
                <div class="ligamx-status">Modelo Bivariado de Poisson · DraftKings Odds · Over/Under 2.5 & Moneyline</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")

# Selector de navegación interna
vista = st.radio(
    "Sección Liga MX",
    ["Partidos de la Jornada", "Rendimiento e Historial"],
    horizontal=True,
    label_visibility="collapsed",
    key="ligamx_vista_principal",
)

# Cargar estado de predicciones de la jornada
predicciones_actuales = cargar_predicciones_ligamx(forzar=False)
hay_pendientes_por_liquidar = any(
    p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]
    for p in predicciones_actuales
)

# Barra de acciones (actualizar resultados y cuotas a la misma altura)
st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
col_act1, col_act2 = st.columns(2, gap="medium")
with col_act1:
    btn_deshabilitado = not hay_pendientes_por_liquidar
    lbl_btn_res = "Resultados Ya Registrados" if btn_deshabilitado else "Actualizar Resultados Jornada"
    help_btn_res = (
        "Todos los partidos concluidos ya han sido liquidados en Rendimiento e Historial."
        if btn_deshabilitado else
        "Consulta marcadores finales oficiales de ESPN, liquida las apuestas y las pasa a Rendimiento e Historial."
    )
    if st.button(lbl_btn_res, key="btn_act_res_liga", type="primary", disabled=btn_deshabilitado, use_container_width=True, help=help_btn_res):
        with st.spinner("Liquidando partidos y actualizando historial Liga MX..."):
            res = liquidar_partidos_pendientes_ligamx()
            if res.get("evaluados", 0) > 0:
                st.success(f"✅ {res['mensaje']}")
            else:
                st.info(f"ℹ️ {res['mensaje']}")
            st.rerun()

with col_act2:
    if st.button("Actualizar Cuotas", key="btn_act_cuotas_liga", type="primary", use_container_width=True, help="Consulta las últimas líneas de DraftKings y actualiza proyecciones de la jornada."):
        with st.spinner("Consultando DraftKings y ejecutando modelos..."):
            cargar_predicciones_ligamx(forzar=True)
            st.success("✅ Cuotas y proyecciones de Liga MX actualizadas.")
            st.rerun()

st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)


# ==========================================================
# VISTA 1: PARTIDOS DE LA JORNADA Y PROYECCIONES
# ==========================================================
if vista == "Partidos de la Jornada":
    st.markdown(
        f"""
        <div class="ligamx-view-hero">
            <div>
                <div class="ligamx-eyebrow">FÚTBOL MEXICANO · ORÁCULO AI</div>
                <h1>Partidos y Líneas Liga MX</h1>
                <div class="ligamx-subtitle">Modelo Bivariado de Poisson enfocado en Over/Under 2.5 y Moneyline (1X2). Hora CDMX: {hora_actual_cdmx}.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    predicciones = list(predicciones_actuales)

    if not predicciones:
        st.info("⚽ No hay partidos programados en este momento para la Liga MX. Puedes forzar actualización con el botón superior.")
        st.stop()

    partidos_pendientes = [p for p in predicciones if p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]]
    partidos_liquidados = [p for p in predicciones if p.get("resultado") in ["GANADA", "PERDIDA", "PUSH"]]

    n_pendientes = len(partidos_pendientes)
    n_liquidados = len(partidos_liquidados)

    # Tarjetas de métricas
    mcols = st.columns(4)
    mcols[0].metric("Partidos en Cartelera", f"{len(predicciones)} partidos")
    mcols[1].metric("Picks Alta Confianza", sum(1 for p in predicciones if p.get("confianza") == "ALTA"))
    mcols[2].metric("Picks Over/Under", sum(1 for p in predicciones if "Totales" in p.get("pick_mercado", "")))
    mcols[3].metric("Picks Moneyline (1X2)", sum(1 for p in predicciones if "Moneyline" in p.get("pick_mercado", "")))

    # Controles de filtrado
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        filtro_mercado = st.selectbox(
            "Filtrar por Mercado:",
            ["Todos los mercados", "Totales (Over/Under)", "Moneyline"]
        )
    with fcol2:
        filtro_confianza = st.selectbox(
            "Filtrar por Confianza:",
            ["Todas las selecciones", "Solo ALTA confianza", "Solo MEDIA confianza"]
        )

    filtrados = list(predicciones)
    if filtro_mercado == "Totales (Over/Under)":
        filtrados = [p for p in filtrados if "Totales" in p.get("pick_mercado", "")]
    elif filtro_mercado == "Moneyline":
        filtrados = [p for p in filtrados if "Moneyline" in p.get("pick_mercado", "")]

    if filtro_confianza == "Solo ALTA confianza":
        filtrados = [p for p in filtrados if p.get("confianza") == "ALTA"]
    elif filtro_confianza == "Solo MEDIA confianza":
        filtrados = [p for p in filtrados if p.get("confianza") == "MEDIA"]

    if not filtrados:
        st.warning("No hay partidos que coincidan con los filtros seleccionados.")
        st.stop()

    # Despliegue de tarjetas de partidos
    for p in filtrados:
        id_ev = p.get("id_evento", "")
        estado = str(p.get("estado", "")).upper()
        es_final = "FINAL" in estado or "FULL_TIME" in estado
        en_vivo = "PROGRESS" in estado

        m_loc = p.get("marcador_local")
        m_vis = p.get("marcador_visita")
        tiene_marcador = (m_loc is not None and m_vis is not None)

        confianza = p.get("confianza", "MEDIA")
        badge_conf_cls = "badge-conf-alta" if confianza == "ALTA" else "badge-conf-media"

        # Badge superior izquierdo
        hora_txt = f"{p.get('fecha_cdmx', '')} · {p.get('hora_cdmx', '')} CDMX"
        if es_final:
            badge_top_left = f'<span class="badge-time">🏁 FINALIZADO</span><span style="margin-left: 0.5rem; color: #8ba797; font-size: 0.8rem;">{hora_txt}</span>'
        elif en_vivo:
            badge_top_left = f'<span class="badge-time" style="background:#27150a;color:#ff8c33;border-color:#ff6b00;">🔴 EN VIVO</span><span style="margin-left: 0.5rem; color: #8ba797; font-size: 0.8rem;">{hora_txt}</span>'
        else:
            badge_top_left = f'<span class="badge-time">⏰ {hora_txt}</span><span style="margin-left: 0.5rem; color: #8ba797; font-size: 0.8rem;">DraftKings</span>'

        badge_top_right = f'<span class="{badge_conf_cls}">CONFIANZA {confianza}</span>'

        # Fila de equipos
        if tiene_marcador:
            teams_html = f"""
            <div class="teams-row">
                <div>
                    <div class="team-name">{p.get('equipo_visita')} <span style="color: #00e676; margin-left: 0.4rem; font-size: 1.4rem; font-weight: 900;">{int(m_vis)}</span></div>
                    <div class="team-abbr">Visitante · ML: {p.get('ml_visita', 'N/D')}</div>
                </div>
                <div style="font-size: 0.95rem; color: #00e676; font-weight: 900; letter-spacing: 0.08em; background: #092416; border: 1px solid #00e676; padding: 0.2rem 0.6rem; border-radius: 6px;">{'FINAL' if es_final else 'EN VIVO'}</div>
                <div style="text-align: right;">
                    <div class="team-name"><span style="color: #00e676; margin-right: 0.4rem; font-size: 1.4rem; font-weight: 900;">{int(m_loc)}</span> {p.get('equipo_local')}</div>
                    <div class="team-abbr">Local · ML: {p.get('ml_local', 'N/D')}</div>
                </div>
            </div>
            """
        else:
            teams_html = f"""
            <div class="teams-row">
                <div>
                    <div class="team-name">{p.get('equipo_visita')}</div>
                    <div class="team-abbr">Visitante · ML: {p.get('ml_visita', 'N/D')} ({p.get('ml_visita_dec', 'N/D')})</div>
                </div>
                <div style="font-size: 1.1rem; color: #446452; font-weight: 800;">vs</div>
                <div style="text-align: right;">
                    <div class="team-name">{p.get('equipo_local')}</div>
                    <div class="team-abbr">Local · ML: {p.get('ml_local', 'N/D')} ({p.get('ml_local_dec', 'N/D')})</div>
                </div>
            </div>
            """

        with st.container(border=True):
            st.markdown(
                f"""
                <div class="card-top">
                    <div>{badge_top_left}</div>
                    <div>{badge_top_right}</div>
                </div>
                {teams_html}
                """,
                unsafe_allow_html=True
            )

            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                st.caption("⚽ **Moneyline (1X2 Modelo)**")
                p_loc = p.get("prob_local", 0.4) * 100
                p_emp = p.get("prob_empate", 0.3) * 100
                p_vis = p.get("prob_visita", 0.3) * 100
                st.write(f"Local: **{p_loc:.1f}%** · Empate: **{p_emp:.1f}%** · Visita: **{p_vis:.1f}%**")
                st.markdown(f"<span class='stat-pill'>Marcador más probable: <b>{p.get('marcador_mas_probable', 'N/D')}</b></span>", unsafe_allow_html=True)

            with col_c2:
                st.caption("🎯 **Totales (Over / Under 2.5)**")
                p_ov = p.get("prob_over", 0.5) * 100
                p_un = p.get("prob_under", 0.5) * 100
                tot_proj = p.get("total_proyectado", 2.6)
                st.write(f"Over 2.5: **{p_ov:.1f}%** · Under 2.5: **{p_un:.1f}%**")
                st.markdown(f"<span class='stat-pill'>Goles esperados totales: <b>{tot_proj:.2f}</b></span>", unsafe_allow_html=True)

            with col_c3:
                st.caption("📊 **Goles Esperados (xG)**")
                xg_h = p.get("xg_local", 1.4)
                xg_a = p.get("xg_visita", 1.2)
                st.write(f"Local xG: **{xg_h:.2f}** | Visita xG: **{xg_a:.2f}**")
                cuota_emp = p.get("ml_empate", "+250")
                st.markdown(f"<span class='stat-pill'>Momio Empate Book: <b>{cuota_emp}</b></span>", unsafe_allow_html=True)

            # Caja de Recomendación Oficial
            resultado_pick = p.get("resultado")
            u_gan = p.get("unidades_ganadas")

            if resultado_pick in ["GANADA", "PERDIDA", "PUSH"]:
                color_res = "#4ade80" if resultado_pick == "GANADA" else ("#f87171" if resultado_pick == "PERDIDA" else "#cbd5e1")
                val_u_box = f"+{u_gan:.2f}" if (u_gan is not None and u_gan > 0) else ("+0.85" if u_gan is None else f"{u_gan:.2f}")
                pick_res_html = f"""
                <div style="text-align: right;">
                    <div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">RESULTADO OFICIAL</div>
                    <div style="font-size: 1.15rem; font-weight: 900; color: {color_res};">{resultado_pick} ({val_u_box} u)</div>
                </div>
                """
            else:
                pick_res_html = f"""
                <div style="text-align: right;">
                    <div style="font-size: 0.72rem; color: #8ba797;">PROBABILIDAD MODELO</div>
                    <div style="font-size: 1.25rem; font-weight: 900; color: #00e676;">{p.get('pick_probabilidad', 0.0)*100:.1f}%</div>
                </div>
                """

            momio_pick_str = f" · Momio: {p.get('pick_cuota', '')} ({p.get('pick_cuota_dec', '')})" if p.get('pick_cuota') else ""
            st.markdown(
                f"""
                <div class="pick-box">
                    <div>
                        <div class="pick-title">Recomendación Oficial ({p.get('pick_mercado')})<span style="color:#ffffff;font-weight:700;">{momio_pick_str}</span></div>
                        <div class="pick-sel">{p.get('pick_seleccion')}</div>
                        <div style="font-size: 0.8rem; color: #8ba797; margin-top: 0.2rem;">{p.get('pick_detalle')}</div>
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
        <div class="ligamx-view-hero">
            <div>
                <div class="ligamx-eyebrow">AUDITORÍA Y TRACK RECORD</div>
                <h1>Rendimiento Histórico Liga MX</h1>
                <div class="ligamx-subtitle">Historial de aciertos, balance de unidades (+/- u) y retorno de inversión (ROI) con marcadores oficiales.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    df_historial = cargar_historial_rendimiento_ligamx()

    if df_historial.empty:
        st.info("Todavía no hay partidos auditados en el historial de Liga MX.")
        st.stop()

    liquidados = df_historial[df_historial["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()

    # Métricas Globales
    ganadas = (liquidados["resultado"] == "GANADA").sum()
    perdidas = (liquidados["resultado"] == "PERDIDA").sum()
    pushes = (liquidados["resultado"] == "PUSH").sum()
    total_eval = len(liquidados)

    tasa_acierto = (ganadas / (ganadas + perdidas)) * 100 if (ganadas + perdidas) > 0 else 0.0
    unidades_totales = float(liquidados["unidades_ganadas"].sum())
    roi_global = (unidades_totales / total_eval) * 100 if total_eval > 0 else 0.0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Picks Auditados", f"{total_eval:,}")
    kpi2.metric("Tasa de Acierto", f"{tasa_acierto:.2f}%", f"{ganadas}G - {perdidas}P" + (f" ({pushes} Push)" if pushes else ""))
    kpi3.metric("Beneficio Acumulado", f"{unidades_totales:+.2f} u")
    kpi4.metric("Retorno de Inversión (ROI)", f"{roi_global:+.2f}%")

    st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

    # Filtros de tabla
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        mercado_hist = st.selectbox("Filtrar por Mercado:", ["Todos", "Moneyline", "Totales (Over/Under)"], key="filtro_hist_mercado")
    with col_f2:
        res_hist = st.selectbox("Filtrar por Resultado:", ["Todos", "Solo GANADAS", "Solo PERDIDAS"], key="filtro_hist_res")

    df_tabla = liquidados.copy()
    if mercado_hist != "Todos":
        df_tabla = df_tabla[df_tabla["mercado"] == mercado_hist]
    if res_hist == "Solo GANADAS":
        df_tabla = df_tabla[df_tabla["resultado"] == "GANADA"]
    elif res_hist == "Solo PERDIDAS":
        df_tabla = df_tabla[df_tabla["resultado"] == "PERDIDA"]

    columnas_mostrar = [
        "fecha", "equipo_visitante", "equipo_local", "mercado", "seleccion",
        "cuota", "marcador_visitante", "marcador_local", "resultado", "unidades_ganadas"
    ]
    renombres = {
        "fecha": "Fecha",
        "equipo_visitante": "Visita",
        "equipo_local": "Local",
        "mercado": "Mercado",
        "seleccion": "Selección",
        "cuota": "Cuota",
        "marcador_visitante": "Goles Visita",
        "marcador_local": "Goles Local",
        "resultado": "Resultado",
        "unidades_ganadas": "Unidades (+/-)"
    }

    cols_existentes = [c for c in columnas_mostrar if c in df_tabla.columns]
    df_ver = df_tabla[cols_existentes].rename(columns=renombres).sort_values("Fecha", ascending=False)

    st.dataframe(
        df_ver,
        use_container_width=True,
        hide_index=True
    )
