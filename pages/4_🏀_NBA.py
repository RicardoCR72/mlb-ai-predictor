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
from nba.registro import cargar_historial_rendimiento
from core.constants import ZONA_CDMX

# Estilos CSS específicos de la NBA con acentos neón y modo oscuro premium
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 85% 0%, rgba(255, 107, 0, 0.07), transparent 30rem),
            radial-gradient(circle at 15% 90%, rgba(183, 255, 60, 0.05), transparent 28rem),
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
        border: 1px solid #202938;
        border-radius: 13px;
        background: #111720;
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
    .nba-status { color: #8e99a9; font-size: .78rem; font-weight: 700; }
    .nba-view-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: .9rem 0 1.25rem;
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
    .nba-subtitle { color: #8994a5; font-size: .88rem; }
    div[data-testid="stMetric"] {
        background: #111720;
        border: 1px solid #202938;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8994a5; }
    div[data-testid="stMetricValue"] { color: #f4f7fb; }

    .nba-card {
        padding: 1.2rem 1.4rem;
        border: 1px solid #253044;
        border-radius: 16px;
        background: linear-gradient(145deg, #121824, #0c111a);
        margin-bottom: 1.1rem;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .nba-card:hover {
        border-color: #3b4861;
    }
    .card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.8rem;
        color: #828fa3;
        margin-bottom: 0.85rem;
        border-bottom: 1px solid #1c2636;
        padding-bottom: 0.5rem;
    }
    .badge-time {
        background: #182232;
        color: #ff8c33;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
    }
    .badge-conf-alta {
        background: rgba(183, 255, 60, 0.15);
        color: #b7ff3c;
        border: 1px solid rgba(183, 255, 60, 0.4);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-weight: 800;
        font-size: 0.75rem;
    }
    .badge-conf-media {
        background: rgba(255, 140, 51, 0.15);
        color: #ff8c33;
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
        margin-bottom: 0.9rem;
    }
    .team-name {
        font-size: 1.25rem;
        font-weight: 800;
        color: #f5f8fb;
    }
    .team-abbr {
        color: #8b97a8;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .pick-box {
        background: rgba(183, 255, 60, 0.05);
        border: 1px solid rgba(183, 255, 60, 0.25);
        border-radius: 12px;
        padding: 0.75rem 1rem;
        margin-top: 0.8rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .pick-title {
        color: #b7ff3c;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .pick-sel {
        color: #ffffff;
        font-size: 1.05rem;
        font-weight: 800;
    }
    .stat-pill {
        background: #151d2a;
        padding: 0.35rem 0.65rem;
        border-radius: 8px;
        font-size: 0.82rem;
        color: #b4c0d1;
        border: 1px solid #1f2c3f;
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
            return json.load(f)
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

# Selector de navegación interna (Proyecciones de Hoy vs Rendimiento e Historial)
vista = st.radio(
    "Sección NBA",
    ["🔮 Proyecciones de Hoy", "📈 Rendimiento e Historial"],
    horizontal=True,
    label_visibility="collapsed",
    key="nba_vista_principal",
)

# ==========================================================
# VISTA 1: PROYECCIONES Y LÍNEAS DE HOY
# ==========================================================
if vista == "🔮 Proyecciones de Hoy":
    hero_col1, hero_col2 = st.columns([4, 1])
    with hero_col1:
        st.markdown(
            f"""
            <div class="nba-view-hero">
                <div>
                    <div class="nba-eyebrow">BALONCESTO PROFESIONAL</div>
                    <h1>Predicciones y Líneas NBA</h1>
                    <div class="nba-subtitle">Modelos de Spread, Totales (Over/Under) y Moneyline sincronizados en base de datos. Hora CDMX: {hora_actual_cdmx}.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with hero_col2:
        st.write("")
        if st.button("🔄 Actualizar Cuotas", use_container_width=True, help="Consulta las últimas líneas de DraftKings y actualiza la base de datos."):
            cargar_predicciones(forzar=True)
            st.rerun()

    # Cargar datos
    predicciones = cargar_predicciones(forzar=False)

    if not predicciones:
        st.info("🏀 No hay partidos programados para hoy en la cartelera de la NBA. Puedes volver a consultar más tarde o forzar la actualización.")
        st.stop()

    # Métricas superiores
    total_partidos = len(predicciones)
    picks_altos = sum(1 for p in predicciones if p.get("confianza") == "ALTA")
    picks_totales = sum(1 for p in predicciones if "Totales" in p.get("pick_mercado", ""))
    picks_spread = sum(1 for p in predicciones if "Spread" in p.get("pick_mercado", ""))

    mcols = st.columns(4)
    mcols[0].metric("Partidos Hoy", total_partidos)
    mcols[1].metric("Picks Alta Confianza", picks_altos)
    mcols[2].metric("Picks de Totales (O/U)", picks_totales)
    mcols[3].metric("Picks de Spread / ML", picks_spread + sum(1 for p in predicciones if "Moneyline" in p.get("pick_mercado", "")))

    # Controles de filtrado
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
        criterio_orden = st.selectbox(
            "Ordenar por",
            ["Horario de inicio", "Mayor Edge (+EV)", "Mayor Probabilidad"]
        )

    # Aplicar filtros
    filtrados = list(predicciones)

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

    if criterio_orden == "Mayor Edge (+EV)":
        filtrados.sort(key=lambda x: abs(x.get("pick_edge", 0.0)), reverse=True)
    elif criterio_orden == "Mayor Probabilidad":
        filtrados.sort(key=lambda x: x.get("pick_probabilidad", 0.0), reverse=True)
    else:
        filtrados.sort(key=lambda x: x.get("hora_cdmx", ""))

    st.write("")
    st.subheader(f"Partidos Disponibles ({len(filtrados)})")

    # Render de tarjetas
    for p in filtrados:
        conf = p.get("confianza", "NEUTRAL")
        badge_conf = "badge-conf-alta" if conf == "ALTA" else "badge-conf-media"
        
        with st.container():
            st.markdown(
                f"""
                <div class="nba-card">
                    <div class="card-top">
                        <div>
                            <span class="badge-time">⏰ {p.get('hora_cdmx', 'TBD')} CDMX</span>
                            <span style="margin-left: 0.6rem;">{p.get('provider', 'DraftKings')} Sportsbook</span>
                        </div>
                        <div>
                            <span class="{badge_conf}">CONFIANZA {conf}</span>
                        </div>
                    </div>
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
                </div>
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

            st.markdown(
                f"""
                <div class="pick-box">
                    <div>
                        <div class="pick-title">Recomendación Oficial del Oráculo AI ({p.get('pick_mercado')})</div>
                        <div class="pick-sel">{p.get('pick_seleccion')}</div>
                        <div style="font-size: 0.8rem; color: #8e9bb0; margin-top: 0.2rem;">{p.get('pick_detalle')}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.72rem; color: #8e9bb0;">PROBABILIDAD MODELO</div>
                        <div style="font-size: 1.25rem; font-weight: 900; color: #b7ff3c;">{p.get('pick_probabilidad', 0.0)*100:.1f}%</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.write("")

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

    # Filtros de rendimiento
    rcol1, rcol2, rcol3 = st.columns(3)
    with rcol1:
        mercados_disp = ["Todos los mercados"] + sorted(list(liquidados["mercado"].unique()))
        sel_mercado = st.selectbox("Mercado para Auditoría", mercados_disp)
    with rcol2:
        confianzas_disp = ["Todas las confianzas", "Solo ALTA", "Solo MEDIA"]
        sel_conf = st.selectbox("Nivel de Confianza en Auditoría", confianzas_disp)
    with rcol3:
        sel_resultado = st.selectbox("Estado del Resultado", ["Todos los resultados", "Solo Ganadas", "Solo Perdidas"])

    # Aplicar filtros
    f_liq = liquidados.copy()
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
    rmcols[1].metric("Acierto", f"{acierto_pct:.1f}%", f"{ganadas}G - {perdidas}P ({pushes} Push)")
    rmcols[2].metric("Unidades Netas", f"{beneficio_u:+.2f} u")
    rmcols[3].metric("ROI Simulado", f"{roi_pct:+.2f}%")

    st.write("")
    
    # Gráfica de evolución acumulada en el tiempo
    st.subheader("📈 Evolución de Unidades en el Tiempo (Simulación 1 u por pick)")
    if not f_liq.empty:
        f_liq["fecha_dt"] = pd.to_datetime(f_liq["fecha"])
        evolucion = f_liq.sort_values("fecha_dt").copy()
        evolucion["Unidades Acumuladas"] = evolucion["unidades_ganadas"].cumsum()
        
        chart_data = evolucion.set_index("fecha_dt")["Unidades Acumuladas"]
        st.line_chart(chart_data, use_container_width=True)

    # Desglose por mercado
    with st.expander("📊 Desglose Detallado por Mercado"):
        agrupado = []
        for m, g in liquidados.groupby("mercado"):
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

    # Tabla con el historial completo
    st.subheader(f"Historial Liquidado ({len(f_liq)} registros)")
    cols_hist = [
        "fecha", "hora_cdmx", "equipo_visitante", "equipo_local",
        "mercado", "seleccion", "cuota", "probabilidad", "resultado", "unidades_ganadas"
    ]
    st.dataframe(
        f_liq[cols_hist].sort_values("fecha", ascending=False),
        use_container_width=True,
        hide_index=True
    )
