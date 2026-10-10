"""Comparador de rendimiento del modelo, separado de dinero apostado."""
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.comparador import read_models,comparison,COLUMNS
from core.ui_rendimiento import performance_filters,safe_select
from core.ui_controles import state_message
from core.ui_movil import apply_mobile_layout


@st.cache_data(ttl=60)
def load_comparison():
    conn=None
    try:
        conn=get_db_connection()
        return read_models(conn)
    except Exception:return pd.DataFrame(columns=COLUMNS),['MySQL']
    finally:
        if conn is not None:conn.close()


def render_comparison():
    apply_mobile_layout()
    st.title('Comparador de rendimiento')
    st.caption('Simulación de 1 u por pick con cuotas guardadas. La procedencia y el modelo se comparan por separado.')
    if st.button('Actualizar comparador',key='comparison_refresh'):
        load_comparison.clear()
    frame,errors=load_comparison()
    if errors:state_message('No se pudieron consultar: '+', '.join(errors)+'. Las fuentes disponibles siguen visibles.',kind='offline')
    if frame.empty:
        state_message('Aún no hay picks guardados disponibles para comparar.');return
    sport=safe_select('Deporte',['Todos']+sorted(frame.deporte.unique()),key='comparison_sport')
    if sport!='Todos':frame=frame[frame.deporte.eq(sport)]
    frame=performance_filters(frame,'fecha','comparison',season_col='Temporada',probability_col='probabilidad',probability_scale=100,
        market_col='mercado',result_col='resultado',provenance_col='procedencia',expanded=True,
        extra_keys={'sport':'comparison_sport','minimum':'comparison_minimum'})
    result=comparison(frame)
    st.caption('Las unidades y el ROI solo incluyen beneficios conocidos. El acierto usa ganadas y perdidas; '
               'push aporta 0 u. Picks pendientes, anulados o sin resultado no participan en el ROI.')
    if result.empty:state_message('No hay picks liquidados para estos filtros.',kind='filters')
    else:
        minimum=st.number_input('Mínimo de picks con beneficio conocido',min_value=1,value=1,step=1,key='comparison_minimum')
        result=result[result['Picks con beneficio conocido'].ge(minimum)]
        if result.empty:state_message('Ningún mercado alcanza el tamaño de muestra seleccionado.',kind='filters')
        else:
            result=result.sort_values('ROI (%)',ascending=False,na_position='last',kind='stable')
            st.dataframe(result,hide_index=True,use_container_width=True)
            st.download_button('Descargar comparación filtrada',result.to_csv(index=False),'comparacion_modelos.csv','text/csv')
    st.caption('Moneyline excluye fechas con dos juegos entre los mismos equipos porque el registro antiguo no permite '
               'identificar cuál corresponde al pick. NFL conserva las versiones guardadas y no certifica hora de publicación. '
               'Liga MX mantiene su evaluación estadística: sin cuotas históricas no se inventa un ROI. '
               'Tus apuestas realizadas se consultan en Bankroll.')
