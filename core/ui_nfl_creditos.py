"""Botón explícito de cuotas NFL; separado de la actualización gratuita de resultados."""
import streamlit as st
from core.nfl_creditos import plan_hoy
from nfl.jornada import ahora_mexico, inicio_evento, MEXICO


@st.cache_data(ttl=60)
def consultar(day, todos=False):
    return plan_hoy(todos=todos)


def render_prediction_button():
    from core.ui_trabajos import action_button
    todos = st.checkbox('Todos los partidos de hoy', value=False, key='nfl_todos_hoy',
                        help='Incluye los juegos de más tarde. Sus líneas pueden cambiar antes del inicio.')
    st.caption('Por defecto: solo partidos que comiencen en las próximas 2 horas.')
    try:plan=consultar(str(ahora_mexico().date()), todos)
    except Exception:
        st.button('Actualizar predicciones NFL de hoy (usa créditos)',disabled=True,key='nfl_predicciones_creditos')
        st.caption('No se pudo comprobar el calendario y saldo.');return
    if not plan['eventos']:
        st.caption('No hay partidos de hoy sin iniciar.' if todos else 'No hay partidos que comiencen en las próximas 2 horas.')
    for event in plan['eventos']:
        start = inicio_evento(event)
        st.caption(f"{event.get('away_team', '')} vs {event.get('home_team', '')} · {start.astimezone(MEXICO):%H:%M} CDMX")
    disabled=not plan['eventos'] or plan['restantes'] is None or plan['restantes']<plan['reserva']+6
    action_button('nfl_predictions',f"Actualizar predicciones NFL {'de hoy' if todos else 'próximas'} (hasta {plan['max_creditos']} créditos)",
        key='nfl_predicciones_creditos',payload=plan,disabled=disabled,
        help=f"Solo los juegos indicados, sin iniciar; se omiten capturas de las últimas 2 h y solicitudes de cobro incierto. Saldo: {plan['restantes']} · Reserva: 120. Cada nueva solicitud puede consumir créditos.")
