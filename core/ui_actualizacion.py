"""Botón común; invalida caché antes de que la pestaña vuelva a leer sus datos."""
from pathlib import Path
import streamlit as st
from core.actualizacion_manual import run_update

ROOT=Path(__file__).resolve().parents[1]
LABELS={'mlb':'Actualizar resultados MLB','nfl_totales':'Actualizar resultados de totales NFL',
        'nfl_props':'Actualizar resultados de props NFL','liga_mx':'Actualizar resultados y calendario Liga MX',
        'bankroll':'Actualizar resultados y bankroll'}


def render_update_button(service, *, compact=False):
    from core.ui_movil import apply_mobile_layout
    apply_mobile_layout()
    key=f'actualizacion_manual_{service}'
    if st.button(LABELS[service],key=key,icon='🔄'):
        with (st.spinner('Actualizando resultados oficiales…') if compact else
              st.status('Actualizando resultados oficiales…',expanded=True)) as status:
            result=run_update(service,ROOT,on_step=None if compact else lambda label:st.write(label))
            if result['busy']:
                if compact:
                    st.toast('Ya hay una actualización de este servicio en curso.',icon='⚠️')
                else:
                    status.update(label='Ya hay una actualización de este servicio en curso.',state='error')
            else:
                st.session_state[key+'_result']=result
                st.cache_data.clear()
                st.session_state.pop('bankroll_predictions',None)
                failures=sum(not item['ok'] for item in result['steps'])
                label='Actualización completa.' if not failures else 'Actualización parcial: revisa el detalle.'
                if compact:
                    st.toast(label,icon='✅' if not failures else '⚠️')
                    if failures:
                        st.error(' · '.join(item['detalle'] for item in result['steps'] if not item['ok']))
                else:
                    status.update(label=label,state='complete' if not failures else 'error')
    if compact:
        return
    result=st.session_state.get(key+'_result')
    if result:
        st.caption(f"Última actualización manual: {result['at'][:19].replace('T',' ')} · CDMX")
        with st.expander('Detalle de la última actualización'):
            for item in result['steps']:
                (st.success if item['ok'] else st.warning)(item['paso']+': '+item['detalle'])
    if service=='liga_mx':st.caption('La primera actualización puede tardar unos minutos mientras ESPN verifica el historial de la temporada.')
    from core.ui_resumen import render_service_status
    render_service_status(service)
