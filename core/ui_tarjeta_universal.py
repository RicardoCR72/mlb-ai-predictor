"""Componente universal de tarjetas de pronóstico de alta fidelidad para OVERDOG AI.

Homologa la experiencia visual en todos los deportes (NBA, NFL, Fútbol, MLB) y mercados
(Totales, Spread, Moneyline, Player Props):
* Contenedor con borde glassmorphic nativo de Streamlit.
* Encabezado con título del pick, contexto del partido, estrellas de confianza y badge EV%.
* 3 métricas ejecutivas: Línea Casa, Proyección del Modelo y Pill de Selección con momios.
* Línea de tendencia narrativa empírica (últimos 5 partidos).
* Alertas contextuales de lesiones o bajas.
* Gráfica interactiva de barras de cobertura de línea (Altair) integrada con expander o vista directa.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Union
import streamlit as st

from core.ui_grafica_cobertura import render_grafica_cobertura


def _color_por_seleccion(sel_str: str) -> str:
    """Retorna color distintivo según el tipo de pick."""
    s = str(sel_str).upper()
    if "OVER" in s or "MÁS" in s or "LOCAL" in s or "HOME" in s or "1" in s:
        return "#10B981"  # Verde esmeralda
    elif "UNDER" in s or "MENOS" in s or "VISITA" in s or "AWAY" in s or "2" in s:
        return "#3B82F6"  # Azul zafiro
    elif "X" in s or "EMPATE" in s or "DRAW" in s:
        return "#8B5CF6"  # Violeta
    return "#10B981"


def _color_por_ev(ev_val: float) -> str:
    """Retorna color del badge según el valor esperado."""
    if ev_val >= 5.0:
        return "#10B981"  # Verde
    elif ev_val > 0.0:
        return "#F59E0B"  # Ámbar
    return "#EF4444"      # Rojo


def _formatear_momio_americano(am_odds: Any, dec_odds: float) -> str:
    """Asegura formato legible de momio americano."""
    if am_odds and str(am_odds).strip() not in ["", "None", "N/D"]:
        s = str(am_odds).strip().upper()
        if s.startswith("+") or s.startswith("-") or s == "EVEN":
            return s
        try:
            val = float(s)
            return f"+{int(val)}" if val > 0 else f"{int(val)}"
        except Exception:
            return s
    # Convertir desde decimal si no viene americano
    if dec_odds and dec_odds > 1.0:
        if dec_odds >= 2.0:
            return f"+{int(round((dec_odds - 1.0) * 100))}"
        else:
            return f"-{int(round(100.0 / (dec_odds - 1.0)))}"
    return "-110"


def render_tarjeta_universal(
    deporte: str,
    titulo: str,
    subtitulo: str,
    mercado: str,
    linea_casa: Union[str, float, None],
    proyeccion_modelo: Union[str, float, None],
    seleccion: str,
    momio_americano: Any = None,
    cuota_decimal: float = 1.909,
    ev_pct: float = 0.0,
    estrellas: str = "⭐",
    tendencia: str = "",
    alerta_contexto: Optional[str] = None,
    jugador: Optional[str] = None,
    equipo: Optional[str] = None,
    rival: Optional[str] = None,
    desplegar_grafica_directa: bool = False,
    key_suffix: str = "",
    etiqueta_linea: str = "Línea Casa",
    etiqueta_proyeccion: str = "Proyección",
    boton_boleta: Optional[Dict[str, Any]] = None,
    contenido_desglose: Optional[Any] = None,
    contenido_lesiones: Optional[Any] = None,
    mostrar_grafica: bool = True,
):
    """Renderiza una tarjeta de pronóstico de alta fidelidad homologada."""
    color_pick = _color_por_seleccion(seleccion)
    color_ev = _color_por_ev(ev_pct)
    momio_am = _formatear_momio_americano(momio_americano, cuota_decimal)

    # Formateo de línea y proyección
    lin_str = f"{float(linea_casa):.1f}" if isinstance(linea_casa, (int, float)) else str(linea_casa or "N/D")
    if isinstance(linea_casa, (int, float)) and float(linea_casa) > 0 and ("spread" in str(mercado).lower() or "hándicap" in str(mercado).lower()):
        lin_str = f"+{float(linea_casa):.1f}"

    proy_str = f"{float(proyeccion_modelo):.1f}" if isinstance(proyeccion_modelo, (int, float)) else str(proyeccion_modelo or "N/D")
    if isinstance(proyeccion_modelo, (int, float)) and float(proyeccion_modelo) > 0 and ("spread" in str(mercado).lower() or "hándicap" in str(mercado).lower()):
        proy_str = f"+{float(proyeccion_modelo):.1f}"

    with st.container(border=True):
        # 1. Encabezado: Título + Mercado + Estrellas + EV%
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"**{titulo}** · `{mercado}`")
            if subtitulo:
                st.caption(subtitulo)
        with c2:
            signo_ev = "+" if ev_pct > 0 else ""
            st.markdown(
                f"<div style='text-align:right;'>"
                f"<span style='font-size:1.1rem;'>{estrellas}</span><br>"
                f"<b style='color:{color_ev};'>{signo_ev}{ev_pct:.1f}% EV</b>"
                f"</div>",
                unsafe_allow_html=True
            )

        # 2. Bloque de 3 Métricas Ejecutivas
        m1, m2, m3 = st.columns(3)
        m1.metric(etiqueta_linea, lin_str)
        m2.metric(etiqueta_proyeccion, proy_str)
        m3.markdown(
            f"<div style='background:{color_pick}22; padding:6px 10px; border-radius:8px; border:1px solid {color_pick}; text-align:center; margin-top:4px;'>"
            f"<b style='color:{color_pick}; font-size:1.05rem;'>{seleccion}</b><br>"
            f"<span style='font-size:0.85rem;'>{momio_am} ({cuota_decimal:.2f})</span>"
            f"</div>",
            unsafe_allow_html=True
        )

        # 3. Tendencia narrativa
        if tendencia:
            st.caption(f"📈 **Tendencia:** {tendencia}")

        # 4. Alerta contextual
        if alerta_contexto:
            st.markdown(
                f"<div style='background:#EF44441a; color:#F87171; padding:4px 8px; border-radius:6px; font-size:0.8rem; font-weight:600; margin-bottom:0.4rem; border:1px solid #EF444433;'>"
                f"{alerta_contexto}"
                f"</div>",
                unsafe_allow_html=True
            )

        # 5. Analítica, Gráfica y Desglose Unificado (1 solo menú con pestañas)
        lin_num = float(linea_casa) if isinstance(linea_casa, (int, float)) else None
        if lin_num is None:
            m_lin = re.search(r'(\d+(?:\.\d+)?)', str(seleccion))
            if m_lin:
                try:
                    lin_num = float(m_lin.group(1))
                except Exception:
                    pass

        key_graf = f"{deporte}_{abs(hash(str(titulo) + str(mercado) + str(seleccion) + str(key_suffix))) % 10000000}"

        if desplegar_grafica_directa:
            if mostrar_grafica:
                render_grafica_cobertura(
                    deporte=deporte,
                    mercado=mercado,
                    seleccion=seleccion,
                    linea=lin_num,
                    equipo=equipo,
                    rival=rival,
                    jugador=jugador,
                    key_suffix=key_graf,
                    modo_compacto=True,
                )
            if callable(contenido_desglose):
                contenido_desglose()
            if callable(contenido_lesiones):
                contenido_lesiones()
        else:
            tabs_config = []
            if mostrar_grafica:
                tabs_config.append(("📊 Gráfica L5", "grafica"))
            if callable(contenido_desglose):
                tabs_config.append(("⚖️ Desglose de Mercados", "desglose"))
            if callable(contenido_lesiones):
                tabs_config.append(("🏥 Reporte de Lesiones", "lesiones"))

            if len(tabs_config) > 1:
                with st.expander("🔍 Analítica Completa (Gráfica, Mercados y Bajas)", expanded=False):
                    creadas = st.tabs([t[0] for t in tabs_config])
                    for tab_ui, (_, tipo) in zip(creadas, tabs_config):
                        with tab_ui:
                            if tipo == "grafica":
                                render_grafica_cobertura(
                                    deporte=deporte,
                                    mercado=mercado,
                                    seleccion=seleccion,
                                    linea=lin_num,
                                    equipo=equipo,
                                    rival=rival,
                                    jugador=jugador,
                                    key_suffix=key_graf,
                                    modo_compacto=True,
                                )
                            elif tipo == "desglose":
                                contenido_desglose()
                            elif tipo == "lesiones":
                                contenido_lesiones()
            elif len(tabs_config) == 1:
                with st.expander(f"{tabs_config[0][0]} vs línea" if tabs_config[0][1] == "grafica" else tabs_config[0][0], expanded=False):
                    if tabs_config[0][1] == "grafica":
                        render_grafica_cobertura(
                            deporte=deporte,
                            mercado=mercado,
                            seleccion=seleccion,
                            linea=lin_num,
                            equipo=equipo,
                            rival=rival,
                            jugador=jugador,
                            key_suffix=key_graf,
                            modo_compacto=True,
                        )
                    elif tabs_config[0][1] == "desglose":
                        contenido_desglose()
                    elif tabs_config[0][1] == "lesiones":
                        contenido_lesiones()

        # 6. Botón opcional de agregar a la boleta
        if boton_boleta:
            try:
                from core.ui_boleta import render_boton_boleta
                render_boton_boleta(boton_boleta, key=f"btn_slip_{key_graf}")
            except Exception:
                pass

