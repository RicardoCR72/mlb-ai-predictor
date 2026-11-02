"""Módulo de Rendimiento Total Consolidado NFL (OVERDOG AI).
Unifica en una sola visión ejecutiva:
1. Moneyline (Ganador Directo)
2. Totales de Partido (Over / Under)
3. Props de Jugadores (Yardas recepción, recepciones, pases, touchdowns, terrestres)
Permite auditar el resumen completo de la jornada de hoy o de cualquier fecha/semana de la NFL.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st

from core.db import get_db_connection
from core.constants import ZONA_CDMX

NOMBRES_MERCADOS = {
    "Moneyline": "Moneyline (1X2)",
    "Totales": "Totales (Over/Under)",
    "receiving_yards": "Yardas de recepción",
    "receptions": "Recepciones",
    "passing_yards": "Yardas por pase",
    "passing_tds": "Pases de touchdown",
    "rushing_yards": "Yardas terrestres",
    "anytime_td": "Anota touchdown",
}


def fecha_a_semana_nfl(dt: Any) -> Optional[int]:
    """Calcula la semana oficial NFL 2026 a partir de la fecha de juego (Semana 1 = 8 Sep 2026)."""
    if dt is None or pd.isna(dt):
        return None
    if isinstance(dt, datetime):
        dt = dt.date()
    elif isinstance(dt, str):
        try:
            dt = datetime.strptime(str(dt)[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    # Inicio oficial Semana 1 temporada 2026 (martes previo al Kickoff)
    inicio_temp = date(2026, 9, 8)
    dias = (dt - inicio_temp).days
    return int((dias // 7) + 1) if dias >= 0 else 1


@st.cache_data(ttl=30)
def cargar_rendimiento_consolidado_nfl() -> pd.DataFrame:
    """Extrae y unifica los tres registros oficiales de NFL desde MySQL con su respectiva semana."""
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)

        # 1. Moneyline
        c.execute("""
            SELECT id_prediccion, id_juego, fecha_cdmx as fecha_str, hora_cdmx, partido,
                   equipo_local, equipo_visita as equipo_visitante,
                   'Moneyline' as pilar, 'Moneyline' as mercado_raw,
                   'Equipo' as jugador, seleccion, 'N/D' as linea,
                   CONCAT(COALESCE(marcador_visita, 0), ' - ', COALESCE(marcador_local, 0)) as valor_real,
                   cuota_pick as cuota, cuota_dec, probabilidad_pick as probabilidad,
                   confianza, resultado_pick as resultado, beneficio_unidades as unidades,
                   NULL as semana_raw
            FROM nfl_predicciones_moneyline
            WHERE confianza IN ('ALTA', 'MEDIA')
        """)
        filas_ml = c.fetchall()

        # 2. Totales
        c.execute("""
            SELECT p.id_prediccion, p.id_juego, DATE_FORMAT(j.fecha, '%Y-%m-%d') as fecha_str, 'N/D' as hora_cdmx,
                   CONCAT(j.equipo_visitante, ' @ ', j.equipo_local) as partido,
                   j.equipo_local, j.equipo_visitante,
                   'Totales' as pilar, 'Totales' as mercado_raw,
                   'Partido' as jugador, p.seleccion, CAST(p.linea_total AS CHAR) as linea,
                   CAST(COALESCE(p.total_real, 'N/D') AS CHAR) as valor_real,
                   p.cuota_pick as cuota, NULL as cuota_dec,
                   p.probabilidad_pick / 100.0 as probabilidad,
                   p.estado_pick as confianza, p.resultado_pick as resultado,
                   p.beneficio_unidades as unidades,
                   CAST(j.semana AS CHAR) as semana_raw
            FROM nfl_predicciones_totales p
            JOIN nfl_juegos j ON j.id_juego = p.id_juego
            WHERE p.estado_pick = 'PICK'
        """)
        filas_tot = c.fetchall()

        # 3. Props
        c.execute("""
            SELECT p.id_proyeccion as id_prediccion, p.id_juego, DATE_FORMAT(j.fecha, '%Y-%m-%d') as fecha_str, 'N/D' as hora_cdmx,
                   CONCAT(j.equipo_visitante, ' @ ', j.equipo_local) as partido,
                   j.equipo_local, j.equipo_visitante,
                   'Props de Jugadores' as pilar, p.tipo_prop as mercado_raw,
                   ju.nombre as jugador, p.seleccion, CAST(p.linea AS CHAR) as linea,
                   CAST(COALESCE(p.valor_real, 'N/D') AS CHAR) as valor_real,
                   p.cuota_pick as cuota, NULL as cuota_dec,
                   p.probabilidad_pick as probabilidad,
                   p.estado_pick as confianza, p.resultado_pick as resultado,
                   p.beneficio_unidades as unidades,
                   CAST(j.semana AS CHAR) as semana_raw
            FROM nfl_proyecciones_props p
            JOIN nfl_juegos j ON j.id_juego = p.id_juego
            JOIN nfl_jugadores ju ON ju.id_jugador = p.id_jugador
            WHERE p.estado_pick IN ('CANDIDATO', 'REVISAR LESION')
        """)
        filas_props = c.fetchall()

    except Exception as exc:
        st.warning(f"Error conectando a base de datos NFL: {exc}")
        filas_ml, filas_tot, filas_props = [], [], []
    finally:
        if conn and conn.is_connected():
            conn.close()

    registros = filas_ml + filas_tot + filas_props
    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    df["fecha"] = pd.to_datetime(df["fecha_str"], errors="coerce").dt.date
    df["mercado"] = df["mercado_raw"].map(lambda m: NOMBRES_MERCADOS.get(m, m))
    df["unidades"] = pd.to_numeric(df["unidades"], errors="coerce")
    df["probabilidad"] = pd.to_numeric(df["probabilidad"], errors="coerce")
    df["resultado"] = df["resultado"].fillna("PENDIENTE").astype(str).str.strip().str.upper()

    # Cálculo y asignación de semana oficial
    df["semana"] = pd.to_numeric(df["semana_raw"], errors="coerce")
    df["semana"] = df["semana"].fillna(df["fecha"].apply(fecha_a_semana_nfl)).astype("Int64")

    return df


def render():
    """Renderiza la vista ejecutiva de Rendimiento Total Consolidado NFL."""
    st.markdown(
        """<div style="background: linear-gradient(135deg, #0d1e15 0%, #06110a 100%);
        border: 1px solid #1a422b; border-radius: 12px; padding: 1.1rem; margin-bottom: 1.2rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
        <div>
        <div style="font-size: 1.2rem; font-weight: 900; color: #ffffff;">
        🏆 RENDIMIENTO TOTAL CONSOLIDADO · <span style="color: #00e676;">NFL 360°</span>
        </div>
        <div style="color: #94a3b8; font-size: 0.82rem; margin-top: 0.15rem;">
        Auditoría unificada a 1 unidad plana: <b>Moneyline + Totales de Partido + Props de Jugadores</b>.
        </div>
        </div>
        <div>
        <span style="background: #092416; color: #00e676; padding: 0.3rem 0.75rem; border-radius: 8px; font-size: 0.78rem; font-weight: 800; border: 1px solid #00e676;">
        AUDITORÍA OFICIAL EN VIVO
        </span>
        </div>
        </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Botón de liquidación en vivo con ESPN
    c_btn1, c_btn2 = st.columns([1.5, 2.5])
    with c_btn1:
        if st.button("🏈 Sincronizar y Liquidar con ESPN", type="primary", use_container_width=True):
            with st.spinner("Consultando marcadores y boxscores en ESPN..."):
                from nfl.actualizar_nfl import ejecutar_pipeline_nfl
                res = ejecutar_pipeline_nfl()
                cargar_rendimiento_consolidado_nfl.clear()
                msg = res.get("mensaje", "Liquidación completada.")
                st.toast(msg, icon="✅")
                st.rerun()

    df = cargar_rendimiento_consolidado_nfl()
    if df.empty:
        st.info("No hay registros de NFL disponibles en este momento.")
        return

    # Controles de Filtrado
    hoy_cdmx = datetime.now(ZONA_CDMX).date()
    semanas_disponibles = sorted([int(s) for s in df["semana"].dropna().unique()], reverse=True)

    with st.expander("🔍 Filtros de Auditoría: Semana, Periodo y Mercados", expanded=True):
        col_sem, col_f1, col_f2 = st.columns([1.2, 1.2, 1.6], gap="medium")
        
        with col_sem:
            opciones_semana = ["Todas las semanas"] + [
                f"Semana {s}" + (" (Actual)" if s == 8 else "") for s in semanas_disponibles
            ]
            semana_sel_str = st.selectbox(
                "🏈 Filtrar por Semana NFL:",
                opciones_semana,
                index=0,
                key="nfl_total_semana_sel",
            )

        with col_f1:
            periodo = st.selectbox(
                "Periodo / Fecha:",
                [
                    "Cualquier fecha (Toda la temporada)",
                    "Hoy (Domingo 1 de Noviembre)",
                    "Últimos 7 días",
                    "Rango personalizado",
                ],
                key="nfl_total_periodo",
            )

        start_date = end_date = None
        if periodo == "Hoy (Domingo 1 de Noviembre)":
            start_date = end_date = date(2026, 11, 1)
        elif periodo == "Últimos 7 días":
            start_date = hoy_cdmx - timedelta(days=6)
            end_date = hoy_cdmx
        elif periodo == "Rango personalizado":
            c_r1, c_r2 = st.columns(2)
            start_date = c_r1.date_input("Desde", hoy_cdmx - timedelta(days=7), key="nfl_tot_start")
            end_date = c_r2.date_input("Hasta", hoy_cdmx, key="nfl_tot_end")

        # Filtrar por fecha
        df_f = df.copy()
        if start_date and end_date:
            df_f = df_f[(df_f["fecha"] >= start_date) & (df_f["fecha"] <= end_date)]

        # Filtrar por semana si se seleccionó una
        if semana_sel_str != "Todas las semanas":
            num_sem = int(semana_sel_str.replace("Semana ", "").split()[0])
            df_f = df_f[df_f["semana"] == num_sem]

        with col_f2:
            mercados_disponibles = sorted(df_f["mercado"].unique().tolist())
            mercados_sel = st.multiselect(
                "Mercados incluidos (vacío = todos):",
                options=mercados_disponibles,
                default=[],
                placeholder="Todos los mercados...",
                key="nfl_tot_mercados_sel",
            )

        if mercados_sel:
            df_f = df_f[df_f["mercado"].isin(mercados_sel)]

        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            mercados_excluir = st.multiselect(
                "🚫 Excluir mercados específicos (ej. Yardas terrestres):",
                options=sorted(df["mercado"].unique().tolist()),
                default=[],
                placeholder="Ninguno excluido...",
                key="nfl_tot_excluir",
            )
            if mercados_excluir:
                df_f = df_f[~df_f["mercado"].isin(mercados_excluir)]

        with col_ex2:
            filtro_resultado = st.selectbox(
                "Estado de Resolución:",
                ["Todos los estados", "Solo Ganadas", "Solo Perdidas", "Solo Liquidados (Concluidos)", "Solo Pendientes"],
                key="nfl_tot_resultado_filtro",
            )
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

    # Cálculos globales
    liquidados = df_f[df_f["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()
    ganadas = int((liquidados["resultado"] == "GANADA").sum())
    perdidas = int((liquidados["resultado"] == "PERDIDA").sum())
    pushes = int((liquidados["resultado"] == "PUSH").sum())
    pendientes = int((df_f["resultado"] == "PENDIENTE").sum())

    total_evaluados = len(liquidados)
    win_rate = (ganadas / (ganadas + perdidas) * 100) if (ganadas + perdidas) > 0 else 0.0
    unidades_netas = float(liquidados["unidades"].sum(skipna=True))
    roi_global = (unidades_netas / total_evaluados * 100) if total_evaluados > 0 else 0.0

    # 4 Tarjetas Métricas Principales
    st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Picks Evaluados", f"{total_evaluados} picks", help=f"Pendientes: {pendientes}")
    with m2:
        st.metric("Acierto (Win Rate)", f"{win_rate:.1f}%", f"{ganadas}G - {perdidas}P" + (f" ({pushes} push)" if pushes > 0 else ""))
    with m3:
        st.metric("Beneficio Neto", f"{unidades_netas:+.2f} u")
    with m4:
        st.metric("ROI Consolidado", f"{roi_global:+.1f}%")

    st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

    # 3 Pilares en 3 Columnas Destacadas
    st.subheader("📊 Desglose por Pilar de Mercado")
    c_p1, c_p2, c_p3 = st.columns(3)

    for pilar_nom, col_dest in [("Moneyline", c_p1), ("Totales", c_p2), ("Props de Jugadores", c_p3)]:
        sub_df = liquidados[liquidados["pilar"] == pilar_nom]
        sub_tot = len(sub_df)
        sub_g = int((sub_df["resultado"] == "GANADA").sum())
        sub_p = int((sub_df["resultado"] == "PERDIDA").sum())
        sub_u = float(sub_df["unidades"].sum(skipna=True))
        sub_wr = (sub_g / (sub_g + sub_p) * 100) if (sub_g + sub_p) > 0 else 0.0
        sub_roi = (sub_u / sub_tot * 100) if sub_tot > 0 else 0.0

        p_color = "#00e676" if sub_u > 0 else ("#ff5252" if sub_u < 0 else "#94a3b8")
        icono = "👑" if pilar_nom == "Moneyline" else ("🎯" if pilar_nom == "Totales" else "⚡")

        with col_dest:
            with st.container(border=True):
                st.markdown(
                    f"""<div style="font-weight: 800; font-size: 1.05rem; color: #ffffff; margin-bottom: 0.4rem;">
                    {icono} {pilar_nom}
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem;">
                    <span style="color: #94a3b8; font-size: 0.85rem;">Picks Evaluados:</span>
                    <span style="font-weight: 800; color: #ffffff;">{sub_tot}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem;">
                    <span style="color: #94a3b8; font-size: 0.85rem;">Récord:</span>
                    <span style="font-weight: 800; color: #ffffff;">{sub_g}G - {sub_p}P ({sub_wr:.1f}%)</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem;">
                    <span style="color: #94a3b8; font-size: 0.85rem;">Unidades Netas:</span>
                    <span style="font-weight: 900; color: {p_color};">{sub_u:+.2f} u</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                    <span style="color: #94a3b8; font-size: 0.85rem;">Retorno (ROI):</span>
                    <span style="font-weight: 900; color: {p_color};">{sub_roi:+.1f}%</span>
                    </div>""",
                    unsafe_allow_html=True,
                )

    # Desglose interactivo Semana a Semana (si hay más de 1 semana visible)
    semanas_en_vista = sorted(df_f["semana"].dropna().unique().tolist())
    if len(semanas_en_vista) > 1:
        st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)
        with st.expander("📅 Resumen Comparativo Semana a Semana", expanded=True):
            filas_semanas = []
            for s in sorted(semanas_en_vista, reverse=True):
                sub_sem = liquidados[liquidados["semana"] == s]
                tot_s = len(sub_sem)
                g_s = int((sub_sem["resultado"] == "GANADA").sum())
                p_s = int((sub_sem["resultado"] == "PERDIDA").sum())
                u_s = float(sub_sem["unidades"].sum(skipna=True))
                wr_s = (g_s / (g_s + p_s) * 100) if (g_s + p_s) > 0 else 0.0
                roi_s = (u_s / tot_s * 100) if tot_s > 0 else 0.0
                filas_semanas.append({
                    "Semana": f"Semana {s}" + (" (Actual)" if s == 8 else ""),
                    "Picks Evaluados": tot_s,
                    "Récord": f"{g_s}G - {p_s}P",
                    "Acierto (%)": wr_s,
                    "Unidades Netas (u)": u_s,
                    "ROI (%)": roi_s,
                })
            
            df_semanas_summary = pd.DataFrame(filas_semanas)
            st.dataframe(
                df_semanas_summary,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Semana": st.column_config.TextColumn("Semana NFL", width="medium"),
                    "Picks Evaluados": st.column_config.NumberColumn("Picks", width="small"),
                    "Récord": st.column_config.TextColumn("Récord (G - P)", width="small"),
                    "Acierto (%)": st.column_config.NumberColumn("Win Rate", format="%.1f%%"),
                    "Unidades Netas (u)": st.column_config.NumberColumn("Unidades", format="%+.2f u"),
                    "ROI (%)": st.column_config.NumberColumn("ROI", format="%+.1f%%"),
                }
            )

    st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

    # Tabla Detallada de Auditoría
    st.subheader("📋 Auditoría Partida por Partida")

    display_df = df_f[[
        "semana", "fecha_str", "partido", "jugador", "pilar", "mercado",
        "seleccion", "linea", "valor_real", "cuota", "resultado", "unidades"
    ]].copy()

    display_df["semana"] = display_df["semana"].map(lambda s: f"Semana {s}" if pd.notna(s) else "N/D")

    display_df = display_df.rename(columns={
        "semana": "Semana",
        "fecha_str": "Fecha",
        "partido": "Partido",
        "jugador": "Jugador / Sujeto",
        "pilar": "Pilar",
        "mercado": "Mercado",
        "seleccion": "Selección",
        "linea": "Línea",
        "valor_real": "Real (ESPN)",
        "cuota": "Momio",
        "resultado": "Resultado",
        "unidades": "Unidades (u)",
    })

    table_cfg = {
        "Semana": st.column_config.TextColumn("Semana", width="small"),
        "Fecha": st.column_config.TextColumn("Fecha", width="small"),
        "Partido": st.column_config.TextColumn("Partido", width="medium"),
        "Jugador / Sujeto": st.column_config.TextColumn("Jugador", width="medium"),
        "Pilar": st.column_config.TextColumn("Pilar", width="small"),
        "Mercado": st.column_config.TextColumn("Mercado", width="medium"),
        "Selección": st.column_config.TextColumn("Selección", width="medium"),
        "Línea": st.column_config.TextColumn("Línea", width="small"),
        "Real (ESPN)": st.column_config.TextColumn("Real (ESPN)", width="small"),
        "Momio": st.column_config.TextColumn("Momio", width="small"),
        "Resultado": st.column_config.TextColumn("Resultado", width="small"),
        "Unidades (u)": st.column_config.NumberColumn("Unidades", format="%+.2f u"),
    }

    st.dataframe(display_df, hide_index=True, use_container_width=True, column_config=table_cfg)

    # Nombre dinámico de archivo CSV según filtros
    tag_sem = semana_sel_str.lower().replace(" ", "_").replace("(", "").replace(")", "")
    csv_data = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Descargar Auditoría NFL Consolidada (CSV)",
        data=csv_data,
        file_name=f"rendimiento_total_nfl_{tag_sem}.csv",
        mime="text/csv",
    )
