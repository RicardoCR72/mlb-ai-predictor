"""Filtros compartidos aplicados antes de las métricas, con días de CDMX."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

PERIODS = ['Todo el historial','Hoy','Últimos 7 días','Este mes','Temporada','Rango personalizado']


def filter_frame(frame, date_col, *, period='Todo el historial', today=None, start=None, end=None,
                 season_col=None, season=None, probability_col=None, probability_scale=1, minimum=0,
                 market_col=None, market=None, result_col=None, result=None):
    result_frame = frame.copy()
    today = today or datetime.now(ZoneInfo('America/Mexico_City')).date()
    if period in ('Hoy','Últimos 7 días','Este mes','Rango personalizado'):
        if period == 'Hoy': start = end = today
        elif period == 'Últimos 7 días': start, end = today-timedelta(days=6), today
        elif period == 'Este mes': start, end = today.replace(day=1), today
        if start is None or end is None or start > end: return result_frame.iloc[0:0]
        def local_date(v):
            t = pd.to_datetime(v, errors='coerce')
            if pd.isna(t): return None
            if t.tzinfo is not None: t = t.tz_convert('America/Mexico_City')
            return t.date()
        dates = result_frame[date_col].map(local_date)
        result_frame = result_frame[dates.map(lambda d: d is not None and start <= d <= end)]
    if period == 'Temporada' and season_col and season is not None:
        result_frame = result_frame[result_frame[season_col].astype(str).eq(str(season))]
    if minimum > 0 and probability_col:
        p = pd.to_numeric(result_frame[probability_col], errors='coerce') * probability_scale
        result_frame = result_frame[p.ge(minimum) & p.le(100)]
    for col, value in ((market_col,market),(result_col,result)):
        if col and value is not None: result_frame = result_frame[result_frame[col].astype(str).eq(str(value))]
    return result_frame


def performance_filters(frame, date_col, key, *, season_col=None, probability_col=None,
                        probability_scale=1, market_col=None, result_col=None):
    with st.expander('Filtros de rendimiento', expanded=False):
        period = st.selectbox('Periodo', PERIODS, key=key+'_period')
        start = end = season = None
        if period == 'Temporada':
            if season_col and season_col in frame:
                seasons = sorted(frame[season_col].dropna().astype(str).unique(), reverse=True)
                if seasons: season = st.selectbox('Temporada', seasons, key=key+'_season')
            else:
                st.info('Esta fuente no tiene temporadas verificadas. Selecciona un rango de fechas.')
                return frame.iloc[0:0]
        if period == 'Rango personalizado':
            today = datetime.now(ZoneInfo('America/Mexico_City')).date()
            cols = st.columns(2)
            start = cols[0].date_input('Desde', today-timedelta(days=30), key=key+'_start')
            end = cols[1].date_input('Hasta', today, key=key+'_end')
            if start > end: st.warning('La fecha inicial debe ser anterior o igual a la final.')
        minimum = 0
        if probability_col:
            minimum = st.slider('Confianza mínima (%)',0,100,0,key=key+'_confidence')
        selected = {}
        for kind,col,label in [('market',market_col,'Mercado'),('result',result_col,'Resultado')]:
            if col and col in frame:
                values = sorted(frame[col].dropna().astype(str).unique())
                choice = st.selectbox(label,['Todos']+values,key=key+'_'+kind)
                selected[kind] = None if choice=='Todos' else choice
    filtered = filter_frame(frame,date_col,period=period,start=start,end=end,season_col=season_col,season=season,
        probability_col=probability_col,probability_scale=probability_scale,minimum=minimum,
        market_col=market_col,market=selected.get('market'),result_col=result_col,result=selected.get('result'))
    st.caption(f'Muestra filtrada: {len(filtered):,} registros. Fechas en CDMX; las métricas usan esta selección.')
    return filtered
