"""Actualización de resultados con respuesta breve junto al control."""
from pathlib import Path
import re
import streamlit as st
from core.actualizacion_manual import run_update

ROOT=Path(__file__).resolve().parents[1]
LABELS={'mlb':'Actualizar resultados MLB','nfl_totales':'Actualizar resultados de totales NFL',
        'nfl_props':'Actualizar resultados de props NFL','liga_mx':'Actualizar resultados y calendario Liga MX',
        'bankroll':'Actualizar resultados y bankroll'}


def update_message(result):
    parts=[]; known=[]
    names={'Marcadores MLB':'partidos MLB actualizados','Resultados MLB Totales V2':'resultados de totales MLB revisados',
           'Resultados NFL totales':'resultados de totales NFL evaluados','Resultados NFL props':'resultados de props NFL evaluados',
           'Liquidación de bankroll':'apuestas liquidadas'}
    failures=[item for item in result['steps'] if not item['ok']]
    for item in result['steps']:
        if not item['ok']: continue
        match=re.match(r'\s*(\d+)\b',str(item['detalle']))
        no_pending=str(item['detalle']).startswith('Sin partidos MLB pendientes')
        if item['paso'] in names and (match or no_pending):
            n=int(match.group(1)) if match else 0
            known.append(n)
            if n:parts.append(f"{n} {names[item['paso']]}")
        else:
            known.append(None)
            parts.append('Calendario e historial revisados' if 'Liga MX' in item['paso'] else item['detalle'])
    if failures: return 'Actualización parcial'+(' · '+' · '.join(parts) if parts else '')+'.'
    if known and all(n==0 for n in known):return 'Sin cambios: no hay nuevos resultados para guardar.'
    return ' · '.join(parts)+'.' if parts else 'Consulta completada.'


def render_update_button(service, *, compact=True):
    from core.ui_movil import apply_mobile_layout
    apply_mobile_layout()
    key=f'actualizacion_manual_{service}'
    help_text='Consulta resultados oficiales y revisa tus apuestas pendientes. No consume créditos de cuotas.'
    if service=='liga_mx':help_text+=' La verificación del historial puede tardar unos minutos.'
    if not st.button(LABELS[service],key=key,help=help_text):return
    with st.spinner('Actualizando resultados oficiales…'):
        result=run_update(service,ROOT)
    if result['busy']:
        st.toast('Ya hay una actualización de este servicio en curso.')
        return
    st.session_state[key+'_result']=result
    st.cache_data.clear()
    st.session_state.pop('bankroll_predictions',None)
    label=update_message(result)
    st.toast(label)
    st.caption(label)
    failures=[item for item in result['steps'] if not item['ok']]
    if failures:
        st.warning(' · '.join(item['paso']+': '+item['detalle'] for item in failures))
