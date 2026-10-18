from core.ui_rendimiento_resumen import history_window
from core.ui_controles import state_message, roi_sample, render_order
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
                return
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
            pred['model_id']=load(ROOT)['model_id'] if (ROOT/'modelo_portable.json').exists() else None
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
    except Exception as exc:
        state_message('No se pudo cargar Totales. Comprueba el modelo, los históricos y la conexión de datos.',kind='offline')
    finally:
        if connection is not None:connection.close()


def render_performance(connect):
    from core.ui_historial_publicado import render_history
    render_history('MLB','Totales',key='mlb_total_period')
