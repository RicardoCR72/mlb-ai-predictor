"""Página interactiva del Oráculo AI para la NBA en Streamlit con módulo de Rendimiento y Base de Datos.

Rediseñada con arquitectura de Divulgación Progresiva (Progressive Disclosure),
estética Obsidian & Court Neon Orange, navegación por pestañas y reducción de fatiga visual.
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
from nba.registro import cargar_historial_rendimiento, liquidar_partidos_pendientes_nba, guardar_predicciones_nba
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
                    return predecir_partidos_hoy(force_refresh=True)

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
    except Exception:
        return predecir_partidos_hoy(force_refresh=True)


# Encabezado de Navegación y Marca
st.markdown(
    """<div class="nba-shell">
<div class="nba-brand">
<span class="nba-logo">🏀</span>
<div>
<div style="font-size: 1.05rem; font-weight: 900; color: #ffffff;">ORÁCULO <span class="nba-accent">NBA AI</span></div>
<div class="nba-status">DraftKings Odds · Four Factors Analytics · Sincronizado con Base de Datos</div>
</div>
</div>
<div style="text-align: right;">
<div style="font-size: 0.78rem; color: #a4978e;">Mercados Activos</div>
<div style="font-size: 0.95rem; font-weight: 800; color: #ff8c33;">Spread · Totales (O/U) · Moneyline</div>
</div>
</div>""",
    unsafe_allow_html=True,
)

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")

# Cargar estado de predicciones de hoy
predicciones_actuales = cargar_predicciones(forzar=False)
hay_pendientes_por_liquidar = any(
    p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]
    for p in predicciones_actuales
)

# Toolbar superior compacta
top_col1, top_col2, top_col3 = st.columns([2, 1, 1])

with top_col1:
    st.caption(f"📅 Cartelera oficial NBA · Hora CDMX: **{hora_actual_cdmx}** · Líneas oficiales DraftKings")

with top_col2:
    if st.button("🔄 Actualizar Cuotas", key="btn_act_cuotas", use_container_width=True, help="Consulta las últimas líneas de DraftKings y actualiza las predicciones de hoy."):
        with st.spinner("Consultando DraftKings y ejecutando modelos NBA..."):
            cargar_predicciones(forzar=True)
            st.success("✅ Cuotas y predicciones actualizadas desde DraftKings.")
            st.rerun()

with top_col3:
    btn_deshabilitado = not hay_pendientes_por_liquidar
    lbl_btn_res = "🏁 Resultados Registrados" if btn_deshabilitado else "🏁 Liquidar Resultados"
    help_btn_res = (
        "Todos los partidos disponibles ya fueron liquidados y registrados en Rendimiento e Historial."
        if btn_deshabilitado else
        "Consulta marcadores finales de ESPN, liquida las apuestas y las pasa a Rendimiento e Historial."
    )
    if st.button(lbl_btn_res, key="btn_act_res", disabled=btn_deshabilitado, use_container_width=True, help=help_btn_res):
        with st.spinner("Liquidando partidos y actualizando historial NBA..."):
            res = liquidar_partidos_pendientes_nba()
            if res.get("evaluados", 0) > 0:
                st.success(f"✅ {res['mensaje']}")
            else:
                st.info(f"ℹ️ {res['mensaje']}")
            st.rerun()

# Navegación estandarizada por pestañas
tab_cartelera, tab_historial = st.tabs(["🏀 Cartelera y Picks de Hoy", "📊 Rendimiento y Auditoría"])

# ==========================================================
# PESTAÑA 1: CARTELERA Y PROYECCIONES DE HOY
# ==========================================================
with tab_cartelera:
    st.markdown(
        """<div class="nba-view-hero">
<div>
<h1 class="nba-hero-title">Centro de Inteligencia Deportiva · NBA</h1>
<div class="nba-hero-sub">Proyecciones matemáticas de margen, Totales Over/Under y Spreads de DraftKings con analítica Four Factors.</div>
</div>
</div>""",
        unsafe_allow_html=True,
    )

    predicciones = list(predicciones_actuales)

    if not predicciones:
        st.info("🏀 No hay partidos programados para hoy en la cartelera de la NBA. Puedes volver a consultar más tarde o forzar la actualización.")
    else:
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

        ganadas_hoy = sum(1 for p in predicciones if p.get("resultado") == "GANADA")
        perdidas_hoy = sum(1 for p in predicciones if p.get("resultado") == "PERDIDA")
        pushes_hoy = sum(1 for p in predicciones if p.get("resultado") == "PUSH")
        u_hoy = sum(float(p.get("unidades_ganadas") or 0.0) for p in predicciones if p.get("unidades_ganadas") is not None)

        # Panel de métricas ejecutivas
        mcols = st.columns(4)
        mcols[0].metric("Partidos en Cartelera", f"{n_pendientes} pendientes")
        if n_liquidados > 0 and n_pendientes == 0:
            mcols[1].metric("Picks Auditados", f"{n_liquidados} liquidados")
            mcols[2].metric("Balance Auditado", f"{u_hoy:+.2f} u", f"{ganadas_hoy}G - {perdidas_hoy}P" + (f" ({pushes_hoy} Push)" if pushes_hoy else ""))
            mcols[3].metric("Estado de Jornada", "Finalizada y Archivada")
        else:
            picks_altos = sum(1 for p in partidos_pendientes if p.get("confianza") == "ALTA")
            picks_totales = sum(1 for p in partidos_pendientes if "Totales" in p.get("pick_mercado", ""))
            picks_spread = sum(1 for p in partidos_pendientes if "Spread" in p.get("pick_mercado", ""))
            mcols[1].metric("Picks Alta Confianza", picks_altos)
            mcols[2].metric("Picks de Totales (O/U)", picks_totales)
            mcols[3].metric("Picks de Spread / ML", picks_spread + sum(1 for p in partidos_pendientes if "Moneyline" in p.get("pick_mercado", "")))

        if n_pendientes == 0:
            st.markdown(
                f"""<div style="background: linear-gradient(145deg, #18110b, #0f0a06); border: 1px solid #ff6b00; border-radius: 16px; padding: 2rem; text-align: center; margin-top: 1.2rem; margin-bottom: 2rem;">
<div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🏀🏁</div>
<div style="font-size: 1.35rem; font-weight: 900; color: #ff8c33; margin-bottom: 0.5rem;">Partidos Concluidos y Auditados</div>
<div style="color: #cbd5e1; font-size: 0.95rem; max-width: 620px; margin: 0 auto; line-height: 1.55;">
Los partidos de la cartelera anterior ({n_liquidados} juegos) ya finalizaron y han sido liquidados en la pestaña <b>Rendimiento y Auditoría</b>. Para consultar la nueva cartelera, pulsa <b>Actualizar Cuotas</b>.
</div>
</div>""",
                unsafe_allow_html=True,
            )
        else:
            # Filtros rápidos para partidos pendientes
            fcol1, fcol2, fcol3 = st.columns(3)
            with fcol1:
                filtro_mercado = st.selectbox(
                    "Mercado del Pick:",
                    ["Todos los mercados", "Totales (Over/Under)", "Spread", "Moneyline"],
                    key="f_nba_mercado",
                )
            with fcol2:
                filtro_confianza = st.selectbox(
                    "Nivel de Confianza:",
                    ["Todas las selecciones", "Solo ALTA confianza", "Solo MEDIA confianza"],
                    key="f_nba_confianza",
                )
            with fcol3:
                filtro_orden = st.selectbox(
                    "Ordenar por:",
                    ["Hora (Más temprano primero)", "Confianza (ALTA primero)"],
                    key="f_nba_orden",
                )

            filtrados = list(partidos_pendientes)

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

            if filtro_orden == "Hora (Más temprano primero)":
                filtrados.sort(key=lambda x: x.get("hora_cdmx", ""))
            else:
                filtrados.sort(key=lambda x: 0 if x.get("confianza") == "ALTA" else 1)

            st.write("")
            st.subheader(f"Partidos Disponibles ({len(filtrados)})")

            # Renderizado de Tarjetas con Divulgación Progresiva
            for p in filtrados:
                conf = p.get("confianza", "NEUTRAL")
                badge_conf = "badge-conf-alta" if conf == "ALTA" else "badge-conf-media"

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
                    badge_top_right = f'<span class="{badge_conf}">CONFIANZA {conf}</span>'

                card_top_html = (
                    f'<div class="card-top">'
                    f'<div style="display: flex; align-items: center; gap: 0.5rem;">'
                    f'{badge_status}'
                    f'<span style="color: #a4978e; font-size: 0.8rem;">{p.get("provider", "DraftKings")} Sportsbook</span>'
                    f'</div>'
                    f'<div>{badge_top_right}</div>'
                    f'</div>'
                )

                # Fila de equipos
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

                # Momio del pick
                cuota_pick_str = ""
                if "Totales" in str(p.get("pick_mercado", "")) or "Spread" in str(p.get("pick_mercado", "")):
                    cuota_pick_str = " · Momio: -110 (1.91)"
                elif "Moneyline" in str(p.get("pick_mercado", "")):
                    sel_text = str(p.get("pick_seleccion", ""))
                    ml_val = p.get("ml_local") if (str(p.get("equipo_local", "")).lower() in sel_text.lower()) else p.get("ml_visita")
                    if ml_val:
                        cuota_pick_str = f" · Momio: {ml_val}"

                # Caja de recomendación oficial
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
                    prob_pct = p.get("pick_probabilidad", 0.0) * 100
                    pick_res_html = (
                        f'<div style="text-align: right;">'
                        f'<div style="font-size: 0.72rem; color: #a4978e; font-weight: 700;">PROBABILIDAD MODELO</div>'
                        f'<div style="font-size: 1.35rem; font-weight: 900; color: #ff8c33;">{prob_pct:.1f}%</div>'
                        f'</div>'
                    )

                pick_box_html = (
                    f'<div class="pick-box">'
                    f'<div style="min-width: 0; flex: 1;">'
                    f'<div class="pick-title">Recomendación Oficial ({p.get("pick_mercado")})<span style="color:#ffffff;font-weight:700;">{cuota_pick_str}</span></div>'
                    f'<div class="pick-sel">{p.get("pick_seleccion")}</div>'
                    f'<div style="font-size: 0.82rem; color: #a4978e; margin-top: 0.2rem;">{p.get("pick_detalle", "")}</div>'
                    f'</div>'
                    f'{pick_res_html}'
                    f'</div>'
                )

                with st.container(border=True):
                    # Nivel 1: Datos principales claros e inmediatos
                    st.markdown(card_top_html + teams_html + pick_box_html, unsafe_allow_html=True)

                    # Nivel 2: Divulgación progresiva (Desglose analítico completo colapsable)
                    with st.expander("📊 Ver desglose analítico completo (Spreads, Totales y Probabilidades 1X2)"):
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


# ==========================================================
# PESTAÑA 2: RENDIMIENTO Y AUDITORÍA HISTÓRICA
# ==========================================================
with tab_historial:
    st.markdown(
        """<div class="nba-view-hero">
<div>
<h1 class="nba-hero-title">Rendimiento Histórico y Auditoría · NBA</h1>
<div class="nba-hero-sub">Registro auditado de aciertos, simulación de unidades ganadas (+/- u) y retorno de inversión (ROI) con datos verificados.</div>
</div>
</div>""",
        unsafe_allow_html=True,
    )

    df_hist = cargar_historial_rendimiento()

    if df_hist.empty:
        st.info("No hay historial disponible aún en la base de datos de la NBA.")
    else:
        liquidados = df_hist[df_hist["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()

        # Asignación de Temporada NBA
        dt_serie = pd.to_datetime(liquidados["fecha"], errors="coerce")
        y_serie = dt_serie.dt.year
        m_serie = dt_serie.dt.month
        next_yy = ((y_serie + 1) % 100).astype(str).str.zfill(2)
        cur_yy = (y_serie % 100).astype(str).str.zfill(2)
        prev_y = (y_serie - 1).astype(str)
        liquidados["temporada"] = np.where(m_serie >= 10, y_serie.astype(str) + "-" + next_yy, prev_y + "-" + cur_yy)

        temporadas_ordenadas = sorted(liquidados["temporada"].unique().tolist(), reverse=True)
        temp_actual = temporadas_ordenadas[0] if temporadas_ordenadas else "2026-27"

        # Filtros Temporales y de Partido
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

        # Criterios de Auditoría
        st.markdown("<div style='font-size: 0.82rem; font-weight: 800; color: #ff8c33; letter-spacing: 0.08em; margin-top: 0.4rem; margin-bottom: 0.35rem;'>CRITERIOS DE AUDITORÍA</div>", unsafe_allow_html=True)
        rcol1, rcol2, rcol3 = st.columns(3)
        with rcol1:
            mercados_disp = ["Todos los mercados"] + sorted(list(liquidados["mercado"].unique()))
            sel_mercado = st.selectbox("Mercado para Auditoría", mercados_disp)
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
        elif sel_resultado == "Solo Pushes":
            f_liq = f_liq[f_liq["resultado"] == "PUSH"]

        if f_liq.empty:
            st.warning("⚠️ No se encontraron picks ni partidos liquidados para la combinación de filtros seleccionada.")
        else:
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
            rmcols[3].metric("ROI Simulado", f"{roi_pct:+.2f}%")

            # Gráfica de evolución acumulada
            if len(f_liq) > 1 and f_liq["fecha"].nunique() > 1:
                st.write("")
                st.subheader("📈 Evolución de Unidades en el Tiempo (Simulación 1 u por pick)")
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
                partidos_grupos.append({
                    "fecha": f_val,
                    "hora_cdmx": h_cdmx,
                    "temporada": temp_val,
                    "equipo_visitante": ev_val,
                    "equipo_local": el_val,
                    "marcador_visitante": mv,
                    "marcador_local": ml,
                    "picks": g_df.to_dict(orient="records"),
                    "unidades_totales": float(g_df["unidades_ganadas"].sum())
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

            # Tabla Completa de Auditoría
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
