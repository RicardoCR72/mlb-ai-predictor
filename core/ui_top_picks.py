"""Módulo para recolectar y renderizar los Picks Candado del Día (+EV) combinando todos los deportes."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from core.constants import ZONA_CDMX
from core.ui_boleta import parsear_cuota_decimal, obtener_boleta, alternar_en_boleta, esta_en_boleta

RAIZ = Path(__file__).resolve().parents[1]


@st.cache_data(ttl=60)
def obtener_picks_candado_del_dia(max_picks: int = 4, modo: str = "global") -> list[dict]:
    """Recolecta y clasifica las mejores recomendaciones del día de todos los deportes con mayor EV%.

    Modos disponibles:
      - 'global': Los 4 picks con mayor EV% absoluto de cualquier deporte (sin duplicar jugador/partido).
      - 'balanceado': Garantiza presencia multi-deporte (1 mejor de NBA, 1 mejor de NFL, 1 mejor de Fútbol + 1 mejor restante).
      - 'props': Únicamente props individuales de jugadores con alto valor esperado.
      - 'juegos': Únicamente mercados de juego directo (Moneyline, Totales y Spread).
    """
    hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
    candidatos = []

    # 1. NBA Props de Jugadores (Alto EV)
    p_nba_props = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.json"
    if p_nba_props.exists():
        try:
            with open(p_nba_props, "r", encoding="utf-8") as f:
                data_props = json.load(f)
            seen_players = set()
            for p in data_props:
                f_j = str(p.get("fecha") or "")[:10]
                if f_j and f_j < hoy_cdmx:
                    continue
                player = p.get("player_name") or p.get("player_clean", "")
                if player in seen_players:
                    continue
                prob = float(p.get("model_prob") or 0.5)
                c_am = str(p.get("pick_odds_american") or "-110")
                c_dec = float(p.get("pick_odds_decimal") or parsear_cuota_decimal(c_am))
                ev = float(p.get("ev_pct") or ((prob * c_dec - 1.0) * 100.0))

                if ev > 4.0 and prob >= 0.55:
                    seen_players.add(player)
                    candidatos.append({
                        "id": f"NBA_PROP_{player}_{p.get('market')}_{p.get('pick_type')}_{p.get('line')}",
                        "deporte": "NBA",
                        "icono": "🏀",
                        "tipo": "Prop",
                        "color": "#ff6b35",
                        "color_bg": "rgba(255, 107, 53, 0.12)",
                        "color_border": "rgba(255, 107, 53, 0.4)",
                        "liga": "NBA · Props Jugador",
                        "partido": p.get("game") or f"{p.get('away_team', '')} @ {p.get('home_team', '')}",
                        "fecha": p.get("fecha") or hoy_cdmx,
                        "hora": p.get("hora") or "",
                        "mercado": f"Prop · {p.get('market', 'Jugador')}",
                        "seleccion": f"{player} {p.get('pick_type', 'UNDER')} {p.get('line')}",
                        "cuota": c_am,
                        "cuota_dec": c_dec,
                        "probabilidad": prob,
                        "edge": round(prob - (1.0 / c_dec if c_dec > 0 else 0.5238), 4),
                        "ev_pct": round(ev, 1),
                        "confianza": p.get("confidence", "ALTA"),
                        "pagina": "pages/4_🏀_NBA.py",
                        "detalle": p.get("trend") or f"Proyección {p.get('projection')} vs línea {p.get('line')}",
                    })
        except Exception:
            pass

    # 2. NBA Mercados de Juego (Totales, Spread, Moneyline)
    p_nba_games = RAIZ / "data" / "nba" / "predictions" / "predicciones_nba_hoy.json"
    if p_nba_games.exists():
        try:
            with open(p_nba_games, "r", encoding="utf-8") as f:
                data_nba = json.load(f)
            for j in data_nba:
                f_j = str(j.get("fecha_cdmx") or j.get("fecha", ""))[:10]
                if f_j and f_j < hoy_cdmx:
                    continue
                estado = str(j.get("estado", "")).upper()
                res = str(j.get("resultado", "PENDIENTE")).upper()
                if "FINAL" in estado or res in ["GANADA", "PERDIDA", "PUSH"]:
                    continue

                prob = float(j.get("pick_probabilidad") or 0.5)
                c_am = str(j.get("pick_cuota") or "-110")
                c_dec = float(j.get("pick_cuota_dec") or parsear_cuota_decimal(c_am))
                ev = float(j.get("pick_ev") or ((prob * c_dec - 1.0) * 100.0))

                if ev > 2.0 and prob >= 0.53:
                    candidatos.append({
                        "id": f"NBA_GAME_{j.get('id_evento')}_{j.get('pick_mercado')}_{j.get('pick_seleccion')}",
                        "deporte": "NBA",
                        "icono": "🏀",
                        "tipo": "Juego",
                        "color": "#ff6b35",
                        "color_bg": "rgba(255, 107, 53, 0.12)",
                        "color_border": "rgba(255, 107, 53, 0.4)",
                        "liga": "NBA · Baloncesto",
                        "partido": j.get("partido") or f"{j.get('equipo_visita', '')} @ {j.get('equipo_local', '')}",
                        "fecha": j.get("fecha_cdmx") or hoy_cdmx,
                        "hora": j.get("hora_cdmx") or "",
                        "mercado": j.get("pick_mercado", "Totales"),
                        "seleccion": j.get("pick_seleccion", ""),
                        "cuota": c_am,
                        "cuota_dec": c_dec,
                        "probabilidad": prob,
                        "edge": float(j.get("pick_edge") or 0.0),
                        "ev_pct": round(ev, 1),
                        "confianza": j.get("confianza", "MEDIA"),
                        "pagina": "pages/4_🏀_NBA.py",
                        "detalle": j.get("pick_detalle") or f"Línea de casa {j.get('linea_total', '')}",
                    })
        except Exception:
            pass

    # 3. NFL Moneyline y Totales
    p_nfl = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_moneyline.json"
    if p_nfl.exists():
        try:
            with open(p_nfl, "r", encoding="utf-8") as f:
                data_nfl = json.load(f)
            for j in data_nfl:
                f_j = str(j.get("fecha_cdmx") or j.get("gameday", ""))[:10]
                if f_j and f_j < hoy_cdmx:
                    continue
                estado = str(j.get("estado", "")).upper()
                res = str(j.get("resultado_pick", "PENDIENTE")).upper()
                if "FINAL" in estado or res in ["GANADA", "PERDIDA", "PUSH"]:
                    continue

                prob = float(j.get("pick_probabilidad") or j.get("prob_pick_ml", 0.5))
                c_am = str(j.get("pick_cuota") or j.get("momio_pick_ml", "-110"))
                c_dec = float(j.get("pick_cuota_dec") or parsear_cuota_decimal(c_am))
                ev = float(j.get("ev_estimado") or ((prob * c_dec - 1.0) * 100.0))

                if ev > 0.0 and prob >= 0.50:
                    candidatos.append({
                        "id": f"NFL_ML_{j.get('id_evento')}_{j.get('pick_seleccion')}",
                        "deporte": "NFL",
                        "icono": "🏈",
                        "tipo": "Juego",
                        "color": "#b7ff3c",
                        "color_bg": "rgba(183, 255, 60, 0.12)",
                        "color_border": "rgba(183, 255, 60, 0.4)",
                        "liga": f"NFL · Semana {j.get('semana', 'Actual')}",
                        "partido": j.get("partido") or f"{j.get('equipo_visita', '')} @ {j.get('equipo_local', '')}",
                        "fecha": j.get("fecha_cdmx") or j.get("gameday", ""),
                        "hora": j.get("hora_cdmx") or "",
                        "mercado": "Moneyline",
                        "seleccion": j.get("pick_seleccion", j.get("pick_moneyline", "")),
                        "cuota": c_am,
                        "cuota_dec": c_dec,
                        "probabilidad": prob,
                        "edge": float(j.get("pick_edge") or 0.0),
                        "ev_pct": round(ev, 1),
                        "confianza": j.get("confianza", "MEDIA"),
                        "pagina": "pages/2_🏈_NFL.py",
                        "detalle": j.get("pick_detalle") or "Ventaja matemática en Moneyline",
                    })
        except Exception:
            pass

    # 4. Fútbol Mundial (8 Ligas)
    p_futbol = RAIZ / "data" / "futbol" / "predicciones_futbol_mundial.json"
    if not p_futbol.exists():
        p_futbol = RAIZ / "data" / "futbol" / "predicciones_futbol.json"
    if p_futbol.exists():
        try:
            with open(p_futbol, "r", encoding="utf-8") as f:
                data_futbol = json.load(f)
            for j in data_futbol:
                f_j = str(j.get("fecha_cdmx") or j.get("fecha", ""))[:10]
                if f_j and f_j < hoy_cdmx:
                    continue
                estado = str(j.get("estado", "")).upper()
                res = str(j.get("resultado_pick", "PENDIENTE")).upper()
                if "FINAL" in estado or "FULL_TIME" in estado or res in ["GANADA", "PERDIDA", "PUSH"]:
                    continue

                prob = float(j.get("pick_probabilidad") or 0.5)
                c_am = str(j.get("pick_cuota") or "-110")
                c_dec = float(j.get("pick_cuota_dec") or parsear_cuota_decimal(c_am))
                ev = float(j.get("pick_ev") or ((prob * c_dec - 1.0) * 100.0))

                if ev > 0.0 and prob >= 0.50:
                    candidatos.append({
                        "id": f"FUTBOL_{j.get('id_evento')}_{j.get('pick_mercado')}_{j.get('pick_seleccion')}",
                        "deporte": "Fútbol",
                        "icono": "⚽",
                        "tipo": "Juego",
                        "color": "#00e676",
                        "color_bg": "rgba(0, 230, 118, 0.12)",
                        "color_border": "rgba(0, 230, 118, 0.4)",
                        "liga": f"{j.get('liga_bandera', '')} {j.get('liga_nombre', 'Fútbol')}".strip(),
                        "partido": j.get("partido") or f"{j.get('equipo_visita', '')} @ {j.get('equipo_local', '')}",
                        "fecha": j.get("fecha_cdmx") or j.get("fecha", ""),
                        "hora": j.get("hora_cdmx") or "",
                        "mercado": j.get("pick_mercado", "Fútbol"),
                        "seleccion": j.get("pick_seleccion", ""),
                        "cuota": c_am,
                        "cuota_dec": c_dec,
                        "probabilidad": prob,
                        "edge": float(j.get("pick_edge") or 0.0),
                        "ev_pct": round(ev, 1),
                        "confianza": j.get("confianza", "MEDIA"),
                        "pagina": "pages/3_⚽_Futbol.py",
                        "detalle": j.get("pick_detalle") or "Modelo xG y ventaja en momio",
                    })
        except Exception:
            pass

    # Filtrar según modo
    if modo == "props":
        candidatos = [c for c in candidatos if c.get("tipo") == "Prop"]
    elif modo == "juegos":
        candidatos = [c for c in candidatos if c.get("tipo") == "Juego"]

    # Ordenar estrictamente por mayor EV% y mayor probabilidad
    candidatos.sort(key=lambda x: (round(x.get("ev_pct", 0.0), 2), round(x.get("probabilidad", 0.0), 4)), reverse=True)

    if modo == "balanceado":
        # Asegura representación de los 3 deportes activos (1 NBA, 1 NFL, 1 Fútbol)
        balanceados = []
        deportes_cubiertos = set()
        for dep in ["NBA", "NFL", "Fútbol"]:
            pick_dep = next((c for c in candidatos if c["deporte"] == dep), None)
            if pick_dep:
                balanceados.append(pick_dep)
                deportes_cubiertos.add(pick_dep["id"])
        # Completar hasta max_picks con los restantes de mayor EV
        for c in candidatos:
            if len(balanceados) >= max_picks:
                break
            if c["id"] not in deportes_cubiertos:
                balanceados.append(c)
                deportes_cubiertos.add(c["id"])
        return balanceados[:max_picks]

    # Modo global o filtrado: deduplicar para que no haya dos picks del mismo partido
    final_picks = []
    seen_matches = set()
    for c in candidatos:
        match_key = f"{c['deporte']}_{c['partido']}"
        if match_key in seen_matches:
            continue
        seen_matches.add(match_key)
        final_picks.append(c)
        if len(final_picks) >= max_picks:
            break

    return final_picks


# Alias de retrocompatibilidad
def obtener_top_picks_del_dia(max_picks: int = 4) -> list[dict]:
    return obtener_picks_candado_del_dia(max_picks=max_picks, modo="global")


def render_top_picks_section():
    """Renderiza la sección destacada de Picks Candado del Día (+EV) con botón de boleta rápida."""
    # Control de Modo de Candados
    if "candados_modo" not in st.session_state:
        st.session_state["candados_modo"] = "global"

    opciones_modo = {
        "🔥 Top 4 Máximo EV Global": "global",
        "🌐 Balance Multi-Deporte (NBA, NFL, Fútbol)": "balanceado",
        "📊 Solo Props de Jugador": "props",
        "🏟️ Solo Mercados de Juego (ML / Totales)": "juegos",
    }

    # Contenedor superior con diseño Candado Neon
    st.markdown("<div style='margin-top: 0.8rem; margin-bottom: 0.25rem;'></div>", unsafe_allow_html=True)
    c_head1, c_head2 = st.columns([3, 2])
    with c_head1:
        st.markdown(
            '<div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.2rem;">'
            '<span style="font-size:1.35rem;">🔒</span>'
            '<h3 style="margin:0; font-size:1.3rem; font-weight:900; color:#ffffff; letter-spacing:-0.01em;">Picks Candado del Día (+EV)</h3>'
            '<span style="font-size:0.70rem; font-weight:800; color:#ffd700; background:rgba(255,215,0,0.12); border:1px solid rgba(255,215,0,0.35); padding:0.2rem 0.55rem; border-radius:12px;">'
            'MÁXIMA VENTAJA MATEMÁTICA'
            '</span>'
            '</div>'
            '<div style="font-size:0.83rem; color:#94a3b8; line-height:1.45;">'
            'Acceso rápido a las mejores selecciones con mayor Valor Esperado de toda la plataforma combinada (NBA, NFL y Fútbol).'
            '</div>',
            unsafe_allow_html=True,
        )

    # Selector de modalidad rápida
    modo_sel_label = st.radio(
        "Filtro de Candados",
        list(opciones_modo.keys()),
        horizontal=True,
        label_visibility="collapsed",
        key="radio_candados_modo",
    )
    modo_activo = opciones_modo.get(modo_sel_label, "global")

    candados = obtener_picks_candado_del_dia(max_picks=4, modo=modo_activo)
    if not candados:
        st.info("No hay pronósticos activos con Valor Esperado positivo (+EV) para los filtros seleccionados.")
        return

    # Barra de Acción Rápida: Agregar todos los Candados a la Boleta en 1 Toque
    todos_en_boleta = all(esta_en_boleta(p["id"]) for p in candados)
    col_act1, col_act2 = st.columns([3, 2], gap="small")

    with col_act1:
        avg_ev = sum(p["ev_pct"] for p in candados) / len(candados)
        st.caption(f"Mostrando **{len(candados)} picks candado** · Promedio de Valor Esperado: **+{avg_ev:.1f}% EV**")

    with col_act2:
        if todos_en_boleta:
            st.markdown(
                '<div style="text-align:right;">'
                '<span style="background:rgba(0,230,118,0.15); color:#00e676; border:1px solid rgba(0,230,118,0.4); padding:0.35rem 0.75rem; border-radius:8px; font-size:0.80rem; font-weight:800;">'
                '✅ Todos los Candados en tu Boleta'
                '</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            if st.button("⚡ Agregar todos los Candados a la Boleta", key="btn_agregar_todos_candados", type="primary", use_container_width=True):
                for p in candados:
                    if not esta_en_boleta(p["id"]):
                        slip_item = {
                            "id": p["id"],
                            "deporte": p["deporte"],
                            "icono": p["icono"],
                            "partido": p["partido"],
                            "mercado": p["mercado"],
                            "seleccion": p["seleccion"],
                            "cuota": p["cuota"],
                            "cuota_dec": p["cuota_dec"],
                            "prob": p["probabilidad"],
                        }
                        alternar_en_boleta(slip_item)
                st.toast(f"🔒 ¡{len(candados)} Picks Candado agregados a tu Boleta del Día!", icon="✅")
                st.rerun()

    from core.ui_boleta import render_boton_boleta, render_widget_boleta

    # Renderizado en columnas responsivas
    cols = st.columns(len(candados), gap="medium")
    for idx, (col, p) in enumerate(zip(cols, candados)):
        with col:
            hora_str = f"{p['hora']} CDMX" if p.get("hora") else "Hoy"
            cuota_str = p.get("cuota") or "N/D"
            sport_key = p["deporte"].lower().replace("ú", "u")
            ev_val = float(p.get("ev_pct") or 0.0)

            card_html = (
                f'<div class="top-pick-card" style="border-top: 3px solid {p["color"]}; margin-bottom: 0.4rem; background: linear-gradient(145deg, #0e1726, #070c14); border-radius: 14px; padding: 1.1rem; box-shadow: 0 4px 18px rgba(0,0,0,0.3);">'
                f'<div>'
                f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">'
                f'<span class="top-pick-badge" style="background:{p["color_bg"]}; color:{p["color"]}; border: 1px solid {p["color_border"]};">'
                f'{p["icono"]} {p["deporte"]} · {p["liga"]}'
                f'</span>'
                f'<span style="font-size:0.72rem; color:#8fa0b5; font-weight:700;">'
                f'⏰ {hora_str}'
                f'</span>'
                f'</div>'
                f'<div class="top-pick-match" style="font-size: 0.95rem; font-weight: 800; color: #f1f5f9; min-height: 2.5rem; margin: 0.35rem 0;">{p["partido"]}</div>'
                f'<div class="top-pick-box" style="background: rgba(0, 0, 0, 0.45); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 0.7rem 0.85rem; margin: 0.4rem 0;">'
                f'<div style="font-size:0.68rem; color:#8fa0b5; text-transform:uppercase; font-weight:750; letter-spacing:0.06em;">'
                f'{p["mercado"]}'
                f'</div>'
                f'<div class="top-pick-sel" style="color:#ffffff; font-size:1.12rem; font-weight:900; margin:0.2rem 0 0.3rem;">{p["seleccion"]}</div>'
                f'<div style="display:flex; justify-content:space-between; align-items:center; font-size:0.75rem; color:#a4b3c6;">'
                f'<span>Momio: <b style="color:#ffffff;">{cuota_str}</b></span>'
                f'<span style="color:#ffd700; font-weight:800;">🔒 CANDADO</span>'
                f'</div>'
                f'</div>'
                f'</div>'
                f'<div style="display:flex; justify-content:space-between; align-items:flex-end; margin:0.4rem 0 0.1rem;">'
                f'<div>'
                f'<div style="font-size:0.65rem; color:#8fa0b5; font-weight:700; text-transform:uppercase;">Probabilidad Modelo</div>'
                f'<div class="top-pick-prob" style="color:{p["color"]}; font-size:1.5rem; font-weight:900;">{p["probabilidad"]*100:.1f}%</div>'
                f'</div>'
                f'<div style="text-align:right;">'
                f'<span style="background:rgba(255,215,0,0.15); color:#ffd700; border:1px solid rgba(255,215,0,0.4); padding:0.25rem 0.6rem; border-radius:8px; font-size:0.78rem; font-weight:900;">'
                f'🔥 +{ev_val:.1f}% EV'
                f'</span>'
                f'</div>'
                f'</div>'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

            slip_item = {
                "id": p["id"],
                "deporte": p["deporte"],
                "icono": p["icono"],
                "partido": p["partido"],
                "mercado": p["mercado"],
                "seleccion": p["seleccion"],
                "cuota": cuota_str,
                "cuota_dec": p["cuota_dec"],
                "prob": p["probabilidad"],
            }

            b_c1, b_c2 = st.columns([1, 1], gap="small")
            with b_c1:
                render_boton_boleta(slip_item, key=f"btn_slip_{sport_key}_{idx}")
            with b_c2:
                if st.button(f"Análisis {p['icono']} →", key=f"btn_top_pick_{sport_key}_{idx}", use_container_width=True):
                    st.switch_page(p["pagina"])

    # Renderizar boleta interactiva del día
    render_widget_boleta()
    st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
