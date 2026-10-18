"""Botón explícito de cuotas NFL; separado de la actualización gratuita de resultados."""
from pathlib import Path
import streamlit as st
from core.nfl_creditos import plan_hoy, run_predictions
from nfl.jornada import ahora_mexico


@st.cache_data(ttl=60)
def consultar(day):
    return plan_hoy()


def render_prediction_button():
    from core.permisos import session_token
    from core.ui_trabajos import action_button
    if session_token() is None:
        action_button('nfl_predictions','Actualizar predicciones NFL de hoy (usa créditos)',key='nfl_predicciones_creditos')
        return
    try:plan=consultar(str(ahora_mexico().date()))
    except Exception:
        st.button('Actualizar predicciones NFL de hoy (usa créditos)',disabled=True,key='nfl_predicciones_creditos')
        st.caption('No se pudo comprobar el calendario y saldo.');return
    disabled=not plan['eventos'] or plan['restantes'] is None or plan['restantes']<plan['reserva']+6
    action_button('nfl_predictions',f"Actualizar predicciones NFL de hoy (hasta {plan['max_creditos']} créditos)",
        key='nfl_predicciones_creditos',payload=plan,disabled=disabled,
        help=f"Solo juegos de hoy sin iniciar. Saldo: {plan['restantes']} · Reserva: 120. Cada nueva solicitud puede consumir créditos.")
