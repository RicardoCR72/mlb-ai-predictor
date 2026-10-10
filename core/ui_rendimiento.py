"""Filtros compartidos aplicados antes de las métricas, con días de CDMX."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from core.ui_favoritos import render_favorites
from core.ui_controles import state_message

PERIODS = ['Todo el historial','Hoy','Últimos 7 días','Este mes','Temporada','Rango personalizado']


def filter_frame(frame, date_col, *, period='Todo el historial', today=None, start=None, end=None,
                 season_col=None, season=None, probability_col=None, probability_scale=1, minimum=0,
                 market_col=None, market=None, result_col=None, result=None, week_col=None, week=None, provenance_col=None, provenance=None):
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
    for col, value in ((market_col,market),(result_col,result),(week_col,week),(provenance_col,provenance)):
        if col and value is not None: result_frame = result_frame[result_frame[col].astype(str).eq(str(value))]
    return result_frame


def performance_filters(frame, date_col, key, *, season_col=None, probability_col=None,
                        probability_scale=1, market_col=None, result_col=None, week_col=None, provenance_col=None, expanded=False, extra_keys=None):
    render_favorites(key,extra_keys)
    week = None
    with st.expander('Filtros de rendimiento', expanded=expanded):
        period = safe_select('Periodo', PERIODS, key=key+'_period')
        start = end = season = None
        if period == 'Temporada':
            if season_col and season_col in frame:
                seasons = sorted(frame[season_col].dropna().astype(str).unique(), reverse=True)
                if seasons: season = safe_select('Temporada', seasons, key=key+'_season')
            else:
                state_message('Esta fuente no tiene temporadas verificadas. Selecciona un rango de fechas.',kind='filters')
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
        if week_col and week_col in frame:
            weeks = sorted(frame[week_col].dropna().astype(str).unique(),
                           key=lambda value: float(value), reverse=True)
            choice = safe_select('Semana', ['Todas']+weeks, key=key+'_week',
                format_func=lambda value: value if value=='Todas' else f'Semana {float(value):g}')
            week = None if choice=='Todas' else choice
        selected = {}
        for kind,col,label in [('market',market_col,'Mercado'),('result',result_col,'Resultado'),('provenance',provenance_col,'Procedencia')]:
            if col and col in frame:
                values = sorted(frame[col].dropna().astype(str).unique())
                choice = safe_select(label,['Todos']+values,key=key+'_'+kind,
                    **({'help':'Indica si el registro se verificó antes del partido, conserva una hora no comprobable o fue reconstruido.'} if kind=='provenance' else {}))
                selected[kind] = None if choice=='Todos' else choice
    filtered = filter_frame(frame,date_col,period=period,start=start,end=end,season_col=season_col,season=season,
        probability_col=probability_col,probability_scale=probability_scale,minimum=minimum,
        market_col=market_col,market=selected.get('market'),result_col=result_col,result=selected.get('result'),
        week_col=week_col,week=week,provenance_col=provenance_col,provenance=selected.get('provenance'))
    st.caption(f'Muestra filtrada: {len(filtered):,} registros. Fechas en CDMX; las métricas usan esta selección.')
    return filtered


def safe_select(label,options,*,key=None,**kwargs):
    if key is None:return st.selectbox(label,options,**kwargs)
    if st.session_state.get(key) not in options:st.session_state.pop(key,None)
    return st.selectbox(label,options,key=key,**kwargs)

