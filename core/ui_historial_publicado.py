"""Presentación de históricos guardados; nunca carga modelos ni genera picks."""
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.confianza_datos import read_history
from core.ui_rendimiento_diseno import performance_filters,safe_select
from core.ui_controles import state_message,render_order
from core.ui_rendimiento_resumen import history_window
from core.ui_tarjetas import render_pick, number

ROOT=Path(__file__).resolve().parents[1]


@st.cache_data(ttl=120,show_spinner=False)
def load_history():
    conn=None
    try:
        conn=get_db_connection()
        frame,errors=read_history(conn,ROOT,include_liga=False,only_candidates=False)
        if not frame.empty:
            from core.infrastructure.queries import rows
            try:
                games=rows(conn,'SELECT id_juego,temporada,semana FROM nfl_juegos')
                if not games.empty:
                    weeks={str(r.id_juego):str(int(r.semana)) for r in games.itertuples() if pd.notna(r.semana)}
                    frame['Semana']=[weeks.get(str(r.identidad).split('|')[0]) if r.deporte=='NFL' else None for r in frame.itertuples()]
            except Exception:errors.append('No se pudo consultar la semana NFL.')
        return frame,errors
    except Exception:
        return pd.DataFrame(),['No se pudo consultar el historial guardado.']
    finally:
        if conn is not None:conn.close()



def actual_result_details(row):
    """Mostrar el valor observado; nunca sustituirlo por la proyección o la línea."""
    reason = row.get('motivo_devolucion')
    if pd.notna(reason) and str(reason).strip():
        return [('Devolución', str(reason))]
    sport = row.get('deporte')
    market = row.get('mercado')
    settled = str(row.get('resultado', '')).strip().upper() in ('GANADA','PERDIDA','PUSH')
    if sport == 'NFL' and market != 'Totales':
        units = {'Recepciones':'recepciones', 'Yardas de recepción':'yardas',
                 'Yardas por pase':'yardas', 'Yardas terrestres':'yardas',
                 'Pases de touchdown':'pases de touchdown', 'Anota touchdown':'touchdowns'}
        actual = number(row.get('valor_real'))
        value = f"{actual:g} {units.get(market, '')}".strip() if settled and actual is not None else 'No disponible' if settled else 'Pendiente'
        return [('Resultado real', value)]
    if market == 'Totales' and sport in ('NFL','MLB'):
        actual = number(row.get('total_real'))
        away = number(row.get('marcador_visitante') if sport == 'NFL' else row.get('away_runs'))
        home = number(row.get('marcador_local') if sport == 'NFL' else row.get('home_runs'))
        if actual is None and settled and away is not None and home is not None:
            actual = away + home
        unit = 'puntos' if sport == 'NFL' else 'carreras'
        value = f'{actual:g} {unit}' if settled and actual is not None else 'No disponible' if settled else 'Pendiente'
        details = [('Total real', value)]
        if settled and away is not None and home is not None:
            details.append(('Marcador final', f'{away:g} – {home:g} (visitante – local)'))
        return details
    return []

def render_manual_refund(row, key):
    if row.get('deporte') not in ('MLB', 'NFL') or row.get('resultado') != 'PENDIENTE':
        return
    with st.popover('Registrar devolución', use_container_width=True):
        st.caption('Úsalo si confirmaste que la apuesta fue anulada. Quedará identificada como devolución manual.')
        reasons = ['Partido no disputado en la fecha del pick', 'Apuesta anulada por la casa']
        if row.get('deporte') == 'NFL' and row.get('mercado') != 'Totales':
            reasons.insert(0, 'Jugador no participó')
        reason = st.selectbox('Motivo', reasons, key=key+'_reason')
        confirmed = st.checkbox('Confirmo la devolución de este pick', key=key+'_confirm')
        if st.button('Guardar como push', key=key+'_save', disabled=not confirmed):
            conn = None
            try:
                from core.devoluciones import record_manual_refund
                conn = get_db_connection()
                record_manual_refund(conn, row, reason)
            except Exception:
                st.error('No se pudo guardar la devolución. Intenta nuevamente.')
            else:
                from core.ui_trabajos import invalidate_readers
                invalidate_readers()
                st.toast('Devolución registrada: push y 0 unidades.')
                st.rerun()
            finally:
                if conn is not None:
                    conn.close()


def render_history(sport,market=None,*,key):
    raw,errors=load_history()
    if errors:state_message('Consulta parcial del historial. Algunas fuentes no están disponibles.',kind='offline')
    if raw.empty:
        state_message('No hay publicaciones disponibles para esta consulta.',kind='offline' if errors else 'empty');return
    frame=raw[raw.deporte.eq(sport)].copy()
    if market is not None:frame=frame[frame.mercado.eq(market)]
    elif sport=='NFL':frame=frame[~frame.mercado.eq('Totales')]
    if frame.empty:state_message('Todavía no hay publicaciones de este mercado.');return
    st.subheader('Rendimiento de picks publicados')
    st.caption('Primera publicación original cuando existe; registros antiguos identificados por procedencia. Simulación de 1 unidad por pick.')
    from core.modelos_legibles import model_names
    labels=model_names(frame)
    model=safe_select('Versión del modelo',['Todas']+sorted(frame.modelo.astype(str).unique()),key=key+'_model',
        format_func=lambda v:'Todas' if v=='Todas' else labels[(sport,str(v))])
    if model!='Todas':frame=frame[frame.modelo.astype(str).eq(model)]
    if market=='Totales' and sport=='NFL':
        # OVER/UNDER es el mercado operativo en esta vista; conservar el nombre global para la tarjeta.
        frame['Lado']=frame.get('seleccion')
    frame=performance_filters(frame,'fecha',key,season_col='Temporada',probability_col='probabilidad',probability_scale=100,
        market_col='Lado' if 'Lado' in frame else 'mercado',result_col='resultado',provenance_col='procedencia',
        week_col='Semana' if 'Semana' in frame and frame.Semana.notna().any() else None,
        candidate_col='candidato' if sport=='MLB' and market=='Totales' and 'candidato' in frame else None)
    if frame.empty:state_message('No hay registros para estos filtros.',kind='filters');return
    settled=frame[frame.resultado.isin(['GANADA','PERDIDA','PUSH'])]
    decided=settled[settled.resultado.ne('PUSH')]
    known=settled[np.isfinite(pd.to_numeric(settled.unidades,errors='coerce'))]
    metrics=st.columns(4)
    metrics[0].metric('Picks evaluados',len(settled))
    metrics[1].metric('Acierto',f'{decided.resultado.eq("GANADA").mean():.1%}' if len(decided) else 'N/D')
    metrics[2].metric('Unidades',f'{known.unidades.sum():+.2f} u' if len(known) else 'N/D')
    metrics[3].metric('ROI',f'{100*known.unidades.mean():+.1f}%' if len(known) else 'N/D')
    with st.expander('Orden del historial'):
        ordered=render_order(frame,key+'_order',date_col='fecha',confidence_col='probabilidad',profit_col='unidades')
    shown=history_window(ordered,key+'_history')
    for start in range(0,len(shown),2):
        columns=st.columns(2,gap='medium')
        for col,(_,row) in zip(columns,shown.iloc[start:start+2].iterrows()):
            with col:
                identity=str(row.identidad).split('|')
                if pd.notna(row.get('equipo_local')) and pd.notna(row.get('equipo_visitante')):
                    event=f'{row.equipo_visitante} @ {row.equipo_local}'
                else:event=' · '.join(identity)
                selection=str(row.get('seleccion')) if pd.notna(row.get('seleccion')) else 'Selección guardada'
                if pd.notna(row.get('jugador')):selection=str(row.jugador)+' · '+selection
                line=row.get('linea') if pd.notna(row.get('linea')) else row.get('linea_total')
                if pd.notna(line):selection+=f' {line:g}'
                away_sc = row.get('marcador_visitante') if pd.notna(row.get('marcador_visitante')) else (row.get('away_runs') if pd.notna(row.get('away_runs')) else row.get('goles_visitante'))
                home_sc = row.get('marcador_local') if pd.notna(row.get('marcador_local')) else (row.get('home_runs') if pd.notna(row.get('home_runs')) else row.get('goles_local'))
                pick=dict(fecha=row.fecha,deporte=sport,partido=event,seleccion=selection,casa='DraftKings',
                    probabilidad=row.probabilidad,cuota=row.cuota,referencia={},
                    equipo_visitante=row.get('equipo_visitante'),equipo_local=row.get('equipo_local'),
                    away_runs=row.get('away_runs'),home_runs=row.get('home_runs'),
                    away_score=away_sc,home_score=home_sc,
                    unidades=row.get('unidades'),resultado=row.get('resultado'))
                if pd.notna(row.get('start_utc')):pick['referencia']['inicio_utc']=pd.Timestamp(row.start_utc).tz_localize('UTC').isoformat() if pd.Timestamp(row.start_utc).tzinfo is None else str(row.start_utc)
                render_pick(pick,market=row.mercado,state=row.resultado,allow_register=False,
                    details=actual_result_details(row)+[('Unidades',f'{row.unidades:+.2f} u' if pd.notna(row.unidades) else 'N/D'),('Procedencia',row.procedencia),('Versión',labels[(sport,str(row.modelo))])])
                import hashlib
                refund_key=hashlib.sha256(f'{key}|{row.modelo}|{row.identidad}|{row.mercado}'.encode()).hexdigest()[:24]
                render_manual_refund(row,'refund_'+refund_key)
    st.download_button('Descargar rendimiento filtrado',frame.to_csv(index=False),sport.lower()+'_rendimiento.csv','text/csv',key=key+'_csv')
