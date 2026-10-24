"""Comparación de ventanas completas de igual duración y sin solapamiento."""
from datetime import timedelta
import pandas as pd
from core.comparador import comparison
from core.ui_rendimiento_diseno import filter_frame


def pool(frame,settings):
    return filter_frame(frame,'fecha',period='Temporada' if settings.get('period')=='Temporada' else 'Todo el historial',
        season_col='Temporada',season=settings.get('season'),probability_col='probabilidad',probability_scale=100,minimum=settings.get('confidence',0),
        market_col='mercado',market=None if settings.get('market')=='Todos' else settings.get('market'),
        result_col='resultado',result=None if settings.get('result')=='Todos' else settings.get('result'),
        provenance_col='procedencia',provenance=None if settings.get('provenance')=='Todos' else settings.get('provenance'))


def compare_periods(frame,end,days):
    end=pd.Timestamp(end).date()
    if days not in (7,14,28):raise ValueError('La ventana debe ser de 7, 14 o 28 días.')
    start=end-timedelta(days=days-1);previous_end=start-timedelta(days=1);previous_start=start-timedelta(days=days)
    keys=['Deporte','Mercado','Modelo','Procedencia']
    parts=[]
    for name,a,b in [('actual',start,end),('anterior',previous_start,previous_end)]:
        f=filter_frame(frame,'fecha',period='Rango personalizado',start=a,end=b)
        stats=comparison(f)
        columns=keys+['Picks evaluados','Picks con beneficio conocido','Acierto (%)','Unidades','ROI (%)']
        if stats.empty:stats=pd.DataFrame(columns=columns)
        parts.append(stats[columns].rename(columns={c:f'{c} · {name}' for c in columns if c not in keys}))
    result=parts[0].merge(parts[1],on=keys,how='outer',validate='one_to_one')
    for name in ('actual','anterior'):
        for c in ('Picks evaluados','Picks con beneficio conocido'):
            result[f'{c} · {name}']=result[f'{c} · {name}'].fillna(0).astype(int)
    result['Cambio ROI (pp)']=result['ROI (%) · actual']-result['ROI (%) · anterior']
    return result,dict(start=start,end=end,previous_start=previous_start,previous_end=previous_end)


def render(frame):
    import altair as alt
    import streamlit as st
    from datetime import datetime
    from zoneinfo import ZoneInfo
    with st.expander('Comparar periodos'):
        days=st.radio('Duración de cada periodo',[7,14,28],horizontal=True,key='period_compare_days')
        today=datetime.now(ZoneInfo('America/Mexico_City')).date()
        end=st.date_input('Último día del periodo actual',value=today-timedelta(days=1),max_value=today,key='period_compare_end')
        settings={k:st.session_state.get('center_'+k) for k in ('period','season','confidence','market','result','provenance')}
        settings['confidence']=settings.get('confidence') or 0
        table,limits=compare_periods(pool(frame,settings),end,days)
        st.caption(f"Actual: {limits['start']:%d/%m/%Y}–{limits['end']:%d/%m/%Y} · Anterior: {limits['previous_start']:%d/%m/%Y}–{limits['previous_end']:%d/%m/%Y}")
        st.caption('Mantiene los filtros de deporte, modelo, mercado, confianza, resultado y procedencia; usa sus propias fechas. El cambio se expresa en puntos porcentuales de ROI.')
        if table.empty:st.caption('No hay resultados en estos periodos.');return
        visible=table.copy()
        if 'modelo_visible' in frame:
            names={(str(r.deporte),str(r.modelo)):str(r.modelo_visible) for r in frame.itertuples()}
            visible['Modelo']=[names.get((str(r.Deporte),str(r.Modelo)),str(r.Modelo)) for r in visible.itertuples()]
        valid=visible[visible['Cambio ROI (pp)'].notna()].copy()
        if not valid.empty:
            valid['Grupo']=valid[['Deporte','Mercado','Modelo','Procedencia']].astype(str).agg(' · '.join,axis=1)
            bars=alt.Chart(valid).mark_bar().encode(x=alt.X('Cambio ROI (pp):Q',title='Cambio de ROI (puntos porcentuales)'),
                y=alt.Y('Grupo:N',title=None,sort='-x',axis=alt.Axis(labelLimit=210)),
                color=alt.condition(alt.datum['Cambio ROI (pp)']>=0,alt.value('#b7ff3c'),alt.value('#ff6b76')),
                tooltip=['Grupo:N',alt.Tooltip('ROI (%) · actual:Q',format='+.1f'),alt.Tooltip('ROI (%) · anterior:Q',format='+.1f'),
                         'Picks con beneficio conocido · actual:Q','Picks con beneficio conocido · anterior:Q'])
            st.altair_chart(bars.properties(height=max(160,35*len(valid))),width='stretch',key='period_change_chart')
        st.caption('Verde: el ROI aumentó · Rojo: disminuyó. Un cambio positivo puede seguir correspondiendo a un ROI negativo. Sin beneficio conocido en ambos periodos no se calcula el cambio.')
        comp_period_cfg = {
            'Deporte': st.column_config.TextColumn('Deporte', width='small'),
            'Mercado': st.column_config.TextColumn('Mercado', width='medium'),
            'Modelo': st.column_config.TextColumn('Modelo', width='medium'),
            'Procedencia': st.column_config.TextColumn('Procedencia', width='medium'),
            'Picks evaluados · actual': st.column_config.NumberColumn('Picks Act.', format='%d'),
            'Acierto (%) · actual': st.column_config.ProgressColumn('Acierto Act.', format='%.1f%%', min_value=0, max_value=100),
            'Unidades · actual': st.column_config.NumberColumn('Unidades Act.', format='%+.2f u'),
            'ROI (%) · actual': st.column_config.NumberColumn('ROI Act.', format='%+.1f%%'),
            'Picks evaluados · anterior': st.column_config.NumberColumn('Picks Ant.', format='%d'),
            'Acierto (%) · anterior': st.column_config.ProgressColumn('Acierto Ant.', format='%.1f%%', min_value=0, max_value=100),
            'Unidades · anterior': st.column_config.NumberColumn('Unidades Ant.', format='%+.2f u'),
            'ROI (%) · anterior': st.column_config.NumberColumn('ROI Ant.', format='%+.1f%%'),
            'Cambio ROI (pp)': st.column_config.NumberColumn('Cambio ROI (pp)', format='%+.1f pp', help='Variación en puntos porcentuales respecto al periodo anterior'),
        }
        st.dataframe(visible, hide_index=True, width='stretch', column_config=comp_period_cfg)
        st.download_button('Descargar comparación de periodos',table.to_csv(index=False),'comparacion_periodos.csv','text/csv')
