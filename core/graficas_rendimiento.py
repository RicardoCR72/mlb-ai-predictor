"""Gráficas de simulación de 1 u, calculadas sobre la muestra filtrada."""
import numpy as np
import pandas as pd
import streamlit as st


def chart_data(frame, *, date_col, profit_col, result_col, group_cols=(), default_group='Todos los picks'):
    out = frame.copy()
    state = out[result_col].astype(str).str.upper().str.extract(r'\b(GANADA|PERDIDA|PUSH)\b', expand=False)
    units = pd.to_numeric(out[profit_col], errors='coerce')
    mask=state.notna() & np.isfinite(units)
    out = out[mask].copy()
    out['Unidades'] = units[mask].to_numpy()
    columns = ['Mercado', 'Muestra', 'Unidades', 'ROI (%)']
    if out.empty:
        return pd.DataFrame(columns=['Fecha', 'Mercado', 'Unidades acumuladas']), pd.DataFrame(columns=columns), 0
    out['Mercado'] = out[list(group_cols)].astype(str).agg(' · '.join, axis=1) if group_cols else default_group
    roi = out.groupby('Mercado', as_index=False).agg(Muestra=('Unidades', 'size'), Unidades=('Unidades', 'sum'))
    roi['ROI (%)'] = roi.Unidades / roi.Muestra * 100
    def local_day(value):
        stamp = pd.to_datetime(value, errors='coerce')
        if pd.isna(stamp): return pd.NaT
        if stamp.tzinfo is not None: stamp = stamp.tz_convert('America/Mexico_City')
        return pd.Timestamp(stamp.date())
    out['Fecha'] = out[date_col].map(local_day)
    missing_dates = int(out.Fecha.isna().sum())
    curve = out.dropna(subset=['Fecha']).groupby(['Mercado', 'Fecha'], as_index=False).Unidades.sum()
    curve = curve.sort_values(['Mercado', 'Fecha'], kind='stable')
    curve['Unidades acumuladas'] = curve.groupby('Mercado').Unidades.cumsum()
    return curve.drop(columns='Unidades'), roi.sort_values('ROI (%)', ascending=False), missing_dates


def render_performance_charts(frame, *, date_col, profit_col, result_col, group_cols=(), default_group='Todos los picks'):
    import altair as alt
    curve, roi, missing = chart_data(frame, date_col=date_col, profit_col=profit_col,
        result_col=result_col, group_cols=group_cols, default_group=default_group)
    if roi.empty:
        st.caption('Las gráficas aparecerán cuando haya picks liquidados con beneficio conocido.')
        return
    st.subheader('Evolución del rendimiento')
    st.caption(f'{int(roi.Muestra.sum()):,} picks con beneficio conocido · 1 u por pick · filtros activos.')
    if not curve.empty:
        chart = alt.Chart(curve).mark_line(point=True).encode(
            x=alt.X('Fecha:T', title='Fecha (CDMX)'), y=alt.Y('Unidades acumuladas:Q', title='Beneficio acumulado (u)'),
            color=alt.Color('Mercado:N', title='Mercado', legend=alt.Legend(orient='bottom', columns=1, labelLimit=240)),
            tooltip=[alt.Tooltip('Fecha:T', format='%d/%m/%Y'), 'Mercado:N',
                     alt.Tooltip('Unidades acumuladas:Q', format='+.2f')])
        st.altair_chart(chart, use_container_width=True)
    if missing: st.caption(f'{missing} picks sin fecha válida participan en el ROI, pero no en la curva temporal.')
    bars = alt.Chart(roi).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X('ROI (%):Q', title='ROI (%)'), y=alt.Y('Mercado:N', sort='-x', title=None, axis=alt.Axis(labelLimit=130)),
        color=alt.condition(alt.datum['ROI (%)'] >= 0, alt.value('#b7ff3c'), alt.value('#ff6b76')),
        tooltip=['Mercado:N', alt.Tooltip('Muestra:Q', title='Picks'),
                 alt.Tooltip('ROI (%):Q', format='+.2f'), alt.Tooltip('Unidades:Q', format='+.2f')])
    zero = alt.Chart(pd.DataFrame({'zero': [0]})).mark_rule(color='#8994a5').encode(x='zero:Q')
    st.altair_chart((bars + zero).properties(height=max(110, min(700, 40*len(roi)))), use_container_width=True)
    with st.expander('Ver muestra y ROI por mercado'):
        st.dataframe(roi, hide_index=True, use_container_width=True)
