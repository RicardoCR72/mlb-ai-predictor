"""Interfaz interactiva para Moneyline (Ganador Directo) NFL en Streamlit.

Diseño Gridiron Turf Neon de alta gama con tarjetas de pronósticos,
probabilidades proyectadas vs cuotas de DraftKings, y módulo de rendimiento.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from nfl.predecir_moneyline import predecir_jornada_nfl_moneyline
from nfl.registro_moneyline import (
    cargar_historial_moneyline_mysql,
    liquidar_partidos_pendientes_moneyline,
)

ZONA_CDMX = ZoneInfo("America/Mexico_City")
RAIZ = Path(__file__).resolve().parents[1]
RUTA_PREDICCIONES = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_moneyline.json"


def cargar_predicciones_nfl_moneyline(forzar: bool = False):
    """Carga las predicciones desde disco o ejecuta inferencia si no existen o se fuerza."""
    hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")

    if forzar or not RUTA_PREDICCIONES.exists():
        with st.spinner("Consultando DraftKings y ejecutando modelo Moneyline NFL..."):
            return predecir_jornada_nfl_moneyline(force_refresh=forzar)

    try:
        with open(RUTA_PREDICCIONES, "r", encoding="utf-8") as f:
            preds = json.load(f)

        if not preds or not isinstance(preds, list):
            return predecir_jornada_nfl_moneyline(force_refresh=True)

        # Evitar partidos pegados: si todos los partidos son pasados y concluidos, refrescar
        fechas = [p.get("fecha_cdmx") for p in preds if p.get("fecha_cdmx")]
        todos_pasados = all(f < hoy_cdmx for f in fechas) if fechas else False
        todos_finalizados = all(
            p.get("resultado_pick") in ["GANADA", "PERDIDA", "PUSH"] or "FINAL" in str(p.get("estado", "")).upper()
            for p in preds
        )

        if todos_pasados or (todos_finalizados and max(fechas, default="") < hoy_cdmx):
            with st.spinner("Actualizando cartelera activa de la NFL..."):
                return predecir_jornada_nfl_moneyline(force_refresh=True)

        return preds
    except Exception:
        return predecir_jornada_nfl_moneyline(force_refresh=True)


def render():
    """Renderiza la sección completa de Moneyline NFL."""
    sub_vista = st.radio(
        "Sub-sección Moneyline",
        ["Partidos de la Semana", "Rendimiento e Historial"],
        horizontal=True,
        label_visibility="collapsed",
        key="nfl_ml_subvista",
    )

    predicciones = cargar_predicciones_nfl_moneyline(forzar=False)

    hay_pendientes_por_liquidar = any(
        p.get("resultado_pick") not in ["GANADA", "PERDIDA", "PUSH"]
        for p in predicciones
    )

    # Barra superior de botones
    st.markdown("<div style='margin-bottom: 0.8rem;'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        btn_disabled = not hay_pendientes_por_liquidar
        lbl_res = "Resultados Ya Registrados" if btn_disabled else "Actualizar Marcadores y Liquidar"
        help_res = "Consulta resultados oficiales en ESPN y liquida las apuestas concluidas."
        if st.button(lbl_res, key="btn_act_res_nfl_ml", type="primary", disabled=btn_disabled, use_container_width=True, help=help_res):
            with st.spinner("Liquidando partidos y actualizando historial Moneyline NFL..."):
                res = liquidar_partidos_pendientes_moneyline()
                if res.get("evaluados", 0) > 0:
                    st.success(f"✅ {res['mensaje']}")
                else:
                    st.info(f"ℹ️ {res['mensaje']}")
                st.rerun()

    with col2:
        if st.button("Actualizar Cuotas DraftKings", key="btn_act_cuotas_nfl_ml", type="primary", use_container_width=True, help="Consulta las últimas líneas de Moneyline de DraftKings y actualiza proyecciones."):
            with st.spinner("Consultando DraftKings y ejecutando modelo calibrado..."):
                cargar_predicciones_nfl_moneyline(forzar=True)
                st.success("✅ Cuotas y pronósticos de Moneyline actualizados.")
                st.rerun()

    st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

    if sub_vista == "Partidos de la Semana":
        render_cartelera(predicciones)
    else:
        render_historial()


def render_cartelera(predicciones: list[dict]):
    """Muestra las tarjetas interactivas de pronósticos Moneyline."""
    if not predicciones:
        st.info("🏈 No hay partidos programados para la NFL en este momento.")
        return

    pendientes = [p for p in predicciones if p.get("resultado_pick") not in ["GANADA", "PERDIDA", "PUSH"]]
    liquidados = [p for p in predicciones if p.get("resultado_pick") in ["GANADA", "PERDIDA", "PUSH"]]

    # Métricas clave superiores
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Partidos", len(predicciones))
    with c2:
        st.metric("Pendientes", len(pendientes))
    with c3:
        st.metric("Finalizados", len(liquidados))
    with c4:
        picks_valor = sum(1 for p in predicciones if p.get("pick_edge", 0) >= 0.05)
        st.metric("Picks de Alto Valor", picks_valor)

    st.markdown("<div style='margin-bottom: 1.25rem;'></div>", unsafe_allow_html=True)

    # Renderizar tarjetas individuales
    for p in predicciones:
        home = p["equipo_local"]
        away = p["equipo_visita"]
        prob_h = p.get("prob_local", 0.5) * 100
        prob_a = p.get("prob_visita", 0.5) * 100
        ml_h = p.get("ml_local") or "N/D"
        ml_a = p.get("ml_visita") or "N/D"
        spread = p.get("spread_line")
        spread_str = f"Spread: {spread:+g}" if spread is not None else "Spread: N/D"

        estado = str(p.get("estado", "")).upper()
        desc_estado = p.get("descripcion_estado", "")
        resultado_pick = p.get("resultado_pick", "PENDIENTE")

        # Badge de estado de juego
        if "FINAL" in estado:
            badge_estado = f"<span style='background: #192e22; color: #8fa899; padding: 0.2rem 0.55rem; border-radius: 6px; font-weight: 700; font-size: 0.75rem;'>FINAL: {away} {p.get('marcador_visita', 0)} - {p.get('marcador_local', 0)} {home}</span>"
        elif "PROGRESS" in estado:
            badge_estado = f"<span style='background: rgba(255, 75, 75, 0.2); color: #ff6b6b; padding: 0.2rem 0.55rem; border-radius: 6px; font-weight: 800; font-size: 0.75rem; border: 1px solid #ff4b4b;'>EN VIVO: {away} {p.get('marcador_visita', 0)} - {p.get('marcador_local', 0)} {home}</span>"
        else:
            badge_estado = f"<span style='background: #112a1f; color: #b7ff3c; border: 1px solid #1a382a; padding: 0.2rem 0.55rem; border-radius: 6px; font-weight: 700; font-size: 0.75rem;'>🕒 {p.get('fecha_cdmx')} {p.get('hora_cdmx')} CDMX</span>"

        # Badge de resultado de pick
        if resultado_pick == "GANADA":
            u_gan = p.get("beneficio_unidades", 0.0)
            badge_res = f"<span style='background: rgba(183, 255, 60, 0.2); color: #b7ff3c; border: 1px solid #b7ff3c; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>✅ GANADA (+{u_gan:.2f}u)</span>"
        elif resultado_pick == "PERDIDA":
            badge_res = "<span style='background: rgba(255, 75, 75, 0.2); color: #ff6b6b; border: 1px solid #ff4b4b; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>❌ PERDIDA (-1.00u)</span>"
        elif resultado_pick == "PUSH":
            badge_res = "<span style='background: rgba(255, 214, 0, 0.2); color: #ffd600; border: 1px solid #ffd600; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>🤝 PUSH (0.00u)</span>"
        else:
            badge_res = "<span style='background: #112a1f; color: #8fa899; padding: 0.25rem 0.6rem; border-radius: 7px; font-weight: 750; font-size: 0.8rem;'>PENDIENTE</span>"

        # Badge de confianza
        conf = p.get("confianza", "NEUTRAL")
        if conf == "ALTA":
            badge_conf = "<span class='badge-conf-alta'>CONFIANZA ALTA</span>"
        elif conf == "MEDIA":
            badge_conf = "<span style='background: rgba(255, 214, 0, 0.15); color: #ffd600; border: 1px solid rgba(255, 214, 0, 0.5); padding: 0.2rem 0.6rem; border-radius: 6px; font-weight: 800; font-size: 0.72rem;'>CONFIANZA MEDIA</span>"
        else:
            badge_conf = "<span style='background: rgba(143, 168, 153, 0.15); color: #8fa899; border: 1px solid #1a382a; padding: 0.2rem 0.6rem; border-radius: 6px; font-weight: 800; font-size: 0.72rem;'>CONFIANZA NEUTRAL</span>"

        pick_sel = p.get("pick_seleccion", "")
        pick_cuota = p.get("pick_cuota", "")
        pick_edge = p.get("pick_edge", 0.0) * 100
        pick_ev = p.get("ev_estimado", 0.0)

        card_html = f"""<div class="oracle-pick nfl-card">
<div class="card-top">
{badge_estado}
<div style="display: flex; gap: 0.5rem; align-items: center;">
<span style="color: #8fa899; font-size: 0.76rem; font-weight: 700;">{spread_str}</span>
{badge_conf}
{badge_res}
</div>
</div>
<div style="display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 1rem; margin: 1rem 0;">
<div style="text-align: left;">
<div style="font-size: 1.35rem; font-weight: 900; color: #f5f8fb;">{away}</div>
<div style="font-size: 0.82rem; color: #8fa899;">DraftKings ML: <b style="color: #b7ff3c;">{ml_a}</b></div>
<div style="font-size: 1.1rem; font-weight: 800; color: #eef3f8; margin-top: 0.25rem;">{prob_a:.1f}%</div>
<div style="font-size: 0.72rem; color: #8fa899;">Probabilidad Modelo</div>
</div>
<div style="text-align: center; color: #4f6859; font-weight: 900; font-size: 1.1rem;">@</div>
<div style="text-align: right;">
<div style="font-size: 1.35rem; font-weight: 900; color: #f5f8fb;">{home}</div>
<div style="font-size: 0.82rem; color: #8fa899;">DraftKings ML: <b style="color: #b7ff3c;">{ml_h}</b></div>
<div style="font-size: 1.1rem; font-weight: 800; color: #eef3f8; margin-top: 0.25rem;">{prob_h:.1f}%</div>
<div style="font-size: 0.72rem; color: #8fa899;">Probabilidad Modelo</div>
</div>
</div>
<div style="width: 100%; height: 8px; background: #07140e; border-radius: 4px; overflow: hidden; display: flex; margin-bottom: 1.1rem;">
<div style="width: {prob_a}%; background: #4f6859; transition: width 0.3s ease;"></div>
<div style="width: {prob_h}%; background: #b7ff3c; transition: width 0.3s ease;"></div>
</div>
<div class="pick-box" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
<div>
<span class="pick-lbl">🎯 PICK RECOMENDADO MONEYLINE</span>
<div class="pick-sel">{pick_sel} <span style="color: #b7ff3c; font-size: 1.1rem; margin-left: 0.35rem;">({pick_cuota})</span></div>
<div style="font-size: 0.78rem; color: #8fa899; margin-top: 0.2rem;">{p.get('pick_detalle', '')}</div>
</div>
<div style="display: flex; gap: 0.6rem;">
<div class="stat-pill">
<div style="font-size: 0.68rem; color: #8fa899; text-transform: uppercase;">Ventaja (Edge)</div>
<div style="font-weight: 800; color: #b7ff3c; font-size: 0.95rem;">+{pick_edge:.1f}%</div>
</div>
<div class="stat-pill">
<div style="font-size: 0.68rem; color: #8fa899; text-transform: uppercase;">Valor Esp. (EV)</div>
<div style="font-weight: 800; color: {'#b7ff3c' if pick_ev >= 0 else '#ff6b6b'}; font-size: 0.95rem;">{pick_ev:+.1f}%</div>
</div>
        st.markdown(card_html, unsafe_allow_html=True)

        if resultado_pick not in ["GANADA", "PERDIDA", "PUSH"]:
            from core.ui_boleta import render_boton_boleta
            partido_id = str(p.get("id_evento") or p.get("id_juego") or f"{away}_{home}_{idx}")
            slip_item = {
                "id": f"NFL_ML_{partido_id}_{pick_sel}",
                "deporte": "NFL",
                "icono": "🏈",
                "partido": f"{away} @ {home}",
                "mercado": "Moneyline",
                "seleccion": pick_sel,
                "momio": pick_cuota,
                "prob": p.get("pick_probabilidad", p.get("prob_local", 0.5)),
            }
            render_boton_boleta(slip_item, key=f"btn_nfl_ml_slip_{partido_id}_{idx}")

    from core.ui_boleta import render_widget_boleta
    render_widget_boleta()


def render_historial():
    """Muestra el historial y rendimiento acumulado de Moneyline NFL."""
    df_hist = cargar_historial_moneyline_mysql()

    if df_hist.empty:
        # Fallback a predicciones locales
        if RUTA_PREDICCIONES.exists():
            with open(RUTA_PREDICCIONES, "r", encoding="utf-8") as f:
                preds = json.load(f)
            df_hist = pd.DataFrame(preds)

    if df_hist.empty:
        st.info("📊 Aún no hay picks de Moneyline registrados en el historial.")
        return

    # Filtrar picks concluidos
    resueltos = df_hist[df_hist["resultado_pick"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()

    total_picks = len(resueltos)
    ganadas = len(resueltos[resueltos["resultado_pick"] == "GANADA"])
    perdidas = len(resueltos[resueltos["resultado_pick"] == "PERDIDA"])
    pushes = len(resueltos[resueltos["resultado_pick"] == "PUSH"])

    win_rate = (ganadas / (ganadas + perdidas) * 100) if (ganadas + perdidas) > 0 else 0.0
    unidades = float(pd.to_numeric(resueltos["beneficio_unidades"], errors="coerce").sum()) if not resueltos.empty else 0.0
    roi = (unidades / (ganadas + perdidas) * 100) if (ganadas + perdidas) > 0 else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total Resueltos", total_picks)
    with c2:
        st.metric("Récord (G-P-E)", f"{ganadas}-{perdidas}-{pushes}")
    with c3:
        st.metric("Win Rate", f"{win_rate:.1f}%")
    with c4:
        st.metric("Balance Unidades", f"{unidades:+.2f}u", delta=f"{unidades:+.2f}u")
    with c5:
        st.metric("ROI", f"{roi:+.2f}%")

    st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

    # Tabla con detalle de picks
    cols_mostrar = [
        "fecha_cdmx", "partido", "seleccion", "cuota_pick", "edge", "resultado_pick", "beneficio_unidades"
    ]
    cols_existentes = [c for c in cols_mostrar if c in df_hist.columns]

    df_tabla = df_hist[cols_existentes].copy()
    if "edge" in df_tabla.columns:
        df_tabla["edge"] = df_tabla["edge"].apply(lambda x: f"+{float(x)*100:.1f}%" if pd.notna(x) else "N/D")
    if "beneficio_unidades" in df_tabla.columns:
        df_tabla["beneficio_unidades"] = df_tabla["beneficio_unidades"].apply(lambda x: f"{float(x):+.2f}u" if pd.notna(x) else "N/D")

    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
    )
