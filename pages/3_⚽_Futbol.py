"""Página interactiva del Oráculo AI para Fútbol Mundial en Streamlit.

Cubre las 8 principales ligas con cuotas oficiales de DraftKings y modelado bivariado:
- 🇲🇽 Liga MX
- 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
- 🇪🇸 LaLiga
- 🇮🇹 Serie A
- 🇩🇪 Bundesliga
- 🇫🇷 Ligue 1
- 🇳🇱 Eredivisie
- 🇺🇸 MLS
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(
    page_title="Fútbol Oráculo AI · Ligas Mundiales",
    page_icon="⚽",
    layout="wide",
)

from core.ui_diseno import apply_design
apply_design()

from core.ui_navegacion_movil import install_navigation
install_navigation()

from core.constants import ZONA_CDMX
from core.ui_rendimiento_diseno import performance_filters, safe_select
from futbol.constantes import LIGAS_DISPONIBLES, CODIGOS_LIGAS, obtener_info_liga
from futbol.predecir_jornada import (
    predecir_futbol_mundial,
    liquidar_partidos_pendientes_futbol,
    cargar_historial_futbol,
    RUTA_PREDICCIONES_JSON,
)

# Header de navegación
st.markdown(
    """<div class="futbol-shell">
<div class="futbol-brand">
<span class="futbol-logo">⚽</span>
<div>
<div style="font-size: 1.05rem; font-weight: 900; color: #ffffff;">FÚTBOL MUNDIAL <span class="futbol-accent">ORÁCULO AI</span></div>
<div class="futbol-status">8 Ligas Principales · Cuotas DraftKings · Modelo Bivariado Calibrado</div>
</div>
</div>
<div style="text-align: right;">
<div style="font-size: 0.78rem; color: #8ba797;">Ligas Activas</div>
<div style="font-size: 0.95rem; font-weight: 800; color: #00e676;">🇲🇽 🏴󠁧󠁢󠁥󠁮󠁧󠁿 🇪🇸 🇮🇹 🇩🇪 🇫🇷 🇳🇱 🇺🇸</div>
</div>
</div>""",
    unsafe_allow_html=True,
)

# Hero Section
st.markdown(
    """<div class="futbol-view-hero">
<div>
<h1 class="futbol-hero-title">Centro de Inteligencia Deportiva · Fútbol</h1>
<div class="futbol-hero-sub">Proyecciones matemáticas de goles (xG), Moneyline (1X2) y Totales Over/Under con momios oficiales en vivo.</div>
</div>
</div>""",
    unsafe_allow_html=True,
)

# Acciones superiores (Actualización y Liquidación)
top_col1, top_col2, top_col3 = st.columns([2, 1, 1])

with top_col2:
    if st.button("🔄 Actualizar Cuotas", use_container_width=True, key="btn_act_cuotas_futbol"):
        with st.spinner("Descargando partidos y momios oficiales de DraftKings para todas las ligas..."):
            predecir_futbol_mundial(force_refresh=True)
            st.success("✅ Cuotas y cartelera actualizadas.")
            st.rerun()

with top_col3:
    if st.button("✅ Liquidar Partidos", use_container_width=True, key="btn_liq_futbol"):
        with st.spinner("Evaluando partidos concluidos y liquidando picks..."):
            res = liquidar_partidos_pendientes_futbol()
            st.success(f"✅ Evaluados: {res['resueltas']} picks | Ganadas: {res['ganadas']} | PnL: {res['unidades_netas']:+.2f} u")
            st.rerun()

# Carga de datos
if not RUTA_PREDICCIONES_JSON.exists():
    with st.spinner("Generando predicciones iniciales para las 8 ligas..."):
        predicciones = predecir_futbol_mundial(force_refresh=True)
else:
    try:
        with open(RUTA_PREDICCIONES_JSON, "r", encoding="utf-8") as f:
            predicciones = json.load(f)
    except Exception:
        predicciones = predecir_futbol_mundial(force_refresh=False)

if not predicciones:
    st.info("⚽ No hay partidos registrados en la cartelera. Pulsa 'Actualizar Cuotas' para consultar ESPN.")
    st.stop()

tab_cartelera, tab_historial = st.tabs(["⚽ Cartelera y Predicciones en Vivo", "📊 Historial y Rendimiento Auditado"])

with tab_cartelera:
    # Selector de Ligas (League Filter)
    nombres_ligas = {
        "todas": "🌍 Todas las Ligas",
        "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
        "esp.1": "🇪🇸 LaLiga",
        "mex.1": "🇲🇽 Liga MX",
        "ita.1": "🇮🇹 Serie A",
        "ger.1": "🇩🇪 Bundesliga",
        "fra.1": "🇫🇷 Ligue 1",
        "ned.1": "🇳🇱 Eredivisie",
        "usa.1": "🇺🇸 MLS",
    }

    # Conteo de partidos por liga
    conteo_por_liga = {}
    for p in predicciones:
        cod = p.get("liga_codigo", "mex.1")
        conteo_por_liga[cod] = conteo_por_liga.get(cod, 0) + 1

    opciones_selector = ["todas"] + [c for c in CODIGOS_LIGAS if c in conteo_por_liga]
    etiquetas_selector = [
        f"{nombres_ligas.get(c, c)} ({len(predicciones) if c == 'todas' else conteo_por_liga.get(c, 0)})"
        for c in opciones_selector
    ]

    liga_sel_idx = st.selectbox(
        "Selecciona Liga:",
        range(len(opciones_selector)),
        format_func=lambda i: etiquetas_selector[i],
        key="sel_liga_futbol",
    )
    liga_seleccionada = opciones_selector[liga_sel_idx]

    # Filtrar por liga
    if liga_seleccionada != "todas":
        predicciones_liga = [p for p in predicciones if p.get("liga_codigo") == liga_seleccionada]
    else:
        predicciones_liga = list(predicciones)

    # Métricas del panel
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("Partidos en Cartelera", f"{len(predicciones_liga)} partidos")
    mcol2.metric("Picks Alta Confianza", sum(1 for p in predicciones_liga if p.get("confianza") == "ALTA"))
    mcol3.metric("Picks Over/Under", sum(1 for p in predicciones_liga if "Totales" in p.get("pick_mercado", "")))
    mcol4.metric("Picks Moneyline (1X2)", sum(1 for p in predicciones_liga if "Moneyline" in p.get("pick_mercado", "")))

    # Filtros adicionales
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        filtro_mercado = st.selectbox(
            "Mercado:",
            ["Todos los mercados", "Totales (Over/Under)", "Moneyline"],
            key="f_mercado"
        )
    with fcol2:
        filtro_confianza = st.selectbox(
            "Nivel de Confianza:",
            ["Todas las selecciones", "Solo ALTA confianza", "Solo MEDIA confianza"],
            key="f_confianza"
        )
    with fcol3:
        filtro_estado = st.selectbox(
            "Estado del Partido:",
            ["Todos los estados", "Solo Próximos", "Solo En Vivo", "Solo Finalizados"],
            key="f_estado"
        )

    filtrados = list(predicciones_liga)
    if filtro_mercado == "Totales (Over/Under)":
        filtrados = [p for p in filtrados if "Totales" in p.get("pick_mercado", "")]
    elif filtro_mercado == "Moneyline":
        filtrados = [p for p in filtrados if "Moneyline" in p.get("pick_mercado", "")]

    if filtro_confianza == "Solo ALTA confianza":
        filtrados = [p for p in filtrados if p.get("confianza") == "ALTA"]
    elif filtro_confianza == "Solo MEDIA confianza":
        filtrados = [p for p in filtrados if p.get("confianza") == "MEDIA"]

    if filtro_estado == "Solo Próximos":
        filtrados = [p for p in filtrados if "SCHEDULED" in str(p.get("estado", "")).upper()]
    elif filtro_estado == "Solo En Vivo":
        filtrados = [p for p in filtrados if "PROGRESS" in str(p.get("estado", "")).upper()]
    elif filtro_estado == "Solo Finalizados":
        filtrados = [p for p in filtrados if ("FINAL" in str(p.get("estado", "")).upper() or "FULL_TIME" in str(p.get("estado", "")).upper())]

    if not filtrados:
        st.warning("No hay partidos que coincidan con los filtros seleccionados.")
    else:
        # Despliegue de tarjetas de partidos
        for p in filtrados:
            estado = str(p.get("estado", "")).upper()
            es_final = "FINAL" in estado or "FULL_TIME" in estado
            en_vivo = "PROGRESS" in estado

            m_loc = p.get("marcador_local")
            m_vis = p.get("marcador_visita")
            tiene_marcador = (es_final or en_vivo) and (m_loc is not None and m_vis is not None)

            confianza = p.get("confianza", "MEDIA")
            badge_conf_cls = "badge-conf-alta" if confianza == "ALTA" else "badge-conf-media"

            bandera = p.get("liga_bandera", "⚽")
            liga_nom = p.get("liga_nombre", "Fútbol")
            hora_txt = f"{p.get('fecha_cdmx', '')} · {p.get('hora_cdmx', '')} CDMX"

            if es_final:
                badge_status = '<span class="badge-time">🏁 FINAL</span>'
            elif en_vivo:
                badge_status = '<span class="badge-time" style="background:#27150a;color:#ff8c33;border-color:#ff6b00;">🔴 EN VIVO</span>'
            else:
                badge_status = f'<span class="badge-time">⏰ {hora_txt}</span>'

            # Fila de equipos y marcadores
            vis_name = p.get("equipo_visita")
            loc_name = p.get("equipo_local")
            vis_ml = p.get("moneyline_visita") or "N/D"
            loc_ml = p.get("moneyline_local") or "N/D"
            emp_ml = p.get("moneyline_empate") or "N/D"

            if tiene_marcador:
                score_center = (
                    f'<div style="font-size: 1.35rem; color: #00e676; font-weight: 900; background: #092416; '
                    f'border: 1px solid #00e676; padding: 0.2rem 0.8rem; border-radius: 8px;">'
                    f'{int(m_vis)} - {int(m_loc)}</div>'
                )
            else:
                score_center = '<div style="font-size: 1.1rem; color: #446452; font-weight: 800;">vs</div>'

            teams_html = (
                f'<div class="teams-row">'
                f'<div>'
                f'<div class="team-name">{vis_name}</div>'
                f'<div class="team-sub">Visitante · ML: <b>{vis_ml}</b></div>'
                f'</div>'
                f'<div style="text-align: center;">{score_center}</div>'
                f'<div style="text-align: right;">'
                f'<div class="team-name" style="justify-content: flex-end;">{loc_name}</div>'
                f'<div class="team-sub">Local · ML: <b>{loc_ml}</b></div>'
                f'</div>'
                f'</div>'
            )

            card_top_html = (
                f'<div class="card-top">'
                f'<div style="display: flex; align-items: center; gap: 0.5rem;">'
                f'<span class="badge-league">{bandera} {liga_nom}</span>'
                f'{badge_status}'
                f'</div>'
                f'<div>'
                f'<span class="{badge_conf_cls}">CONFIANZA {confianza}</span>'
                f'</div>'
                f'</div>'
            )

            with st.container(border=True):
                st.markdown(card_top_html + teams_html, unsafe_allow_html=True)

                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    st.caption("⚽ **Moneyline (1X2 Modelo)**")
                    p_loc = p.get("prob_local", 0.4) * 100
                    p_emp = p.get("prob_empate", 0.3) * 100
                    p_vis = p.get("prob_visita", 0.3) * 100
                    st.write(f"Loc: **{p_loc:.1f}%** · Emp: **{p_emp:.1f}%** · Vis: **{p_vis:.1f}%**")
                    st.markdown(f"<span class='stat-pill'>Marcador más probable: <b>{p.get('marcador_mas_probable', 'N/D')}</b></span>", unsafe_allow_html=True)

                with col_c2:
                    lin_tot = p.get("linea_total", 2.5)
                    st.caption(f"🎯 **Totales (Línea {lin_tot:g})**")
                    p_ov = p.get("prob_over", 0.5) * 100
                    p_un = p.get("prob_under", 0.5) * 100
                    tot_proj = p.get("total_proyectado", 2.6)
                    st.write(f"Over: **{p_ov:.1f}%** · Under: **{p_un:.1f}%**")
                    st.markdown(f"<span class='stat-pill'>Goles esperados: <b>{tot_proj:.2f}</b></span>", unsafe_allow_html=True)

                with col_c3:
                    st.caption("📊 **xG y Momios de Mercado**")
                    xg_h = p.get("xg_local", 1.4)
                    xg_a = p.get("xg_visita", 1.2)
                    st.write(f"Local xG: **{xg_h:.2f}** | Visita xG: **{xg_a:.2f}**")
                    st.markdown(f"<span class='stat-pill'>Momio Empate: <b>{emp_ml}</b></span>", unsafe_allow_html=True)

                # Caja de Recomendación Oficial
                res_pick = p.get("resultado_pick")
                u_gan = p.get("beneficio_unidades")
                momio_pick_str = f" · Momio: {p.get('pick_cuota', '')}" if p.get("pick_cuota") else ""

                if res_pick in ["GANADA", "PERDIDA", "PUSH"]:
                    color_res = "#4ade80" if res_pick == "GANADA" else ("#f87171" if res_pick == "PERDIDA" else "#cbd5e1")
                    val_u = f"{u_gan:+.2f} u" if u_gan is not None else ""
                    res_box_html = (
                        f'<div style="text-align: right;">'
                        f'<div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">RESULTADO AUDITADO</div>'
                        f'<div style="font-size: 1.15rem; font-weight: 900; color: {color_res};">{res_pick} ({val_u})</div>'
                        f'</div>'
                    )
                else:
                    prob_hit = p.get("pick_probabilidad", 0.5) * 100
                    res_box_html = (
                        f'<div style="text-align: right;">'
                        f'<div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">PROBABILIDAD ORÁCULO</div>'
                        f'<div style="font-size: 1.25rem; font-weight: 900; color: #00e676;">{prob_hit:.1f}%</div>'
                        f'</div>'
                    )

                pick_box_html = (
                    f'<div class="pick-box">'
                    f'<div style="min-width: 0; flex: 1;">'
                    f'<div class="pick-title">Recomendación Oficial ({p.get("pick_mercado")})<span style="color:#ffffff;font-weight:700;">{momio_pick_str}</span></div>'
                    f'<div class="pick-sel">{p.get("pick_seleccion")}</div>'
                    f'<div style="font-size: 0.82rem; color: #8ba797; margin-top: 0.2rem;">{p.get("pick_detalle", "")}</div>'
                    f'</div>'
                    f'{res_box_html}'
                    f'</div>'
                )

                st.markdown(pick_box_html, unsafe_allow_html=True)

                with st.expander("Ver detalles de cuotas y desglose"):
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        st.write("**Cuotas DraftKings Moneyline:**")
                        st.write(f"- {p.get('equipo_local')} (Local): {p.get('moneyline_local')} ({p.get('ml_local_dec')})")
                        st.write(f"- Empate: {p.get('moneyline_empate')} ({p.get('ml_empate_dec')})")
                        st.write(f"- {p.get('equipo_visita')} (Visita): {p.get('moneyline_visita')} ({p.get('ml_visita_dec')})")
                    with col_d2:
                        st.write("**Cuotas DraftKings Totales:**")
                        st.write(f"- OVER {p.get('linea_total', 2.5):g}: {p.get('over_momio')} ({p.get('over_momio_dec')})")
                        st.write(f"- UNDER {p.get('linea_total', 2.5):g}: {p.get('under_momio')} ({p.get('under_momio_dec')})")
                        st.write(f"- Edge del Pick: **+{p.get('pick_edge', 0.0)*100:.1f}%**")

with tab_historial:
    st.subheader("Auditoría Histórica de Selecciones Oficiales")
    df_hist = cargar_historial_futbol()
    if df_hist.empty:
        st.info("Aún no hay historial de partidos liquidados en el registro de fútbol mundial.")
    else:
        df_filtrado = performance_filters(
            df_hist,
            "fecha",
            "hist_futbol_tab",
            probability_col="probabilidad",
            result_col="resultado",
        )
        if not df_filtrado.empty:
            total_picks = len(df_filtrado)
            ganados = sum(df_filtrado["resultado"] == "GANADA")
            perdidos = sum(df_filtrado["resultado"] == "PERDIDA")
            resueltos = ganados + perdidos
            win_rate = (ganados / resueltos * 100) if resueltos > 0 else 0.0
            pnl_tot = sum(df_filtrado.get("beneficio_unidades", 0.0).fillna(0))

            hc1, hc2, hc3, hc4 = st.columns(4)
            hc1.metric("Picks Auditados", total_picks)
            hc2.metric("Tasa de Acierto", f"{win_rate:.1f}%", f"{ganados}W - {perdidos}L")
            hc3.metric("Beneficio Acumulado", f"{pnl_tot:+.2f} u")
            hc4.metric("ROI Estimado", f"{(pnl_tot/max(resueltos, 1))*100:+.1f}%")

            st.dataframe(
                df_filtrado[[
                    "fecha_cdmx", "liga_nombre", "partido", "pick_mercado",
                    "pick_seleccion", "pick_cuota", "pick_probabilidad", "resultado", "beneficio_unidades"
                ]].rename(columns={
                    "fecha_cdmx": "Fecha", "liga_nombre": "Liga", "partido": "Partido",
                    "pick_mercado": "Mercado", "pick_seleccion": "Pick", "pick_cuota": "Cuota",
                    "pick_probabilidad": "Prob", "resultado": "Estado", "beneficio_unidades": "Unidades"
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning("No hay registros en el rango seleccionado.")

