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
                from nfl.liquidar_nfl import liquidar_todo_nfl
                res = liquidar_todo_nfl()
                if res.get("total", 0) > 0 or res.get("evaluados", 0) > 0:
                    st.success(f"✅ {res['mensaje']}")
                else:
                    st.info(f"ℹ️ {res['mensaje']}")
                st.rerun()

    with col2:
        if st.button("⚡ Actualizar Moneyline (0 Créditos · ESPN/DraftKings)", key="btn_act_cuotas_nfl_ml", type="primary", use_container_width=True, help="Consulta cuotas oficiales en tiempo real desde ESPN y Bovada (0 créditos consumidos) y recalcula el ensamble calibrado."):
            with st.spinner("Consultando ESPN/DraftKings/Bovada y ejecutando modelo calibrado..."):
                cargar_predicciones_nfl_moneyline(forzar=True)
                st.success("✅ Cuotas y pronósticos de Moneyline actualizados a 0 créditos.")
                st.rerun()

    st.markdown("<div style='margin-bottom: 1.1rem;'></div>", unsafe_allow_html=True)

    if sub_vista == "Partidos de la Semana":
        render_cartelera(predicciones)
    else:
        render_historial()


def render_cartelera(predicciones: list[dict]):
    """Muestra las tarjetas interactivas homologadas de pronósticos Moneyline."""
    if not predicciones:
        st.info("🏈 No hay partidos programados para la NFL en este momento.")
        return

    from core.ui_tarjeta_universal import render_tarjeta_universal
    from core.ui_boleta import parsear_cuota_decimal, render_widget_boleta
    from nfl.ui_lesiones_helper import crear_callback_lesiones_nfl

    pendientes = [p for p in predicciones if p.get("resultado_pick") not in ["GANADA", "PERDIDA", "PUSH"]]
    liquidados = [p for p in predicciones if p.get("resultado_pick") in ["GANADA", "PERDIDA", "PUSH"]]
    picks_calificados = sum(1 for p in predicciones if p.get("confianza") in ["ALTA", "MEDIA"])

    # Métricas clave superiores
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Partidos", len(predicciones))
    with c2:
        st.metric("Pendientes", len(pendientes))
    with c3:
        st.metric("Finalizados", len(liquidados))
    with c4:
        st.metric("Picks Calificados (+EV)", picks_calificados)

    st.markdown("<div style='margin-bottom: 1.25rem;'></div>", unsafe_allow_html=True)

    # Filtros ejecutivos homologados con NBA y Fútbol
    f_col1, f_col2, f_col3 = st.columns([1.6, 1.2, 1.2], gap="medium")
    with f_col1:
        busqueda_nfl = st.text_input(
            "Buscar equipo NFL",
            key="nfl_ml_search_input",
            placeholder="🔍 Ej: Chiefs, 49ers, Eagles, Cowboys, Ravens...",
        ).strip().lower()
    with f_col2:
        st.markdown("<div style='margin-top: 1.8rem;'></div>", unsafe_allow_html=True)
        solo_ev = st.checkbox("🔥 Solo picks Calificados (+EV)", key="nfl_ml_ev_filter")
    with f_col3:
        filtro_estado = st.selectbox(
            "Estado:",
            ["Solo Próximos (Por Jugar)", "Solo Finalizados", "Todos los partidos"],
            key="nfl_ml_filtro_estado",
        )

    lista_mostrar = list(predicciones)

    # 1. Búsqueda por texto
    if busqueda_nfl:
        lista_mostrar = [
            p for p in lista_mostrar
            if (busqueda_nfl in str(p.get("equipo_local", "")).lower() or
                busqueda_nfl in str(p.get("equipo_visita", "")).lower() or
                busqueda_nfl in str(p.get("partido", "")).lower())
        ]

    # Helper para determinar si el partido está concluido
    def _es_partido_final_ml(p: dict) -> bool:
        res = str(p.get("resultado_pick") or "").upper()
        st_raw = str(p.get("estado") or "").upper()
        return res in ["GANADA", "PERDIDA", "PUSH"] or "FINAL" in st_raw

    # 2. Filtro por estado
    if filtro_estado == "Solo Próximos (Por Jugar)":
        lista_mostrar = [p for p in lista_mostrar if not _es_partido_final_ml(p)]
    elif filtro_estado == "Solo Finalizados":
        lista_mostrar = [p for p in lista_mostrar if _es_partido_final_ml(p)]

    # Helper de cálculo/extracción de EV%
    def _get_ev_nfl_ml(p: dict) -> float:
        ev = p.get("ev_estimado")
        if ev is not None:
            try:
                return float(ev)
            except (ValueError, TypeError):
                pass
        c = parsear_cuota_decimal(p.get("pick_cuota"))
        prob = float(p.get("pick_probabilidad") or p.get("pick_prob") or 0.5)
        if c > 1.0 and prob > 0:
            return (prob * c - 1.0) * 100.0
        return float(p.get("pick_edge", 0.0) or 0.0) * 100.0

    # 3. Filtro "Solo Picks Calificados ordenados de Mayor a Menor EV%"
    if solo_ev:
        lista_mostrar = [
            p for p in lista_mostrar
            if p.get("confianza") in ["ALTA", "MEDIA"] and _get_ev_nfl_ml(p) > 0
        ]
        if lista_mostrar:
            lista_mostrar.sort(key=_get_ev_nfl_ml, reverse=True)
            st.caption("🔥 Mostrando picks calificados ordenados de **Mayor a Menor Valor Esperado (+EV)**.")
    else:
        # Orden natural por EV descendente
        lista_mostrar.sort(key=_get_ev_nfl_ml, reverse=True)

    if not lista_mostrar:
        st.warning("No hay partidos o picks que coincidan con los filtros de búsqueda seleccionados.")
        return

    # Renderizar tarjetas individuales homologadas
    for idx, p in enumerate(lista_mostrar):
        home = str(p.get("equipo_local") or "LOC")
        away = str(p.get("equipo_visita") or "VIS")
        prob_h = float(p.get("prob_local", 0.5) or 0.5) * 100
        prob_a = float(p.get("prob_visita", 0.5) or 0.5) * 100
        ml_h = p.get("ml_local") or "N/D"
        ml_a = p.get("ml_visita") or "N/D"
        spread = p.get("spread_line")
        spread_str = f"{spread:+g}" if spread is not None else "N/D"

        estado = str(p.get("estado", "")).upper()
        resultado_pick = str(p.get("resultado_pick") or "PENDIENTE").upper()
        es_resuelta = resultado_pick in ["GANADA", "PERDIDA", "PUSH"] or "FINAL" in estado

        # Si ya finalizó, mostrar contenedor histórico limpio
        if es_resuelta:
            m_vis = p.get("marcador_visita", 0)
            m_loc = p.get("marcador_local", 0)
            u_gan = float(p.get("beneficio_unidades") or 0.0)

            if resultado_pick == "GANADA":
                badge_res = f"<span style='background: rgba(183, 255, 60, 0.2); color: #b7ff3c; border: 1px solid #b7ff3c; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>✅ GANADA (+{u_gan:.2f}u)</span>"
            elif resultado_pick == "PERDIDA":
                badge_res = "<span style='background: rgba(255, 75, 75, 0.2); color: #ff6b6b; border: 1px solid #ff4b4b; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>❌ PERDIDA (-1.00u)</span>"
            elif resultado_pick == "PUSH":
                badge_res = "<span style='background: rgba(255, 214, 0, 0.2); color: #ffd600; border: 1px solid #ffd600; padding: 0.25rem 0.65rem; border-radius: 7px; font-weight: 900; font-size: 0.85rem;'>🤝 PUSH (0.00u)</span>"
            else:
                badge_res = f"<span style='background: #192e22; color: #8fa899; padding: 0.2rem 0.55rem; border-radius: 6px; font-weight: 700; font-size: 0.75rem;'>FINAL: {away} {m_vis} - {m_loc} {home}</span>"

            with st.container(border=True):
                st.markdown(
                    f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;'>"
                    f"<span style='background: #192e22; color: #8fa899; padding: 0.2rem 0.55rem; border-radius: 6px; font-weight: 700; font-size: 0.75rem;'>FINAL: {away} {m_vis} – {m_loc} {home}</span>"
                    f"{badge_res}"
                    f"</div>"
                    f"<div style='font-size: 1.15rem; font-weight: 800; color: #eef3f8;'>{away} @ {home}</div>"
                    f"<div style='font-size: 0.85rem; color: #8fa899; margin-top:0.25rem;'>Selección recomendada: <b>{p.get('pick_seleccion')}</b> ({p.get('pick_cuota')}) · {p.get('pick_detalle', '')}</div>",
                    unsafe_allow_html=True
                )
            continue

        # Partido activo / pendiente: TARJETA UNIVERSAL
        ev_val = _get_ev_nfl_ml(p)
        conf = p.get("confianza", "NEUTRAL") if ev_val > 0 else "NEUTRAL"
        pick_sel = str(p.get("pick_seleccion") or f"{home} ML")
        pick_cuota = str(p.get("pick_cuota") or "-110")
        cuota_dec = float(p.get("pick_cuota_dec") or parsear_cuota_decimal(pick_cuota) or 1.909)
        prob_modelo_pick = float(p.get("pick_probabilidad") or (prob_h / 100 if home in pick_sel else prob_a / 100))

        # Asignación estricta de estrellas por Valor Esperado Positivo (+EV)
        if ev_val > 0:
            if conf == "ALTA" or ev_val >= 10.0:
                estrellas = "⭐⭐⭐"
            elif conf == "MEDIA" or ev_val >= 5.0:
                estrellas = "⭐⭐"
            else:
                estrellas = "⭐"
        else:
            estrellas = "⚪"

        diff_epa = float(p.get("diff_total_epa", 0.0) or 0.0)
        diff_ol = float(p.get("diff_injury_ol", 0.0) or 0.0)
        diff_pass = float(p.get("diff_pass_epa", 0.0) or 0.0)

        alerta_contexto = None
        if abs(diff_ol) >= 1.0:
            alerta_contexto = f"🛡️ Desbalance en Línea Ofensiva: Diff OL {diff_ol:+.1f} (favorece presión al QB)"
        elif abs(diff_pass) >= 6.0:
            alerta_contexto = f"🎯 Brecha Aérea: Ventaja neta en eficiencia de pase de {diff_pass:+.1f} EPA"

        # Pestaña 1 del menú: Desglose de Mercados
        def _render_ml_desglose(p_curr=p, home_curr=home, away_curr=away, prob_h_curr=prob_h, prob_a_curr=prob_a, ml_h_curr=ml_h, ml_a_curr=ml_a, sp_str=spread_str, d_epa=diff_epa, d_pass=diff_pass, d_ol=diff_ol):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Cuotas DraftKings Moneyline & Spread:**")
                st.markdown(f"- **{home_curr}** (Local): ML `{ml_h_curr}`")
                st.markdown(f"- **{away_curr}** (Visita): ML `{ml_a_curr}`")
                st.markdown(f"- Spread Oficial: `{sp_str}`")
            with col2:
                st.markdown("**Métricas Ensamble EPA + LightGBM:**")
                st.markdown(f"- Prob. Modelo: **{away_curr} {prob_a_curr:.1f}%** @ **{home_curr} {prob_h_curr:.1f}%**")
                st.markdown(f"- Diff Total EPA: **{d_epa:+.2f}**")
                st.markdown(f"- Diff Pass EPA: **{d_pass:+.2f}**")
                st.markdown(f"- Salud Línea Ofensiva (OL): **{d_ol:+.1f}**")

        # Pestaña 2 del menú: Reporte de Lesiones
        extra_inj = f"Impacto analítico en trincheras: Salud Línea Ofensiva Diff **{diff_ol:+.1f}**"
        fn_lesiones = crear_callback_lesiones_nfl(away, home, extra_context=extra_inj)

        partido_id = str(p.get("id_evento") or p.get("id_juego") or f"{away}_{home}_{idx}")
        # Solo permitir agregar a la boleta picks con EV positivo
        slip_item = None
        if conf in ["ALTA", "MEDIA"] and ev_val > 0:
            slip_item = {
                "id": f"NFL_ML_{partido_id}_{pick_sel}",
                "deporte": "NFL",
                "icono": "🏈",
                "partido": f"{away} @ {home}",
                "mercado": "Moneyline",
                "seleccion": pick_sel,
                "momio": pick_cuota,
                "prob": prob_modelo_pick,
            }

        render_tarjeta_universal(
            deporte="NFL",
            titulo=f"{away} @ {home}",
            subtitulo=f"⏰ {p.get('fecha_cdmx', '')} {p.get('hora_cdmx', '')} CDMX · DraftKings / ESPN",
            mercado="🏈 Moneyline",
            linea_casa=f"Spread {spread_str}" if spread is not None else "Moneyline",
            proyeccion_modelo=f"{prob_modelo_pick * 100:.1f}%",
            seleccion=pick_sel,
            momio_americano=pick_cuota,
            cuota_decimal=cuota_dec,
            ev_pct=ev_val,
            estrellas=estrellas,
            tendencia=str(p.get("pick_detalle") or f"Probabilidad Modelo: {prob_modelo_pick*100:.1f}%"),
            alerta_contexto=alerta_contexto,
            equipo=home,
            rival=away,
            desplegar_grafica_directa=False,
            key_suffix=f"nfl_ml_{partido_id}_{idx}",
            etiqueta_linea="Línea Spread",
            etiqueta_proyeccion="Prob. Modelo",
            boton_boleta=slip_item,
            contenido_desglose=_render_ml_desglose,
            contenido_lesiones=fn_lesiones,
            mostrar_grafica=False,
        )

        if conf == "NEUTRAL" or ev_val <= 0:
            st.caption("🛡️ *Filtro de Disciplina Activo: Este partido está en la Zona Muerta (EV negativo o cuota castigada). Descartado para apuestas directas.*")

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

    # Filtrar picks concluidos (excluyendo programados o en vivo)
    resueltos = df_hist[df_hist["resultado_pick"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()

    if resueltos.empty:
        st.info("📊 Aún no hay picks concluidos ni liquidados en el historial de Moneyline. Los partidos de hoy y en vivo se encuentran en 'Partidos de la Semana'.")
        return

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

    # Tabla con detalle de picks concluidos
    cols_mostrar = [
        "fecha_cdmx", "partido", "seleccion", "cuota_pick", "edge", "resultado_pick", "beneficio_unidades"
    ]
    cols_existentes = [c for c in cols_mostrar if c in resueltos.columns]

    df_tabla = resueltos[cols_existentes].copy()
    if "edge" in df_tabla.columns:
        df_tabla["edge"] = df_tabla["edge"].apply(lambda x: f"+{float(x)*100:.1f}%" if pd.notna(x) else "N/D")
    if "beneficio_unidades" in df_tabla.columns:
        df_tabla["beneficio_unidades"] = df_tabla["beneficio_unidades"].apply(lambda x: f"{float(x):+.2f}u" if pd.notna(x) else "N/D")

    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
    )
