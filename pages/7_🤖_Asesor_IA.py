"""Página interactiva del Asesor Inteligente Overdog AI en Streamlit.
Doble Filtro Cuantitativo, Asesor de Varianza y Chat Analítico en Tiempo Real.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import streamlit as st

st.set_page_config(
    page_title="Asesor AI · OVERDOG",
    page_icon="🤖",
    layout="wide",
)

from core.ui_diseno import apply_design
apply_design()

from core.ui_navegacion_movil import install_navigation
install_navigation()

from core.constants import ZONA_CDMX
from core.asesor_ia import (
    cargar_candidatos_hoy,
    seleccionar_candado_oficial,
    construir_parlay_seguro,
    responder_consulta_asesor,
    obtener_gemini_api_key,
)

hora_actual_cdmx = datetime.now(ZONA_CDMX).strftime("%H:%M")
fecha_hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%d/%m/%Y")

# ==============================================================================
# ENCABEZADO Y BRANDING OVERDOG AI
# ==============================================================================
st.markdown(
    f"""
    <div style="background: linear-gradient(135deg, #0d1b14 0%, #07100b 100%); 
                border: 1px solid #1a382a; border-radius: 14px; padding: 1.2rem 1.5rem; 
                margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center;
                box-shadow: 0 8px 24px rgba(0,0,0,0.4);">
        <div style="display: flex; align-items: center; gap: 14px;">
            <div style="background: rgba(183, 255, 60, 0.12); border: 1px solid #b7ff3c; 
                        border-radius: 12px; width: 48px; height: 48px; display: flex; 
                        align-items: center; justify-content: center; font-size: 1.8rem;">
                🤖
            </div>
            <div>
                <div style="font-size: 1.35rem; font-weight: 900; letter-spacing: 0.5px; color: #ffffff;">
                    OVERDOG <span style="color: #b7ff3c;">ASESOR AI</span>
                </div>
                <div style="font-size: 0.82rem; color: #8ba396; font-weight: 500;">
                    Supervisor de Varianza · Doble Filtro Cuantitativo (Shrinkage + Veto de Blowout) · Ensamble Estadístico
                </div>
            </div>
        </div>
        <div style="text-align: right;">
            <span style="background: #112a1f; color: #b7ff3c; padding: 0.35rem 0.85rem; 
                         border-radius: 8px; font-size: 0.8rem; font-weight: 800; border: 1px solid #1a382a;">
                🕒 {hora_actual_cdmx} CDMX · {fecha_hoy_cdmx}
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ==============================================================================
# CARGAR POOL DE DATOS EN CACHE DE SESIÓN
# ==============================================================================
if "candidatos_hoy" not in st.session_state:
    with st.spinner("Sincronizando modelos matemáticos y cartelera del día..."):
        st.session_state.candidatos_hoy = cargar_candidatos_hoy()

candidatos = st.session_state.candidatos_hoy
total_cand = candidatos.get("total_candidatos", 0)

# ==============================================================================
# SIDEBAR / CONFIGURACIÓN DE IA Y ESTADO DEL DOBLE FILTRO
# ==============================================================================
with st.sidebar:
    st.markdown("### 🛡️ Supervisor Cuantitativo")
    st.caption("Arquitectura de doble validación activa:")
    
    st.markdown(
        """
        - **1. Shrinkage Bayesiano:** Ponderación 60/40 (NBA) y 65/35 (NFL) hacia el mercado para eliminar falsos edges.
        - **2. Veto de Divergencia:** Bloqueo automático ante desviaciones irreales (>35% NBA, >40% NFL).
        - **3. Filtro de Blowout:** Penalización en partidos con spread mayor a 8.5 pts.
        - **4. Descuento de Atrición:** Ajuste conservador de -3.5% en Overs por riesgo de minutos.
        """
    )
    st.divider()

    st.markdown("### 📊 Pool Calificado de Hoy")
    col_sb1, col_sb2 = st.columns(2)
    col_sb1.metric("NBA Props", len(candidatos.get("nba_props", [])))
    col_sb2.metric("NFL Props", len(candidatos.get("nfl_props", [])))
    col_sb1.metric("NBA Partidos", len(candidatos.get("nba_partidos", [])))
    col_sb2.metric("NFL Partidos", len(candidatos.get("nfl_partidos", [])))
    
    if st.button("🔄 Refrescar Oportunidades", use_container_width=True):
        st.session_state.candidatos_hoy = cargar_candidatos_hoy()
        st.rerun()

    st.divider()
    st.markdown("### 🔑 Motor de Razonamiento")
    api_key_default = obtener_gemini_api_key() or ""
    api_key_input = st.text_input(
        "Gemini API Key:",
        value=api_key_default,
        type="password",
        help="Clave para activar el razonamiento profundo de Gemini. Si se deja vacía, opera el motor cuantitativo autónomo."
    )
    if api_key_input:
        os.environ["GEMINI_API_KEY"] = api_key_input.strip().rstrip(".")
        st.success("🟢 Gemini AI Activo (Flash)", icon="⚡")
    else:
        st.info("🟡 Motor Heurístico Cuantitativo", icon="🛡️")

# ==============================================================================
# ACCIONES RÁPIDAS (BOTONES DE UN SOLO CLIC)
# ==============================================================================
st.markdown("##### ⚡ Consultas Rápidas al Supervisor")

col1, col2, col3, col4 = st.columns(4)

pregunta_accion = None

if col1.button("🔒 El Candado del Día", use_container_width=True, help="Selección de menor varianza y mayor solidez estadística"):
    pregunta_accion = "¿Cuál es el partido o pick más seguro del día según el doble filtro?"

if col2.button("🎯 Combinada Segura (2 Patas)", use_container_width=True, help="2 selecciones independientes sin correlación cruzada"):
    pregunta_accion = "Arma la combinada o parlay más seguro del día de 2 selecciones de baja varianza."

if col3.button("🏀 Top Oportunidades NBA", use_container_width=True, help="Mejores opciones cuantitativas NBA de hoy"):
    pregunta_accion = "¿Cuáles son las mejores selecciones y tendencias para la NBA hoy?"

if col4.button("🏈 Top Oportunidades NFL", use_container_width=True, help="Mejores opciones cuantitativas NFL de hoy"):
    pregunta_accion = "¿Cuáles son las mejores selecciones y tendencias para la NFL hoy?"

# ==============================================================================
# HISTORIAL DE CHAT
# ==============================================================================
if "asesor_chat_history" not in st.session_state:
    st.session_state.asesor_chat_history = [
        {
            "role": "assistant",
            "content": (
                "👋 **Hola, soy el Asesor Inteligente de Overdog Sports AI.**\n\n"
                "Actúo como un supervisor independiente sobre las predicciones de los modelos de la plataforma. "
                "Mi función es someter cada proyección a un **doble filtro**: descartar trampas de varianza, "
                "evaluar riesgo de paliza (blowout) y validar la solidez del mercado.\n\n"
                "Puedes presionar los botones superiores o preguntarme directamente: *'¿Cuál es la selección más segura?'*, "
                "*'¿Qué combinada de 2 patas recomiendas hoy?'* o consultar por un jugador o equipo específico."
            )
        }
    ]

# Renderizar mensajes anteriores
for msg in st.session_state.asesor_chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ==============================================================================
# PROCESAMIENTO DE PREGUNTAS (BOTONES O TEXTO)
# ==============================================================================
prompt = st.chat_input("Escribe tu consulta al Asesor AI (ej. '¿Cuál es el juego más seguro de hoy?')...")

# Si se presionó un botón de acción rápida, toma precedencia
if pregunta_accion:
    prompt = pregunta_accion

if prompt:
    # 1. Mostrar mensaje del usuario
    st.session_state.asesor_chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Generar respuesta con Asesor AI
    with st.chat_message("assistant"):
        with st.spinner("Consultando modelos cuantitativos y aplicando doble filtro de varianza..."):
            key_a_usar = api_key_input or os.getenv("GEMINI_API_KEY")
            respuesta = responder_consulta_asesor(
                pregunta=prompt,
                candidatos=candidatos,
                historial=st.session_state.asesor_chat_history,
                gemini_api_key=key_a_usar
            )
            st.markdown(respuesta)
            st.session_state.asesor_chat_history.append({"role": "assistant", "content": respuesta})

# ==============================================================================
# TABLA RESUMEN EXPANDIBLE DEL POOL DE HOY
# ==============================================================================
st.write("")
with st.expander("🔍 Ver desglose de candidatos calificados del día (Auditoría del Modelo)", expanded=False):
    if total_cand == 0:
        st.info("No hay proyecciones activas registradas en los archivos locales de hoy. El Asesor utilizará análisis contextual y heurístico.")
    else:
        tab_nba, tab_nfl = st.tabs(["🏀 NBA Calificados", "🏈 NFL Calificados"])
        
        with tab_nba:
            nba_p = candidatos.get("nba_props", [])
            if nba_p:
                import pandas as pd
                df_view_nba = pd.DataFrame(nba_p)[[
                    "jugador", "mercado", "seleccion", "linea", "proyeccion", "probabilidad", "cuota", "estrellas"
                ]]
                df_view_nba["probabilidad"] = df_view_nba["probabilidad"].apply(lambda x: f"{x*100:.1f}%")
                st.dataframe(df_view_nba, use_container_width=True)
            else:
                st.caption("No hay props de NBA en el pool calificado.")

        with tab_nfl:
            nfl_p = candidatos.get("nfl_props", [])
            if nfl_p:
                import pandas as pd
                df_view_nfl = pd.DataFrame(nfl_p)[[
                    "jugador", "mercado", "seleccion", "linea", "proyeccion", "probabilidad", "cuota", "estrellas"
                ]]
                df_view_nfl["probabilidad"] = df_view_nfl["probabilidad"].apply(lambda x: f"{x*100:.1f}%")
                st.dataframe(df_view_nfl, use_container_width=True)
            else:
                st.caption("No hay props de NFL en el pool calificado.")
