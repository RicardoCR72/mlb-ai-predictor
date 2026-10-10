"""Botón explícito de cuotas NFL; separado de la actualización gratuita de resultados."""
from pathlib import Path
import streamlit as st
from core.nfl_creditos import plan_hoy, run_predictions
from nfl.jornada import ahora_mexico


@st.cache_data(ttl=60)
def consultar(day):
    return plan_hoy()


def render_prediction_button():
    key = 'nfl_predicciones_creditos'
    try:
        plan = consultar(str(ahora_mexico().date()))
    except Exception as exc:
        help_text = str(exc) if type(exc) is RuntimeError else 'No se pudo consultar el calendario y saldo.'
        st.button('Actualizar predicciones NFL de hoy (usa créditos)',key=key,
                  disabled=True,help=help_text)
        return
    disabled = not plan['eventos'] or plan['restantes'] is None or plan['restantes'] < plan['reserva']+6
    help_text = ('Solo partidos de hoy en México sin iniciar. DraftKings: hasta 6 créditos por partido. '
                 f"Saldo: {plan['restantes'] if plan['restantes'] is not None else 'No verificado'}. "
                 'Reserva: 120 créditos. Cada pulsación puede consumir créditos de nuevo.')
    if disabled:
        help_text += ' Sin partidos elegibles o sin saldo suficiente por encima de la reserva.'
    if not st.button(f"Actualizar predicciones NFL de hoy (hasta {plan['max_creditos']} créditos)",
                     key=key,disabled=disabled,help=help_text):
        return
    with st.spinner('Actualizando predicciones NFL de hoy…'):
        result = run_predictions(Path(__file__).resolve().parents[1],plan)
    st.session_state[key+'_result'] = result
    st.cache_data.clear()
    st.session_state.pop('bankroll_predictions',None)
    message = result['detalle']
    report = result.get('reporte')
    if report:
        cost = report['creditos'] if report['creditos'] is not None else 'No confirmado por la API'
        message += f" · Consumo: {cost} · Restantes: {report['restantes']}"
    st.toast(message)
    st.caption(message)
    if not result['ok']:
        st.error(message)
