"""Página interactiva del Oráculo AI para la NBA con diseño y estética 100% uniforme."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="NBA Oráculo",
    page_icon="🏀",
    layout="wide",
)

from core.ui_navegacion_movil import install_navigation
install_navigation()

from core.ui_diseno import apply_design, render_sport_header
apply_design()

from core.ui_tarjetas import render_pick
from core.ui_controles import state_message
from core.constants import ZONA_CDMX

RAIZ = Path(__file__).resolve().parents[1]
RUTA_PREDICCIONES = RAIZ / "data" / "nba" / "predictions" / "predicciones_nba_hoy.json"

from nba.predecir_hoy import predecir_partidos_hoy
from nba.registro import cargar_historial_rendimiento


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


# Encabezado estándar unificado
render_sport_header("NBA", "🏀", "Spreads, totales y ganador directo")

# Selector de navegación con el mismo estilo que MLB, NFL y Liga MX
vista = st.radio(
    "Sección NBA",
    ["🔮 Proyecciones de Hoy", "📈 Rendimiento e Historial"],
    horizontal=True,
    format_func=lambda value: value.lstrip("🔥📋📈⚾🏈📊⚽🔮💼 "),
    label_visibility="collapsed",
    key="nba_vista_principal",
)

# ==========================================================
# VISTA 1: PROYECCIONES DE HOY
# ==========================================================
if vista == "🔮 Proyecciones de Hoy":
    col_titulo, col_boton = st.columns([4, 1])
    with col_titulo:
        st.subheader("Oportunidades NBA")
        st.caption("Picks calculados con cuotas en vivo de DraftKings y modelos analíticos de posesiones, ritmo y ratings.")
    with col_boton:
        st.write("")
        if st.button("🔄 Actualizar cuotas", use_container_width=True, help="Consulta las últimas líneas de DraftKings en ESPN y actualiza los picks."):
            cargar_predicciones(forzar=True)
            st.rerun()

    predicciones = cargar_predicciones(forzar=False)

    if not predicciones:
        state_message("No hay partidos programados para hoy en el calendario de la NBA.", kind="empty")
        st.stop()

    # Métricas estándar
    total_partidos = len(predicciones)
    picks_altos = sum(1 for p in predicciones if p.get("confianza") == "ALTA")
    picks_totales = sum(1 for p in predicciones if "Totales" in p.get("pick_mercado", ""))
    picks_spread = sum(1 for p in predicciones if "Spread" in p.get("pick_mercado", ""))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Partidos Hoy", total_partidos)
    m2.metric("Picks Alta Confianza", picks_altos)
    m3.metric("Picks Totales (O/U)", picks_totales)
    m4.metric("Picks Spread / ML", picks_spread + sum(1 for p in predicciones if "Moneyline" in p.get("pick_mercado", "")))

    # Filtros estándar
    f1, f2, f3 = st.columns(3)
    with f1:
        filtro_mercado = st.selectbox(
            "Mercado",
            ["Todos los mercados", "Totales (Over/Under)", "Spread", "Moneyline"]
        )
    with f2:
        filtro_confianza = st.selectbox(
            "Confianza",
            ["Todas las selecciones", "Solo ALTA confianza", "Solo MEDIA confianza"]
        )
    with f3:
        criterio_orden = st.selectbox(
            "Ordenar por",
            ["Horario de inicio", "Mayor Edge (+EV)", "Mayor Probabilidad"]
        )

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

    if not filtrados:
        state_message("No hay pronósticos que cumplan con los filtros seleccionados.", kind="filters")
        st.stop()

    st.write("")
    # Renderizado en cuadrícula de dos columnas usando las tarjetas oficiales unificadas
    for start_idx in range(0, len(filtrados), 2):
        col_izq, col_der = st.columns(2, gap="medium")
        for col, p in zip([col_izq, col_der], filtrados[start_idx:start_idx+2]):
            with col:
                # Determinar cuota decimal
                cuota_pick = p.get("ml_local_dec") if p.get("abbr_local") in p.get("pick_seleccion") else (p.get("ml_visita_dec") if p.get("abbr_visita") in p.get("pick_seleccion") else 1.909)
                
                pick_data = {
                    "fecha": p.get("fecha_cdmx"),
                    "deporte": "NBA",
                    "partido": p.get("partido"),
                    "seleccion": p.get("pick_seleccion"),
                    "probabilidad": float(p.get("pick_probabilidad") or 0.5),
                    "cuota": float(cuota_pick or 1.91),
                    "casa": "DraftKings",
                    "modelo": "NBA Oráculo",
                    "origen": "nba",
                    "referencia": {"game_id": str(p.get("id_evento"))},
                    "cuota_capturada_utc": p.get("timestamp"),
                }
                
                detalles = [
                    ("Horario", f"{p.get('hora_cdmx', 'TBD')} CDMX"),
                    ("Mercado", str(p.get("pick_mercado"))),
                    ("Edge modelo", f"{p.get('pick_edge', 0.0)*100:+.1f}%"),
                    ("Confianza", str(p.get("confianza", "MEDIA"))),
                    ("Spread oficial", str(p.get("spread_detalles", "N/D"))),
                    ("Margen proyectado", f"{p.get('margen_local_esperado', 0.0):+.1f} pts local"),
                    ("Línea O/U", str(p.get("linea_total", "N/D"))),
                    ("Total proyectado", f"{p.get('total_proyectado', 0.0):.1f} pts"),
                ]
                
                render_pick(
                    pick_data,
                    market=p.get("pick_mercado", "Baloncesto"),
                    state="Publicado",
                    details=detalles,
                    allow_register=False
                )

# ==========================================================
# VISTA 2: RENDIMIENTO E HISTORIAL
# ==========================================================
else:
    st.subheader("Rendimiento del Modelo NBA")
    st.caption("Auditoría histórica de aciertos, simulación de unidades ganadas (+/- u) y retorno de inversión (ROI).")

    df_hist = cargar_historial_rendimiento()

    if df_hist.empty:
        state_message("Aún no hay picks guardados para analizar.", kind="empty")
        st.stop()

    liquidados = df_hist[df_hist["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()

    # Controles de filtrado de rendimiento
    rf1, rf2, rf3 = st.columns(3)
    with rf1:
        mercados_disp = ["Todos los mercados"] + sorted(list(liquidados["mercado"].unique()))
        sel_mercado = st.selectbox("Mercado", mercados_disp)
    with rf2:
        confianzas_disp = ["Todas las confianzas", "Solo ALTA", "Solo MEDIA"]
        sel_conf = st.selectbox("Nivel de confianza", confianzas_disp)
    with rf3:
        sel_resultado = st.selectbox("Resultado", ["Todos los resultados", "Solo Ganadas", "Solo Perdidas"])

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

    if f_liq.empty:
        state_message("No hay picks liquidados para estos filtros.", kind="filters")
        st.stop()

    n_eval = len(f_liq)
    ganadas = int((f_liq["resultado"] == "GANADA").sum())
    perdidas = int((f_liq["resultado"] == "PERDIDA").sum())
    pushes = int((f_liq["resultado"] == "PUSH").sum())
    decididas = ganadas + perdidas
    acierto_pct = (ganadas / decididas * 100.0) if decididas else 0.0
    beneficio_u = float(f_liq["unidades_ganadas"].sum()) if n_eval else 0.0
    roi_pct = (beneficio_u / n_eval * 100.0) if n_eval else 0.0

    # Tarjetas métricas idénticas al resto del sistema
    rm1, rm2, rm3, rm4 = st.columns(4)
    rm1.metric("Picks Evaluados", f"{n_eval:,}")
    rm2.metric("Acierto", f"{acierto_pct:.1f}%", f"{ganadas}G - {perdidas}P ({pushes} Push)")
    rm3.metric("Unidades", f"{beneficio_u:+.2f} u")
    rm4.metric("ROI", f"{roi_pct:+.1f}%")

    st.caption("Simulación de 1 u por pick con cuotas guardadas. Los resultados agregados no son apuestas reales realizadas.")

    # Gráfica de evolución
    with st.expander("📈 Evolución de unidades acumuladas", expanded=True):
        f_liq["fecha_dt"] = pd.to_datetime(f_liq["fecha"])
        evolucion = f_liq.sort_values("fecha_dt").copy()
        evolucion["Unidades Acumuladas"] = evolucion["unidades_ganadas"].cumsum()
        chart_data = evolucion.set_index("fecha_dt")["Unidades Acumuladas"]
        st.line_chart(chart_data, use_container_width=True)

    # Desglose comparativo por mercado
    with st.expander("📊 Desglose por mercado"):
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

    # Historial de partidos
    st.subheader("Historial liquidado")
    cols_hist = [
        "fecha", "hora_cdmx", "equipo_visitante", "equipo_local",
        "mercado", "seleccion", "cuota", "probabilidad", "resultado", "unidades_ganadas"
    ]
    st.dataframe(
        f_liq[cols_hist].sort_values("fecha", ascending=False),
        use_container_width=True,
        hide_index=True
    )
