from core.graficas_rendimiento import render_performance_charts
from core.modelos_legibles import model_names,label_models
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
    except Exception:return pd.DataFrame(columns=COLUMNS),['Datos guardados']
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
    names=model_names(frame)
    frame=label_models(frame,names)
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
            visible=result.copy()
            visible['Modelo']=[names[(str(r.Deporte),str(r.Modelo))] for r in result.itertuples()]
            st.dataframe(visible,hide_index=True,use_container_width=True)
            st.download_button('Descargar comparación filtrada',result.to_csv(index=False),'comparacion_modelos.csv','text/csv')
            identities=set(zip(result.Deporte,result.Mercado,result.Modelo,result.Procedencia))
            graph_frame=frame[[tuple(row) in identities for row in frame[['deporte','mercado','modelo','procedencia']].itertuples(index=False,name=None)]]
            render_performance_charts(graph_frame,date_col='fecha',profit_col='unidades',result_col='resultado',
                group_cols=('deporte','mercado','modelo_visible','procedencia'))
            with st.expander('Versiones e identificadores de los modelos'):
                versions=frame[['deporte','modelo_visible','modelo']].drop_duplicates()
                st.dataframe(versions.rename(columns={'deporte':'Deporte','modelo_visible':'Modelo','modelo':'Identificador original'}),
                    hide_index=True,use_container_width=True)
    with st.expander('Cómo interpretar la comparación'):
        st.write('Procedencia distingue los registros verificados antes del inicio de aquellos cuya hora no podemos comprobar. '
                 'Las versiones se mantienen separadas. Para comparar mercados completos, deja Resultado en Todos.')
        st.caption('Moneyline excluye dobles carteleras ambiguas. NFL no certifica hora de publicación. '
                   'Liga MX carece de cuotas históricas para calcular ROI. Tus apuestas realizadas están en Bankroll.')
