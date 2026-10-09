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
    with st.expander('Actualizar predicciones de hoy · usa créditos', expanded=True):
        st.caption('Solo partidos de hoy en México que aún no comienzan: TNF/MNF del día y juegos del domingo. '
                   'DraftKings, hasta 6 créditos por partido para los seis mercados de props. '
                   'Totales usa el calendario NFL sin costo adicional. Reserva mensual: 120 créditos.')
        try:
            plan = consultar(str(ahora_mexico().date()))
        except Exception as exc:
            st.info(str(exc) if type(exc) is RuntimeError else 'No se pudo consultar el calendario y saldo.')
            return
        st.caption(f"Partidos sin iniciar: {len(plan['eventos'])} · Consumo máximo: {plan['max_creditos']} · "
                   f"Créditos restantes: {plan['restantes'] if plan['restantes'] is not None else 'No verificados'}")
        for event in plan['eventos']:
            st.caption(event['away_team']+' @ '+event['home_team'])
        disabled = not plan['eventos'] or plan['restantes'] is None or plan['restantes'] < plan['reserva']+6
        if st.button(f"Actualizar predicciones NFL de hoy (hasta {plan['max_creditos']} créditos)",
                     key=key, icon='🏈', disabled=disabled):
            with st.status('Actualizando predicciones NFL de hoy…', expanded=True) as status:
                result = run_predictions(Path(__file__).resolve().parents[1], plan, on_step=st.write)
                st.session_state[key+'_result'] = result
                st.cache_data.clear()
                st.session_state.pop('bankroll_predictions', None)
                status.update(label=result['detalle'], state='complete' if result['ok'] else 'error')
        result = st.session_state.get(key+'_result')
        if result:
            (st.success if result['ok'] else st.warning)(result['detalle'])
            report = result.get('reporte')
            if report:
                cost = report['creditos'] if report['creditos'] is not None else 'No confirmado por la API'
                st.caption(f"Fecha México: {report['fecha']} · Consultas pagadas: {report['solicitados']} · "
                    f"Consumo: {cost} · Restantes: {report['restantes']} · Líneas guardadas: {report['insertadas']}")
        if disabled:
            st.caption('Sin partidos elegibles o sin saldo suficiente por encima de la reserva; no se consultarán cuotas.')
        st.caption('Cada nueva pulsación puede volver a consumir créditos para refrescar las líneas del día. '
                   'El botón de resultados de arriba sigue siendo gratuito.')
