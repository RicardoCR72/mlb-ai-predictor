"""Gráficas de resultados y retorno con muestras explícitas y cuotas guardadas."""
import numpy as np
import pandas as pd
import streamlit as st
from core.graficas_rendimiento import chart_data

COLORS=['#b7ff3c','#ff6b76','#f6c761']


def visual_data(frame,*,date_col,profit_col,result_col,group_cols=(),default_group='Todos los picks'):
    state=frame[result_col].astype(str).str.upper().str.extract(r'\b(GANADA|PERDIDA|PUSH)\b',expand=False)
    distribution=pd.DataFrame({'Resultado':['Ganadas','Perdidas','Push'],
        'Picks':[int(state.eq(s).sum()) for s in ['GANADA','PERDIDA','PUSH']]})
    total=int(distribution.Picks.sum())
    distribution['Porcentaje']=distribution.Picks/total if total else 0.0
    curve,_,missing=chart_data(frame,date_col=date_col,profit_col=profit_col,result_col=result_col,default_group='Total')
    _,roi,_=chart_data(frame,date_col=date_col,profit_col=profit_col,result_col=result_col,
        group_cols=group_cols,default_group=default_group)
    return dict(distribution=distribution,total=total,curve=curve,roi=roi,missing=missing)


def render_visual_performance(frame,*,date_col,profit_col,result_col,group_cols=(),default_group='Todos los picks',key='visual_perf'):
    import altair as alt
    data=visual_data(frame,date_col=date_col,profit_col=profit_col,result_col=result_col,
        group_cols=group_cols,default_group=default_group)
    with st.container(key=key+'_charts'):
        left,right=st.columns([1,1.35],gap='large')
        with left:
            st.subheader('Cómo terminaron los picks')
            if not data['total']:st.caption('Todavía no hay resultados liquidados para esta selección.')
            else:
                pie=alt.Chart(data['distribution']).mark_arc(innerRadius=65,outerRadius=105).encode(
                    theta=alt.Theta('Picks:Q',stack=True),
                    color=alt.Color('Resultado:N',scale=alt.Scale(domain=['Ganadas','Perdidas','Push'],range=COLORS),
                                    legend=alt.Legend(orient='bottom',title=None)),
                    tooltip=['Resultado:N','Picks:Q',alt.Tooltip('Porcentaje:Q',format='.1%')])
                center=alt.Chart(pd.DataFrame({'texto':[f"{data['total']} picks"]})).mark_text(fontSize=20,color='#eef3f8').encode(text='texto:N')
                st.altair_chart((pie+center).properties(height=265),width='stretch',key=key+'_outcomes')
                counts=data['distribution'].set_index('Resultado').Picks
                st.caption(f"✅ {counts['Ganadas']} ganadas · ❌ {counts['Perdidas']} perdidas · ↔ {counts['Push']} push")
                st.caption('El pastel incluye todos los picks liquidados. Push significa devolución y no cuenta para el porcentaje de acierto.')
        with right:
            st.subheader('ROI por mercado')
            roi=data['roi']
            if roi.empty:st.caption('El ROI aparecerá cuando haya resultados con beneficio conocido.')
            else:
                base=alt.Chart(roi).encode(x=alt.X('ROI (%):Q',title='Retorno sobre lo simulado (%)',scale=alt.Scale(zero=True)),
                    y=alt.Y('Mercado:N',sort='-x',title=None,axis=alt.Axis(labelLimit=210)),
                    tooltip=['Mercado:N',alt.Tooltip('Muestra:Q',title='Picks con beneficio conocido'),
                             alt.Tooltip('ROI (%):Q',format='+.1f'),alt.Tooltip('Unidades:Q',format='+.2f')])
                bars=base.mark_bar(cornerRadiusEnd=4).encode(color=alt.condition(alt.datum['ROI (%)']>=0,alt.value(COLORS[0]),alt.value(COLORS[1])))
                zero=alt.Chart(pd.DataFrame({'cero':[0]})).mark_rule(color='#8994a5').encode(x='cero:Q')
                st.altair_chart((bars+zero).properties(height=max(200,38*len(roi))),width='stretch',key=key+'_roi')
                st.caption('Verde: retorno positivo · Rojo: retorno negativo · La línea marca 0%. Cada barra separa los grupos seleccionados; toca o pasa el cursor para ver sus picks.')
                st.caption('Ejemplo: ROI +10% significa +10 u por cada 100 u simuladas. Un ROI alto con pocos picks puede ser inestable.')
        st.subheader('Unidades acumuladas')
        st.caption('Muestra cómo cambia el beneficio simulado con el tiempo. Por encima de cero hay ganancia; por debajo, pérdida.')
        if not data['curve'].empty:
            curve=alt.Chart(data['curve']).encode(x=alt.X('Fecha:T',title='Fecha (CDMX)'),
                y=alt.Y('Unidades acumuladas:Q',title='Beneficio acumulado (u)',scale=alt.Scale(zero=True)),
                tooltip=[alt.Tooltip('Fecha:T',format='%d/%m/%Y'),alt.Tooltip('Unidades acumuladas:Q',format='+.2f')])
            zero=alt.Chart(pd.DataFrame({'cero':[0]})).mark_rule(color='#8994a5',strokeDash=[4,4]).encode(y='cero:Q')
            st.altair_chart((curve.mark_area(color=COLORS[0],opacity=.10)+curve.mark_line(color=COLORS[0],point=True)+zero).properties(height=270),
                width='stretch',key=key+'_curve')
        else:st.caption('La curva requiere resultados con fecha y beneficio conocidos.')
        known=int(data['roi'].Muestra.sum()) if not data['roi'].empty else 0
        st.caption(f"{data['total']} picks liquidados en el pastel · {known} con beneficio conocido en ROI y unidades · simulación de 1 u por pick.")
        if data['missing']:st.caption(f"{data['missing']} picks sin fecha válida cuentan en el ROI, pero no aparecen en la curva.")
        with st.expander('Ver cifras de las gráficas'):
            st.dataframe(data['distribution'],hide_index=True,width='stretch',column_config={'Porcentaje':st.column_config.NumberColumn(format='percent')})
            st.dataframe(data['roi'],hide_index=True,width='stretch')
            st.caption('Las gráficas usan la misma muestra filtrada. Las probabilidades del modelo no son garantías de acierto.')


def weekly_roi(week):
    if week.empty:return pd.DataFrame(columns=['Semana','Picks con beneficio','Unidades','ROI (%)'])
    # Ponderar por apuestas conocidas, no promediar porcentajes de mercados de distinto tamaño.
    out=week[week.Semana.notna()].groupby('Semana',as_index=False).agg(
        **{'Picks con beneficio':('Muestra_ROI','sum'),'Unidades':('Unidades',lambda s:s.sum(min_count=1))})
    out['ROI (%)']=100*out.Unidades/out['Picks con beneficio'].replace(0,np.nan)
    return out


def render_weekly_roi(week,key='weekly_visual'):
    import altair as alt
    table=weekly_roi(week)
    table=table[np.isfinite(pd.to_numeric(table['ROI (%)'],errors='coerce'))]
    st.subheader('Retorno por semana')
    st.caption('Cada barra reúne los picks de esa semana dentro de los filtros actuales. NFL usa su semana oficial; los demás deportes, la semana ISO.')
    if table.empty:st.caption('Faltan resultados con beneficio conocido para comparar semanas.');return
    bars=alt.Chart(table).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X('Semana:N',title=None,sort='ascending',axis=alt.Axis(labelAngle=-35,labelLimit=150)),
        y=alt.Y('ROI (%):Q',title='ROI semanal (%)',scale=alt.Scale(zero=True)),
        color=alt.condition(alt.datum['ROI (%)']>=0,alt.value(COLORS[0]),alt.value(COLORS[1])),
        tooltip=['Semana:N','Picks con beneficio:Q',alt.Tooltip('Unidades:Q',format='+.2f'),alt.Tooltip('ROI (%):Q',format='+.1f')])
    zero=alt.Chart(pd.DataFrame({'cero':[0]})).mark_rule(color='#8994a5').encode(y='cero:Q')
    st.altair_chart((bars+zero).properties(height=245),width='stretch',key=key)
