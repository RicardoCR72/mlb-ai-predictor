"""Estado de la última solicitud de esta sesión; no sustituye el estado del workflow."""
from datetime import datetime,timezone
from html import escape
from zoneinfo import ZoneInfo
import streamlit as st


def save_status(key,phase,message):
    st.session_state[key+'_status']=dict(phase=phase,message=message,at=datetime.now(timezone.utc).isoformat())


def render_status(key,slot=None,*,previous=False):
    record=st.session_state.get(key+'_status')
    if not record:return
    if previous and record['phase']=='running':
        record=dict(record,phase='unknown',message='La pantalla se recargó durante la solicitud. El resultado no está confirmado; revisa antes de reintentar.')
        st.session_state[key+'_status']=record
    labels={'running':'Actualizando','success':'Completado','partial':'Completado con pendientes',
            'error':'Falló','busy':'Servicio ocupado al solicitar','unknown':'Estado por confirmar'}
    stamp=datetime.fromisoformat(record['at']).astimezone(ZoneInfo('America/Mexico_City')).strftime('%d/%m · %H:%M:%S CDMX')
    color={'success':'#b7ff3c','error':'#ff6b76','partial':'#f6c761'}.get(record['phase'],'#a8b4c5')
    html=(f'<div class="oracle-update-state" role="status" aria-live="polite" style="border-left:3px solid {color};padding:.4rem .65rem;margin:.3rem 0;color:#a8b4c5;font-size:.8rem">'
          f'<strong style="color:{color}">{escape(labels.get(record["phase"],record["phase"]))}</strong> · {escape(stamp)} · solicitud de esta sesión<br>{escape(record["message"])}</div>')
    (slot or st).markdown(html,unsafe_allow_html=True)
