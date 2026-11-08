"""Interfaz de usuario para Totales de Partido NFL.

Diseño homologado con Tarjeta Universal de alta fidelidad, 3 métricas ejecutivas,
estrellas de confianza, botón flotante de boleta y menú analítico unificado con pestañas.
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from core.ui_controles import state_message
from core.ui_tarjetas import nfl_pick
from nfl.ui_lesiones_helper import crear_callback_lesiones_nfl

ZONA_MEXICO = ZoneInfo("America/Mexico_City")
RAIZ = Path(__file__).resolve().parents[1]


def filtrar_partidos_pendientes(datos: pd.DataFrame) -> pd.DataFrame:
    if datos.empty:
        return datos.copy()
    states = datos.resultado_pick.fillna("PENDIENTE").astype(str).str.strip().str.upper()
    return datos[~states.isin(["GANADA", "PERDIDA", "PUSH"])].copy()


def opciones_partidos(datos: pd.DataFrame) -> dict:
    """Construye etiquetas legibles y conserva el ID único para filtrar."""
    opciones = {"Todos los partidos": None}
    if datos.empty:
        return opciones

    juegos = (
        datos.sort_values("gameday", ascending=False, na_position="last")
        .drop_duplicates("id_juego")
    )
    for _, juego in juegos.iterrows():
        fecha = (
            juego["gameday"].strftime("%d/%m/%Y")
            if pd.notna(juego["gameday"]) else "Sin fecha"
        )
        etiqueta = (
            f"{juego['away_team']} @ {juego['home_team']} · {fecha}"
            f" · {int(juego['season'])} S{int(juego['week'])}"
        )
        opciones[etiqueta] = juego["id_juego"]
    return opciones


def formatear_numero(valor: Any, decimales: int = 2) -> str:
    if pd.isna(valor) or valor is None:
        return "N/D"
    try:
        return f"{float(valor):.{decimales}f}"
    except (ValueError, TypeError):
        return str(valor)


def formatear_porcentaje(valor: Any) -> str:
    if pd.isna(valor) or valor is None:
        return "N/D"
    try:
        return f"{float(valor) * 100:.2f}%"
    except (ValueError, TypeError):
        return str(valor)


def formatear_momio(valor: Any) -> str:
    if pd.isna(valor) or valor is None:
        return "N/D"
    try:
        val = float(valor)
        if val > 0:
            return f"+{val:.0f}"
        return f"{val:.0f}"
    except (ValueError, TypeError):
        return str(valor)


def html_seguro(valor: Any, defecto: str = "N/D") -> str:
    if valor is None or pd.isna(valor) or not str(valor).strip():
        return html.escape(defecto)
    return html.escape(str(valor).strip())


def cargar_predicciones_mysql():
    from nfl.repositorio import cargar_predicciones_mysql as read
    return read()


def mostrar_partido(fila: pd.Series):
    """Renderiza el partido con Tarjeta Universal homologada."""
    res = str(fila.get("resultado_pick") or "").strip().upper()
    es_resuelta = res in ("GANADA", "PERDIDA", "PUSH")

    away = str(fila.get("away_team") or "VIS")
    home = str(fila.get("home_team") or "LOC")

    if es_resuelta:
        # Tarjeta histórica para partidos finalizados
        away_sc = int(fila["marcador_visitante"]) if pd.notna(fila.get("marcador_visitante")) else (int(fila["away_score"]) if pd.notna(fila.get("away_score")) else 0)
        home_sc = int(fila["marcador_local"]) if pd.notna(fila.get("marcador_local")) else (int(fila["home_score"]) if pd.notna(fila.get("home_score")) else 0)
        tot_real = float(fila["total_real"]) if pd.notna(fila.get("total_real")) else float(away_sc + home_sc)
        u_val = float(fila.get("beneficio_unidades") or 0.0)

        if res == "GANADA":
            badge_res = f"<span style='background: rgba(183, 255, 60, 0.2); color: #b7ff3c; border: 1px solid #b7ff3c; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>✅ GANADA (+{u_val:.2f}u)</span>"
        elif res == "PERDIDA":
            badge_res = "<span style='background: rgba(255, 75, 75, 0.2); color: #ff6b6b; border: 1px solid #ff4b4b; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>❌ PERDIDA (-1.00u)</span>"
        else:
            badge_res = "<span style='background: rgba(255, 214, 0, 0.2); color: #ffd600; border: 1px solid #ffd600; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>🤝 PUSH (0.00u)</span>"

        with st.container(border=True):
            st.markdown(
                f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;'>"
                f"<span style='background: #192e22; color: #8fa899; padding: 0.2rem 0.55rem; border-radius: 6px; font-weight: 700; font-size: 0.75rem;'>FINAL: {away} {away_sc} – {home_sc} {home} · Total Real: {tot_real:.1f} pts</span>"
                f"{badge_res}"
                f"</div>"
                f"<div style='font-size: 1.15rem; font-weight: 800; color: #eef3f8;'>{away} @ {home}</div>"
                f"<div style='font-size: 0.85rem; color: #8fa899; margin-top:0.25rem;'>Selección recomendada: <b>{fila.get('pick')} {fila.get('total_line')}</b> · Línea Casa: {fila.get('total_line')} · Proy. Modelo: {float(fila.get('pred_total', 0)):.1f}</div>",
                unsafe_allow_html=True
            )
        return

    # Tarjeta Universal Homologada para partidos activos / pendientes
    from core.ui_tarjeta_universal import render_tarjeta_universal
    from core.ui_boleta import parsear_cuota_decimal

    fecha_dt = fila.get("gameday")
    fecha_str = fecha_dt.strftime("%d/%m/%Y") if pd.notna(fecha_dt) and hasattr(fecha_dt, "strftime") else str(fecha_dt or "")
    subtitulo = f"Semana {int(fila.get('week', 1))} · {fecha_str} · Bovada / ESPN"

    lin_total = float(fila["total_line"]) if pd.notna(fila.get("total_line")) else None
    proy_total = float(fila["pred_total"]) if pd.notna(fila.get("pred_total")) else None
    pick_sel = str(fila.get("pick") or "NO PICK").upper()
    seleccion_str = f"{pick_sel} {lin_total:g}" if (pick_sel in ("OVER", "UNDER") and lin_total is not None) else pick_sel

    odds_raw = fila.get("odds_pick")
    cuota_dec = float(parsear_cuota_decimal(odds_raw) or 1.909)
    ev_num = float(fila.get("ev", 0.0) or 0.0) * 100.0
    edge_num = float(fila.get("edge_absoluto", 0.0) or fila.get("edge", 0.0) or 0.0)
    es_pick = (fila.get("estado") == "PICK")

    if es_pick:
        if ev_num >= 10.0 or edge_num >= 4.0:
            estrellas = "⭐⭐⭐"
        elif ev_num >= 5.0 or edge_num >= 2.5:
            estrellas = "⭐⭐"
        elif ev_num > 0:
            estrellas = "⭐"
        else:
            estrellas = "⚪"
    else:
        estrellas = "⚪"

    tendencia = f"Proyección IA: {proy_total:.1f} pts · Ventaja: {edge_num:+.1f} pts vs línea {lin_total} · P({pick_sel}): {float(fila.get('prob_pick', 0.5))*100:.1f}%"

    alerta_contexto = None
    if pd.notna(fila.get("wind")) and float(fila.get("wind")) >= 15:
        alerta_contexto = f"💨 Alerta Meteorológica: Viento sostenido de {float(fila['wind']):.0f} mph (tiende a recortar juego aéreo)"

    # Menú Unificado: Pestaña 2 (Desglose de Mercados)
    def _render_totales_desglose():
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Desglose de Proyección del Modelo:**")
            st.markdown(f"- Proyección Ajustada: **{formatear_numero(fila.get('pred_total'), 1)} pts**")
            st.markdown(f"- Proyección Base: **{formatear_numero(fila.get('pred_total_base'), 1)} pts**")
            st.markdown(f"- Ventaja vs Línea (Edge): **{float(fila.get('edge', 0.0)):+.2f} pts**")
            if pd.notna(fila.get("wind")):
                st.markdown(f"- Viento pronosticado: **{float(fila['wind']):.0f} mph**")
        with c2:
            st.markdown("**Probabilidades Calibradas:**")
            st.markdown(f"- P(OVER {lin_total}): **{formatear_porcentaje(fila.get('prob_over'))}**")
            st.markdown(f"- P(UNDER {lin_total}): **{formatear_porcentaje(fila.get('prob_under'))}**")
            st.markdown(f"- Valor Esperado (+EV): **{ev_num:+.1f}%**")
            st.markdown(f"- Estatus del Sistema: **{fila.get('estado', 'PENDIENTE')}**")

    # Menú Unificado: Pestaña 3 (Reporte de Lesiones)
    fn_lesiones = crear_callback_lesiones_nfl(away, home)

    # Botón flotante de boleta
    tot_id = f"{fila.get('id_juego')}_total"
    slip_item = None
    if es_pick and pick_sel in ("OVER", "UNDER") and lin_total is not None:
        slip_item = {
            "id": f"NFL_TOT_{tot_id}_{pick_sel}",
            "deporte": "NFL",
            "icono": "🏈",
            "partido": f"{away} @ {home}",
            "mercado": "Totales",
            "seleccion": seleccion_str,
            "momio": str(odds_raw or "-110"),
            "prob": fila.get("prob_pick"),
        }

    render_tarjeta_universal(
        deporte="NFL",
        titulo=f"{away} @ {home}",
        subtitulo=subtitulo,
        mercado="🏈 Total del Partido",
        linea_casa=lin_total,
        proyeccion_modelo=proy_total,
        seleccion=seleccion_str,
        momio_americano=odds_raw,
        cuota_decimal=cuota_dec,
        ev_pct=ev_num,
        estrellas=estrellas,
        tendencia=tendencia,
        alerta_contexto=alerta_contexto,
        equipo=home,
        rival=away,
        desplegar_grafica_directa=False,
        key_suffix=f"nfl_tot_{tot_id}",
        etiqueta_linea="Línea Total",
        etiqueta_proyeccion="Proy. Total",
        boton_boleta=slip_item,
        contenido_desglose=_render_totales_desglose,
        contenido_lesiones=fn_lesiones,
        mostrar_grafica=True,
    )


def mostrar_resultado_total(fila: pd.Series):
    """Muestra el resultado histórico de una apuesta de Totales ya concluida."""
    mostrar_partido(fila)


# ==========================================================
# RENDER PRINCIPAL DE TOTALES NFL
# ==========================================================

def render():
    try:
        with st.spinner("Consultando predicciones guardadas…"):
            historico = cargar_predicciones_mysql()
    except Exception:
        state_message("No fue posible consultar las predicciones NFL. Reintenta cuando vuelva la conexión.", kind="offline")
        st.stop()

    if historico.empty:
        state_message("La base de datos todavía no contiene predicciones NFL.", kind="empty")
        st.stop()

    temporada = int(historico["season"].max())
    semana = int(
        historico.loc[
            historico["season"] == temporada,
            "week",
        ].max()
    )
    df = historico[
        (historico["season"] == temporada)
        & (historico["week"] == semana)
    ].copy()

    pendientes = filtrar_partidos_pendientes(df)
    picks = pendientes[pendientes["estado"] == "PICK"].copy()

    seccion_totales = st.radio(
        "Sección de totales",
        ["🔥 Picks filtrados", "📋 Todos los partidos", "📈 Rendimiento"],
        horizontal=True,
        format_func=lambda value: value.lstrip("🔥📋📈⚾🏈📊⚽🔮💼 "),
        label_visibility="collapsed",
        key="nfl_totales_seccion",
    )

    # Barra superior de botones
    from core.ui_actualizacion import render_update_button

    st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        render_update_button("nfl_totales", compact=True)
    with col2:
        if st.button("⚡ Actualizar Totales (0 Créditos · ESPN/Bovada)", key="btn_act_totales_nfl_free", type="primary", use_container_width=True, help="Consulta líneas en tiempo real desde ESPN y Bovada (0 créditos) y recalcula el modelo predictivo de Totales."):
            with st.spinner("Actualizando líneas de Totales y ejecutando modelo calibrado..."):
                import subprocess, sys
                res = subprocess.run([sys.executable, "nfl/predecir_semana_actual.py"], capture_output=True, text=True, timeout=600)
                if res.returncode == 0:
                    st.success("✅ ¡Líneas y Totales actualizados con éxito (0 Créditos)!")
                else:
                    st.warning("Líneas actualizadas con advertencias.")
                st.cache_data.clear()
                st.rerun()
    st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

    if seccion_totales != "📈 Rendimiento":
        finalizados = df[df["resultado_pick"].isin(["GANADA", "PERDIDA", "PUSH"]) | df.get("away_score", pd.Series(dtype=float)).notna()]
        num_finalizados = len(finalizados)
        num_pendientes = max(0, len(df) - num_finalizados)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total Partidos", len(df))
        with c2:
            st.metric("Pendientes", num_pendientes)
        with c3:
            st.metric("Finalizados", num_finalizados)
        with c4:
            st.metric("Picks de Alto Valor", len(picks))
        st.markdown("<div style='margin-bottom: 1.25rem;'></div>", unsafe_allow_html=True)

        # Filtros ejecutivos homologados con NBA y Fútbol
        f_col1, f_col2, f_col3 = st.columns([1.6, 1.2, 1.2], gap="medium")
        with f_col1:
            busqueda_tot = st.text_input(
                "Buscar equipo NFL",
                key="nfl_tot_search_input",
                placeholder="🔍 Ej: Chiefs, 49ers, Eagles, Cowboys...",
            ).strip().lower()
        with f_col2:
            st.markdown("<div style='margin-top: 1.8rem;'></div>", unsafe_allow_html=True)
            solo_ev_tot = st.checkbox(
                "🔥 Solo picks Calificados (+EV)",
                key="nfl_tot_ev_filter",
                value=(seccion_totales == "🔥 Picks filtrados"),
            )
        with f_col3:
            filtro_estado = st.selectbox(
                "Estado:",
                ["Solo Próximos (Por Jugar)", "Solo Finalizados", "Todos los partidos"],
                index=0 if seccion_totales != "📋 Todos los partidos" else 2,
                key="nfl_tot_filtro_estado",
            )

        base_mostrar = df.copy()

        # Filtrar por equipo
        if busqueda_tot:
            base_mostrar = base_mostrar[
                base_mostrar["home_team"].astype(str).str.lower().str.contains(busqueda_tot, na=False) |
                base_mostrar["away_team"].astype(str).str.lower().str.contains(busqueda_tot, na=False)
            ]

        # Filtro de Estado
        es_fin = base_mostrar["resultado_pick"].isin(["GANADA", "PERDIDA", "PUSH"]) | base_mostrar.get("away_score", pd.Series(dtype=float)).notna()
        if filtro_estado == "Solo Próximos (Por Jugar)":
            base_mostrar = base_mostrar[~es_fin]
        elif filtro_estado == "Solo Finalizados":
            base_mostrar = base_mostrar[es_fin]

        # Filtro "Solo Picks Calificados ordenados de Mayor a Menor EV%"
        if solo_ev_tot or seccion_totales == "🔥 Picks filtrados":
            base_mostrar = base_mostrar[
                (base_mostrar["estado"] == "PICK") |
                ((pd.to_numeric(base_mostrar.get("ev", 0.0), errors="coerce") > 0) &
                 (pd.to_numeric(base_mostrar.get("edge_absoluto", 0.0), errors="coerce") >= 2.0))
            ]
            if not base_mostrar.empty and "ev" in base_mostrar.columns:
                base_mostrar = base_mostrar.sort_values(by="ev", ascending=False).reset_index(drop=True)
            st.caption("🔥 Mostrando picks calificados ordenados de **Mayor a Menor Valor Esperado (+EV)**.")
        else:
            base_mostrar = base_mostrar.sort_values(
                ["ev", "edge_absoluto"],
                ascending=[False, False],
                na_position="last",
            ).reset_index(drop=True)

        if base_mostrar.empty:
            st.warning("No hay partidos o picks que coincidan con los filtros de búsqueda seleccionados.")
        else:
            for _, fila in base_mostrar.iterrows():
                mostrar_partido(fila)

    if seccion_totales == "📈 Rendimiento":
        from core.ui_historial_publicado import render_history
        render_history("NFL", "Totales", key="nfl_totales_perf")

    if seccion_totales != "📈 Rendimiento":
        from core.ui_boleta import render_widget_boleta
        render_widget_boleta()
