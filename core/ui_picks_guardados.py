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
    hoy_date=now.tz_convert(ZONA_CDMX).date()
    hoy_all=frame[days.eq(hoy_date)].copy()

    total_partidos=hoy_all['identidad'].nunique() if not hoy_all.empty else 0
    pendientes=hoy_all[starts.gt(now)&hoy_all.resultado.eq('PENDIENTE')]['identidad'].nunique() if not hoy_all.empty else 0
    finalizados=max(0,total_partidos-pendientes)

    frame=frame[starts.gt(now)&days.eq(hoy_date)&frame.resultado.eq('PENDIENTE')]
    if 'publicada_utc' in frame:frame=frame.sort_values('publicada_utc',ascending=False,na_position='last')
    frame=frame.drop_duplicates('identidad')

    picks_valor=int((frame['probabilidad']>=0.55).sum()) if not frame.empty and 'probabilidad' in frame else len(frame)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Partidos", total_partidos)
    with c2:
        st.metric("Pendientes", pendientes)
    with c3:
        st.metric("Finalizados", finalizados)
    with c4:
        st.metric("Picks de Alto Valor", picks_valor)
    st.markdown("<div style='margin-bottom: 1.25rem;'></div>", unsafe_allow_html=True)

    if frame.empty:state_message('No hay picks publicados para partidos de hoy sin iniciar.');return
    shown=frame.sort_values('probabilidad',ascending=False)
    for start in range(0,len(shown),2):
        columns=st.columns(2,gap='medium')
        for col,(_,row) in zip(columns,shown.iloc[start:start+2].iterrows()):
            with col:
                pick=dict(fecha=row.fecha,deporte='MLB',partido=f'{row.get("equipo_visitante","Visitante")} @ {row.get("equipo_local","Local")}',
                    equipo_visitante=row.get("equipo_visitante"),equipo_local=row.get("equipo_local"),
                    seleccion=str(row.get('seleccion','Selección guardada'))+(f' {row.linea:g}' if pd.notna(row.get('linea')) else ''),
                    probabilidad=row.probabilidad,cuota=row.cuota,casa='DraftKings',modelo=row.modelo,mercado_confianza=market,
                    origen='mlb_total' if market=='Totales' else 'mlb_ml',p_push=row.get('p_push',0),
                    referencia=dict(game_id=str(row.identidad),inicio_utc=pd.to_datetime(row.start_utc,utc=True).isoformat()))
                render_pick(pick,market=market,state='Publicado',details=[('Procedencia',row.procedencia)])

                from core.ui_boleta import render_boton_boleta
                clean_market = str(market).replace(' ', '_')
                ident = str(row.identidad).replace(' ', '_')
                slip_item = {
                    "id": f"MLB_{ident}_{clean_market}_{pick['seleccion']}",
                    "deporte": "MLB",
                    "icono": "⚾",
                    "partido": pick["partido"],
                    "mercado": market,
                    "seleccion": pick["seleccion"],
                    "cuota": row.cuota,
                    "prob": row.probabilidad,
                }
                render_boton_boleta(slip_item, key=f"btn_mlb_slip_{ident}_{clean_market}")

    from core.ui_boleta import render_widget_boleta
    render_widget_boleta()
