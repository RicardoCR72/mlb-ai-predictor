"""Módulo para recolectar y renderizar los Top Picks del día combinando todos los deportes."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from core.constants import ZONA_CDMX

RAIZ = Path(__file__).resolve().parents[1]


@st.cache_data(ttl=60)
def obtener_top_picks_del_dia(max_picks: int = 3) -> list[dict]:
    """Recolecta y clasifica las mejores recomendaciones del día de todos los deportes."""
    hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
    picks = []

    # 1. Fútbol
    p_futbol = RAIZ / "data" / "futbol" / "predicciones_futbol_mundial.json"
    if not p_futbol.exists():
        p_futbol = RAIZ / "data" / "futbol" / "predicciones_futbol.json"
    if p_futbol.exists():
        try:
            with open(p_futbol, "r", encoding="utf-8") as f:
                data = json.load(f)
            for j in data:
                f_j = str(j.get("fecha_cdmx") or j.get("fecha", ""))[:10]
                if f_j and f_j < hoy_cdmx:
                    continue
                estado = str(j.get("estado", "")).upper()
                res = str(j.get("resultado_pick", "PENDIENTE")).upper()
                if "FINAL" not in estado and "FULL_TIME" not in estado and res not in ["GANADA", "PERDIDA", "PUSH"]:
                    prob = float(j.get("pick_probabilidad", 0.5))
                    edge = float(j.get("pick_edge", 0.0))
                    momio = str(j.get("pick_cuota", "") or "")
                    picks.append({
                        "deporte": "Fútbol",
                        "icono": "⚽",
                        "color": "#00e676",
                        "color_bg": "rgba(0, 230, 118, 0.12)",
                        "color_border": "rgba(0, 230, 118, 0.4)",
                        "liga": f"{j.get('liga_bandera', '')} {j.get('liga_nombre', 'Fútbol')}",
                        "partido": j.get("partido", ""),
                        "fecha": j.get("fecha_cdmx", ""),
                        "hora": j.get("hora_cdmx", ""),
                        "mercado": j.get("pick_mercado", "Fútbol"),
                        "seleccion": j.get("pick_seleccion", ""),
                        "cuota": momio,
                        "probabilidad": prob,
                        "edge": edge,
                        "confianza": j.get("confianza", "MEDIA"),
                        "pagina": "pages/3_⚽_Futbol.py",
                    })
        except Exception:
            pass

    # 2. NBA
    p_nba = RAIZ / "data" / "nba" / "predictions" / "predicciones_nba_hoy.json"
    if p_nba.exists():
        try:
            with open(p_nba, "r", encoding="utf-8") as f:
                data = json.load(f)
            for j in data:
                f_j = str(j.get("fecha_cdmx") or j.get("fecha", ""))[:10]
                if f_j and f_j < hoy_cdmx:
                    continue
                estado = str(j.get("estado", "")).upper()
                res = str(j.get("resultado", "PENDIENTE")).upper()
                if "FINAL" not in estado and res not in ["GANADA", "PERDIDA", "PUSH"]:
                    prob = float(j.get("pick_probabilidad", 0.5))
                    edge = float(j.get("pick_edge", 0.0))
                    sel = j.get("pick_seleccion") or ""
                    mercado = j.get("pick_mercado", "Totales")

                    # Evaluar los mejores mercados del partido para extraer la máxima ventaja probabilística
                    candidatos_juego = [
                        {"mercado": mercado, "seleccion": sel, "prob": prob, "edge": edge}
                    ]
                    linea_tot = j.get("linea_total")
                    p_under = float(j.get("prob_under") or 0.0)
                    if p_under >= 0.70 and linea_tot:
                        candidatos_juego.append({
                            "mercado": "Totales (UNDER)",
                            "seleccion": f"UNDER {linea_tot}",
                            "prob": p_under,
                            "edge": round(p_under - 0.5238, 4),
                        })
                    p_over = float(j.get("prob_over") or 0.0)
                    if p_over >= 0.70 and linea_tot:
                        candidatos_juego.append({
                            "mercado": "Totales (OVER)",
                            "seleccion": f"OVER {linea_tot}",
                            "prob": p_over,
                            "edge": round(p_over - 0.5238, 4),
                        })
                    p_loc = float(j.get("prob_local_win") or 0.0)
                    c_loc_dec = float(j.get("ml_local_dec") or 1.91)
                    edge_loc = p_loc - (1.0 / c_loc_dec if c_loc_dec > 0 else 0.5238)
                    if p_loc >= 0.70 and edge_loc >= 0.02 and j.get("equipo_local"):
                        candidatos_juego.append({
                            "mercado": "Moneyline",
                            "seleccion": f"{j['equipo_local']} ML",
                            "prob": p_loc,
                            "edge": round(edge_loc, 4),
                        })
                    p_vis = float(j.get("prob_visita_win") or 0.0)
                    c_vis_dec = float(j.get("ml_visita_dec") or 1.91)
                    edge_vis = p_vis - (1.0 / c_vis_dec if c_vis_dec > 0 else 0.5238)
                    if p_vis >= 0.70 and edge_vis >= 0.02 and j.get("equipo_visita"):
                        candidatos_juego.append({
                            "mercado": "Moneyline",
                            "seleccion": f"{j['equipo_visita']} ML",
                            "prob": p_vis,
                            "edge": round(edge_vis, 4),
                        })

                    # Spread / Hándicap NBA
                    spread_val = float(j.get("linea_spread") or 0.0)
                    p_cov_loc = float(j.get("prob_cover_home") or 0.0)
                    p_cov_vis = float(j.get("prob_cover_away") or 0.0)
                    if p_cov_loc >= 0.60 and j.get("equipo_local"):
                        candidatos_juego.append({
                            "mercado": "Spread",
                            "seleccion": f"{j.get('equipo_local')} {spread_val:+0.1f}",
                            "prob": p_cov_loc,
                            "edge": round(p_cov_loc - 0.5238, 4),
                        })
                    if p_cov_vis >= 0.60 and j.get("equipo_visita"):
                        candidatos_juego.append({
                            "mercado": "Spread",
                            "seleccion": f"{j.get('equipo_visita')} {-spread_val:+0.1f}",
                            "prob": p_cov_vis,
                            "edge": round(p_cov_vis - 0.5238, 4),
                        })

                    candidatos_juego.sort(key=lambda x: (x["edge"] > 0, round(x["prob"], 4), round(x["edge"], 4)), reverse=True)
                    best_cand = candidatos_juego[0]
                    prob = best_cand["prob"]
                    edge = best_cand["edge"]
                    sel = best_cand["seleccion"]
                    mercado = best_cand["mercado"]

                    # Cuota exacta de mercado
                    if "Totales" in mercado:
                        c = "-110"
                    elif "Spread" in mercado:
                        c = "-110"
                    elif "Moneyline" in mercado:
                        eq_loc = j.get("equipo_local", "")
                        eq_vis = j.get("equipo_visita", "")
                        if eq_loc and eq_loc in sel:
                            c = j.get("ml_local") or "-110"
                        elif eq_vis and eq_vis in sel:
                            c = j.get("ml_visita") or "-110"
                        else:
                            c = j.get("ml_local") or j.get("ml_visita") or "-110"
                    else:
                        c = "-110"

                    picks.append({
                        "deporte": "NBA",
                        "icono": "🏀",
                        "color": "#ff6b35",
                        "color_bg": "rgba(255, 107, 53, 0.12)",
                        "color_border": "rgba(255, 107, 53, 0.4)",
                        "liga": "NBA · Baloncesto",
                        "partido": j.get("partido") or f"{j.get('equipo_visitante')} @ {j.get('equipo_local')}",
                        "fecha": j.get("fecha_cdmx") or j.get("fecha", ""),
                        "hora": j.get("hora_cdmx", ""),
                        "mercado": mercado,
                        "seleccion": sel,
                        "cuota": str(c or "-110"),
                        "probabilidad": prob,
                        "edge": edge,
                        "confianza": "ALTA" if (prob >= 0.70 and edge >= 0.03) else j.get("confianza", "MEDIA"),
                        "pagina": "pages/4_🏀_NBA.py",
                    })
        except Exception:
            pass

    # 3. NFL Moneyline
    p_nfl = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_moneyline.json"
    if p_nfl.exists():
        try:
            with open(p_nfl, "r", encoding="utf-8") as f:
                data = json.load(f)
            for j in data:
                f_j = str(j.get("fecha_cdmx") or j.get("gameday", ""))[:10]
                if f_j and f_j != hoy_cdmx:
                    continue
                estado = str(j.get("estado", "")).upper()
                res = str(j.get("resultado_pick", "PENDIENTE")).upper()
                if "FINAL" not in estado and res not in ["GANADA", "PERDIDA", "PUSH"]:
                    prob = float(j.get("pick_probabilidad", j.get("prob_pick_ml", 0.5)))
                    edge = float(j.get("pick_edge", 0.0))
                    picks.append({
                        "deporte": "NFL",
                        "icono": "🏈",
                        "color": "#b7ff3c",
                        "color_bg": "rgba(183, 255, 60, 0.12)",
                        "color_border": "rgba(183, 255, 60, 0.4)",
                        "liga": f"NFL · Semana {j.get('semana', '')}",
                        "partido": j.get("partido") or f"{j.get('equipo_visita', '')} @ {j.get('equipo_local', '')}",
                        "fecha": j.get("fecha_cdmx") or j.get("gameday", ""),
                        "hora": j.get("hora_cdmx", ""),
                        "mercado": "Moneyline",
                        "seleccion": j.get("pick_seleccion", j.get("pick_moneyline", "")),
                        "cuota": str(j.get("pick_cuota", j.get("momio_pick_ml", "-110"))),
                        "probabilidad": prob,
                        "edge": edge,
                        "confianza": j.get("confianza", "MEDIA"),
                        "pagina": "pages/2_🏈_NFL.py",
                    })
        except Exception:
            pass

    # 4. MLB
    p_mlb = RAIZ / "data" / "mlb" / "predicciones_mlb.json"
    if p_mlb.exists():
        try:
            with open(p_mlb, "r", encoding="utf-8") as f:
                data = json.load(f)
            for j in data:
                f_j = str(j.get("fecha", ""))[:10]
                if f_j and f_j != hoy_cdmx:
                    continue
                res = str(j.get("resultado", "PENDIENTE")).upper()
                if res not in ["GANADA", "PERDIDA", "PUSH"]:
                    prob = float(j.get("probabilidad", 0.5))
                    edge = float(j.get("edge", prob - 0.5))
                    picks.append({
                        "deporte": "MLB",
                        "icono": "⚾",
                        "color": "#00e5ff",
                        "color_bg": "rgba(0, 229, 255, 0.12)",
                        "color_border": "rgba(0, 229, 255, 0.4)",
                        "liga": "MLB · Grandes Ligas",
                        "partido": j.get("partido", ""),
                        "fecha": j.get("fecha", ""),
                        "hora": j.get("hora", ""),
                        "mercado": j.get("mercado", "Moneyline"),
                        "seleccion": j.get("seleccion", ""),
                        "cuota": str(j.get("cuota", "-110")),
                        "probabilidad": prob,
                        "edge": edge,
                        "confianza": j.get("confianza", "MEDIA"),
                        "pagina": "pages/1_⚾_MLB.py",
                    })
        except Exception:
            pass

    # Clasificar: mayor probabilidad y mayor edge (orden estrictamente determinista)
    picks.sort(key=lambda x: (round(x.get("probabilidad", 0.0), 4), round(x.get("edge", 0.0), 4), x.get("partido", "")), reverse=True)
    return picks[:max_picks]


def render_top_picks_section():
    """Renderiza la sección destacada de Top Picks del Día en la página de inicio."""
    top_picks = obtener_top_picks_del_dia(max_picks=3)
    if not top_picks:
        return

    st.markdown("<div style='margin-top: 0.8rem; margin-bottom: 0.25rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.25rem;">'
        '<h3 style="margin:0; font-size:1.25rem; font-weight:850; color:#ffffff;">⭐ Top Picks del Día</h3>'
        '<span style="font-size:0.75rem; font-weight:750; color:#b7ff3c; background:rgba(183,255,60,0.1); border:1px solid rgba(183,255,60,0.3); padding:0.25rem 0.6rem; border-radius:20px;">'
        'MATEMÁTICAMENTE DESTACADOS'
        '</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption("Las 3 mejores selecciones con mayor probabilidad y ventaja matemática combinando todos los deportes.")

    from core.ui_boleta import render_boton_boleta, render_widget_boleta

    cols = st.columns(len(top_picks), gap="medium")
    for idx, (col, p) in enumerate(zip(cols, top_picks)):
        with col:
            hora_str = f"{p['hora']} CDMX" if p.get("hora") else "Hoy"
            cuota_str = p.get("cuota") or "N/D"
            sport_key = p["deporte"].lower().replace("ú", "u")
            edge_val = float(p.get("edge") or 0.0)
            ev_html = f'<span class="badge-ev" style="margin-left:0.4rem;">🔥 +EV +{edge_val*100:.1f}%</span>' if edge_val > 0.01 else ""

            card_html = (
                f'<div class="top-pick-card" style="border-top: 3px solid {p["color"]}; margin-bottom: 0.4rem;">'
                f'<div>'
                f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">'
                f'<span class="top-pick-badge" style="background:{p["color_bg"]}; color:{p["color"]}; border: 1px solid {p["color_border"]};">'
                f'{p["icono"]} {p["deporte"]} · {p["liga"]}'
                f'</span>'
                f'<span style="font-size:0.75rem; color:#8fa0b5; font-weight:700;">'
                f'⏰ {hora_str}'
                f'</span>'
                f'</div>'
                f'<div class="top-pick-match">{p["partido"]}</div>'
                f'<div class="top-pick-box">'
                f'<div style="font-size:0.7rem; color:#8fa0b5; text-transform:uppercase; font-weight:750; letter-spacing:0.06em;">'
                f'Recomendación Oficial ({p["mercado"]})'
                f'</div>'
                f'<div class="top-pick-sel">{p["seleccion"]}</div>'
                f'<div style="font-size:0.78rem; color:#a4b3c6;">'
                f'Momio DraftKings: <b style="color:#ffffff;">{cuota_str}</b>'
                f'</div>'
                f'</div>'
                f'</div>'
                f'<div style="display:flex; justify-content:space-between; align-items:flex-end; margin:0.4rem 0 0.1rem;">'
                f'<div>'
                f'<div style="font-size:0.68rem; color:#8fa0b5; font-weight:700;">PROBABILIDAD ORÁCULO</div>'
                f'<div class="top-pick-prob" style="color:{p["color"]};">{p["probabilidad"]*100:.1f}%</div>'
                f'</div>'
                f'<div style="display:flex; align-items:center;">'
                f'<span style="background:{p["color_bg"]}; color:{p["color"]}; border: 1px solid {p["color_border"]}; padding: 0.25rem 0.65rem; border-radius: 8px; font-size: 0.75rem; font-weight: 850;">'
                f'★ ALTO VALOR'
                f'</span>'
                f'{ev_html}'
                f'</div>'
                f'</div>'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

            slip_item = {
                "id": f"{p['deporte']}_{p['partido']}_{p['mercado']}_{p['seleccion']}",
                "deporte": p["deporte"],
                "icono": p["icono"],
                "partido": p["partido"],
                "mercado": p["mercado"],
                "seleccion": p["seleccion"],
                "cuota": cuota_str,
                "prob": p["probabilidad"],
            }

            b_c1, b_c2 = st.columns([1, 1], gap="small")
            with b_c1:
                render_boton_boleta(slip_item, key=f"btn_slip_{sport_key}_{idx}")
            with b_c2:
                if st.button(f"Análisis {p['icono']} →", key=f"btn_top_pick_{sport_key}_{idx}", use_container_width=True):
                    st.switch_page(p["pagina"])

    render_widget_boleta()
    st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)


