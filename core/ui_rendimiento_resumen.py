"""Vista resumida y límites de tarjetas; las métricas usan la muestra completa."""
import hashlib
import pandas as pd
import streamlit as st
from core.graficas_rendimiento import chart_data


def history_window(frame,key):
    signature=hashlib.sha256(frame.to_json(date_format='iso',default_handler=str).encode()).hexdigest()
    if st.session_state.get(key+'_signature')!=signature:
        st.session_state[key+'_signature']=signature
        st.session_state[key+'_limit']=10
    limit=st.session_state.get(key+'_limit',10)
    if len(frame)>limit and st.button('Ver 10 más',key=key+'_more'):
        limit+=10;st.session_state[key+'_limit']=limit
    st.caption(f'Mostrando {min(limit,len(frame))} de {len(frame)} picks. Las métricas y la descarga incluyen toda la muestra filtrada.')
    return frame.head(limit)


def render_performance_charts(frame, *, date_col, profit_col, result_col, group_cols=(), default_group='Todos los picks'):
    import altair as alt
    curve,_,missing=chart_data(frame,date_col=date_col,profit_col=profit_col,
        result_col=result_col,default_group='Total')
    _,roi,_=chart_data(frame,date_col=date_col,profit_col=profit_col,
        result_col=result_col,group_cols=group_cols,default_group=default_group)
    if roi.empty:
        st.caption('La curva aparecerá cuando haya picks liquidados con beneficio conocido.');return
    st.subheader('Unidades acumuladas')
    if not curve.empty:
        st.altair_chart(alt.Chart(curve).mark_line(color='#b7ff3c').encode(
            x=alt.X('Fecha:T',title='Fecha (CDMX)'),
            y=alt.Y('Unidades acumuladas:Q',title='Unidades (u)'),
            tooltip=[alt.Tooltip('Fecha:T',format='%d/%m/%Y'),alt.Tooltip('Unidades acumuladas:Q',format='+.2f')]),width='stretch')
    if missing:st.caption(f'{missing} picks sin fecha válida cuentan en el ROI, pero no en la curva.')
    with st.expander('Comparar mercados'):
        bars=alt.Chart(roi).mark_bar(cornerRadiusEnd=4).encode(
            x=alt.X('ROI (%):Q'),y=alt.Y('Mercado:N',sort='-x',title=None),
            color=alt.condition(alt.datum['ROI (%)']>=0,alt.value('#b7ff3c'),alt.value('#ff6b76')),
            tooltip=['Mercado:N','Muestra:Q',alt.Tooltip('ROI (%):Q',format='+.2f')])
        st.altair_chart(bars.properties(height=max(110,min(700,40*len(roi)))),width='stretch')
        st.dataframe(roi,hide_index=True,width='stretch')
