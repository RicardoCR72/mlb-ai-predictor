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
from core.ui_actualizacion import render_update_button
from core.ui_rendimiento_resumen import history_window
from core.ui_controles import state_message, render_order
from core.ui_tarjetas import render_pick, render_liga_matches
from core.ui_rendimiento_diseno import performance_filters
from futbol_liga_mx.inferencia import historical_probabilities, upcoming_probabilities

RAIZ = Path(__file__).resolve().parents[1]
RUTA_FUTBOL = RAIZ / "futbol_liga_mx"
RUTA_DATA = RUTA_FUTBOL / "data"
RUTA_MODELOS = RUTA_FUTBOL / "modelos"

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
        background: #0b1f15;
        border: 1px solid #143523;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8ba797; }
    div[data-testid="stMetricValue"] { color: #00e676; }

    /* Acento Emerald para radio activo */
    [data-testid="stRadio"] [role="radiogroup"] {
        background: #091710 !important;
        border: 1px solid #143523 !important;
    }
    [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
        background: #00e676 !important;
        color: #04150b !important;
        font-weight: 850 !important;
    }

    /* Acentos Emerald para botones y controles */
    [data-testid="stButton"] button:hover {
        background: #00e676 !important;
        color: #04150b !important;
        border-color: #00e676 !important;
    }
    [data-testid="stButton"] button[kind="primary"] {
        background: #00e676 !important;
        color: #04150b !important;
        border-color: #00e676 !important;
    }

    /* Personalización de tarjetas Oracle Pick para Liga MX */
    .stApp .oracle-pick {
        background: #0b1f15 !important;
        border: 1px solid #143523 !important;
        border-top: 3px solid #00e676 !important;
    }
    .stApp .oracle-bar i {
        background: #00e676 !important;
    }
    .stApp .oracle-details summary {
        color: #00e676 !important;
    }
    .stApp .oracle-odds {
        background: #122b1e !important;
        color: #00e676 !important;
        font-weight: 750;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Encabezado principal de la marca Liga MX
st.markdown(
    """
    <div class="ligamx-shell">
        <div class="ligamx-brand">
            <span class="ligamx-logo">⚽</span>
            <div>
                <div>ORÁCULO <span class="ligamx-accent">LIGA MX AI</span></div>
                <div class="ligamx-status">Modelo Bivariado de Poisson · xG Proyectado · Torneo BBVA MX</div>
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
    <div class="ligamx-view-hero">
        <div>
            <div class="ligamx-eyebrow">FÚTBOL MEXICANO · LIGA BBVA MX</div>
            <h1 style="margin:.25rem 0 .2rem;color:#f0fdf4;">Proyecciones de Goles & Over/Under 2.5</h1>
            <div class="ligamx-subtitle">Modelado probabilístico con distribución de Poisson para cada partido del torneo local.</div>
        </div>
        <div style="text-align:right;">
            <span style="background:#0f291c;color:#00e676;padding:.3rem .75rem;border-radius:8px;font-size:.78rem;font-weight:800;border:1px solid #143523;">
                🕒 {hora_actual_cdmx} CDMX
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Funciones de carga de datos
def cargar_datos_ligamx():
    from futbol_liga_mx.repositorio import read_games
    return read_games(RUTA_DATA / 'partidos.csv')

def cargar_proximos_ligamx():
    from futbol_liga_mx.repositorio import read_games
    return read_games(RUTA_DATA / 'proximos.csv')

@st.cache_data(ttl=600)
def cargar_metricas_ligamx():
    metricas_path = RUTA_MODELOS / "metricas.json"
    if metricas_path.exists():
        return json.loads(metricas_path.read_text(encoding="utf-8"))
    return {}

@st.cache_data(ttl=600)
def cargar_modelo_portable():
    modelo_path = RUTA_MODELOS / "modelo_portable.json"
    if modelo_path.exists():
        return json.loads(modelo_path.read_text(encoding="utf-8"))
    return {}

@st.cache_data(ttl=600)
def probabilidades_historicas(games, params):
    return historical_probabilities(games, params)

# Selector de navegación interna
vista = st.radio(
    "Sección Liga MX",
    ["🔮 Próximos Partidos", "⚽ Resultados Históricos", "📋 Historial y Cobertura"],
    horizontal=True,
    label_visibility="collapsed",
    key="ligamx_vista_v2",
)

# Barra de acciones (actualizaciones)
st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
render_update_button("liga_mx", compact=True)
st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

df_partidos = cargar_datos_ligamx()
df_proximos = cargar_proximos_ligamx()
metricas = cargar_metricas_ligamx()
modelo_params = cargar_modelo_portable()
df_probabilidades = pd.DataFrame()
if not df_partidos.empty and modelo_params:
    try:
        df_probabilidades = probabilidades_historicas(df_partidos, modelo_params)
    except (ValueError, KeyError):
        state_message("No se pudieron calcular las probabilidades de Liga MX. Revisa los datos del modelo.", kind="blocked")

# ==========================================================
# VISTA 0: PRÓXIMOS PARTIDOS Y PROYECCIONES
# ==========================================================
if vista == "🔮 Próximos Partidos":
    try:
        futuros = upcoming_probabilities(df_partidos, df_proximos, modelo_params, metricas)
    except (ValueError, KeyError):
        state_message("Las predicciones están suspendidas hasta verificar la cobertura de los datos.", kind="blocked")
        st.caption("Usa «Actualizar resultados y calendario Liga MX» para verificar los datos.")
        futuros = pd.DataFrame()

    if futuros.empty:
        state_message('No hay partidos habilitados para predecir en los próximos siete días.', kind='empty')
    else:
        st.metric("Próximos partidos programados", len(futuros))
        st.caption("Probabilidades estimadas mediante el modelo Bivariado de Poisson validado.")
        futuros = render_order(futuros, 'liga_picks', date_col='inicio_utc', confidence_col='p_over25', upcoming=True)
        render_liga_matches(futuros)

# ==========================================================
# VISTA 1: RESULTADOS HISTÓRICOS
# ==========================================================
elif vista == "⚽ Resultados Históricos":
    if df_partidos.empty or df_probabilidades.empty:
        state_message('Todavía no hay partidos históricos disponibles.', kind='empty')
    else:
        df_probabilidades['resultado'] = np.where(
            (df_probabilidades.goles_local + df_probabilidades.goles_visitante) > 2.5,
            'GANADA',
            'PERDIDA'
        )
        df_probabilidades = performance_filters(
            df_probabilidades,
            'fecha',
            'liga_hist',
            season_col='season',
            probability_col='p_over25',
            probability_scale=100,
            result_col='resultado'
        )
        df_partidos = df_probabilidades.copy()
        if df_partidos.empty:
            state_message('No hay partidos para los filtros seleccionados.', kind='filters')
            st.stop()

        st.metric('Partidos evaluados', len(df_partidos))
        with st.expander('📊 Estadísticas y métricas históricas de goles'):
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Partidos Registrados", f"{len(df_partidos):,}")
            with m2:
                prom_goles = (df_partidos['goles_local'] + df_partidos['goles_visitante']).mean()
                st.metric("Media Goles / Partido", f"{prom_goles:.2f}")
            with m3:
                over_rate = ((df_partidos['goles_local'] + df_partidos['goles_visitante']) > 2.5).mean()
                st.metric("Tasa Histórica Over 2.5", f"{over_rate * 100:.1f}%")
            with m4:
                st.metric("Temporada Activa", str(df_partidos.season.max()))

        st.markdown("### Partidos Recientes y Proyecciones")
        df_filtrado = render_order(df_probabilidades, 'liga_hist', date_col='fecha', confidence_col='p_over25').reset_index(drop=True)
        st.caption('Evaluación histórica sin cuotas: seguimiento probabilístico del modelo Poisson.')

        for idx, row in history_window(df_filtrado, 'liga_history').iterrows():
            total_goles = row['goles_local'] + row['goles_visitante']
            es_over = total_goles > 2.5
            pick = dict(
                fecha=row['fecha'],
                deporte='Liga MX',
                partido=f"{row['visitante']} @ {row['local']}",
                seleccion='OVER 2.5',
                casa='Sin cuota histórica',
                cuota=None,
                probabilidad=float(row['p_over25']),
            )
            render_pick(
                pick,
                market='Total de goles · Evaluación histórica',
                state=f"Real: {row['goles_visitante']} – {row['goles_local']} · {'OVER' if es_over else 'UNDER'}",
                details=[
                    ('Probabilidad Under 2.5', f"{1-float(row['p_over25']):.1%}"),
                    ('Jornada', str(row['ronda']))
                ],
                allow_register=False
            )

# ==========================================================
# VISTA 2: HISTORIAL Y COBERTURA
# ==========================================================
else:
    st.subheader('Cobertura e Historial Completo Liga MX')
    if not df_partidos.empty:
        col_filtro1, col_filtro2 = st.columns(2)
        with col_filtro1:
            equipos_todos = sorted(list(set(df_partidos['local'].unique().tolist() + df_partidos['visitante'].unique().tolist())))
            equipo_sel = st.selectbox("Filtrar por Equipo:", ["Todos"] + equipos_todos)
        with col_filtro2:
            ronda_filtro = st.text_input("Buscar por Ronda o Jornada (ej. Matchday 1, Final):")

        df_show = df_partidos.copy()
        if equipo_sel != "Todos":
            df_show = df_show[(df_show['local'] == equipo_sel) | (df_show['visitante'] == equipo_sel)]
        if ronda_filtro:
            df_show = df_show[df_show['ronda'].str.contains(ronda_filtro, case=False, na=False)]

        df_show['total_goles'] = df_show['goles_local'] + df_show['goles_visitante']
        df_show['over_25'] = np.where(df_show['total_goles'] > 2.5, "Over", "Under")

        columnas_ver = ['season', 'fecha', 'local', 'visitante', 'goles_local', 'goles_visitante', 'total_goles', 'over_25', 'ronda']
        st.dataframe(
            df_show[columnas_ver].sort_values(by="fecha", ascending=False),
            use_container_width=True,
            hide_index=True
        )
