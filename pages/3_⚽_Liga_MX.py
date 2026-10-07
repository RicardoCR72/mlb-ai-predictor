from core.ui_picks import render_pick, liga_pick
from core.ui_filtros import performance_filters
from core.ui_actualizacion import render_update_button
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import pandas as pd
import numpy as np
import streamlit as st
from futbol_liga_mx.inferencia import historical_probabilities, upcoming_probabilities

st.set_page_config(
    page_title="Liga MX Oráculo",
    page_icon="⚽",
    layout="wide",
)

RAIZ = Path(__file__).resolve().parents[1]
RUTA_FUTBOL = RAIZ / "futbol_liga_mx"
RUTA_DATA = RUTA_FUTBOL / "data"
RUTA_MODELOS = RUTA_FUTBOL / "modelos"

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 85% 0%, rgba(183,255,60,.055), transparent 28rem),
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
    .soccer-shell {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #202938;
        border-radius: 13px;
        background: #111720;
        margin-bottom: .75rem;
    }
    .soccer-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .soccer-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #b7ff3c;
        color: #071006;
        font-weight: 900;
    }
    .soccer-accent { color: #b7ff3c; }
    .soccer-status { color: #8e99a9; font-size: .78rem; font-weight: 700; }
    .soccer-view-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: .9rem 0 1.25rem;
    }
    .soccer-eyebrow {
        color: #b7ff3c;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .12em;
    }
    .soccer-view-hero h1 {
        margin: .22rem 0 .15rem;
        color: #f5f8fb;
        font-size: clamp(1.75rem, 3vw, 2.45rem);
    }
    .soccer-subtitle { color: #8994a5; font-size: .88rem; }
    div[data-testid="stMetric"] {
        background: #111720;
        border: 1px solid #202938;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8994a5; }
    div[data-testid="stMetricValue"] { color: #f4f7fb; }
    .match-card {
        padding: 1.15rem 1.3rem;
        border: 1px solid #253044;
        border-radius: 16px;
        background: linear-gradient(145deg, #111722, #0d131d);
        margin-bottom: 0.95rem;
    }
    .match-header {
        display: flex;
        justify-content: space-between;
        font-size: 0.78rem;
        color: #798699;
        margin-bottom: 0.7rem;
    }
    .match-teams {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 1.2rem;
        font-weight: 800;
        color: #f5f8fb;
        margin-bottom: 0.8rem;
    }
    .match-badge {
        padding: 0.25rem 0.6rem;
        border-radius: 999px;
        background: rgba(183, 255, 60, 0.08);
        border: 1px solid rgba(183, 255, 60, 0.3);
        color: #b7ff3c;
        font-size: 0.75rem;
        font-weight: 800;
    }
    .prob-bar {
        height: 6px;
        border-radius: 3px;
        background: #202938;
        overflow: hidden;
        margin-top: 0.5rem;
    }
    .prob-fill {
        height: 100%;
        background: #b7ff3c;
    }
    </style>
    <div class="soccer-shell">
        <div class="soccer-brand">
            <span class="soccer-logo">⚽</span>
            <span>ORÁCULO <span class="soccer-accent">LIGA MX</span></span>
        </div>
        <div class="soccer-status">MODELO CUANTITATIVO · TOTALES 2.5 · MODELO CONGELADO</div>
    </div>
    """,
    unsafe_allow_html=True,
)

vista = st.radio(
    "Sección Liga MX",
    ["🔮 Próximos Partidos", "⚽ Resultados Históricos", "📊 Métricas de Validación", "📋 Historial y Cobertura"],
    horizontal=True,
    label_visibility="collapsed",
    key="ligamx_vista",
)

@st.cache_data(ttl=300)
def cargar_datos_ligamx():
    partidos_csv = RUTA_DATA / "partidos.csv"
    if not partidos_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(partidos_csv)
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df

@st.cache_data(ttl=300)
def cargar_proximos_ligamx():
    proximos_csv = RUTA_DATA / "proximos.csv"
    if not proximos_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(proximos_csv)
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df

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

render_update_button("liga_mx")

df_partidos = cargar_datos_ligamx()
df_proximos = cargar_proximos_ligamx()
metricas = cargar_metricas_ligamx()
modelo_params = cargar_modelo_portable()
df_probabilidades = pd.DataFrame()
if not df_partidos.empty and modelo_params:
    try:
        df_probabilidades = probabilidades_historicas(df_partidos, modelo_params)
    except (ValueError, KeyError) as exc:
        st.error(f"No se pudieron calcular las probabilidades: {exc}")

# ==========================================================
# VISTA 0: PRÓXIMOS PARTIDOS Y PROYECCIONES
# ==========================================================
if vista == "🔮 Próximos Partidos":
    st.markdown(
        """
        <div class="soccer-view-hero">
            <div>
                <div class="soccer-eyebrow">PROYECCIONES MODELO POISSON</div>
                <h1>Próximos Partidos Liga MX</h1>
                <div class="soccer-subtitle">Probabilidades calibradas de Over / Under 2.5 goles para la temporada actual.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        futuros = upcoming_probabilities(df_partidos, df_proximos, modelo_params, metricas)
    except (ValueError, KeyError) as exc:
        st.warning(f"Predicciones suspendidas: {exc}")
        st.caption("Actualiza los datos con el workflow Liga MX. El modelo congelado se conserva.")
        futuros = pd.DataFrame()
    if futuros.empty:
        st.info("No hay partidos habilitados para predecir en los próximos siete días.")
    else:
        st.metric("Próximos partidos", len(futuros))
        st.caption("Probabilidades del modelo validado. Registra la cuota tomada en Bankroll para calcular EV.")
        for _, row in futuros.iterrows():
            cols = st.columns(2)
            for col, side in zip(cols, ('OVER','UNDER')):
                with col:
                    render_pick(liga_pick(row, side), market='Total de goles', state='Modelo congelado',
                        details=[('Cuota', 'Introduce la cuota tomada al registrar')])

# ==========================================================
# VISTA 1: RESULTADOS HISTÓRICOS
# ==========================================================
elif vista == "⚽ Resultados Históricos":
    st.markdown(
        """
        <div class="soccer-view-hero">
            <div>
                <div class="soccer-eyebrow">HISTORIAL 2018–2025</div>
                <h1>Resultados Históricos Liga MX</h1>
                <div class="soccer-subtitle">Resultados reales con probabilidad pre-partido Over/Under 2.5 según el modelo Poisson calibrado.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df_partidos.empty or df_probabilidades.empty:
        st.warning("No se encontraron partidos en `futbol_liga_mx/data/partidos.csv`.")
    else:
        df_probabilidades = performance_filters(df_probabilidades, 'fecha', 'liga_hist', season_col='season')
        df_partidos = df_probabilidades.copy()
        if df_partidos.empty:
            st.info('No hay partidos para los filtros seleccionados.'); st.stop()
        # Métricas generales arriba
        ultimos = df_partidos.sort_values(by="fecha", ascending=False)
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Partidos Registrados", f"{len(df_partidos):,}")
        with m2:
            prom_goles = (df_partidos['goles_local'] + df_partidos['goles_visitante']).mean()
            st.metric("Media Goles / Partido", f"{prom_goles:.2f}")
        with m3:
            over_rate = ((df_partidos['goles_local'] + df_partidos['goles_visitante']) > 2.5).mean()
            st.metric("Tasa Histórica Over 2.5", f"{over_rate * 100:.1f}%")
        with m4:
            st.metric("Temporada Activa", str(df_partidos.season.max()))

        st.markdown("### Partidos Recientes y Proyecciones")
        df_filtrado = df_probabilidades.sort_values(by='fecha', ascending=False).reset_index(drop=True)
        st.caption('Se muestran los 15 partidos más recientes de la muestra filtrada. Evaluación histórica, sin dinero apostado.')

        # Mostrar los partidos
        for idx, row in df_filtrado.head(15).iterrows():
            total_goles = row['goles_local'] + row['goles_visitante']
            es_over = total_goles > 2.5
            fecha_str = row['fecha'].strftime("%d/%m/%Y")
            p_over_val = row['p_over25']
            p_over_pct = p_over_val * 100

            pick = dict(fecha=row['fecha'], deporte='Liga MX', partido=f"{row['visitante']} @ {row['local']}",
                seleccion='OVER 2.5', casa='Sin cuota histórica', cuota=None, probabilidad=float(row['p_over25']))
            render_pick(pick, market='Total de goles · Evaluación histórica',
                state=f"Real: {row['goles_visitante']} – {row['goles_local']} · {'OVER' if es_over else 'UNDER'}",
                details=[('Probabilidad Under 2.5',f"{1-float(row['p_over25']):.1%}"),
                         ('Jornada',str(row['ronda']))], allow_register=False)

# ==========================================================
# VISTA 2: MÉTRICAS DE VALIDACIÓN
# ==========================================================
elif vista == "📊 Métricas de Validación":
    st.markdown(
        """
        <div class="soccer-view-hero">
            <div>
                <div class="soccer-eyebrow">AUDITORÍA ESTADÍSTICA</div>
                <h1>Validación del Modelo Liga MX</h1>
                <div class="soccer-subtitle">Rendimiento riguroso medido por Brier Score y Log Loss frente al baseline de mercado.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if metricas:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### Confirmación 2024–25")
            conf = metricas.get("confirmation", {}).get("calibrated", {})
            st.metric("Brier Score", f"{conf.get('brier', 0):.4f}")
            st.metric("Log Loss", f"{conf.get('logloss', 0):.4f}")
            st.metric("Probabilidad Media", f"{conf.get('prob_media', 0)*100:.1f}%")
        with c2:
            st.markdown("#### Baseline de Comparación")
            base = metricas.get("confirmation", {}).get("baseline", {})
            st.metric("Brier Baseline", f"{base.get('brier', 0):.4f}")
            st.metric("Log Loss Baseline", f"{base.get('logloss', 0):.4f}")
            st.metric("Tasa Real Over", f"{base.get('real_over', 0)*100:.1f}%")
        with c3:
            st.markdown("#### Estado de Congelamiento")
            st.info(
                f"**Modelo:** Calibrado\n\n"
                f"**Muestra de entrenamiento:** {metricas.get('train_games', 0)} partidos\n\n"
                f"**Temporadas base:** 2018–19 a 2021–22\n\n"
                f"**Selección:** 2023–24\n\n"
                f"**Evaluación ciega:** 2024–25"
            )

        st.markdown("---")
        st.markdown("#### Cobertura Histórica de Partidos por Temporada")
        cobertura = metricas.get("coverage", {})
        if cobertura:
            df_cob = pd.DataFrame(list(cobertura.items()), columns=["Temporada", "Partidos"])
            st.dataframe(df_cob, use_container_width=True, hide_index=True)
    else:
        st.warning("No se encontró `futbol_liga_mx/modelos/metricas.json`.")

# ==========================================================
# VISTA 3: HISTORIAL Y COBERTURA
# ==========================================================
else:
    st.markdown(
        """
        <div class="soccer-view-hero">
            <div>
                <div class="soccer-eyebrow">BASE DE DATOS</div>
                <h1>Historial Completo Liga MX</h1>
                <div class="soccer-subtitle">Consulta de marcadores, goles totales y temporadas registradas.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
