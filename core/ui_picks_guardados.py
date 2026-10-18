"""Lectura de publicaciones del día; no ejecuta modelos ni consulta cuotas."""
from datetime import datetime,timezone
import pandas as pd
import streamlit as st
from core import ui_historial_publicado as history
from core.ui_tarjetas import render_pick
from core.ui_controles import state_message
from core.constants import ZONA_CDMX


def render_mlb_today(market):
    raw,errors=history.load_history()
    if errors:state_message('Consulta parcial: algunos registros no están disponibles.',kind='offline')
    if raw.empty:state_message('Todavía no hay predicciones publicadas.');return
    now=pd.Timestamp(datetime.now(timezone.utc))
    frame=raw[raw.deporte.eq('MLB') & raw.mercado.eq(market)].copy()
    if 'start_utc' not in frame:state_message('No hay publicaciones con inicio verificable.');return
    starts=pd.to_datetime(frame.start_utc,utc=True,errors='coerce')
    days=starts.dt.tz_convert(ZONA_CDMX).dt.date
    frame=frame[starts.gt(now)&days.eq(now.tz_convert(ZONA_CDMX).date())&frame.resultado.eq('PENDIENTE')]
    if frame.empty:state_message('No hay picks publicados para partidos de hoy sin iniciar.');return
    if 'publicada_utc' in frame:frame=frame.sort_values('publicada_utc',ascending=False,na_position='last')
    frame=frame.drop_duplicates('identidad')
    minimum=st.slider('Confianza mínima (%)',0,100,50,key='mlb_today_'+market)
    frame=frame[frame.probabilidad.ge(minimum/100)]
    if frame.empty:state_message('No hay picks que cumplan el filtro.',kind='filters');return
    st.metric('Partidos con pronóstico',len(frame))
    shown=frame.sort_values('probabilidad',ascending=False)
    for start in range(0,len(shown),2):
        columns=st.columns(2,gap='medium')
        for col,(_,row) in zip(columns,shown.iloc[start:start+2].iterrows()):
            with col:
                pick=dict(fecha=row.fecha,deporte='MLB',partido=f'{row.get("equipo_visitante","Visitante")} @ {row.get("equipo_local","Local")}',
                    seleccion=str(row.get('seleccion','Selección guardada'))+(f' {row.linea:g}' if pd.notna(row.get('linea')) else ''),
                    probabilidad=row.probabilidad,cuota=row.cuota,casa='DraftKings',modelo=row.modelo,mercado_confianza=market,
                    origen='mlb_total' if market=='Totales' else 'mlb_ml',p_push=row.get('p_push',0),
                    referencia=dict(game_id=str(row.identidad),inicio_utc=pd.to_datetime(row.start_utc,utc=True).isoformat()),
                    cuota_capturada_utc=row.get('quote_utc'))
                render_pick(pick,market=market,state='Publicado',details=[('Procedencia',row.procedencia)])
