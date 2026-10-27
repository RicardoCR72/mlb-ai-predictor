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
from datetime import datetime, timedelta
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


def obtener_pick_para_mercado_futbol(p: dict, mercado_tipo: str) -> dict:
    """Extrae o proyecta la recomendación del partido adaptada al mercado seleccionado."""
    info = {
        "mercado": mercado_tipo,
        "seleccion": p.get("pick_seleccion", "N/D"),
        "cuota": p.get("pick_cuota", "N/D"),
        "probabilidad": float(p.get("pick_probabilidad", 0.5)),
        "edge": float(p.get("pick_edge", 0.0)),
        "detalle": p.get("pick_detalle", ""),
        "confianza": p.get("confianza", "MEDIA"),
        "resultado": p.get("resultado_pick", "PENDIENTE"),
        "unidades": p.get("beneficio_unidades"),
    }

    if "Totales" in mercado_tipo:
        lin_tot = float(p.get("linea_total", 2.5))
        p_ov = float(p.get("prob_over", 0.5))
        p_un = float(p.get("prob_under", 0.5))
        ed_ov = float(p.get("edge_over", 0.0))
        ed_un = float(p.get("edge_under", 0.0))
        tot_proj = float(p.get("total_proyectado", 2.5))
        delta_xg = tot_proj - lin_tot

        if ed_ov >= ed_un:
            info["seleccion"] = f"OVER {lin_tot:g} Goles"
            info["cuota"] = p.get("over_momio") or "-110"
            info["probabilidad"] = p_ov
            info["edge"] = ed_ov
            if delta_xg >= 0.28 and ed_ov >= 0.045 and p_ov >= 0.54:
                info["confianza"] = "ALTA" if ed_ov >= 0.07 else "MEDIA"
                info["detalle"] = f"xG Proyectado: {tot_proj:.2f} goles vs línea {lin_tot:g} (Edge: {ed_ov*100:+.1f}%)"
            else:
                info["confianza"] = "NEUTRAL"
                info["detalle"] = f"Línea de mercado eficiente (xG: {tot_proj:.2f} vs {lin_tot:g}). Sin ventaja estadística clara."
        else:
            info["seleccion"] = f"UNDER {lin_tot:g} Goles"
            info["cuota"] = p.get("under_momio") or "-110"
            info["probabilidad"] = p_un
            info["edge"] = ed_un
            if delta_xg <= -0.28 and ed_un >= 0.045 and p_un >= 0.54:
                info["confianza"] = "ALTA" if ed_un >= 0.07 else "MEDIA"
                info["detalle"] = f"xG Proyectado: {tot_proj:.2f} goles vs línea {lin_tot:g} (Edge: {ed_un*100:+.1f}%)"
            else:
                info["confianza"] = "NEUTRAL"
                info["detalle"] = f"Línea de mercado eficiente (xG: {tot_proj:.2f} vs {lin_tot:g}). Sin ventaja estadística clara."

        return info

    elif "Moneyline" in mercado_tipo:
        p_loc = float(p.get("prob_local", 0.4))
        p_emp = float(p.get("prob_empate", 0.3))
        p_vis = float(p.get("prob_visita", 0.3))
        ed_loc = float(p.get("edge_local", 0.0))
        ed_emp = float(p.get("edge_empate", 0.0))
        ed_vis = float(p.get("edge_visita", 0.0))

        max_ed = max(ed_loc, ed_emp, ed_vis)
        if max_ed == ed_loc and ed_loc > 0:
            sel = f"{p.get('equipo_local')} (Victoria Local)"
            c = p.get("moneyline_local") or "+100"
            pr = p_loc
            ed = ed_loc
        elif max_ed == ed_vis and ed_vis > 0:
            sel = f"{p.get('equipo_visita')} (Victoria Visitante)"
            c = p.get("moneyline_visita") or "+100"
            pr = p_vis
            ed = ed_vis
        elif max_ed == ed_emp and ed_emp > 0:
            sel = "Empate (X)"
            c = p.get("moneyline_empate") or "+250"
            pr = p_emp
            ed = ed_emp
        else:
            sel = f"{p.get('equipo_local')} ML"
            c = p.get("moneyline_local") or "+100"
            pr = p_loc
            ed = ed_loc

        info["seleccion"] = sel
        info["cuota"] = c
        info["probabilidad"] = pr
        info["edge"] = ed

        if ed >= 0.045:
            if pr < 0.45:
                info["confianza"] = "LONGSHOT"
                info["detalle"] = f"🎯 Longshot (+EV {ed*100:+.1f}%). Probabilidad de victoria ({pr*100:.1f}%) moderada/baja."
            elif ed >= 0.065 and pr >= 0.50:
                info["confianza"] = "ALTA"
                info["detalle"] = f"Probabilidad calibrada: {pr*100:.1f}% vs Book (Edge: {ed*100:+.1f}%)"
            else:
                info["confianza"] = "MEDIA"
                info["detalle"] = f"Probabilidad calibrada: {pr*100:.1f}% vs Book (Edge: {ed*100:+.1f}%)"
        else:
            info["confianza"] = "NEUTRAL"
            info["detalle"] = f"Sin ventaja sobre la cuota ({ed*100:+.1f}% edge). Partido en Zona Muerta descartado."

        return info

    elif "Ambos Anotan" in mercado_tipo or "BTTS" in mercado_tipo:
        if "Ambos Anotan" in str(p.get("pick_mercado", "")) or "BTTS" in str(p.get("pick_mercado", "")):
            return info

        p_si = float(p.get("prob_btts_si", 0.52))
        p_no = float(p.get("prob_btts_no", 0.48))
        xg_h = float(p.get("xg_local", 1.4))
        xg_a = float(p.get("xg_visita", 1.2))

        if p_si >= p_no:
            info["seleccion"] = "Ambos Anotan: SÍ"
            info["cuota"] = "-125"
            info["probabilidad"] = p_si
            info["edge"] = p_si - 0.52
            info["detalle"] = f"BTTS SÍ: {p_si*100:.1f}% · xG {xg_h:.2f} y {xg_a:.2f}"
            info["confianza"] = "ALTA" if p_si >= 0.60 else "MEDIA"
        else:
            info["seleccion"] = "Ambos Anotan: NO"
            info["cuota"] = "-110"
            info["probabilidad"] = p_no
            info["edge"] = p_no - 0.48
            info["detalle"] = f"BTTS NO: {p_no*100:.1f}% · Superioridad defensiva proyectada"
            info["confianza"] = "ALTA" if p_no >= 0.58 else "MEDIA"
        return info

    elif "Doble Oportunidad" in mercado_tipo:
        p_1x = float(p.get("prob_1x", 0.70))
        p_x2 = float(p.get("prob_x2", 0.60))
        loc_team = p.get("equipo_local", "Local")
        vis_team = p.get("equipo_visita", "Visita")

        if p_1x >= p_x2:
            info["seleccion"] = f"1X ({loc_team} o Empate)"
            info["cuota"] = "-220"
            info["probabilidad"] = p_1x
            info["edge"] = max(p_1x - 0.68, 0.02)
            info["detalle"] = f"Dixon-Coles 1X: {p_1x*100:.1f}% certidumbre"
            info["confianza"] = "ALTA" if p_1x >= 0.75 else "MEDIA"
        else:
            info["seleccion"] = f"X2 ({vis_team} o Empate)"
            info["cuota"] = "-200"
            info["probabilidad"] = p_x2
            info["edge"] = max(p_x2 - 0.60, 0.02)
            info["detalle"] = f"Dixon-Coles X2: {p_x2*100:.1f}% certidumbre"
            info["confianza"] = "ALTA" if p_x2 >= 0.70 else "MEDIA"
        return info

    return info


def render_cartelera_futbol(predicciones: list[dict], mercado_activo: str):
    """Renderiza las métricas y tarjetas de partidos de la jornada para el mercado seleccionado."""
    tot_partidos = len(predicciones)
    n_pendientes = sum(1 for p in predicciones if p.get("resultado_pick") not in ["GANADA", "PERDIDA", "PUSH"])
    n_finalizados = sum(
        1 for p in predicciones
        if p.get("resultado_pick") in ["GANADA", "PERDIDA", "PUSH"]
        or "FINAL" in str(p.get("estado", "")).upper()
        or "FULL_TIME" in str(p.get("estado", "")).upper()
    )
    picks_calificados = sum(
        1 for p in predicciones
        if obtener_pick_para_mercado_futbol(p, mercado_activo).get("confianza") in ["ALTA", "MEDIA"]
    )

    # Nivel 4: 4 Tarjetas Métricas
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("Total Partidos", f"{tot_partidos} juegos")
    mcol2.metric("Pendientes", n_pendientes)
    mcol3.metric("Finalizados", n_finalizados)
    mcol4.metric("Picks Calificados (+EV)", picks_calificados)

    st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)

    f_col1, f_col2 = st.columns([2, 1], gap="medium")
    with f_col1:
        busqueda_futbol = st.text_input(
            "Buscar equipo de Fútbol",
            key="futbol_search_input",
            placeholder="🔍 Ej: Real Madrid, Barcelona, Arsenal, América, Chivas...",
        ).strip().lower()
    with f_col2:
        st.markdown("<div style='margin-top: 1.8rem;'></div>", unsafe_allow_html=True)
        solo_ev = st.checkbox("🔥 Solo picks Calificados (+EV)", key="futbol_ev_filter")

    # Selector de Ligas y Filtros
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

    conteo_por_liga = {}
    for p in predicciones:
        cod = p.get("liga_codigo", "mex.1")
        conteo_por_liga[cod] = conteo_por_liga.get(cod, 0) + 1

    opciones_selector = ["todas"] + [c for c in CODIGOS_LIGAS if c in conteo_por_liga]
    etiquetas_selector = [
        f"{nombres_ligas.get(c, c)} ({len(predicciones) if c == 'todas' else conteo_por_liga.get(c, 0)})"
        for c in opciones_selector
    ]

    f_lig_col, f_fec_col, f_conf_col, f_est_col = st.columns([1.4, 1.1, 1.1, 1.1])
    with f_lig_col:
        liga_sel_idx = st.selectbox(
            "Filtrar por Liga:",
            range(len(opciones_selector)),
            format_func=lambda i: etiquetas_selector[i],
            key="sel_liga_futbol",
        )
        liga_seleccionada = opciones_selector[liga_sel_idx]

    with f_fec_col:
        filtro_fecha = st.selectbox(
            "Fecha:",
            ["Todas las fechas", "Hoy", "Mañana", "Próximos días"],
            key="f_fecha_futbol",
        )

    with f_conf_col:
        filtro_confianza = st.selectbox(
            "Nivel de Confianza:",
            ["Todas las selecciones", "Solo ALTA confianza", "Solo MEDIA confianza"],
            key="f_confianza_futbol",
        )

    with f_est_col:
        filtro_estado = st.selectbox(
            "Estado del Partido:",
            ["Solo Próximos y En Vivo", "Todos los estados", "Solo Próximos", "Solo En Vivo", "Solo Finalizados"],
            key="f_estado_futbol",
        )

    # Filtrar predicciones
    filtrados = list(predicciones)
    if busqueda_futbol:
        filtrados = [
            p for p in filtrados
            if (busqueda_futbol in str(p.get("equipo_local", "")).lower() or
                busqueda_futbol in str(p.get("equipo_visita", "")).lower() or
                busqueda_futbol in str(p.get("partido", "")).lower())
        ]
    if solo_ev:
        filtrados = [
            p for p in filtrados
            if obtener_pick_para_mercado_futbol(p, mercado_activo).get("confianza") in ["ALTA", "MEDIA"]
        ]
    if liga_seleccionada != "todas":
        filtrados = [p for p in filtrados if p.get("liga_codigo") == liga_seleccionada]

    hoy_cdmx = datetime.now(ZONA_CDMX).date()
    manana_cdmx = hoy_cdmx + timedelta(days=1)

    def _extraer_fecha(item: dict):
        f = item.get("fecha_cdmx")
        if not f:
            return None
        try:
            if isinstance(f, str):
                return datetime.strptime(f[:10], "%Y-%m-%d").date()
            if hasattr(f, "date"):
                return f.date()
            return f
        except Exception:
            return None

    if filtro_fecha == "Hoy":
        filtrados = [p for p in filtrados if _extraer_fecha(p) == hoy_cdmx]
    elif filtro_fecha == "Mañana":
        filtrados = [p for p in filtrados if _extraer_fecha(p) == manana_cdmx]
    elif filtro_fecha == "Próximos días":
        filtrados = [p for p in filtrados if _extraer_fecha(p) and _extraer_fecha(p) > manana_cdmx]

    if filtro_confianza == "Solo ALTA confianza":
        filtrados = [p for p in filtrados if p.get("confianza") == "ALTA"]
    elif filtro_confianza == "Solo MEDIA confianza":
        filtrados = [p for p in filtrados if p.get("confianza") == "MEDIA"]

    if filtro_estado == "Solo Próximos y En Vivo":
        filtrados = [
            p for p in filtrados
            if not ("FINAL" in str(p.get("estado", "")).upper() or "FULL_TIME" in str(p.get("estado", "")).upper() or "POST" in str(p.get("estado", "")).upper())
        ]
    elif filtro_estado == "Solo Próximos":
        filtrados = [p for p in filtrados if "SCHEDULED" in str(p.get("estado", "")).upper()]
    elif filtro_estado == "Solo En Vivo":
        filtrados = [p for p in filtrados if "PROGRESS" in str(p.get("estado", "")).upper()]
    elif filtro_estado == "Solo Finalizados":
        filtrados = [
            p for p in filtrados
            if ("FINAL" in str(p.get("estado", "")).upper() or "FULL_TIME" in str(p.get("estado", "")).upper() or "POST" in str(p.get("estado", "")).upper())
        ]

    if not filtrados:
        st.warning("No hay partidos que coincidan con los filtros seleccionados.")
        return

    # Despliegue de tarjetas de partidos
    for idx, p in enumerate(filtrados):
        pick_data = obtener_pick_para_mercado_futbol(p, mercado_activo)

        estado = str(p.get("estado", "")).upper()
        es_final = "FINAL" in estado or "FULL_TIME" in estado
        en_vivo = "PROGRESS" in estado

        m_loc = p.get("marcador_local")
        m_vis = p.get("marcador_visita")
        tiene_marcador = (es_final or en_vivo) and (m_loc is not None and m_vis is not None)

        confianza = pick_data.get("confianza", "MEDIA")
        badge_conf_cls = "badge-conf-alta" if confianza == "ALTA" else "badge-conf-media"

        # Cálculo de Valor Esperado (+EV) real
        from core.ui_boleta import parsear_cuota_decimal
        c_dec_f = parsear_cuota_decimal(pick_data.get("cuota"))
        prob_f = float(pick_data.get("probabilidad", 0.5))
        ev_calc_f = (prob_f * c_dec_f - 1.0) * 100.0 if (c_dec_f > 1.0 and prob_f > 0) else 0.0
        ev_badge_f = f'<span class="badge-ev" style="margin-left: 0.45rem;">🔥 +EV +{ev_calc_f:.1f}%</span>' if ev_calc_f >= 2.0 else ""

        bandera = p.get("liga_bandera", "⚽")
        liga_nom = p.get("liga_nombre", "Fútbol")
        hora_txt = f"{p.get('fecha_cdmx', '')} · {p.get('hora_cdmx', '')} CDMX"

        if es_final:
            badge_status = '<span class="badge-time">🏁 FINAL</span>'
        elif en_vivo:
            badge_status = '<span class="badge-time" style="background:#27150a;color:#ff8c33;border-color:#ff6b00;">🔴 EN VIVO</span>'
        else:
            badge_status = f'<span class="badge-time">⏰ {hora_txt}</span>'

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

        if confianza == "ALTA":
            badge_top_right = f'<div style="display:inline-flex; align-items:center;"><span class="badge-conf-alta">CONFIANZA ALTA</span>{ev_badge_f}</div>'
        elif confianza == "MEDIA":
            badge_top_right = f'<div style="display:inline-flex; align-items:center;"><span class="badge-conf-media">CONFIANZA MEDIA</span>{ev_badge_f}</div>'
        elif confianza == "LONGSHOT":
            badge_top_right = f'<div style="display:inline-flex; align-items:center;"><span style="background: rgba(245, 158, 11, 0.16); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.55); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem;">🎯 LONGSHOT (+EV ALTO RIESGO)</span>{ev_badge_f}</div>'
        else:
            badge_top_right = '<span style="background: rgba(148, 163, 184, 0.12); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.35); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 700; font-size: 0.8rem;">⏸️ LÍNEA EFICIENTE (SIN EDGE)</span>'

        card_top_html = (
            f'<div class="card-top">'
            f'<div style="display: flex; align-items: center; gap: 0.5rem;">'
            f'<span class="badge-league">{bandera} {liga_nom}</span>'
            f'{badge_status}'
            f'</div>'
            f'<div>{badge_top_right}</div>'
            f'</div>'
        )

        with st.container(border=True):
            st.markdown(card_top_html + teams_html, unsafe_allow_html=True)

            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            with col_c1:
                st.caption("⚽ **1X2 (Dixon-Coles)**")
                p_loc = p.get("prob_local", 0.4) * 100
                p_emp = p.get("prob_empate", 0.3) * 100
                p_vis = p.get("prob_visita", 0.3) * 100
                st.write(f"1: **{p_loc:.0f}%** · X: **{p_emp:.0f}%** · 2: **{p_vis:.0f}%**")
                st.markdown(f"<span class='stat-pill'>Marcador: <b>{p.get('marcador_mas_probable', 'N/D')}</b></span>", unsafe_allow_html=True)

            with col_c2:
                lin_tot = p.get("linea_total", 2.5)
                st.caption(f"🎯 **Totales ({lin_tot:g} Goles)**")
                p_ov = p.get("prob_over", 0.5) * 100
                p_un = p.get("prob_under", 0.5) * 100
                st.write(f"Over: **{p_ov:.0f}%** · Under: **{p_un:.0f}%**")
                tot_proj = p.get("total_proyectado", 2.6)
                st.markdown(f"<span class='stat-pill'>Total xG: <b>{tot_proj:.2f}</b></span>", unsafe_allow_html=True)

            with col_c3:
                st.caption("🔥 **Ambos Anotan (BTTS)**")
                p_btts = p.get("prob_btts_si", 0.52) * 100
                p_btts_no = p.get("prob_btts_no", 0.48) * 100
                st.write(f"SÍ: **{p_btts:.0f}%** · NO: **{p_btts_no:.0f}%**")
                st.markdown(f"<span class='stat-pill'>Empate DK: <b>{emp_ml}</b></span>", unsafe_allow_html=True)

            with col_c4:
                st.caption("🛡️ **Doble Oportunidad**")
                p_1x_val = p.get("prob_1x", 0.70) * 100
                p_x2_val = p.get("prob_x2", 0.60) * 100
                st.write(f"1X: **{p_1x_val:.0f}%** · X2: **{p_x2_val:.0f}%**")
                xg_h = p.get("xg_local", 1.4)
                xg_a = p.get("xg_visita", 1.2)
                st.markdown(f"<span class='stat-pill'>xG: <b>{xg_h:.2f} - {xg_a:.2f}</b></span>", unsafe_allow_html=True)

            # Caja de Recomendación Oficial para el mercado activo
            momio_pick_str = f" · Momio: {pick_data.get('cuota', '')}" if pick_data.get("cuota") else ""

            if confianza == "NEUTRAL":
                if es_final:
                    res_box_html = (
                        f'<div style="text-align: right;">'
                        f'<div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">FILTRO DISCIPLINA</div>'
                        f'<div style="font-size: 1.05rem; font-weight: 800; color: #94a3b8;">DESCARTADO (0.00 u)</div>'
                        f'</div>'
                    )
                else:
                    prob_hit = float(pick_data.get("probabilidad", 0.5)) * 100
                    res_box_html = (
                        f'<div style="text-align: right;">'
                        f'<div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">PROBABILIDAD ORÁCULO</div>'
                        f'<div style="font-size: 1.25rem; font-weight: 900; color: #94a3b8;">{prob_hit:.1f}%</div>'
                        f'</div>'
                    )
            elif es_final and tiene_marcador:
                # Evaluar exactamente la selección mostrada para este mercado
                from core.ui_boleta import parsear_cuota_decimal
                c_dec_eval = parsear_cuota_decimal(pick_data.get("cuota"))
                res_calc, u_calc = liquidar_seleccion_futbol(
                    mercado=pick_data.get("mercado", ""),
                    seleccion=pick_data.get("seleccion", ""),
                    linea=float(p.get("linea_total", 2.5)),
                    cuota_dec=c_dec_eval,
                    marcador_local=m_loc,
                    marcador_visita=m_vis,
                    equipo_local=loc_name,
                    equipo_visita=vis_name,
                )
                if res_calc in ["GANADA", "PERDIDA", "PUSH"]:
                    color_res = "#4ade80" if res_calc == "GANADA" else ("#f87171" if res_calc == "PERDIDA" else "#cbd5e1")
                    val_u = f"{u_calc:+.2f} u"
                    res_box_html = (
                        f'<div style="text-align: right;">'
                        f'<div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">RESULTADO AUDITADO</div>'
                        f'<div style="font-size: 1.15rem; font-weight: 900; color: {color_res};">{res_calc} ({val_u})</div>'
                        f'</div>'
                    )
                else:
                    prob_hit = float(pick_data.get("probabilidad", 0.5)) * 100
                    res_box_html = (
                        f'<div style="text-align: right;">'
                        f'<div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">PROBABILIDAD ORÁCULO</div>'
                        f'<div style="font-size: 1.25rem; font-weight: 900; color: #00e676;">{prob_hit:.1f}%</div>'
                        f'</div>'
                    )
            else:
                prob_hit = float(pick_data.get("probabilidad", 0.5)) * 100
                res_box_html = (
                    f'<div style="text-align: right;">'
                    f'<div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">PROBABILIDAD ORÁCULO</div>'
                    f'<div style="font-size: 1.25rem; font-weight: 900; color: #00e676;">{prob_hit:.1f}%</div>'
                    f'</div>'
                )

            if confianza in ["ALTA", "MEDIA"]:
                titulo_box = f"Recomendación Oficial ({pick_data.get('mercado')})"
            elif confianza == "LONGSHOT":
                titulo_box = f"🎯 Longshot de Valor ({pick_data.get('mercado')}) · Alto Riesgo"
            else:
                titulo_box = f"Línea de Mercado ({pick_data.get('mercado')})"

            pick_box_html = (
                f'<div class="pick-box">'
                f'<div style="min-width: 0; flex: 1;">'
                f'<div class="pick-title">{titulo_box}<span style="color:#ffffff;font-weight:700;">{momio_pick_str}</span></div>'
                f'<div class="pick-sel">{pick_data.get("seleccion")}</div>'
                f'<div style="font-size: 0.82rem; color: #8ba797; margin-top: 0.2rem;">{pick_data.get("detalle", "")}</div>'
                f'</div>'
                f'{res_box_html}'
                f'</div>'
            )

            st.markdown(pick_box_html, unsafe_allow_html=True)

            if confianza in ["ALTA", "MEDIA"]:
                from core.ui_boleta import render_boton_boleta
                partido_id = str(p.get("id_partido") or p.get("id_evento") or f"{p.get('equipo_visita')}_{p.get('equipo_local')}_{idx}")
                clean_mercado = str(pick_data.get("mercado")).replace(" ", "_").replace("(", "").replace(")", "")
                slip_item = {
                    "id": f"FUTBOL_{partido_id}_{clean_mercado}_{pick_data.get('seleccion')}",
                    "deporte": f"Fútbol ({p.get('liga_nombre', 'Ligas')})",
                    "icono": "⚽",
                    "partido": f"{p.get('equipo_visita')} vs {p.get('equipo_local')}",
                    "mercado": pick_data.get("mercado"),
                    "seleccion": pick_data.get("seleccion"),
                    "momio": pick_data.get("cuota"),
                    "prob": pick_data.get("probabilidad"),
                }
                render_boton_boleta(slip_item, key=f"btn_futbol_slip_{partido_id}_{clean_mercado}_{idx}")
            elif confianza == "LONGSHOT":
                st.warning(f"⚠️ **Longshot de Alto Riesgo:** Aunque tiene valor matemático (+EV +{ev_calc_f:.1f}%), la probabilidad de ganar es solo del {prob_f*100:.1f}%. Recomendación: Reducir stake a 0.25u o descartar.")
                from core.ui_boleta import render_boton_boleta
                partido_id = str(p.get("id_partido") or p.get("id_evento") or f"{p.get('equipo_visita')}_{p.get('equipo_local')}_{idx}")
                clean_mercado = str(pick_data.get("mercado")).replace(" ", "_").replace("(", "").replace(")", "")
                slip_item = {
                    "id": f"FUTBOL_{partido_id}_{clean_mercado}_{pick_data.get('seleccion')}",
                    "deporte": f"Fútbol ({p.get('liga_nombre', 'Ligas')})",
                    "icono": "⚽",
                    "partido": f"{p.get('equipo_visita')} vs {p.get('equipo_local')}",
                    "mercado": pick_data.get("mercado"),
                    "seleccion": pick_data.get("seleccion"),
                    "momio": pick_data.get("cuota"),
                    "prob": pick_data.get("probabilidad"),
                }
                render_boton_boleta(slip_item, key=f"btn_futbol_slip_{partido_id}_{clean_mercado}_{idx}")
            else:
                st.caption("🛡️ *Filtro de Disciplina Activo: Este partido está en la Zona Muerta (edge < +4.5% o margen de goles insuficiente). Descartado para apuestas.*")

            with st.expander("Ver detalles de cuotas y desglose"):
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.write("**Cuotas DraftKings Moneyline:**")
                    st.write(f"- {p.get('equipo_local')} (Local): {p.get('moneyline_local')} ({p.get('ml_local_dec')})")
                    st.write(f"- Empate: {p.get('moneyline_empate')} ({p.get('ml_empate_dec')})")
                    st.write(f"- {p.get('equipo_visita')} (Visita): {p.get('moneyline_visita')} ({p.get('ml_visita_dec')})")
                with col_d2:
                    st.write("**Totales y Mercados Alternativos:**")
                    st.write(f"- OVER {p.get('linea_total', 2.5):g}: {p.get('over_momio')} ({p.get('over_momio_dec')})")
                    st.write(f"- UNDER {p.get('linea_total', 2.5):g}: {p.get('under_momio')} ({p.get('under_momio_dec')})")
                    st.write(f"- BTTS SÍ: **{p.get('prob_btts_si', 0.52)*100:.1f}%** · BTTS NO: **{p.get('prob_btts_no', 0.48)*100:.1f}%**")
                    st.write(f"- Doble Op 1X: **{p.get('prob_1x', 0.70)*100:.1f}%** · X2: **{p.get('prob_x2', 0.60)*100:.1f}%**")
                    st.write(f"- Edge del Pick: **+{pick_data.get('edge', 0.0)*100:.1f}%**")

    from core.ui_boleta import render_widget_boleta
    render_widget_boleta()



def render_historial_futbol(mercado_activo: str):
    """Renderiza la auditoría y rendimiento histórico de selecciones de fútbol."""
    st.subheader("Auditoría Histórica de Selecciones Oficiales")
    df_hist = cargar_historial_futbol()
    if df_hist.empty:
        st.info("Aún no hay historial de partidos liquidados en el registro de fútbol mundial.")
        return

    df_filtrado = performance_filters(
        df_hist,
        "fecha",
        "hist_futbol_tab",
        probability_col="probabilidad",
        result_col="resultado",
    )
    if df_filtrado.empty:
        st.warning("No hay registros en el rango seleccionado.")
        return

    # Filtrar por mercado activo si hay coincidencias
    if "Totales" in mercado_activo:
        df_mercado = df_filtrado[df_filtrado["pick_mercado"].astype(str).str.contains("Total|Over|Under", case=False, na=False)]
    elif "Moneyline" in mercado_activo:
        df_mercado = df_filtrado[df_filtrado["pick_mercado"].astype(str).str.contains("Moneyline|1X2", case=False, na=False)]
    elif "Ambos Anotan" in mercado_activo or "BTTS" in mercado_activo:
        df_mercado = df_filtrado[df_filtrado["pick_mercado"].astype(str).str.contains("Ambos|BTTS", case=False, na=False)]
    elif "Doble Oportunidad" in mercado_activo:
        df_mercado = df_filtrado[df_filtrado["pick_mercado"].astype(str).str.contains("Doble|1X|X2", case=False, na=False)]
    else:
        df_mercado = df_filtrado

    # Filtrar solo picks concluidos oficiales (excluyendo descartados por zona muerta)
    df_validos = df_mercado[~df_mercado["resultado"].isin(["DESCARTADO", "PENDIENTE"])]
    df_mostrar = df_validos if not df_validos.empty else df_mercado

    total_picks = len(df_mostrar)
    ganados = sum(df_mostrar["resultado"] == "GANADA")
    perdidos = sum(df_mostrar["resultado"] == "PERDIDA")
    resueltos = ganados + perdidos
    win_rate = (ganados / resueltos * 100) if resueltos > 0 else 0.0
    pnl_tot = sum(df_mostrar.get("beneficio_unidades", 0.0).fillna(0))

    hc1, hc2, hc3, hc4 = st.columns(4)
    hc1.metric("Picks Auditados", total_picks)
    hc2.metric("Tasa de Acierto", f"{win_rate:.1f}%", f"{ganados}W - {perdidos}L")
    hc3.metric("Beneficio Acumulado", f"{pnl_tot:+.2f} u")
    hc4.metric("ROI Estimado", f"{(pnl_tot/max(resueltos, 1))*100:+.1f}%")

    st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)

    columnas_mostrar = [
        "fecha_cdmx", "liga_nombre", "partido", "pick_mercado",
        "pick_seleccion", "pick_cuota", "pick_probabilidad", "resultado", "beneficio_unidades"
    ]
    renombres = {
        "fecha_cdmx": "Fecha", "liga_nombre": "Liga", "partido": "Partido",
        "pick_mercado": "Mercado", "pick_seleccion": "Pick", "pick_cuota": "Cuota",
        "pick_probabilidad": "Prob", "resultado": "Estado", "beneficio_unidades": "Unidades"
    }
    cols_existentes = [c for c in columnas_mostrar if c in df_mostrar.columns]
    st.dataframe(
        df_mostrar[cols_existentes].rename(columns=renombres),
        use_container_width=True,
        hide_index=True,
    )


# ==========================================================
# ESTRUCTURA PRINCIPAL HOMOLOGADA A MLB, NFL Y NBA
# ==========================================================

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")

# Header de navegación y marca (Tarjeta Shell)
st.markdown(
    f"""<div class="futbol-shell">
<div class="futbol-brand">
<span class="futbol-logo">⚽</span>
<div>
<div style="font-size: 1.05rem; font-weight: 900; color: #ffffff;">ORÁCULO <span class="futbol-accent">FÚTBOL AI V2</span></div>
<div class="futbol-status">8 Ligas Mundiales · Cuotas DraftKings · Modelo Dixon-Coles Bivariado Calibrado</div>
</div>
</div>
<div style="text-align: right;">
<span style="background: #092416; color: #00e676; padding: 0.3rem 0.75rem; border-radius: 8px; font-size: 0.78rem; font-weight: 800; border: 1px solid #00e676;">
🕒 {hora_actual_cdmx} CDMX
</span>
</div>
</div>""",
    unsafe_allow_html=True,
)

# Carga de datos de partidos
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
    st.info("⚽ No hay partidos registrados en la cartelera. Pulsa 'Actualizar Cuotas' para consultar ESPN y DraftKings.")
    st.stop()

# Nivel 1: Selector principal de mercado
mercado = st.radio(
    "Mercado Fútbol",
    ["Totales (Over/Under)", "Moneyline (1X2)", "Ambos Anotan (BTTS)", "Doble Oportunidad (1X/X2)"],
    horizontal=True,
    label_visibility="collapsed",
    key="futbol_mercado_principal",
)

# Nivel 2: Selector interno de sección (abajo de mercado)
seccion = st.radio(
    "Sección Fútbol",
    ["Picks de hoy", "Rendimiento e Historial"],
    horizontal=True,
    label_visibility="collapsed",
    key="futbol_seccion",
)

# Nivel 3: Barra superior de 2 botones al 50%/50% en estilo dark glassmorphic
st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
col1, col2 = st.columns(2, gap="medium")

with col1:
    if st.button("🏁 Liquidar Partidos", key="btn_liq_futbol", type="primary", use_container_width=True, help="Consulta marcadores finales en ESPN, evalúa apuestas concluidas y registra el PnL auditado."):
        with st.spinner("Evaluando partidos concluidos y liquidando picks de fútbol..."):
            res = liquidar_partidos_pendientes_futbol()
            st.success(f"✅ Evaluados: {res['resueltas']} picks | Ganadas: {res['ganadas']} | PnL: {res['unidades_netas']:+.2f} u")
            st.rerun()

with col2:
    if st.button("🔄 Actualizar Cuotas DraftKings", key="btn_act_cuotas_futbol", type="primary", use_container_width=True, help="Descarga los partidos más recientes de ESPN y las líneas oficiales de DraftKings para todas las ligas."):
        with st.spinner("Descargando partidos y momios oficiales de DraftKings para todas las ligas..."):
            predecir_futbol_mundial(force_refresh=True)
            st.success("✅ Cuotas y cartelera actualizadas desde DraftKings.")
            st.rerun()

st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

# Nivel 4 y 5: Renderizado de la sección seleccionada
if seccion == "Rendimiento e Historial":
    render_historial_futbol(mercado)
else:
    render_cartelera_futbol(predicciones, mercado)
