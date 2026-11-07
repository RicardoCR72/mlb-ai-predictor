"""Módulo de interfaz visual para Player Props de la NBA en Streamlit.

Permite explorar los props de jugadores del día con:
* Líneas y momios en tiempo real desde Bovada (0 créditos).
* Filtros por partido, mercado (Puntos, Rebotes, Asistencias, Triples, PRA), estrellas y EV%.
* Tarjetas de alta fidelidad con proyección vs línea, hit rate y alerta de lesiones.
* Tabla completa de auditoría cuantitativa.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
RUTA_PRED_PARQUET = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.parquet"
RUTA_PRED_JSON = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.json"

from nba.predecir_props import generar_predicciones_props_hoy
from nba.servicio_bovada_props import extraer_props_nba

NOMBRES_MERCADOS_ES = {
    "Total Points": "🏀 Puntos",
    "Total Rebounds": "🛡️ Rebotes",
    "Total Assists": "🎯 Asistencias",
    "Total Triples": "🏹 Triples",
    "Total PRA": "⚡ Puntos + Rebotes + Asistencias (PRA)",
    "Total PR": "📊 Puntos + Rebotes (PR)",
    "Total PA": "🎨 Puntos + Asistencias (PA)",
}


@st.cache_data(ttl=600, show_spinner=False)
def cargar_predicciones_props() -> pd.DataFrame:
    """Carga las predicciones guardadas en disco o las genera si no existen."""
    if RUTA_PRED_PARQUET.exists():
        try:
            return pd.read_parquet(RUTA_PRED_PARQUET)
        except Exception:
            pass
    if RUTA_PRED_JSON.exists():
        try:
            with open(RUTA_PRED_JSON, "r", encoding="utf-8") as f:
                return pd.DataFrame(json.load(f))
        except Exception:
            pass
    return pd.DataFrame()


def renderizar_ui_props_nba():
    """Renderiza la sección completa de Player Props de la NBA."""
    st.markdown("### 🎯 Player Props NBA — Inteligencia de Líneas (0 Créditos)")
    st.caption("Motor de cuotas y líneas en tiempo real provisto por **Bovada**, sin consumir tu cuota mensual de The Odds API.")

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        if st.button("🔄 Actualizar Líneas en Vivo", use_container_width=True, type="primary"):
            with st.spinner("Descargando líneas frescas de Bovada y proyectando con lesiones..."):
                extraer_props_nba(usar_cache=False)
                df_fresco = generar_predicciones_props_hoy(usar_cache_bovada=True)
                st.cache_data.clear()
                st.success(f"¡Líneas actualizadas! Se analizaron {len(df_fresco)} props.")
                st.rerun()

    df_props = cargar_predicciones_props()

    if df_props.empty:
        st.info("ℹ️ No hay predicciones de props en caché todavía. Haz clic en **Actualizar Líneas en Vivo** para procesar la cartelera de hoy.")
        if st.button("🚀 Generar Props Ahora"):
            with st.spinner("Procesando cartelera completa de NBA..."):
                generar_predicciones_props_hoy(usar_cache_bovada=False)
                st.cache_data.clear()
                st.rerun()
        return

    # Controles y Filtros
    st.markdown("---")
    c_partido, c_mercado, c_conf, c_tipo = st.columns(4)

    # 1. Filtro por Partido
    partidos_unicos = ["Todos los partidos"] + sorted(df_props["game"].dropna().unique().tolist())
    partido_sel = c_partido.selectbox("🏟️ Partido:", partidos_unicos)

    # 2. Filtro por Mercado
    mercados_disp = sorted(df_props["market"].dropna().unique().tolist())
    opciones_mercado = {"Todos los mercados": None}
    for m in mercados_disp:
        etiqueta = NOMBRES_MERCADOS_ES.get(m, m)
        opciones_mercado[etiqueta] = m
    mercado_sel_label = c_mercado.selectbox("📊 Mercado:", list(opciones_mercado.keys()))
    mercado_sel = opciones_mercado[mercado_sel_label]

    # 3. Filtro por Confianza / EV
    opciones_conf = {
        "⭐ Solo Picks de Valor (EV > 0%)": 0.0,
        "⭐⭐ Alta Confianza (EV ≥ 5%)": 5.0,
        "⭐⭐⭐ Top Picks (EV ≥ 10%)": 10.0,
        "Todos los props (Incluye EV negativo)": -999.0,
    }
    conf_sel_label = c_conf.selectbox("🔥 Nivel de Valor / EV:", list(opciones_conf.keys()))
    ev_minimo = opciones_conf[conf_sel_label]

    # 4. Filtro por Selección
    tipo_sel = c_tipo.selectbox("🎯 Selección:", ["Todos", "Solo OVER", "Solo UNDER"])

    # Buscador de jugador
    busqueda_jugador = st.text_input("🔍 Buscar jugador específico (ej. Jokic, Curry, Edwards, Tatum):", "")

    # Aplicar Filtros
    df_filtrado = df_props.copy()
    if partido_sel != "Todos los partidos":
        df_filtrado = df_filtrado[df_filtrado["game"] == partido_sel]

    if mercado_sel:
        df_filtrado = df_filtrado[df_filtrado["market"] == mercado_sel]

    if ev_minimo > -500:
        df_filtrado = df_filtrado[df_filtrado["ev_pct"] >= ev_minimo]

    if tipo_sel == "Solo OVER":
        df_filtrado = df_filtrado[df_filtrado["pick_type"] == "OVER"]
    elif tipo_sel == "Solo UNDER":
        df_filtrado = df_filtrado[df_filtrado["pick_type"] == "UNDER"]

    if busqueda_jugador.strip():
        q = busqueda_jugador.strip().lower()
        df_filtrado = df_filtrado[df_filtrado["player_name"].str.lower().str.contains(q)]

    # KPIs de la Selección
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    total_filtrado = len(df_filtrado)
    kpi1.metric("Picks Filtrados", f"{total_filtrado}")
    
    top_ev = df_filtrado["ev_pct"].max() if not df_filtrado.empty else 0.0
    kpi2.metric("Mejor EV%", f"+{top_ev:.1f}%" if top_ev > 0 else f"{top_ev:.1f}%")
    
    picks_3estrellas = (df_filtrado["stars"] == "⭐⭐⭐").sum() if not df_filtrado.empty else 0
    kpi3.metric("Top Picks ⭐⭐⭐", f"{picks_3estrellas}")

    cuota_media = df_filtrado["pick_odds_decimal"].median() if not df_filtrado.empty else 1.90
    kpi4.metric("Momio Promedio", f"{cuota_media:.2f} dec")

    st.markdown("---")

    if df_filtrado.empty:
        st.warning("⚠️ No se encontraron props con los filtros aplicados. Intenta ampliar los criterios de búsqueda.")
        return

    # Pestañas de Vista: Tarjetas vs Tabla
    tab_cards, tab_tabla = st.tabs(["🎴 Tarjetas de Oportunidades", "📋 Tabla Cuantitativa Completa"])

    with tab_cards:
        # Renderizar en cuadrícula de 2 columnas
        props_a_mostrar = df_filtrado.head(40).to_dict(orient="records")
        cols = st.columns(2)

        for i, p in enumerate(props_a_mostrar):
            with cols[i % 2]:
                _renderizar_tarjeta_prop(p)

        if total_filtrado > 40:
            st.caption(f"Mostrando los mejores 40 picks de {total_filtrado} disponibles. Consulta la pestaña 'Tabla Cuantitativa' para ver la lista completa.")

    with tab_tabla:
        columnas_tabla = [
            "player_name", "team", "market", "line", "projection",
            "pick_type", "pick_odds_american", "pick_odds_decimal",
            "model_prob", "implied_prob", "ev_pct", "stars", "hit_rate_season", "hit_rate_l5", "trend"
        ]
        df_display = df_filtrado[columnas_tabla].copy()
        df_display.rename(columns={
            "player_name": "Jugador",
            "team": "Equipo",
            "market": "Mercado",
            "line": "Línea",
            "projection": "Proy. Modelo",
            "pick_type": "Pick",
            "pick_odds_american": "Momio",
            "pick_odds_decimal": "Cuota Dec",
            "model_prob": "Prob. Modelo",
            "implied_prob": "Prob. Casa",
            "ev_pct": "EV %",
            "stars": "Confianza",
            "hit_rate_season": "Hit Rate Temp",
            "hit_rate_l5": "Hit Rate L5",
            "trend": "Tendencia",
        }, inplace=True)

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "EV %": st.column_config.NumberColumn(format="+%.1f%%"),
                "Prob. Modelo": st.column_config.NumberColumn(format="%.1f%%"),
                "Prob. Casa": st.column_config.NumberColumn(format="%.1f%%"),
                "Hit Rate Temp": st.column_config.NumberColumn(format="%.0f%%"),
                "Hit Rate L5": st.column_config.NumberColumn(format="%.0f%%"),
            }
        )


def _renderizar_tarjeta_prop(p: Dict[str, Any]):
    """Dibuja una tarjeta individual con diseño limpio y métricas visuales."""
    nombre = p["player_name"]
    equipo = p["team"]
    mercado = NOMBRES_MERCADOS_ES.get(p["market"], p["market"])
    linea = p["line"]
    proy = p["projection"]
    pick = p["pick_type"]
    momio_am = p.get("pick_odds_american", "-110")
    cuota_dec = p.get("pick_odds_decimal", 1.909)
    ev = p["ev_pct"]
    estrellas = p.get("stars", "⭐")
    tendencia = p.get("trend", "")
    boost_lesion = p.get("boost_lesion_pct", 0.0)

    color_pick = "#10B981" if pick == "OVER" else "#3B82F6"
    color_ev = "#10B981" if ev >= 5.0 else ("#F59E0B" if ev > 0 else "#EF4444")

    # Contenedor con borde
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"**{nombre}** `({equipo})` · {mercado}")
            st.caption(f"🏟️ {p.get('game', '')}")
        with c2:
            st.markdown(f"<div style='text-align:right;'><span style='font-size:1.1rem;'>{estrellas}</span><br><b style='color:{color_ev};'>+{ev:.1f}% EV</b></div>", unsafe_allow_html=True)

        # Métricas de Proyección
        m1, m2, m3 = st.columns(3)
        m1.metric("Línea Bovada", f"{linea}")
        m2.metric("Proyección", f"{proy:.1f}")
        m3.markdown(
            f"<div style='background:{color_pick}22; padding:6px 10px; border-radius:8px; border:1px solid {color_pick}; text-align:center; margin-top:4px;'>"
            f"<b style='color:{color_pick}; font-size:1.05rem;'>{pick} {linea}</b><br>"
            f"<span style='font-size:0.85rem;'>{momio_am} ({cuota_dec:.2f})</span>"
            f"</div>",
            unsafe_allow_html=True
        )

        st.caption(f"📈 **Tendencia:** {tendencia}")
        if boost_lesion > 0:
            st.markdown(f"<span style='background:#EF444422; color:#EF4444; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:600;'>🚨 +{boost_lesion:.0f}% Uso por bajas en el equipo</span>", unsafe_allow_html=True)
