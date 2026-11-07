"""Módulo de Rendimiento Diario Total Consolidado NBA (OVERDOG AI).
Unifica en una sola visión ejecutiva:
1. Totales de Partido (Over / Under)
2. Moneyline (Ganador Directo)
3. Spread (Línea de Puntos / Hándicap)

Permite auditar el rendimiento total de la NBA día por día (jornada a jornada),
eliminando la segmentación por mercados para ver el balance global real.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

from core.constants import ZONA_CDMX
from nba.registro import (
    cargar_historial_rendimiento,
    es_liquidacion_valida,
    liquidar_partidos_pendientes_nba,
)

logger = logging.getLogger(__name__)

MAPA_PILARES = {
    "Totales": "Totales",
    "Totales (OVER)": "Totales",
    "Totales (UNDER)": "Totales",
    "Totales de Partido": "Totales",
    "Moneyline": "Moneyline",
    "Moneyline (Ganador Directo)": "Moneyline",
    "Spread": "Spread",
    "Spread (Línea de Puntos)": "Spread",
}

NOMBRES_MERCADOS_LINDOS = {
    "Totales": "Totales de Partido",
    "Totales (OVER)": "Totales (OVER)",
    "Totales (UNDER)": "Totales (UNDER)",
    "Moneyline": "Moneyline (Ganador Directo)",
    "Spread": "Spread (Línea de Puntos)",
}


@st.cache_data(ttl=30)
def cargar_rendimiento_consolidado_nba() -> pd.DataFrame:
    """Carga y estandariza el historial completo de predicciones NBA desde MySQL o local."""
    df = cargar_historial_rendimiento()
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Normalizar fecha
    df["fecha_str"] = df["fecha"].astype(str).str[:10]
    df["fecha_dt"] = pd.to_datetime(df["fecha_str"], errors="coerce").dt.date

    # Normalizar pilares y nombres de mercado
    def _obtener_pilar(m_val: Any) -> str:
        m_str = str(m_val or "").strip()
        if "Totales" in m_str:
            return "Totales"
        if "Moneyline" in m_str:
            return "Moneyline"
        if "Spread" in m_str:
            return "Spread"
        return "Otro"

    df["pilar"] = df["mercado"].apply(_obtener_pilar)
    df["mercado_display"] = df["mercado"].map(lambda m: NOMBRES_MERCADOS_LINDOS.get(m, m))

    # Asegurar tipos numéricos
    df["cuota"] = pd.to_numeric(df["cuota"], errors="coerce").fillna(1.91)
    df["probabilidad"] = pd.to_numeric(df["probabilidad"], errors="coerce").fillna(0.5)
    df["edge"] = pd.to_numeric(df["edge"], errors="coerce").fillna(0.0)

    # Normalizar resultado
    df["resultado"] = df["resultado"].fillna("PENDIENTE").astype(str).str.strip().str.upper()

    # Normalizar unidades ganadas
    def _calcular_unidades(row: pd.Series) -> Optional[float]:
        u = row.get("unidades_ganadas")
        if pd.notna(u):
            return float(u)
        res = row.get("resultado")
        cuota = float(row.get("cuota") or 1.91)
        if res == "GANADA":
            return round(cuota - 1.0, 3)
        elif res == "PERDIDA":
            return -1.0
        elif res == "PUSH":
            return 0.0
        return None

    df["unidades"] = df.apply(_calcular_unidades, axis=1)

    # Construir columna descriptiva del partido
    eq_vis = df["equipo_visitante"].fillna("Visita").astype(str)
    eq_loc = df["equipo_local"].fillna("Local").astype(str)
    df["partido"] = eq_vis + " @ " + eq_loc

    # Marcador final
    def _formatear_marcador(r: pd.Series) -> str:
        ml = r.get("marcador_local")
        mv = r.get("marcador_visitante")
        if pd.notna(ml) and pd.notna(mv):
            try:
                ml_i = int(ml)
                mv_i = int(mv)
                if ml_i > 0 and mv_i > 0:
                    return f"{mv_i} - {ml_i}"
            except Exception:
                pass
        return "N/D"

    df["marcador_final"] = df.apply(_formatear_marcador, axis=1)

    return df


def render():
    """Renderiza la vista ejecutiva de Rendimiento Diario Total Consolidado de la NBA."""
    # 1. Header con estilo glassmorphic NBA
    st.markdown(
        """<div style="background: linear-gradient(135deg, #26150b 0%, #120904 100%);
        border: 1px solid #ff6b35; border-radius: 12px; padding: 1.15rem; margin-bottom: 1.2rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.6rem;">
        <div>
        <div style="font-size: 1.25rem; font-weight: 900; color: #ffffff; letter-spacing: 0.02em;">
        🏆 RENDIMIENTO DIARIO TOTAL CONSOLIDADO · <span style="color: #ff8c33;">NBA 360°</span>
        </div>
        <div style="color: #c9b9af; font-size: 0.83rem; margin-top: 0.2rem;">
        Auditoría unificada a 1 unidad plana: <b>Totales de Partido + Moneyline + Spread</b> agrupados día por día.
        </div>
        </div>
        <div>
        <span style="background: #381a0b; color: #ffaa66; padding: 0.35rem 0.85rem; border-radius: 8px; font-size: 0.8rem; font-weight: 800; border: 1px solid #ff6b35;">
        🏀 AUDITORÍA DIARIA EN VIVO
        </span>
        </div>
        </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # 2. Botones de acción superior
    c_btn1, c_btn2 = st.columns([1.5, 2.5])
    with c_btn1:
        if st.button("🏀 Liquidar / Sincronizar con ESPN", key="btn_sync_espn_nba_tot", type="primary", use_container_width=True):
            with st.spinner("Consultando marcadores oficiales en ESPN y liquidando partidos NBA..."):
                res = liquidar_partidos_pendientes_nba()
                cargar_rendimiento_consolidado_nba.clear()
                st.toast(res.get("mensaje", "Liquidación completada"), icon="✅")
                st.rerun()

    with c_btn2:
        if st.button("🔄 Recargar Historial de Rendimiento", key="btn_reload_nba_tot", use_container_width=True):
            cargar_rendimiento_consolidado_nba.clear()
            st.toast("Historial recargado desde la base de datos.", icon="🔄")
            st.rerun()

    df = cargar_rendimiento_consolidado_nba()
    if df.empty:
        st.info("No hay registros históricos de NBA disponibles en la base de datos.")
        return

    hoy_cdmx = datetime.now(ZONA_CDMX).date()
    fechas_disponibles = sorted([f for f in df["fecha_dt"].dropna().unique()], reverse=True)

    # 3. Controles de Filtrado
    with st.expander("🔍 Filtros de Auditoría: Periodo, Mercados y Confianza", expanded=True):
        col_f1, col_f2, col_f3 = st.columns([1.4, 1.4, 1.2], gap="medium")

        with col_f1:
            opciones_periodo = [
                "Toda la temporada (Cualquier fecha)",
                f"Hoy ({hoy_cdmx.strftime('%d-%b-%Y')})",
                "Ayer",
                "Últimos 7 días",
                "Últimos 14 días",
                "Rango personalizado",
            ]
            periodo = st.selectbox("📅 Periodo de Jornadas:", opciones_periodo, index=0, key="nba_tot_periodo")

        start_date: Optional[date] = None
        end_date: Optional[date] = None

        if periodo == f"Hoy ({hoy_cdmx.strftime('%d-%b-%Y')})":
            start_date = end_date = hoy_cdmx
        elif periodo == "Ayer":
            start_date = end_date = hoy_cdmx - timedelta(days=1)
        elif periodo == "Últimos 7 días":
            start_date = hoy_cdmx - timedelta(days=6)
            end_date = hoy_cdmx
        elif periodo == "Últimos 14 días":
            start_date = hoy_cdmx - timedelta(days=13)
            end_date = hoy_cdmx
        elif periodo == "Rango personalizado":
            c_r1, c_r2 = st.columns(2)
            start_date = c_r1.date_input("Desde", hoy_cdmx - timedelta(days=7), key="nba_tot_start")
            end_date = c_r2.date_input("Hasta", hoy_cdmx, key="nba_tot_end")

        with col_f2:
            mercados_disponibles = ["Totales", "Moneyline", "Spread"]
            mercados_sel = st.multiselect(
                "Mercados incluidos (vacío = todos):",
                options=mercados_disponibles,
                default=[],
                placeholder="Todos los mercados...",
                key="nba_tot_mercados_sel",
            )

        with col_f3:
            filtro_resultado = st.selectbox(
                "Estado de Resolución:",
                ["Todos los estados", "Solo Ganadas", "Solo Perdidas", "Solo Liquidados (Concluidos)", "Solo Pendientes"],
                index=3,  # Por defecto Solo Liquidados para ver rendimiento real
                key="nba_tot_resultado_filtro",
            )

        col_sub1, col_sub2 = st.columns(2)
        with col_sub1:
            confianza_sel = st.selectbox(
                "Nivel de Confianza:",
                ["Todas las confianzas", "Solo ALTA", "Solo MEDIA"],
                index=0,
                key="nba_tot_confianza_sel",
            )

        with col_sub2:
            filtro_dia_especifico = st.selectbox(
                "📆 Aislar Jornada / Día específico:",
                ["Todas las jornadas"] + [f.strftime("%Y-%m-%d") for f in fechas_disponibles],
                index=0,
                key="nba_tot_dia_especifico",
            )

    # Aplicar filtros a una copia
    df_f = df.copy()

    if start_date and end_date:
        df_f = df_f[(df_f["fecha_dt"] >= start_date) & (df_f["fecha_dt"] <= end_date)]

    if filtro_dia_especifico != "Todas las jornadas":
        df_f = df_f[df_f["fecha_str"] == filtro_dia_especifico]

    if mercados_sel:
        df_f = df_f[df_f["pilar"].isin(mercados_sel)]

    if confianza_sel == "Solo ALTA":
        df_f = df_f[df_f["confianza"] == "ALTA"]
    elif confianza_sel == "Solo MEDIA":
        df_f = df_f[df_f["confianza"] == "MEDIA"]

    if filtro_resultado == "Solo Ganadas":
        df_f = df_f[df_f["resultado"] == "GANADA"]
    elif filtro_resultado == "Solo Perdidas":
        df_f = df_f[df_f["resultado"] == "PERDIDA"]
    elif filtro_resultado == "Solo Liquidados (Concluidos)":
        df_f = df_f[df_f["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])]
    elif filtro_resultado == "Solo Pendientes":
        df_f = df_f[df_f["resultado"] == "PENDIENTE"]

    if df_f.empty:
        st.warning("No hay registros que coincidan con los filtros seleccionados.")
        return

    # 4. Cálculos ejecutivos globales
    liquidados = df_f[df_f["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()
    ganadas = int((liquidados["resultado"] == "GANADA").sum())
    perdidas = int((liquidados["resultado"] == "PERDIDA").sum())
    pushes = int((liquidados["resultado"] == "PUSH").sum())
    pendientes = int((df_f["resultado"] == "PENDIENTE").sum())

    total_evaluados = len(liquidados)
    win_rate = (ganadas / (ganadas + perdidas) * 100) if (ganadas + perdidas) > 0 else 0.0
    unidades_netas = float(liquidados["unidades"].sum(skipna=True))
    roi_global = (unidades_netas / total_evaluados * 100) if total_evaluados > 0 else 0.0

    # 5. Tarjetas Métricas Principales (Glassmorphic)
    st.markdown("<div style='margin-top: 0.6rem;'></div>", unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Picks Evaluados", f"{total_evaluados} picks", help=f"Picks en juego / pendientes: {pendientes}")
    with m2:
        st.metric("Acierto (Win Rate)", f"{win_rate:.1f}%", f"{ganadas}G - {perdidas}P" + (f" ({pushes} push)" if pushes > 0 else ""))
    with m3:
        color_u = "normal" if unidades_netas >= 0 else "inverse"
        st.metric("Beneficio Neto", f"{unidades_netas:+.2f} u")
    with m4:
        st.metric("ROI Consolidado", f"{roi_global:+.1f}%")

    st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

    # 6. Desglose por Pilar de Mercado NBA (3 Columnas)
    st.subheader("📊 Desglose por Mercado")
    c_p1, c_p2, c_p3 = st.columns(3)

    for pilar_nom, col_dest, icono in [
        ("Totales", c_p1, "🎯"),
        ("Moneyline", c_p2, "👑"),
        ("Spread", c_p3, "⚡"),
    ]:
        sub_df = liquidados[liquidados["pilar"] == pilar_nom]
        sub_tot = len(sub_df)
        sub_g = int((sub_df["resultado"] == "GANADA").sum())
        sub_p = int((sub_df["resultado"] == "PERDIDA").sum())
        sub_u = float(sub_df["unidades"].sum(skipna=True))
        sub_wr = (sub_g / (sub_g + sub_p) * 100) if (sub_g + sub_p) > 0 else 0.0
        sub_roi = (sub_u / sub_tot * 100) if sub_tot > 0 else 0.0

        p_color = "#4ade80" if sub_u > 0 else ("#f87171" if sub_u < 0 else "#cbd5e1")

        with col_dest:
            with st.container(border=True):
                st.markdown(
                    f"""<div style="font-weight: 800; font-size: 1.05rem; color: #ffffff; margin-bottom: 0.4rem;">
                    {icono} {pilar_nom}
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                    <span style="color: #a4978e; font-size: 0.85rem;">Picks Evaluados:</span>
                    <span style="font-weight: 800; color: #ffffff;">{sub_tot}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                    <span style="color: #a4978e; font-size: 0.85rem;">Récord:</span>
                    <span style="font-weight: 800; color: #ffffff;">{sub_g}G - {sub_p}P ({sub_wr:.1f}%)</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                    <span style="color: #a4978e; font-size: 0.85rem;">Unidades Netas:</span>
                    <span style="font-weight: 900; color: {p_color};">{sub_u:+.2f} u</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                    <span style="color: #a4978e; font-size: 0.85rem;">Retorno (ROI):</span>
                    <span style="font-weight: 900; color: {p_color};">{sub_roi:+.1f}%</span>
                    </div>""",
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='margin-bottom: 1.3rem;'></div>", unsafe_allow_html=True)

    # 7. RENDIMIENTO DIARIO TOTAL (Día por Día / Jornada por Jornada)
    st.subheader("📅 Rendimiento Diario Consolidado (Jornada por Jornada)")
    st.caption("Consolidación diaria de todas las apuestas NBA resueltas por fecha de juego.")

    fechas_en_vista = sorted(df_f["fecha_str"].dropna().unique().tolist(), reverse=True)

    # Tabla resumen día por día
    filas_dias = []
    for f_str in fechas_en_vista:
        sub_dia = liquidados[liquidados["fecha_str"] == f_str]
        tot_d = len(sub_dia)
        g_d = int((sub_dia["resultado"] == "GANADA").sum())
        p_d = int((sub_dia["resultado"] == "PERDIDA").sum())
        push_d = int((sub_dia["resultado"] == "PUSH").sum())
        u_d = float(sub_dia["unidades"].sum(skipna=True))
        wr_d = (g_d / (g_d + p_d) * 100) if (g_d + p_d) > 0 else 0.0
        roi_d = (u_d / tot_d * 100) if tot_d > 0 else 0.0

        # Conteo pendientes
        pend_d = int((df_f[(df_f["fecha_str"] == f_str) & (df_f["resultado"] == "PENDIENTE")]).shape[0])

        filas_dias.append({
            "Fecha": f_str,
            "Picks Evaluados": tot_d,
            "Récord": f"{g_d}G - {p_d}P" + (f" ({push_d} push)" if push_d > 0 else ""),
            "Acierto (%)": wr_d,
            "Unidades Netas": u_d,
            "ROI (%)": roi_d,
            "Pendientes": pend_d,
        })

    if filas_dias:
        df_dias_summary = pd.DataFrame(filas_dias)
        st.dataframe(
            df_dias_summary,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Fecha": st.column_config.TextColumn("Jornada (Fecha)", width="medium"),
                "Picks Evaluados": st.column_config.NumberColumn("Evaluados", width="small"),
                "Récord": st.column_config.TextColumn("Récord (G - P)", width="medium"),
                "Acierto (%)": st.column_config.NumberColumn("Win Rate", format="%.1f%%", width="small"),
                "Unidades Netas": st.column_config.NumberColumn("Beneficio", format="%+.2f u", width="small"),
                "ROI (%)": st.column_config.NumberColumn("ROI Diario", format="%+.1f%%", width="small"),
                "Pendientes": st.column_config.NumberColumn("En juego", width="small"),
            },
        )

    st.markdown("<div style='margin-bottom: 1.3rem;'></div>", unsafe_allow_html=True)

    # 8. Desglose Visual Día por Día (Tarjetas de Partidos y Picks)
    st.subheader("🏀 Detalle de Apuestas por Jornada")

    max_dias_mostrar = 10
    dias_a_mostrar = fechas_en_vista[:max_dias_mostrar]

    for f_str in dias_a_mostrar:
        df_dia_all = df_f[df_f["fecha_str"] == f_str]
        df_dia_liq = df_dia_all[df_dia_all["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])]
        
        tot_d = len(df_dia_liq)
        g_d = int((df_dia_liq["resultado"] == "GANADA").sum())
        p_d = int((df_dia_liq["resultado"] == "PERDIDA").sum())
        u_d = float(df_dia_liq["unidades"].sum(skipna=True))
        color_u_d = "#4ade80" if u_d > 0 else ("#f87171" if u_d < 0 else "#cbd5e1")
        
        # Parsear fecha a formato amigable
        try:
            f_obj = datetime.strptime(f_str, "%Y-%m-%d")
            dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            meses_esp = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            f_bonita = f"{dias_esp[f_obj.weekday()]} {f_obj.day} de {meses_esp[f_obj.month - 1]}, {f_obj.year}"
        except Exception:
            f_bonita = f_str

        with st.expander(f"📅 {f_bonita} · {g_d}G - {p_d}P · Balance: {u_d:+.2f} u ({len(df_dia_all)} picks)", expanded=(f_str == fechas_en_vista[0])):
            st.markdown(
                f"""<div style="display: flex; justify-content: space-between; align-items: center; background: #1a100a;
                border: 1px solid #ff6b35; border-radius: 8px; padding: 0.65rem 0.9rem; margin-bottom: 0.8rem;">
                <div>
                <span style="font-weight: 800; color: #ffffff; font-size: 0.95rem;">JORNADA {f_str}</span>
                <span style="color: #a4978e; font-size: 0.8rem; margin-left: 0.5rem;">({tot_d} evaluados, {len(df_dia_all) - tot_d} pendientes)</span>
                </div>
                <div>
                <span style="color: #a4978e; font-size: 0.8rem; font-weight: 700; margin-right: 0.4rem;">BALANCE JORNADA:</span>
                <span style="font-weight: 900; font-size: 1.05rem; color: {color_u_d};">{u_d:+.2f} u</span>
                </div>
                </div>""",
                unsafe_allow_html=True,
            )

            # Iterar por partidos de ese día
            partidos_del_dia = df_dia_all.groupby(["equipo_visitante", "equipo_local"], sort=False)
            for (eq_vis, eq_loc), g_partido in partidos_del_dia:
                h_cdmx = g_partido["hora_cdmx"].iloc[0] if "hora_cdmx" in g_partido.columns else "TBD"
                m_fin = g_partido["marcador_final"].iloc[0] if "marcador_final" in g_partido.columns else "N/D"
                u_partido = float(g_partido["unidades"].sum(skipna=True))
                color_p = "#4ade80" if u_partido > 0 else ("#f87171" if u_partido < 0 else "#cbd5e1")

                with st.container(border=True):
                    st.markdown(
                        f"""<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.45rem;">
                        <span style="font-size: 0.8rem; color: #a4978e;">⏰ {h_cdmx} CDMX</span>
                        <span style="font-size: 0.82rem; font-weight: 800; color: {color_p};">Balance: {u_partido:+.2f} u</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
                        <div style="font-weight: 800; font-size: 1rem; color: #ffffff;">{eq_vis} @ {eq_loc}</div>
                        <div style="font-weight: 900; font-size: 0.95rem; color: #ff8c33; background: #22140a; padding: 0.2rem 0.5rem; border-radius: 6px; border: 1px solid #ff6b35;">{m_fin}</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    for _, p_row in g_partido.iterrows():
                        res_p = p_row.get("resultado", "PENDIENTE")
                        u_p = p_row.get("unidades")
                        color_res = "#4ade80" if res_p == "GANADA" else ("#f87171" if res_p == "PERDIDA" else "#cbd5e1")
                        str_u = f"+{u_p:.2f} u" if (pd.notna(u_p) and u_p > 0) else (f"{u_p:.2f} u" if pd.notna(u_p) else "0.00 u")

                        badge_mercado = p_row.get("pilar", "NBA")
                        color_badge = "#ff8c33" if badge_mercado == "Totales" else ("#ffd166" if badge_mercado == "Moneyline" else "#06d6a0")

                        st.markdown(
                            f"""<div style="background: #140d08; border-radius: 6px; padding: 0.5rem 0.75rem; margin-bottom: 0.35rem; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                            <span style="background: #2b180f; color: {color_badge}; border: 1px solid {color_badge}; font-size: 0.72rem; font-weight: 800; padding: 0.15rem 0.45rem; border-radius: 4px; margin-right: 0.4rem;">{p_row.get('mercado')}</span>
                            <span style="font-weight: 700; color: #ffffff; font-size: 0.9rem;">{p_row.get('seleccion')}</span>
                            <span style="color: #a4978e; font-size: 0.78rem; margin-left: 0.4rem;">(Cuota: {p_row.get('cuota', 1.91):.2f} · Prob: {float(p_row.get('probabilidad', 0.5))*100:.1f}%)</span>
                            </div>
                            <div style="font-weight: 900; font-size: 0.92rem; color: {color_res};">
                            {res_p} ({str_u})
                            </div>
                            </div>""",
                            unsafe_allow_html=True,
                        )

    if len(fechas_en_vista) > max_dias_mostrar:
        st.info(f"ℹ️ Mostrando las {max_dias_mostrar} jornadas más recientes de {len(fechas_en_vista)}. Utiliza los filtros superiores para aislar cualquier fecha específica.")

    st.markdown("<div style='margin-bottom: 1.3rem;'></div>", unsafe_allow_html=True)

    # 9. Tabla Detallada de Auditoría NBA
    st.subheader(f"📋 Auditoría Completa de Picks NBA ({len(df_f)} registros)")

    display_df = df_f[[
        "fecha_str", "hora_cdmx", "partido", "marcador_final",
        "pilar", "mercado_display", "seleccion", "linea", "cuota", "probabilidad", "confianza", "resultado", "unidades"
    ]].copy().rename(columns={
        "fecha_str": "Fecha",
        "hora_cdmx": "Hora CDMX",
        "partido": "Partido",
        "marcador_final": "Marcador Final",
        "pilar": "Pilar",
        "mercado_display": "Mercado",
        "seleccion": "Selección",
        "linea": "Línea",
        "cuota": "Momio",
        "probabilidad": "Prob. Modelo",
        "confianza": "Confianza",
        "resultado": "Resultado",
        "unidades": "Unidades (u)",
    })

    table_cfg = {
        "Fecha": st.column_config.TextColumn("Fecha", width="small"),
        "Hora CDMX": st.column_config.TextColumn("Hora", width="small"),
        "Partido": st.column_config.TextColumn("Partido", width="medium"),
        "Marcador Final": st.column_config.TextColumn("Marcador", width="small"),
        "Pilar": st.column_config.TextColumn("Pilar", width="small"),
        "Mercado": st.column_config.TextColumn("Mercado", width="medium"),
        "Selección": st.column_config.TextColumn("Selección", width="medium"),
        "Línea": st.column_config.NumberColumn("Línea", format="%.1f", width="small"),
        "Momio": st.column_config.NumberColumn("Momio", format="%.2f", width="small"),
        "Prob. Modelo": st.column_config.NumberColumn("Prob.", format="%.1f%%", width="small"),
        "Confianza": st.column_config.TextColumn("Confianza", width="small"),
        "Resultado": st.column_config.TextColumn("Resultado", width="small"),
        "Unidades (u)": st.column_config.NumberColumn("Unidades", format="%+.2f u", width="small"),
    }

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config=table_cfg,
    )

    # 10. Botón de descarga CSV
    csv_data = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Descargar Rendimiento Diario Consolidado NBA (CSV)",
        data=csv_data,
        file_name=f"rendimiento_diario_total_nba_{datetime.now(ZONA_CDMX).strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
