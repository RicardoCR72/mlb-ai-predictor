"""Estados y ordenamiento comunes, sin efectos sobre métricas ni registros."""
from html import escape
import pandas as pd
import streamlit as st


def state_message(message, *, kind='empty'):
    labels={'empty':'Sin datos para mostrar','filters':'Sin coincidencias',
            'offline':'Fuente no disponible','blocked':'Datos pendientes de verificación'}
    title=labels.get(kind,labels['empty'])
    st.markdown('<div class="oracle-state" role="status" style="padding:1rem;border:1px solid #334054;'
                'border-radius:12px;background:#0f151e;color:#a8b4c5;overflow-wrap:anywhere">'
                f'<strong style="color:#eef3f8">{escape(title)}</strong><br>{escape(str(message))}</div>',
                unsafe_allow_html=True)


def roi_sample(count):
    st.caption(f'Muestra del ROI: {int(count):,} picks de 1 u. Compara también la cantidad de picks, no solo el porcentaje.')


def ordered(frame, column, ascending):
    result=frame.copy()
    if column is None or result.empty:return result
    values=result[column]
    if any(word in column.lower() for word in ('fecha','date','day','utc','inicio')):
        values=pd.to_datetime(values,errors='coerce',utc=True)
    else:values=pd.to_numeric(values,errors='coerce')
    return result.assign(_oracle_order=values).sort_values('_oracle_order',ascending=ascending,
        na_position='last',kind='stable').drop(columns='_oracle_order')


def render_order(frame, key, *, date_col=None, confidence_col=None, ev_col=None, profit_col=None, upcoming=False):
    options={}
    if date_col and date_col in frame:
        options['Fecha más próxima' if upcoming else 'Fecha más reciente']=(date_col,upcoming)
        options['Fecha más lejana' if upcoming else 'Fecha más antigua']=(date_col,not upcoming)
    for label,col in [('Mayor confianza',confidence_col),('Mayor EV',ev_col),('Mayor beneficio',profit_col)]:
        if col and col in frame:options[label]=(col,False)
    if not options:return frame
    widget=key+'_order'
    if st.session_state.get(widget) not in options:st.session_state.pop(widget,None)
    choice=st.selectbox('Ordenar por',list(options),key=widget)
    return ordered(frame,*options[choice])
