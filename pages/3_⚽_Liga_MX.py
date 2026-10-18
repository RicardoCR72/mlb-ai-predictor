from core.ui_rendimiento_resumen import history_window
from core.ui_controles import state_message, render_order
from core.ui_tarjetas import render_pick, render_liga_matches
from core.ui_rendimiento_diseno import performance_filters
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
from core.ui_navegacion_movil import install_navigation
install_navigation()
from core.ui_diseno import apply_design
apply_design()


RAIZ = Path(__file__).resolve().parents[1]
RUTA_FUTBOL = RAIZ / "futbol_liga_mx"
RUTA_DATA = RUTA_FUTBOL / "data"
RUTA_MODELOS = RUTA_FUTBOL / "modelos"

from core.ui_diseno import render_sport_header
render_sport_header('Liga MX','⚽','Totales de goles y resultados')

if st.session_state.get('ligamx_vista') == '📊 Métricas de Validación':
    st.session_state.pop('ligamx_vista')
vista = st.radio(
    "Sección Liga MX",
    ["🔮 Próximos Partidos", "⚽ Resultados Históricos", "📋 Historial y Cobertura"],
    horizontal=True,
    format_func=lambda value: value.lstrip("🔥📋📈⚾🏈📊⚽🔮💼 "),
    label_visibility="collapsed",
    key="ligamx_vista",
)

def cargar_datos_ligamx():
    from futbol_liga_mx.repositorio import read_games
    return read_games(RUTA_DATA/'partidos.csv')

def cargar_proximos_ligamx():
    from futbol_liga_mx.repositorio import read_games
    return read_games(RUTA_DATA/'proximos.csv')

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
        state_message("No se pudieron calcular las probabilidades de Liga MX. Revisa los datos del modelo.",kind="blocked")

# ==========================================================
# VISTA 0: PRÓXIMOS PARTIDOS Y PROYECCIONES
# ==========================================================
if vista == "🔮 Próximos Partidos":
    st.subheader('Próximos Partidos Liga MX')

    try:
        futuros = upcoming_probabilities(df_partidos, df_proximos, modelo_params, metricas)
    except (ValueError, KeyError) as exc:
        state_message("Las predicciones están suspendidas hasta verificar la cobertura de los datos.",kind="blocked")
        st.caption("Usa «Actualizar resultados y calendario Liga MX» para verificar los datos.")
        futuros = pd.DataFrame()
    if futuros.empty:
        state_message('No hay partidos habilitados para predecir en los próximos siete días.',kind='empty')
    else:
        st.metric("Próximos partidos", len(futuros))
        st.caption("Probabilidades Over/Under 2.5 del modelo validado.")
        st.caption('Una tarjeta por partido con ambas probabilidades.')
        futuros=render_order(futuros,'liga_picks',date_col='inicio_utc',confidence_col='p_over25',upcoming=True)
        render_liga_matches(futuros)

# ==========================================================
# VISTA 1: RESULTADOS HISTÓRICOS
# ==========================================================
elif vista == "⚽ Resultados Históricos":
    st.subheader('Resultados Históricos Liga MX')

    if df_partidos.empty or df_probabilidades.empty:
        state_message('Todavía no hay partidos históricos disponibles.',kind='empty')
    else:
        df_probabilidades['resultado'] = np.where((df_probabilidades.goles_local+df_probabilidades.goles_visitante)>2.5,'GANADA','PERDIDA')
        df_probabilidades = performance_filters(df_probabilidades, 'fecha', 'liga_hist', season_col='season', probability_col='p_over25', probability_scale=100, result_col='resultado')
        df_partidos = df_probabilidades.copy()
        if df_partidos.empty:
            state_message('No hay partidos para los filtros seleccionados.',kind='filters'); st.stop()
        st.metric('Partidos evaluados',len(df_partidos))
        with st.expander('Estadísticas históricas de goles'):
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
        df_filtrado = render_order(df_probabilidades,'liga_hist',date_col='fecha',confidence_col='p_over25').reset_index(drop=True)
        st.caption('Evaluación histórica sin cuotas: no se calcula ROI ni beneficio en unidades.')

        # Mostrar los partidos
        for idx, row in history_window(df_filtrado,'liga_history').iterrows():
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
else:
    st.subheader('Historial Completo Liga MX')

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
