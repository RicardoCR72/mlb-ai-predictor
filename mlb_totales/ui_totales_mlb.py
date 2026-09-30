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
    today=datetime.now(MX).date()
    col1,col2,col3=st.columns([2,2,2])
    day=col1.date_input('Fecha de partidos',today,key='mlb_totales_fecha')
    max_age=col2.number_input('Antigüedad máxima de cuota (min)',15,1440,180,15,
                             key='mlb_totales_antiguedad')
    if col3.button('Actualizar calendario y líneas',key='mlb_totales_refresh'):
        cached_calendar.clear();cached_predict.clear();st.rerun()
    st.caption('Selecciona otra fecha para consultar los partidos de mañana. '
               'El EV utiliza la línea y ambas cuotas de una misma casa.')
    connection=None
    try:
        connection=connect()
        with st.spinner('Consultando partidos pendientes y líneas reales…'):
            games=cached_calendar(str(day))
            if games.empty:
                st.info('No hay partidos pendientes para esta fecha.');return
            quotes=registro.quote_rows(connection,day)
            zone=str(st.secrets.get('mlb_odds_capture_timezone','America/Mazatlan'))
            aligned=match(games,quotes,max_age_minutes=int(max_age),quote_timezone=zone)
            if aligned.empty:
                st.info('Los partidos de esta fecha ya comenzaron.');return
            houses=sorted(aligned.casa_apuestas.dropna().unique()) if 'casa_apuestas' in aligned else []
            house=st.selectbox('Casa de apuestas',houses,key='mlb_totales_casa') if houses else None
            if house is not None:
                aligned=aligned[(aligned.get('casa_apuestas')==house)|aligned.casa_apuestas.isna()].copy()
            ready=aligned[aligned.estado_mercado=='OK'].reset_index(drop=True)
            if ready.empty:
                st.info('No hay líneas recientes y verificadas. Actualiza la captura de cuotas de MLB.')
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
                    st.warning(f'Las predicciones se muestran, pero el registro falló ({type(exc).__name__}).')
            else:
                st.warning('El registro histórico todavía no está preparado. Consulta la guía de instalación.')
            if (pred.estado=='ACTUALIZAR_HISTORIAL').any():
                st.warning('Actualiza el historial de pitcheo hasta el último día completo antes de utilizar estas predicciones.')
            display=pred[good].copy()
            if not display.empty:
                metrics=st.columns(3)
                metrics[0].metric('Pronósticos',len(display))
                metrics[1].metric('Candidatos con EV positivo',int((display.estado_valor=='CANDIDATO').sum()))
                metrics[2].metric('Historial consultado hasta',str(display.iloc[0].historial_hasta))
            filters=st.columns(2)
            only=filters[0].checkbox('Solo candidatos con EV positivo',value=False,key='mlb_totales_only')
            minimum=filters[1].slider('Probabilidad mínima (%)',0,90,0,key='mlb_totales_min')
            if only:display=display[display.estado_valor=='CANDIDATO']
            display=display[display.prob_seleccion*100>=minimum]
            if display.empty:
                st.info('No hay pronósticos que cumplan los filtros seleccionados.')
            else:
                display['ev_seleccion']=np.where(display.seleccion=='OVER',display.ev_over,display.ev_under)
                display=display.sort_values('ev_seleccion',ascending=False)
                st.caption('Modelo en evaluación. El EV es una estimación; playoffs tiene una muestra histórica pequeña.')
                for _,r in display.iterrows():
                    with st.container(border=True):
                        st.subheader(f'{r.visitante} @ {r.local}')
                        st.caption(f'Abridores: {r.abridor_visitante} · {r.abridor_local} | {r.casa_apuestas}')
                        cols=st.columns(4)
                        cols[0].metric('Selección',f'{r.seleccion} {float(r.linea):g}')
                        cols[1].metric('Probabilidad',f'{r.prob_seleccion*100:.1f}%')
                        odds=r.cuota_over if r.seleccion=='OVER' else r.cuota_under
                        cols[2].metric('Cuota decimal',f'{odds:.3f}')
                        cols[3].metric('EV estimado',f'{r.ev_seleccion*100:+.1f}%')
                        st.write(f'Total proyectado: **{r.total_proyectado:.2f}** · '
                                 f'OVER {r.p_over*100:.1f}% · UNDER {r.p_under*100:.1f}% · '
                                 f'Push {r.p_push*100:.1f}%')
                        state='Playoffs: en evaluación' if r.game_type!='R' else 'En evaluación'
                        st.caption(f'{state} · {r.estado_valor} · Cuota capturada hace {max(r.age_minutes,0):.0f} min')
                st.download_button('Descargar predicciones actuales',display.to_csv(index=False),
                    'mlb_totales_actuales.csv','text/csv',key='mlb_totales_csv')
            issues=pd.concat([aligned[aligned.estado_mercado!='OK'],pred[~good]],ignore_index=True)
            diagnostics(issues)
    except Exception as exc:
        st.error(f'No se pudo cargar Totales V2: {type(exc).__name__}. '
                 'Comprueba el modelo, los históricos y la conexión MySQL.')
        with st.expander('Detalle técnico'):st.code(str(exc))
    finally:
        if connection is not None:connection.close()


def render_performance(connect):
    st.caption('Seguimiento desde la primera predicción registrada por partido, casa y modelo. '
               'La probabilidad y cuota originales se conservan. Simulación de 1 unidad por pronóstico.')
    connection=None
    try:
        connection=connect()
        if not registro.tables_ready(connection):
            st.info('Prepara el registro siguiendo la guía de instalación.');return
        if st.button('Actualizar resultados oficiales',key='mlb_totales_resultados_refresh'):
            with st.spinner('Consultando resultados oficiales…'):
                registro.refresh_results(connection)
        frame=registro.settle(registro.history(connection))
        if frame.empty:
            st.info('Aún no hay predicciones previas al juego registradas. Abre Totales V2 antes de los partidos.');return
        cols=st.columns(3)
        houses=['Todas']+sorted(frame.casa_apuestas.unique())
        house=cols[0].selectbox('Casa',houses,key='mlb_totales_perf_casa')
        confidence=cols[1].slider('Probabilidad registrada mínima (%)',0,95,0,key='mlb_totales_perf_conf')
        candidates=cols[2].checkbox('Solo candidatos originales con EV positivo',value=True,key='mlb_totales_perf_ev')
        frame=frame[frame.confianza_pct>=confidence]
        if house!='Todas':frame=frame[frame.casa_apuestas==house]
        if candidates:frame=frame[frame.candidato==1]
        summary=registro.summary(frame)
        cols=st.columns(4)
        cols[0].metric('Pronósticos resueltos',summary['apuestas'])
        cols[1].metric('Ganancia simulada',f"{summary['unidades']:+.2f} u")
        cols[2].metric('ROI simulado',f"{summary['roi']:+.1f}%")
        cols[3].metric('Acierto sin push',f"{summary['acierto']:.1f}%")
        st.caption(f"Ganadas {summary['ganadas']} · Perdidas {summary['perdidas']} · Push {summary['push']}. "
                   'Cada combinación partido/casa cuenta como un pronóstico; no son necesariamente juegos independientes.')
        for _,r in frame.iterrows():
            with st.container(border=True):
                st.write(f'**{r.equipo_visitante} @ {r.equipo_local} — {r.resultado}**')
                cols=st.columns(4)
                cols[0].metric('Selección original',f'{r.seleccion} {float(r.linea):g}')
                cols[1].metric('Probabilidad original',f'{r.confianza_pct:.1f}%')
                cols[2].metric('Cuota original',f'{r.cuota_seleccion:.3f}')
                cols[3].metric('Unidades',f'{r.unidades:+.2f} u' if pd.notna(r.unidades) else 'Pendiente')
                st.caption(f'{r.fecha_oficial} · {r.casa_apuestas} · EV original {r.ev*100:+.1f}% · '
                           f'Registrado {r.recorded_utc} UTC')
        if not frame.empty:
            st.download_button('Descargar rendimiento',frame.to_csv(index=False),'mlb_totales_rendimiento.csv',
                               'text/csv',key='mlb_totales_performance_csv')
    except Exception as exc:
        st.error(f'No se pudo cargar el rendimiento de totales: {type(exc).__name__}.')
        with st.expander('Detalle técnico'):st.code(str(exc))
    finally:
        if connection is not None:connection.close()
