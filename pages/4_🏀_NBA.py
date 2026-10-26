"""Página interactiva del Oráculo AI para la NBA en Streamlit con módulo de Rendimiento y Base de Datos.

Rediseñada con arquitectura homologada a MLB y NFL:
- Nivel 1: Selector principal de mercado (Totales, Moneyline, Spread)
- Nivel 2: Selector interno de sección (Picks de hoy, Rendimiento e Historial)
- Nivel 3: Barra superior de 2 botones al 50%/50% en estilo dark glassmorphic
- Nivel 4: 4 tarjetas métricas de resumen
- Nivel 5: Proyecciones completas del mercado seleccionado para todos los partidos
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="NBA Oráculo AI · Pronósticos y Rendimiento",
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
from nba.registro import (
    cargar_historial_rendimiento,
    liquidar_partidos_pendientes_nba,
    guardar_predicciones_nba,
    es_liquidacion_valida,
)
from nba.proveedor_cuotas import american_to_prob
from core.constants import ZONA_CDMX


def cargar_predicciones(forzar: bool = False):
    """Carga las predicciones desde disco o ejecuta el pipeline si no existen o se solicita refresco."""
    hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
    if forzar or not RUTA_PREDICCIONES.exists():
        with st.spinner("Consultando DraftKings y ejecutando modelos de la NBA..."):
            preds = predecir_partidos_hoy(force_refresh=forzar)
            return preds
    try:
        with open(RUTA_PREDICCIONES, "r", encoding="utf-8") as f:
            preds = json.load(f)

        if preds and isinstance(preds, list):
            fecha_archivo = preds[0].get("fecha_cdmx")
            if fecha_archivo and fecha_archivo != hoy_cdmx:
                with st.spinner(f"Actualizando cartelera de hoy ({hoy_cdmx})..."):
                    try:
                        return predecir_partidos_hoy(force_refresh=True)
                    except Exception as e_rf:
                        logger.warning(f"Error refrescando cartelera: {e_rf}")
                        return preds

        pendientes = [
            p for p in preds
            if p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]
        ]
        if pendientes:
            try:
                guardar_predicciones_nba(pendientes)
            except Exception:
                pass
        return preds
    except Exception as e:
        logger.warning(f"Error en predicciones NBA: {e}")
        try:
            return predecir_partidos_hoy(force_refresh=True)
        except Exception:
            return []


def obtener_pick_para_mercado(p: dict, mercado_tipo: str) -> dict:
    """Calcula la recomendación, momio, probabilidad calibrada, edge y EV para el mercado elegido."""
    from core.ui_boleta import parsear_cuota_decimal
    from core.calibracion_probabilidades import calibrar_probabilidad

    # 1. Si el partido ya tiene un pick candidato validado por el filtro Dead Zone para este mercado
    candidatos = p.get("candidatos") or []
    for cand in candidatos:
        c_mercado = cand.get("mercado", "")
        if (
            ("Totales" in mercado_tipo and "Totales" in c_mercado)
            or ("Moneyline" in mercado_tipo and "Moneyline" in c_mercado)
            or ("Spread" in mercado_tipo and "Spread" in c_mercado)
        ):
            c_prob = float(cand.get("probabilidad", 0.5))
            c_conf = cand.get("confianza", "MEDIA")
            if "Moneyline" in mercado_tipo and c_prob < 0.50:
                c_conf = "LONGSHOT"
            return {
                "mercado": cand.get("mercado", mercado_tipo),
                "seleccion": cand.get("seleccion", "N/D"),
                "probabilidad": c_prob,
                "edge": float(cand.get("edge", 0.0)),
                "ev": float(cand.get("ev", 0.0)),
                "momio": str(cand.get("cuota", "-110")),
                "detalle": cand.get("detalle", ""),
                "confianza": c_conf,
            }

    # 2. Si no hay candidato calificado (Zona Muerta / Dead Zone o sin edge), calcular lean pasivo calibrado
    if "Totales" in mercado_tipo:
        linea = p.get("linea_total")
        proy = float(p.get("total_proyectado") or 0.0)
        p_over_raw = float(p.get("prob_over") or 0.5)
        p_under_raw = float(p.get("prob_under") or 0.5)
        edge_pts = float(p.get("edge_puntos_total") or 0.0)

        if linea is None or linea <= 0:
            return {
                "mercado": "Totales",
                "seleccion": "Línea N/D",
                "probabilidad": 0.5,
                "edge": 0.0,
                "ev": 0.0,
                "momio": "N/D",
                "detalle": f"Proyección: {proy:.1f} pts · Sin línea oficial disponible",
                "confianza": "NEUTRAL",
            }

        p_over_cal = float(calibrar_probabilidad(p_over_raw, 1.909))
        p_under_cal = float(calibrar_probabilidad(p_under_raw, 1.909))
        edge_over = p_over_cal - 0.5238
        edge_under = p_under_cal - 0.5238
        ev_over = (p_over_cal * 1.909) - 1.0
        ev_under = (p_under_cal * 1.909) - 1.0

        if edge_over >= edge_under:
            sel = f"OVER {linea}"
            prob = p_over_cal
            edge = edge_over
            ev = ev_over
        else:
            sel = f"UNDER {linea}"
            prob = p_under_cal
            edge = edge_under
            ev = ev_under

        if edge >= 0.065 and ev >= 0.04:
            conf = "ALTA"
            det = f"Proyección: {proy:.1f} pts vs Línea {linea} (Edge Cal: {edge*100:+.1f}%, EV: {ev*100:+.1f}%)"
        elif edge >= 0.045 and ev >= 0.025:
            conf = "MEDIA"
            det = f"Proyección: {proy:.1f} pts vs Línea {linea} (Edge Cal: {edge*100:+.1f}%, EV: {ev*100:+.1f}%)"
        else:
            conf = "NEUTRAL"
            det = f"Línea de mercado eficiente. Edge calibrado ({edge*100:+.1f}%) debajo del umbral (+4.5%). Descartado para proteger bankroll."

        return {
            "mercado": "Totales",
            "seleccion": sel,
            "probabilidad": prob,
            "edge": edge,
            "ev": ev,
            "momio": "-110 (1.91)",
            "detalle": det,
            "confianza": conf,
        }

    elif "Moneyline" in mercado_tipo:
        p_loc_raw = float(p.get("prob_local_win") or 0.5)
        p_vis_raw = float(p.get("prob_visita_win") or 0.5)
        ml_loc = p.get("ml_local", "N/D")
        ml_vis = p.get("ml_visita", "N/D")

        cuota_dec_loc = float(p.get("ml_local_dec") or parsear_cuota_decimal(ml_loc) or 1.91)
        cuota_dec_vis = float(p.get("ml_visita_dec") or parsear_cuota_decimal(ml_vis) or 1.91)

        p_loc_cal = float(calibrar_probabilidad(p_loc_raw, cuota_dec_loc))
        p_vis_cal = float(calibrar_probabilidad(p_vis_raw, cuota_dec_vis))

        prob_loc_book = american_to_prob(ml_loc) if ml_loc != "N/D" else 0.5
        prob_vis_book = american_to_prob(ml_vis) if ml_vis != "N/D" else 0.5
        edge_loc = p_loc_cal - prob_loc_book
        edge_vis = p_vis_cal - prob_vis_book
        ev_loc = (p_loc_cal * cuota_dec_loc) - 1.0
        ev_vis = (p_vis_cal * cuota_dec_vis) - 1.0

        spread_det = p.get("spread_detalles", "Spread")

        if ev_loc >= ev_vis:
            sel = f"{p.get('equipo_local')} ML"
            prob = p_loc_cal
            momio = ml_loc
            edge = edge_loc
            ev = ev_loc
        else:
            sel = f"{p.get('equipo_visita')} ML"
            prob = p_vis_cal
            momio = ml_vis
            edge = edge_vis
            ev = ev_vis

        if edge >= 0.065 and ev >= 0.04:
            if prob >= 0.55:
                conf = "ALTA"
                det = f"Prob Calibrada: {prob*100:.1f}% vs Book: {(prob - edge)*100:.1f}% (Edge: {edge*100:+.1f}%, EV: {ev*100:+.1f}%)"
            elif prob >= 0.50:
                conf = "MEDIA"
                det = f"Prob Calibrada: {prob*100:.1f}% vs Book: {(prob - edge)*100:.1f}% (Edge: {edge*100:+.1f}%, EV: {ev*100:+.1f}%)"
            else:
                conf = "LONGSHOT"
                det = f"🎯 Longshot (+EV {ev*100:+.1f}%). Probabilidad de victoria ({prob*100:.1f}%) debajo del 50%. Se sugiere preferir el Spread ({spread_det})."
        elif edge >= 0.045 and ev >= 0.025:
            if prob >= 0.50:
                conf = "MEDIA"
                det = f"Prob Calibrada: {prob*100:.1f}% vs Book: {(prob - edge)*100:.1f}% (Edge: {edge*100:+.1f}%, EV: {ev*100:+.1f}%)"
            else:
                conf = "LONGSHOT"
                det = f"🎯 Longshot (+EV {ev*100:+.1f}%). Probabilidad de victoria ({prob*100:.1f}%) debajo del 50%. Se sugiere preferir el Spread ({spread_det})."
        else:
            conf = "NEUTRAL"
            det = f"Sin ventaja sobre la cuota ({edge*100:+.1f}% edge calibrado). Partido en Zona Muerta descartado."

        return {
            "mercado": "Moneyline",
            "seleccion": sel,
            "probabilidad": prob,
            "edge": edge,
            "ev": ev,
            "momio": str(momio),
            "detalle": det,
            "confianza": conf,
        }

    else:  # Spread / Hándicap
        spread_val = float(p.get("linea_spread") or 0.0)
        spread_det = p.get("spread_detalles", "N/D")
        margen = float(p.get("margen_local_esperado") or 0.0)
        p_cov_loc_raw = float(p.get("prob_cover_home") or 0.5)
        p_cov_vis_raw = float(p.get("prob_cover_away") or 0.5)

        p_cov_loc_cal = float(calibrar_probabilidad(p_cov_loc_raw, 1.909))
        p_cov_vis_cal = float(calibrar_probabilidad(p_cov_vis_raw, 1.909))

        edge_cov_loc = p_cov_loc_cal - 0.5238
        edge_cov_vis = p_cov_vis_cal - 0.5238
        ev_cov_loc = (p_cov_loc_cal * 1.909) - 1.0
        ev_cov_vis = (p_cov_vis_cal * 1.909) - 1.0

        if edge_cov_loc >= edge_cov_vis:
            sel = f"{p.get('equipo_local')} {spread_val:+0.1f}"
            prob = p_cov_loc_cal
            edge = edge_cov_loc
            ev = ev_cov_loc
        else:
            sel = f"{p.get('equipo_visita')} {-spread_val:+0.1f}"
            prob = p_cov_vis_cal
            edge = edge_cov_vis
            ev = ev_cov_vis

        if edge >= 0.06 and ev >= 0.04:
            conf = "ALTA"
            det = f"Margen estimado: {margen:+0.1f} pts · Línea: {spread_det} (Edge Cal: {edge*100:+.1f}%, EV: {ev*100:+.1f}%)"
        elif edge >= 0.045 and ev >= 0.025:
            conf = "MEDIA"
            det = f"Margen estimado: {margen:+0.1f} pts · Línea: {spread_det} (Edge Cal: {edge*100:+.1f}%, EV: {ev*100:+.1f}%)"
        else:
            conf = "NEUTRAL"
            det = f"Margen estimado ({margen:+0.1f} pts) alineado al mercado ({spread_det}). Sin ventaja estadística suficiente."

        return {
            "mercado": "Spread",
            "seleccion": sel,
            "probabilidad": prob,
            "edge": edge,
            "ev": ev,
            "momio": "-110 (1.91)",
            "detalle": det,
            "confianza": conf,
        }



def render_cartelera_nba(predicciones: list[dict], mercado: str):
    """Renderiza las tarjetas interactivas de pronósticos de la NBA para el mercado elegido."""
    if not predicciones:
        st.info("🏀 No hay partidos programados para hoy en la cartelera de la NBA. Puedes volver a consultar más tarde o forzar la actualización.")
        return

    partidos_pendientes = [
        p for p in predicciones
        if p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]
    ]
    partidos_liquidados = [
        p for p in predicciones
        if p.get("resultado") in ["GANADA", "PERDIDA", "PUSH"]
    ]

    total_partidos = len(predicciones)
    n_pendientes = len(partidos_pendientes)
    n_liquidados = len(partidos_liquidados)

    # Picks calificados (+EV fuera de Dead Zone) en el mercado activo
    picks_calificados = sum(
        1 for p in partidos_pendientes
        if obtener_pick_para_mercado(p, mercado).get("confianza") in ["ALTA", "MEDIA"]
    )

    # 4 tarjetas métricas ejecutivas homologadas
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Partidos", total_partidos)
    with c2:
        st.metric("Pendientes", n_pendientes)
    with c3:
        st.metric("Finalizados", n_liquidados)
    with c4:
        st.metric("Picks Calificados (+EV)", picks_calificados)
    st.markdown("<div style='margin-bottom: 1.25rem;'></div>", unsafe_allow_html=True)

    if n_pendientes == 0 and total_partidos > 0:
        st.markdown(
            f"""<div style="background: linear-gradient(145deg, #18110b, #0f0a06); border: 1px solid #ff6b00; border-radius: 16px; padding: 2rem; text-align: center; margin-top: 1.2rem; margin-bottom: 2rem;">
<div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🏀🏁</div>
<div style="font-size: 1.35rem; font-weight: 900; color: #ff8c33; margin-bottom: 0.5rem;">Partidos Concluidos y Auditados</div>
<div style="color: #cbd5e1; font-size: 0.95rem; max-width: 620px; margin: 0 auto; line-height: 1.55;">
Los partidos de la cartelera anterior ({n_liquidados} juegos) ya finalizaron y han sido liquidados en <b>Rendimiento e Historial</b>. Para consultar la nueva cartelera, pulsa <b>Actualizar Cuotas DraftKings</b>.
</div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    from core.ui_boleta import render_boton_boleta, render_widget_boleta

    f_col1, f_col2 = st.columns([2, 1], gap="medium")
    with f_col1:
        busqueda_nba = st.text_input(
            "Buscar equipo NBA",
            key="nba_search_input",
            placeholder="🔍 Ej: Lakers, Celtics, GSW, Warriors, Miami...",
        ).strip().lower()
    with f_col2:
        st.markdown("<div style='margin-top: 1.8rem;'></div>", unsafe_allow_html=True)
        solo_ev = st.checkbox("🔥 Solo picks Calificados (+EV)", key="nba_ev_filter")

    lista_mostrar = predicciones
    if busqueda_nba:
        lista_mostrar = [
            p for p in lista_mostrar
            if (busqueda_nba in str(p.get("equipo_local", "")).lower() or
                busqueda_nba in str(p.get("equipo_visita", "")).lower() or
                busqueda_nba in str(p.get("abbr_local", "")).lower() or
                busqueda_nba in str(p.get("abbr_visita", "")).lower() or
                busqueda_nba in str(p.get("partido", "")).lower())
        ]
    if solo_ev:
        lista_mostrar = [
            p for p in lista_mostrar
            if obtener_pick_para_mercado(p, mercado).get("confianza") in ["ALTA", "MEDIA"]
        ]

    if not lista_mostrar:
        st.warning("No hay partidos o picks que coincidan con los filtros de búsqueda seleccionados.")
        return

    # Renderizado de Tarjetas de partidos individuales para el mercado seleccionado
    for idx, p in enumerate(lista_mostrar):
        pick_info = obtener_pick_para_mercado(p, mercado)
        conf = pick_info["confianza"]
        if conf == "ALTA":
            badge_conf = "badge-conf-alta"
        elif conf == "MEDIA":
            badge_conf = "badge-conf-media"
        else:
            badge_conf = "badge-conf-media"
        
        # Cálculo del Valor Esperado real: EV% = (probabilidad * cuota_decimal - 1.0) * 100
        from core.ui_boleta import parsear_cuota_decimal
        c_dec = parsear_cuota_decimal(pick_info.get("momio"))
        prob = float(pick_info.get("probabilidad") or 0.5)
        ev_calc = (prob * c_dec - 1.0) * 100.0 if (c_dec > 1.0 and prob > 0) else 0.0
        ev_badge = f'<span class="badge-ev" style="margin-left: 0.45rem;">🔥 +EV +{ev_calc:.1f}%</span>' if (ev_calc >= 2.0 and conf != "NEUTRAL") else ""

        resultado_pick = p.get("resultado")
        u_gan = p.get("unidades_ganadas")
        m_loc = p.get("marcador_local")
        m_vis = p.get("marcador_visita")
        estado = str(p.get("estado", "")).upper()
        es_final = ("FINAL" in estado) or (resultado_pick in ["GANADA", "PERDIDA", "PUSH"])
        en_vivo = "PROGRESS" in estado

        if es_final:
            badge_status = '<span class="badge-time">🏁 FINALIZADO</span>'
        elif en_vivo:
            badge_status = '<span class="badge-time" style="background:#2b1208;color:#ff8c33;border-color:#ff6b00;">🔴 EN VIVO</span>'
        else:
            badge_status = f'<span class="badge-time">⏰ {p.get("hora_cdmx", "TBD")} CDMX</span>'

        if resultado_pick == "GANADA":
            val_u = f"+{u_gan:.2f}" if (u_gan is not None and u_gan > 0) else ("+0.91" if u_gan is None else f"{u_gan:.2f}")
            badge_top_right = f'<span style="background: rgba(34, 197, 94, 0.16); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.55); padding: 0.25rem 0.75rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem;">🏆 GANADA ({val_u} u)</span>'
        elif resultado_pick == "PERDIDA":
            badge_top_right = '<span style="background: rgba(239, 68, 68, 0.16); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.55); padding: 0.25rem 0.75rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem;">❌ PERDIDA (-1.00 u)</span>'
        elif resultado_pick == "PUSH":
            badge_top_right = '<span style="background: rgba(148, 163, 184, 0.16); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.55); padding: 0.25rem 0.75rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem;">🤝 PUSH (0.00 u)</span>'
        else:
            if conf == "ALTA":
                badge_top_right = f'<div style="display:inline-flex; align-items:center;"><span class="badge-conf-alta">CONFIANZA ALTA</span>{ev_badge}</div>'
            elif conf == "MEDIA":
                badge_top_right = f'<div style="display:inline-flex; align-items:center;"><span class="badge-conf-media">CONFIANZA MEDIA</span>{ev_badge}</div>'
            elif conf == "LONGSHOT":
                badge_top_right = f'<div style="display:inline-flex; align-items:center;"><span style="background: rgba(245, 158, 11, 0.16); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.55); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem;">🎯 LONGSHOT (+EV ALTO RIESGO)</span>{ev_badge}</div>'
            else:
                badge_top_right = '<span style="background: rgba(148, 163, 184, 0.12); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.35); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 700; font-size: 0.8rem;">⏸️ LÍNEA EFICIENTE (SIN EDGE)</span>'

        card_top_html = (
            f'<div class="card-top">'
            f'<div style="display: flex; align-items: center; gap: 0.5rem;">'
            f'{badge_status}'
            f'<span style="color: #a4978e; font-size: 0.8rem;">{p.get("provider", "DraftKings")} Sportsbook</span>'
            f'</div>'
            f'<div>{badge_top_right}</div>'
            f'</div>'
        )

        tiene_marcador = (es_final or en_vivo) and (m_vis is not None and m_loc is not None)
        if tiene_marcador:
            center_html = (
                f'<div style="font-size: 1.35rem; color: #ff8c33; font-weight: 900; background: #23160e; '
                f'border: 1px solid #ff6b00; padding: 0.2rem 0.8rem; border-radius: 8px;">'
                f'{int(m_vis)} - {int(m_loc)}</div>'
            )
        else:
            center_html = '<div style="font-size: 1.1rem; color: #5a687d; font-weight: 800;">@</div>'

        teams_html = (
            f'<div class="teams-row">'
            f'<div>'
            f'<div class="team-name">{p.get("equipo_visita")}</div>'
            f'<div class="team-sub">Visitante ({p.get("abbr_visita")}) · ML: <b>{p.get("ml_visita", "N/D")}</b></div>'
            f'</div>'
            f'<div style="text-align: center;">{center_html}</div>'
            f'<div style="text-align: right;">'
            f'<div class="team-name">{p.get("equipo_local")}</div>'
            f'<div class="team-sub">Local ({p.get("abbr_local")}) · ML: <b>{p.get("ml_local", "N/D")}</b></div>'
            f'</div>'
            f'</div>'
        )

        cuota_str = f" · Momio: {pick_info['momio']}" if pick_info['momio'] != "N/D" else ""

        if resultado_pick in ["GANADA", "PERDIDA", "PUSH"]:
            color_res = "#4ade80" if resultado_pick == "GANADA" else ("#f87171" if resultado_pick == "PERDIDA" else "#cbd5e1")
            val_u_box = f"+{u_gan:.2f}" if (u_gan is not None and u_gan > 0) else ("+0.91" if u_gan is None else f"{u_gan:.2f}")
            pick_res_html = (
                f'<div style="text-align: right;">'
                f'<div style="font-size: 0.72rem; color: #a4978e; font-weight: 700;">RESULTADO AUDITADO</div>'
                f'<div style="font-size: 1.15rem; font-weight: 900; color: {color_res};">{resultado_pick} ({val_u_box} u)</div>'
                f'</div>'
            )
        else:
            prob_pct = pick_info["probabilidad"] * 100
            lbl_prob = "PROBABILIDAD CALIBRADA" if conf in ["ALTA", "MEDIA", "LONGSHOT"] else "ESTIMACIÓN NEUTRAL"
            clr_prob = "#ff8c33" if conf in ["ALTA", "MEDIA"] else ("#fbbf24" if conf == "LONGSHOT" else "#94a3b8")
            pick_res_html = (
                f'<div style="text-align: right;">'
                f'<div style="font-size: 0.72rem; color: #a4978e; font-weight: 700;">{lbl_prob}</div>'
                f'<div style="font-size: 1.35rem; font-weight: 900; color: {clr_prob};">{prob_pct:.1f}%</div>'
                f'</div>'
            )

        if conf in ["ALTA", "MEDIA"]:
            titulo_box = f"Recomendación ({pick_info['mercado']})"
        elif conf == "LONGSHOT":
            titulo_box = f"🎯 Longshot de Valor ({pick_info['mercado']}) · Alto Riesgo"
        else:
            titulo_box = f"Línea de Referencia ({pick_info['mercado']})"

        pick_box_html = (
            f'<div class="pick-box">'
            f'<div style="min-width: 0; flex: 1;">'
            f'<div class="pick-title">{titulo_box}<span style="color:#ffffff;font-weight:700;">{cuota_str}</span></div>'
            f'<div class="pick-sel">{pick_info["seleccion"]}</div>'
            f'<div style="font-size: 0.82rem; color: #a4978e; margin-top: 0.2rem;">{pick_info["detalle"]}</div>'
            f'</div>'
            f'{pick_res_html}'
            f'</div>'
        )

        with st.container(border=True):
            st.markdown(card_top_html + teams_html + pick_box_html, unsafe_allow_html=True)

            if conf in ["ALTA", "MEDIA"]:
                evento_id = str(p.get("id_evento") or p.get("id_juego") or f"{p.get('abbr_visita')}_{p.get('abbr_local')}_{idx}")
                clean_mercado = str(mercado).replace(" ", "_").replace("(", "").replace(")", "")
                slip_item = {
                    "id": f"NBA_{evento_id}_{clean_mercado}_{pick_info['seleccion']}",
                    "deporte": "NBA",
                    "icono": "🏀",
                    "partido": p.get("partido") or f"{p.get('equipo_visita')} @ {p.get('equipo_local')}",
                    "mercado": mercado,
                    "seleccion": pick_info["seleccion"],
                    "momio": pick_info["momio"],
                    "prob": pick_info["probabilidad"],
                }
                render_boton_boleta(slip_item, key=f"btn_nba_slip_{evento_id}_{clean_mercado}_{idx}")
            elif conf == "LONGSHOT":
                st.warning(f"⚠️ **Longshot de Alto Riesgo:** Aunque tiene valor matemático (+EV +{ev_calc:.1f}%), la probabilidad de ganar es solo del **{prob*100:.1f}%**. Sugerencia: reduce el importe a 0.25u o prefiere el **Spread ({p.get('spread_detalles', 'Hándicap')})**.")
                evento_id = str(p.get("id_evento") or p.get("id_juego") or f"{p.get('abbr_visita')}_{p.get('abbr_local')}_{idx}")
                clean_mercado = str(mercado).replace(" ", "_").replace("(", "").replace(")", "")
                slip_item = {
                    "id": f"NBA_{evento_id}_{clean_mercado}_{pick_info['seleccion']}",
                    "deporte": "NBA",
                    "icono": "🏀",
                    "partido": p.get("partido") or f"{p.get('equipo_visita')} @ {p.get('equipo_local')}",
                    "mercado": mercado,
                    "seleccion": pick_info["seleccion"],
                    "momio": pick_info["momio"],
                    "prob": pick_info["probabilidad"],
                }
                render_boton_boleta(slip_item, key=f"btn_nba_slip_{evento_id}_{clean_mercado}_{idx}")
            else:
                st.caption("🛡️ *Filtro de Disciplina Activo: Este partido está en la Zona Muerta (edge < +4.5%). Descartado para apuestas.*")

            with st.expander("📊 Ver desglose analítico completo (Spreads, Totales y Probabilidades 1X2)"):
                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    st.caption("🏀 **Probabilidad Ganador (Moneyline)**")
                    p_vis = float(p.get("prob_visita_win") or 0.5) * 100
                    p_loc = float(p.get("prob_local_win") or 0.5) * 100
                    st.progress(int(p_loc), text=f"Local {p_loc:.1f}% vs Visita {p_vis:.1f}%")
                    margen = float(p.get("margen_local_esperado") or 0.0)
                    signo = "+" if margen > 0 else ""
                    st.markdown(f"<span class='stat-pill'>Margen modelo: <b>{signo}{margen:.1f} pts</b> local</span>", unsafe_allow_html=True)

                with col_c2:
                    st.caption("🎯 **Totales (Over / Under)**")
                    tot_proy = float(p.get("total_proyectado") or 0.0)
                    linea_tot = p.get("linea_total") or "N/D"
                    edge_tot = float(p.get("edge_puntos_total") or 0.0)
                    signo_edge = "+" if edge_tot > 0 else ""
                    st.write(f"Línea Casa: **{linea_tot}** · Modelo: **{tot_proy:.1f} pts**")
                    st.markdown(f"<span class='stat-pill'>Edge: <b>{signo_edge}{edge_tot:.1f} pts</b></span>", unsafe_allow_html=True)

                with col_c3:
                    st.caption("⚖️ **Spread / Hándicap**")
                    spread_det = p.get("spread_detalles", "N/D")
                    prob_cov_loc = float(p.get("prob_cover_home") or 0.5) * 100
                    prob_cov_vis = float(p.get("prob_cover_away") or 0.5) * 100
                    st.write(f"Línea: **{spread_det}**")
                    st.markdown(f"<span class='stat-pill'>Cubrir spread: Local {prob_cov_loc:.1f}% | Visita {prob_cov_vis:.1f}%</span>", unsafe_allow_html=True)

    render_widget_boleta()


def render_historial_nba(mercado_filtro: str = ""):
    """Renderiza la auditoría histórica de apuestas de la NBA."""
    df_hist = cargar_historial_rendimiento()

    if df_hist.empty:
        st.info("No hay historial disponible aún en la base de datos de la NBA.")
        return

    liquidados = df_hist[df_hist.apply(es_liquidacion_valida, axis=1)].copy()
    if liquidados.empty:
        st.info("Aún no hay apuestas liquidadas en el historial de la NBA.")
        return

    dt_serie = pd.to_datetime(liquidados["fecha"], errors="coerce")
    y_serie = dt_serie.dt.year
    m_serie = dt_serie.dt.month
    next_yy = ((y_serie + 1) % 100).astype(str).str.zfill(2)
    cur_yy = (y_serie % 100).astype(str).str.zfill(2)
    prev_y = (y_serie - 1).astype(str)
    liquidados["temporada"] = np.where(m_serie >= 10, y_serie.astype(str) + "-" + next_yy, prev_y + "-" + cur_yy)

    temporadas_ordenadas = sorted(liquidados["temporada"].unique().tolist(), reverse=True)
    temp_actual = temporadas_ordenadas[0] if temporadas_ordenadas else "2026-27"

    st.markdown("<div style='font-size: 0.82rem; font-weight: 800; color: #ff8c33; letter-spacing: 0.08em; margin-bottom: 0.35rem;'>FILTROS TEMPORALES Y DE PARTIDO</div>", unsafe_allow_html=True)
    tcol1, tcol2, tcol3 = st.columns(3)

    with tcol1:
        opciones_temp = ["Todas las temporadas"] + [
            f"{t} (Actual)" if t == temp_actual else t for t in temporadas_ordenadas
        ]
        sel_temp_label = st.selectbox("📅 Temporada", opciones_temp, index=0)
        sel_temp = sel_temp_label.replace(" (Actual)", "")

    df_para_dias = liquidados if sel_temp == "Todas las temporadas" else liquidados[liquidados["temporada"] == sel_temp]
    fechas_disp = sorted(df_para_dias["fecha"].dropna().unique().tolist(), reverse=True)

    with tcol2:
        opciones_dias = ["Todos los días"] + fechas_disp
        sel_dia = st.selectbox("📆 Día / Fecha", opciones_dias, index=0)

    df_para_juegos = df_para_dias if sel_dia == "Todos los días" else df_para_dias[df_para_dias["fecha"] == sel_dia]

    juegos_unicos_map = {}
    for _, row in df_para_juegos.sort_values("fecha", ascending=False).iterrows():
        id_partido = f"{row['fecha']}_{row['equipo_visitante']}_{row['equipo_local']}"
        if id_partido not in juegos_unicos_map:
            if sel_dia == "Todos los días":
                lbl_juego = f"{row['fecha']} · {row['equipo_visitante']} @ {row['equipo_local']}"
            else:
                lbl_juego = f"{row['equipo_visitante']} @ {row['equipo_local']}"
            juegos_unicos_map[id_partido] = lbl_juego

    with tcol3:
        opciones_juegos = ["Todos los juegos"] + list(juegos_unicos_map.values())
        sel_juego = st.selectbox("🏀 Juego / Partido", opciones_juegos, index=0)

    st.markdown("<div style='font-size: 0.82rem; font-weight: 800; color: #ff8c33; letter-spacing: 0.08em; margin-top: 0.4rem; margin-bottom: 0.35rem;'>CRITERIOS DE AUDITORÍA</div>", unsafe_allow_html=True)
    rcol1, rcol2, rcol3 = st.columns(3)
    with rcol1:
        mercados_disp = ["Todos los mercados", "Totales (Over y Under)", "Moneyline", "Spread", "Totales (OVER)", "Totales (UNDER)"]
        idx_mercado = 0
        if "Totales" in mercado_filtro:
            idx_mercado = 1
        elif "Moneyline" in mercado_filtro:
            idx_mercado = 2
        elif "Spread" in mercado_filtro:
            idx_mercado = 3

        sel_mercado = st.selectbox("Mercado para Auditoría", mercados_disp, index=idx_mercado)
    with rcol2:
        confianzas_disp = ["Todas las confianzas", "Solo ALTA", "Solo MEDIA"]
        sel_conf = st.selectbox("Nivel de Confianza en Auditoría", confianzas_disp)
    with rcol3:
        sel_resultado = st.selectbox("Estado del Resultado", ["Todos los resultados", "Solo Ganadas", "Solo Perdidas", "Solo Pushes"])

    # Aplicar filtros
    f_liq = liquidados.copy()
    if sel_temp != "Todas las temporadas":
        f_liq = f_liq[f_liq["temporada"] == sel_temp]
    if sel_dia != "Todos los días":
        f_liq = f_liq[f_liq["fecha"] == sel_dia]
    if sel_juego != "Todos los juegos":
        for k_id, v_lbl in juegos_unicos_map.items():
            if v_lbl == sel_juego:
                parts = k_id.split("_", 2)
                f_liq = f_liq[
                    (f_liq["fecha"] == parts[0]) &
                    (f_liq["equipo_visitante"] == parts[1]) &
                    (f_liq["equipo_local"] == parts[2])
                ]
                break
    if sel_mercado == "Totales (Over y Under)":
        f_liq = f_liq[f_liq["mercado"].str.startswith("Totales")]
    elif sel_mercado != "Todos los mercados":
        f_liq = f_liq[f_liq["mercado"] == sel_mercado]
    if sel_conf == "Solo ALTA":
        f_liq = f_liq[f_liq["confianza"] == "ALTA"]
    elif sel_conf == "Solo MEDIA":
        f_liq = f_liq[f_liq["confianza"] == "MEDIA"]
    if sel_resultado == "Solo Ganadas":
        f_liq = f_liq[f_liq["resultado"] == "GANADA"]
    elif sel_resultado == "Solo Perdidas":
        f_liq = f_liq[f_liq["resultado"] == "PERDIDA"]
    elif sel_resultado == "Solo Pushes":
        f_liq = f_liq[f_liq["resultado"] == "PUSH"]

    if f_liq.empty:
        st.warning("⚠️ No se encontraron picks ni partidos liquidados para la combinación de filtros seleccionada.")
        return

    # Métricas
    n_eval = len(f_liq)
    ganadas = int((f_liq["resultado"] == "GANADA").sum())
    perdidas = int((f_liq["resultado"] == "PERDIDA").sum())
    pushes = int((f_liq["resultado"] == "PUSH").sum())
    decididas = ganadas + perdidas
    acierto_pct = (ganadas / decididas * 100.0) if decididas else 0.0
    beneficio_u = float(f_liq["unidades_ganadas"].sum()) if n_eval else 0.0
    roi_pct = (beneficio_u / n_eval * 100.0) if n_eval else 0.0

    rmcols = st.columns(4)
    rmcols[0].metric("Picks Evaluados", f"{n_eval:,}")
    rmcols[1].metric("Acierto", f"{acierto_pct:.1f}%", f"{ganadas}G - {perdidas}P" + (f" ({pushes} Push)" if pushes else ""))
    rmcols[2].metric("Unidades Netas", f"{beneficio_u:+.2f} u")
    rmcols[3].metric("ROI", f"{roi_pct:+.2f}%")

    # Gráfica de evolución acumulada
    if len(f_liq) > 1 and f_liq["fecha"].nunique() > 1:
        st.write("")
        st.subheader("📈 Evolución de Unidades en el Tiempo (1 u plana)")
        f_liq_chart = f_liq.copy()
        f_liq_chart["fecha_dt"] = pd.to_datetime(f_liq_chart["fecha"])
        evolucion = f_liq_chart.sort_values("fecha_dt").copy()
        evolucion["Unidades Acumuladas"] = evolucion["unidades_ganadas"].cumsum()

        chart_data = evolucion.set_index("fecha_dt")["Unidades Acumuladas"]
        st.line_chart(chart_data, use_container_width=True)

    # Desglose por mercado
    with st.expander("📊 Desglose Detallado por Mercado"):
        agrupado = []
        for m, g in f_liq.groupby("mercado"):
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

    # Tarjetas de partidos liquidados
    st.write("")
    partidos_grupos = []
    for (f_val, ev_val, el_val), g_df in f_liq.sort_values(["fecha", "hora_cdmx"], ascending=[False, False]).groupby(
        ["fecha", "equipo_visitante", "equipo_local"], sort=False
    ):
        h_cdmx = g_df["hora_cdmx"].iloc[0] if "hora_cdmx" in g_df.columns else "TBD"
        mv = g_df["marcador_visitante"].iloc[0] if "marcador_visitante" in g_df.columns else None
        ml = g_df["marcador_local"].iloc[0] if "marcador_local" in g_df.columns else None
        temp_val = g_df["temporada"].iloc[0] if "temporada" in g_df.columns else ""

        # En juegos pasados solo se maneja Moneyline y Totales (el spread solo aplica para juegos de hoy en adelante)
        hoy_str = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
        if str(f_val) < hoy_str:
            g_df = g_df[g_df["mercado"] != "Spread"]

        # Deduplicar picks del mismo tipo de mercado por partido (máx 1 Totales y 1 Moneyline)
        g_df_picks = g_df.copy()
        g_df_picks["_tipo_m"] = g_df_picks["mercado"].apply(lambda x: "Totales" if "Totales" in str(x) else str(x))
        # Si hay duplicado en Totales, priorizar la línea real (diferente de 228.0)
        g_df_picks = g_df_picks.sort_values(by=["_tipo_m", "linea"], ascending=[True, False]).drop_duplicates(subset=["_tipo_m"], keep="first")
        g_df_picks = g_df_picks.drop(columns=["_tipo_m"])

        partidos_grupos.append({
            "fecha": f_val,
            "hora_cdmx": h_cdmx,
            "temporada": temp_val,
            "equipo_visitante": ev_val,
            "equipo_local": el_val,
            "marcador_visitante": mv,
            "marcador_local": ml,
            "picks": g_df_picks.to_dict(orient="records"),
            "unidades_totales": float(g_df_picks["unidades_ganadas"].sum())
        })

    total_partidos = len(partidos_grupos)
    st.subheader(f"🏀 Partidos Liquidados ({total_partidos} partidos · {n_eval} picks)")

    max_tarjetas = 20
    partidos_a_mostrar = partidos_grupos[:max_tarjetas]

    for p_partido in partidos_a_mostrar:
        mv = p_partido["marcador_visitante"]
        ml = p_partido["marcador_local"]
        mv_str = str(int(mv)) if pd.notna(mv) else "-"
        ml_str = str(int(ml)) if pd.notna(ml) else "-"
        u_partido = p_partido["unidades_totales"]
        color_bal = "#4ade80" if u_partido > 0 else ("#f87171" if u_partido < 0 else "#cbd5e1")

        with st.container(border=True):
            card_hist_top = (
                f'<div class="card-top">'
                f'<div>'
                f'<span class="badge-time" style="background: #2a180e; color: #ffaa66; border: 1px solid #ff6b00; font-weight: 800;">🏁 PARTIDO LIQUIDADO</span>'
                f'<span style="margin-left: 0.6rem; color: #a4978e; font-size: 0.8rem;">📅 {p_partido["fecha"]} · ⏰ {p_partido["hora_cdmx"]} CDMX (Temporada {p_partido["temporada"]})</span>'
                f'</div>'
                f'<div>'
                f'<span style="font-size: 0.78rem; color: #a4978e; font-weight: 700; margin-right: 0.4rem;">BALANCE JUEGO:</span>'
                f'<span style="font-weight: 900; font-size: 1rem; color: {color_bal};">{u_partido:+.2f} u</span>'
                f'</div>'
                f'</div>'
            )

            teams_hist = (
                f'<div class="teams-row">'
                f'<div>'
                f'<div class="team-name">{p_partido["equipo_visitante"]} <span style="color: #ff8c33; margin-left: 0.4rem; font-size: 1.4rem; font-weight: 900;">{mv_str}</span></div>'
                f'<div class="team-sub">Visitante</div>'
                f'</div>'
                f'<div style="font-size: 1rem; color: #ff6b00; font-weight: 900; letter-spacing: 0.08em; background: #22140a; border: 1px solid #ff6b00; padding: 0.2rem 0.6rem; border-radius: 6px;">FINAL</div>'
                f'<div style="text-align: right;">'
                f'<div class="team-name"><span style="color: #ff8c33; margin-right: 0.4rem; font-size: 1.4rem; font-weight: 900;">{ml_str}</span> {p_partido["equipo_local"]}</div>'
                f'<div class="team-sub">Local</div>'
                f'</div>'
                f'</div>'
            )

            st.markdown(card_hist_top + teams_hist, unsafe_allow_html=True)

            for p in p_partido["picks"]:
                resultado_pick = p.get("resultado")
                u_gan = p.get("unidades_ganadas")
                color_res = "#4ade80" if resultado_pick == "GANADA" else ("#f87171" if resultado_pick == "PERDIDA" else "#cbd5e1")
                val_u_box = f"+{u_gan:.2f}" if (u_gan is not None and u_gan > 0) else ("+0.91" if u_gan is None else f"{u_gan:.2f}")

                linea_info = f" · Línea: <b>{p.get('linea')}</b>" if (pd.notna(p.get("linea")) and p.get("linea") != 0.0) else ""

                pick_hist_box = (
                    f'<div class="pick-box" style="margin-bottom: 0.5rem;">'
                    f'<div>'
                    f'<div class="pick-title">Recomendación Auditada ({p.get("mercado")}) · Confianza {p.get("confianza", "MEDIA")}</div>'
                    f'<div class="pick-sel">{p.get("seleccion")}</div>'
                    f'<div style="font-size: 0.8rem; color: #a4978e; margin-top: 0.2rem;">'
                    f'Cuota: <b>{p.get("cuota", 1.91):.2f}</b> · Prob. Modelo: <b>{float(p.get("probabilidad", 0.5))*100:.1f}%</b>{linea_info}'
                    f'</div>'
                    f'</div>'
                    f'<div style="text-align: right;">'
                    f'<div style="font-size: 0.72rem; color: #a4978e; font-weight: 700;">RESULTADO AUDITADO</div>'
                    f'<div style="font-size: 1.15rem; font-weight: 900; color: {color_res};">{resultado_pick} ({val_u_box} u)</div>'
                    f'</div>'
                    f'</div>'
                )
                st.markdown(pick_hist_box, unsafe_allow_html=True)

    if total_partidos > max_tarjetas:
        st.info(f"ℹ️ Mostrando las tarjetas de los {max_tarjetas} partidos más recientes de {total_partidos}. Utiliza los filtros superiores para aislar cualquier fecha específica.")

    st.write("")
    st.subheader(f"📋 Registro Completo de Auditoría ({len(f_liq)} registros)")

    df_tabla = f_liq.sort_values(["fecha", "hora_cdmx"], ascending=[False, False]).copy()
    df_tabla["Partido"] = df_tabla["equipo_visitante"] + " @ " + df_tabla["equipo_local"]
    df_tabla["Marcador Final"] = df_tabla.apply(
        lambda r: f"{int(r['marcador_visitante'])} - {int(r['marcador_local'])}"
        if pd.notna(r.get("marcador_visitante")) and pd.notna(r.get("marcador_local"))
        else "N/D",
        axis=1
    )
    df_tabla["Cuota"] = df_tabla["cuota"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    df_tabla["Probabilidad"] = df_tabla["probabilidad"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
    df_tabla["Unidades Netas"] = df_tabla["unidades_ganadas"].apply(
        lambda x: f"+{x:.2f} u" if (pd.notna(x) and x > 0) else (f"{x:.2f} u" if pd.notna(x) else "0.00 u")
    )

    columnas_mostrar = [
        "temporada", "fecha", "hora_cdmx", "Partido", "Marcador Final",
        "mercado", "seleccion", "Cuota", "Probabilidad", "confianza", "resultado", "Unidades Netas"
    ]
    renombres = {
        "temporada": "Temporada",
        "fecha": "Fecha",
        "hora_cdmx": "Hora CDMX",
        "mercado": "Mercado",
        "seleccion": "Selección",
        "confianza": "Confianza",
        "resultado": "Resultado",
    }
    st.dataframe(
        df_tabla[columnas_mostrar].rename(columns=renombres),
        use_container_width=True,
        hide_index=True
    )


# ==========================================================
# ESTRUCTURA PRINCIPAL HOMOLOGADA A MLB Y NFL
# ==========================================================

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")

# Encabezado principal de la marca NBA
st.markdown(
    f"""<div class="nba-shell">
<div class="nba-brand">
<span class="nba-logo">🏀</span>
<div>
<div style="font-size: 1.05rem; font-weight: 900; color: #ffffff;">ORÁCULO <span class="nba-accent">NBA AI V2</span></div>
<div class="nba-status">DraftKings Odds · Ensamble Ridge-GradientBoosting · Shrinkage Bayesiano y Calibración Logística</div>
</div>
</div>
<div style="text-align: right;">
<span style="background: #23160e; color: #ff8c33; padding: 0.3rem 0.75rem; border-radius: 8px; font-size: 0.78rem; font-weight: 800; border: 1px solid #ff6b00;">
🕒 {hora_actual_cdmx} CDMX
</span>
</div>
</div>""",
    unsafe_allow_html=True,
)

# Cargar estado de predicciones de hoy
predicciones_actuales = cargar_predicciones(forzar=False)
hay_pendientes_por_liquidar = any(
    p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]
    for p in predicciones_actuales
)

# Nivel 1: Selector principal de mercado
mercado = st.radio(
    "Mercado NBA",
    ["Totales de Partido", "Moneyline (Ganador Directo)", "Spread (Línea de Puntos)"],
    horizontal=True,
    label_visibility="collapsed",
    key="nba_mercado_principal",
)

# Nivel 2: Selector interno de sección (abajo de mercado)
seccion = st.radio(
    "Sección NBA",
    ["Picks de hoy", "Rendimiento e Historial"],
    horizontal=True,
    label_visibility="collapsed",
    key="nba_seccion",
)

# Nivel 3: Barra superior de 2 botones al 50%/50% en estilo dark glassmorphic
st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
col1, col2 = st.columns(2, gap="medium")

with col1:
    lbl_btn_res = "Liquidar / Sincronizar Resultados"
    help_btn_res = "Consulta marcadores finales de ESPN, liquida las apuestas concluidas y las registra en Rendimiento e Historial."
    if st.button(lbl_btn_res, key="btn_act_res_nba", type="primary", use_container_width=True, help=help_btn_res):
        with st.spinner("Consultando marcadores ESPN y liquidando partidos NBA..."):
            res = liquidar_partidos_pendientes_nba()
            if res.get("evaluados", 0) > 0:
                st.success(f"✅ {res['mensaje']}")
            else:
                st.info(f"ℹ️ {res['mensaje']}")
            st.rerun()

with col2:
    if st.button("Actualizar Cuotas DraftKings", key="btn_act_cuotas_nba", type="primary", use_container_width=True, help="Consulta las últimas líneas de DraftKings y actualiza las predicciones de hoy."):
        with st.spinner("Consultando DraftKings y ejecutando modelos NBA..."):
            cargar_predicciones(forzar=True)
            st.success("✅ Cuotas y predicciones actualizadas desde DraftKings.")
            st.rerun()

st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

# Nivel 4 y 5: Renderizado de la sección seleccionada
if seccion == "Rendimiento e Historial":
    render_historial_nba(mercado)
else:
    render_cartelera_nba(predicciones_actuales, mercado)
