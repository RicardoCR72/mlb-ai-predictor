"""Botón explícito de cuotas NFL; sincronización gratuita con Bovada (0 Créditos)."""
from __future__ import annotations

import subprocess
import sys
import streamlit as st
from nfl.jornada import ahora_mexico, MEXICO


def render_prediction_button():
    """Botón principal para desplegar panel de actualización de props NFL."""
    opened = "_nfl_prediction_panel"
    btn_label = "⚡ Actualizar Props NFL (Bovada 0 Créditos)"
    if st.button(btn_label, key="nfl_preparar_predicciones", use_container_width=True, type="primary"):
        st.session_state[opened] = not st.session_state.get(opened, False)
    if not st.session_state.get(opened, False):
        return
    with st.container(border=True):
        render_prediction_panel()


def render_prediction_panel():
    """Panel de actualización gratuita a través del servicio Bovada."""
    st.markdown(
        """<div style="background: rgba(0, 230, 118, 0.08); border: 1px solid rgba(0, 230, 118, 0.35); padding: 0.75rem 0.9rem; border-radius: 8px; margin-bottom: 0.8rem;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <span style="color: #00e676; font-weight: 800; font-size: 0.88rem;">🏈 Feed Bovada Oficial Activo</span>
            <span style="background: rgba(0, 230, 118, 0.2); color: #00ffa3; font-size: 0.72rem; font-weight: 800; padding: 0.15rem 0.5rem; border-radius: 4px;">0 CRÉDITOS</span>
        </div>
        <div style="color: #94a3b8; font-size: 0.80rem; margin-top: 0.3rem;">
            Extracción directa en tiempo real de todos los Player Props disponibles (Passing, Rushing, Receiving Yards/TDs y Anytime TD) sin costo.
        </div>
        </div>""",
        unsafe_allow_html=True,
    )

    c_btn, c_info = st.columns([1.2, 1], gap="medium")
    with c_btn:
        if st.button("🚀 Sincronizar Props Ahora (0 Créditos)", key="btn_sync_bovada_nfl_free", use_container_width=True):
            with st.spinner("1/2 Descargando líneas en tiempo real desde Bovada..."):
                try:
                    from nfl.servicio_bovada_props import sincronizar_lineas_bovada_a_mysql
                    n_lineas = sincronizar_lineas_bovada_a_mysql()
                    st.toast(f"✅ {n_lineas} líneas extraídas de Bovada.", icon="🏈")
                except Exception as e:
                    st.error(f"Error extrayendo líneas de Bovada: {e}")
                    return

            with st.spinner("2/2 Calculando modelos de proyección y valor esperado (+EV)..."):
                try:
                    res = subprocess.run(
                        [sys.executable, "nfl/predecir_props_semana_actual.py"],
                        capture_output=True,
                        text=True,
                        timeout=600,
                    )
                    if res.returncode == 0:
                        st.toast("🎯 Proyecciones y EV actualizados.", icon="🔥")
                    else:
                        st.warning("Líneas sincronizadas; cálculo de modelos finalizó con advertencias.")
                except Exception as e:
                    st.error(f"Error ejecutando modelos predictivos: {e}")
                    return

            st.cache_data.clear()
            st.success("¡Líneas y pronósticos NFL actualizados con éxito (0 Créditos consumidos)!")
            st.rerun()

    with c_info:
        st.caption("• **Mercados:** Passing, Rushing, Receiving, Receptions, Anytime TD.")
        st.caption("• **Costo API:** $0.00 / 0 créditos consumidos.")
        st.caption("• **Filtros:** Candados de uso, sinergias y valor esperado (+EV).")
