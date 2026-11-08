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
from core.ui_tarjeta_universal import render_tarjeta_universal

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

    # Ordenar estrictamente de Mayor a Menor EV% y deduplicar por jugador y mercado
    if not df_filtrado.empty and "ev_pct" in df_filtrado.columns:
        df_filtrado = df_filtrado.sort_values(by="ev_pct", ascending=False).reset_index(drop=True)
        # Evita mostrar múltiples tarjetas del mismo jugador en el mismo mercado (conserva la de mayor EV)
        df_filtrado = df_filtrado.drop_duplicates(subset=["player_name", "market"], keep="first").reset_index(drop=True)

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
        c_h1, c_h2, c_h3 = st.columns([2, 1, 1])
        with c_h1:
            st.markdown("##### 🎴 Oportunidades de Valor Seleccionadas")
        with c_h2:
            limite_tarjetas = st.selectbox(
                "Cantidad de tarjetas:",
                [50, 80, 120, "Todas"],
                index=1,
                key="nba_props_limite_cards",
            )
        with c_h3:
            desplegar_todas_graficas = st.toggle("📊 Desplegar gráficas", value=False, key="nba_props_toggle_graficas")

        n_cards = len(df_filtrado) if limite_tarjetas == "Todas" else int(limite_tarjetas)
        props_a_mostrar = df_filtrado.head(n_cards).to_dict(orient="records")
        cols = st.columns(2)

        for i, p in enumerate(props_a_mostrar):
            with cols[i % 2]:
                _renderizar_tarjeta_prop(p, desplegar_grafica_directa=desplegar_todas_graficas)

        if total_filtrado > n_cards:
            st.caption(f"Mostrando los mejores {n_cards} picks de {total_filtrado} disponibles. Aumenta el selector o consulta la pestaña 'Tabla Cuantitativa' para ver la lista completa.")

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


def _renderizar_tarjeta_prop(p: Dict[str, Any], desplegar_grafica_directa: bool = False):
    """Dibuja una tarjeta individual usando el componente universal homologado."""
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

    if boost_lesion > 0:
        if pick == "UNDER":
            alerta = f"⚠️ +{boost_lesion:.0f}% Uso por bajas (Proyección aún muy bajo línea)"
        else:
            alerta = f"🚨 +{boost_lesion:.0f}% Uso por bajas en el equipo"
    else:
        alerta = None
    rival_calc = p.get("away_team") if p.get("home_team") == equipo else p.get("home_team")

    render_tarjeta_universal(
        deporte="NBA",
        titulo=f"{nombre} ({equipo})",
        subtitulo=f"🏟️ {p.get('game', '')}",
        mercado=mercado,
        linea_casa=linea,
        proyeccion_modelo=proy,
        seleccion=f"{pick} {linea}",
        momio_americano=momio_am,
        cuota_decimal=cuota_dec,
        ev_pct=ev,
        estrellas=estrellas,
        tendencia=tendencia,
        alerta_contexto=alerta,
        jugador=nombre,
        equipo=equipo,
        rival=rival_calc,
        desplegar_grafica_directa=desplegar_grafica_directa,
        key_suffix=f"nba_prop_{p.get('bovada_game_id')}_{p.get('player_clean')}_{linea}",
        etiqueta_linea="Línea Bovada",
        etiqueta_proyeccion="Proyección",
    )

