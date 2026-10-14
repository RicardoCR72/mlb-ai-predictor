from core.ui_rendimiento_resumen import render_performance_charts, history_window
from core.ui_controles import state_message, roi_sample, render_order
from core.ui_unidades import render_model_equivalence
from core.ui_rendimiento_diseno import performance_filters
"""Panel de totales separado de moneyline; probabilidades V2 y snapshots previos."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json
import pandas as pd
import numpy as np
import streamlit as st
from mlb_totales.mercado import calendar,match,MX
from mlb_totales.predecir_pitcheo import predict
from mlb_totales.portable import load
from mlb_totales import registro
from mlb_totales.casa_base import only_base
from mlb_totales.tarjetas_actuales import render_cards

ROOT=Path(__file__).resolve().parent/'modelos_pitcheo'


@st.cache_data(ttl=45)
def cached_calendar(day):return calendar(day)


@st.cache_data(ttl=120)
def cached_predict(csv,stamp):
    from io import StringIO
    return predict(pd.read_csv(StringIO(csv)),ROOT,portable=True)


def stamp():
    return tuple((ROOT/name).stat().st_mtime_ns for name in (
        'historial_modelo.csv.gz','historial_pitcheo.csv.gz',
        'historial_modelo.coverage.json','modelo_portable.json'))


def diagnostics(frame):
    if frame.empty:return
    with st.expander('Partidos pendientes de datos o revisión'):
        columns=[c for c in ('local','visitante','casa_apuestas','estado_mercado','estado') if c in frame]
        st.dataframe(frame[columns],hide_index=True,use_container_width=True)


def render_picks(connect):
    day=datetime.now(MX).date()
    minimum=st.slider('Confianza mínima (%)',0,95,50,key='mlb_totales_confianza_hoy')
    if st.button('Recargar calendario y cuotas guardadas',key='mlb_totales_refresh'):
        cached_calendar.clear();cached_predict.clear();st.rerun()
    st.caption('Partidos de hoy · Casa base: DraftKings.')
    connection=None
    try:
        connection=connect()
        with st.spinner('Consultando partidos pendientes y líneas reales…'):
            games=cached_calendar(str(day))
            if games.empty:
                state_message('No hay partidos pendientes para esta fecha.',kind='empty');return
            quotes=only_base(registro.quote_rows(connection,day))
            zone=str(st.secrets.get('mlb_odds_capture_timezone','America/Mazatlan'))
            aligned=match(games,quotes,max_age_minutes=180,quote_timezone=zone)
            if aligned.empty:
                state_message('Los partidos de esta fecha ya comenzaron.');return
            ready=only_base(aligned[aligned.estado_mercado=='OK']).reset_index(drop=True)
            if ready.empty:
                state_message('No hay líneas recientes y verificadas de DraftKings. Actualiza la captura de cuotas de MLB.',kind='empty')
                diagnostics(aligned);return
            with st.spinner('Calculando probabilidades con los abridores anunciados…'):
                pred=cached_predict(ready.to_csv(index=False),stamp())
            # Predicción devuelve filas en el mismo orden; anexar exclusivamente metadata de mercado.
            for key in ('casa_apuestas','odds_game_id','start_utc','captured_utc',
                        'estado_mercado','abridor_local','abridor_visitante','age_minutes'):
                pred[key]=ready[key].to_numpy()
            good=pred.estado.isin(['EXPERIMENTAL','PLAYOFFS_EXPERIMENTAL']) & pred.p_over.notna()
            if registro.tables_ready(connection):
                try:
                    registro.save_snapshots(connection,pred,load(ROOT)['model_id'])
                except Exception as exc:
                    state_message('Las predicciones se muestran, pero no se pudieron guardar. Reintenta cuando vuelva la conexión.',kind='offline')
            else:
                state_message('El registro histórico todavía no está preparado. Consulta la guía de instalación.',kind='empty')
            if (pred.estado=='ACTUALIZAR_HISTORIAL').any():
                state_message('Actualiza el historial de pitcheo hasta el último día completo antes de utilizar estas predicciones.',kind='blocked')
            display=pred[good].copy()
            if not display.empty:
                metrics=st.columns(3)
                metrics[0].metric('Pronósticos',len(display))
                metrics[1].metric('Candidatos con EV positivo',int((display.estado_valor=='CANDIDATO').sum()))
                metrics[2].metric('Historial consultado hasta',str(display.iloc[0].historial_hasta))
            display=display[display.prob_seleccion*100>=minimum]
            if display.empty:
                state_message('No hay pronósticos que cumplan los filtros seleccionados.',kind='filters')
            else:
                display['ev_seleccion']=np.where(display.seleccion=='OVER',display.ev_over,display.ev_under)
                display=display.sort_values('prob_seleccion',ascending=False,kind='stable')
                st.caption('Modelo en evaluación. El EV es una estimación; playoffs tiene una muestra histórica pequeña.')
                render_cards(display)
                st.download_button('Descargar predicciones actuales',display.to_csv(index=False),
                    'mlb_totales_actuales.csv','text/csv',key='mlb_totales_csv')
            issues=pd.concat([aligned[aligned.estado_mercado!='OK'],pred[~good]],ignore_index=True)
            diagnostics(issues)
    except Exception as exc:
        state_message('No se pudo cargar Totales. Comprueba el modelo, los históricos y la conexión de datos.',kind='offline')
    finally:
        if connection is not None:connection.close()


def render_performance(connect):
    st.caption('DraftKings · Seguimiento desde la primera predicción registrada por partido y modelo. '
               'La probabilidad y cuota originales se conservan. Simulación de 1 unidad por pronóstico.')
    connection=None
    try:
        connection=connect()
        if not registro.tables_ready(connection):
            state_message('El registro de predicciones todavía no está preparado.',kind='blocked');return
        frame=registro.settle(only_base(registro.history(connection)))
        if frame.empty:
            state_message('Aún no hay predicciones de DraftKings registradas. Actions o Totales las guardan antes de los partidos.',kind='empty');return
        frame['temporada'] = pd.to_datetime(frame['fecha_oficial']).dt.year
        frame = performance_filters(frame, 'fecha_oficial', 'mlb_total_period', season_col='temporada', result_col='resultado',
            extra_keys={'confidence_total':'mlb_totales_perf_conf','candidates':'mlb_totales_perf_ev'})
        with st.expander('Confianza y valor'):
            cols=st.columns(2)
            confidence=cols[0].slider('Probabilidad registrada mínima (%)',0,95,0,key='mlb_totales_perf_conf')
            candidates=cols[1].checkbox('Solo candidatos originales con EV positivo',value=True,key='mlb_totales_perf_ev')
        frame=frame[frame.confianza_pct>=confidence]
        if candidates:frame=frame[frame.candidato==1]
        summary=registro.summary(frame)
        cols=st.columns(4)
        cols[0].metric('Pronósticos resueltos',summary['apuestas'])
        cols[1].metric('Acierto sin push',f"{summary['acierto']:.1f}%")
        cols[2].metric('Unidades',f"{summary['unidades']:+.2f} u")
        cols[3].metric('ROI simulado',f"{summary['roi']:+.1f}%")
        with st.expander('Balance y equivalencia en pesos'):
            st.caption(f"Ganadas {summary['ganadas']} · Perdidas {summary['perdidas']} · Push {summary['push']}. "
                       'Cuotas, probabilidades y EV originales de DraftKings.')
            render_model_equivalence(summary['apuestas'], summary['unidades'])
        render_performance_charts(frame,date_col='fecha_oficial',profit_col='unidades',
            result_col='resultado',group_cols=('seleccion',))
        with st.expander('Orden del historial'):
            frame=render_order(frame,'mlb_total_period',date_col='fecha_oficial',confidence_col='confianza_pct',profit_col='unidades')
        render_cards(history_window(frame,'mlb_total_history'),performance=True)
        if frame.empty:
            state_message('No hay registros de DraftKings que cumplan los filtros seleccionados.',kind='filters')
        if not frame.empty:
            st.download_button('Descargar rendimiento',frame.to_csv(index=False),'mlb_totales_rendimiento.csv',
                               'text/csv',key='mlb_totales_performance_csv')
    except Exception as exc:
        state_message('No se pudo cargar el rendimiento de totales. Reintenta cuando vuelva la conexión.',kind='offline')
    finally:
        if connection is not None:connection.close()
