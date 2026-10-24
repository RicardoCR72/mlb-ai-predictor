"""Controles de actualización y seguimiento del estado real persistido."""
import streamlit as st
import pandas as pd
from html import escape
from core.trabajos import submit,latest


def invalidate_readers():
    # Invalidar solo lecturas: conservar modelos y cachés de otras operaciones.
    from core.ui_historial_publicado import load_history
    from core.ui_resumen import load_snapshot
    from core.ui_comparador import load_comparison
    from core.ui_confianza import load
    from nfl.repositorio import cargar_props_mysql,cargar_predicciones_mysql
    for reader in (load_history,load_snapshot,load_comparison,load,cargar_props_mysql,cargar_predicciones_mysql):
        clear=getattr(reader,'clear',None)
        if clear:clear()


def render_job(service):
    try:initial=latest(service)
    except Exception:
        st.caption('No se pudo consultar el estado de las actualizaciones.');return
    active=initial is not None and initial['estado'] in ('en_cola','ejecutando')
    @st.fragment(run_every='4s' if active else None)
    def poll(service):
        try:job=latest(service) if active else initial
        except Exception:
            st.caption('No se pudo consultar el estado de las actualizaciones.');return
        if not job:return
        stamp=job.get('terminado_utc') or job.get('iniciado_utc') or job['creado_utc']
        stamp=pd.Timestamp(stamp).tz_localize('UTC').tz_convert('America/Mexico_City').strftime('%d/%m · %H:%M CDMX')
        state=job['estado']
        st.markdown(f'<div class="oracle-job-status" role="status" aria-live="polite"><strong>{escape(state.replace("_"," "))}</strong> · {escape(stamp)} · {escape(job["id"][:8])}</div>',unsafe_allow_html=True)
        st.caption(f'Actualización manual {job["id"][:8]} · {state.replace("_"," ")} · {stamp}')
        if state=='interrumpida':st.caption('El proceso dejó de responder. Comprueba resultados y consumo antes de solicitar otra ejecución.')
        elif state in ('en_cola','ejecutando'):st.caption(job.get('paso') or 'Esperando ejecución.')
        else:
            result=job.get('resultado') or {}
            if result.get('detalle'):st.caption(result['detalle'])
            if 'steps' in result:
                from core.ui_actualizacion import update_message
                st.caption(update_message(result))
            report=result.get('reporte')
            if report:st.caption(f'Créditos: {report.get("creditos") if report.get("creditos") is not None else "por confirmar"} · Restantes: {report.get("restantes")}')
            revision=(job['id'],state)
            if st.session_state.get('_job_seen_'+service)!=revision:
                st.session_state['_job_seen_'+service]=revision
                invalidate_readers()
                st.rerun(scope="app")

    poll(service)


def action_button(service,label,*,key,help=None,payload=None,disabled=False,details_on_click=False,kind=None):
    btn_type = kind if kind else ('secondary' if service.startswith('mlb') else ('primary' if service.endswith('predictions') else 'secondary'))
    clicked=st.button(label,key=key,help=help,disabled=disabled,type=btn_type,use_container_width=True)
    visibility_key = '_show_update_details_' + service
    if clicked:
        if details_on_click:
            st.session_state[visibility_key] = True
        try:
            submit(service,payload=payload)
            st.toast('Solicitud registrada. Puedes seguir consultando la página.')
        except Exception:st.caption('No se pudo registrar la solicitud. Revisa la conexión.')
    if not details_on_click or st.session_state.get(visibility_key, False):
        render_job(service)
        if details_on_click:
            st.button('Ocultar detalles', key=key+'_hide', on_click=lambda: st.session_state.update({visibility_key: False}))


def render_generate_mlb():
    action_button('mlb_predictions','Generar predicciones MLB',key='mlb_generate',
        help='Usa las cuotas ya registradas. No consulta The Odds API ni consume créditos de cuotas.',
        details_on_click=True)
