from core.ui_graficas_claras import render_visual_performance
from core.modelos_legibles import model_names,label_models
"""Comparador de rendimiento del modelo, separado de dinero apostado."""
import runpy
from pathlib import Path
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.comparador import read_models,comparison,COLUMNS
from core.ui_rendimiento_diseno import performance_filters,safe_select
from core.ui_controles import state_message
from core.ui_movil import apply_mobile_layout


@st.cache_data(ttl=60)
def load_comparison():
    conn=None
    try:
        conn=get_db_connection()
        reader=runpy.run_path(str(Path(__file__).with_name('comparador.py')),run_name='comparison_reader')
        frame,errors = reader['read_models'](conn)
        try:
            from futbol.predecir_jornada import cargar_historial_futbol
            from core.comparador import normalize
            df_fut = cargar_historial_futbol()
            if not df_fut.empty:
                df_fut = df_fut.rename(columns={
                    'id_evento': 'id_partido_futbol',
                    'pick_mercado': 'mercado',
                    'pick_seleccion': 'seleccion',
                    'pick_cuota': 'cuota',
                })
                df_fut['modelo'] = 'Poisson Bivariado'
                fut_norm = normalize(df_fut, sport='Fútbol', market=None, identity=['id_partido_futbol'], american=True, verified=True)
                frame = pd.concat([frame, fut_norm], ignore_index=True)
        except Exception:
            pass
        try:
            from nba.registro import cargar_historial_rendimiento
            from core.comparador import normalize
            df_nba = cargar_historial_rendimiento()
            if not df_nba.empty:
                df_nba = df_nba.rename(columns={
                    'id_juego': 'id_partido_nba',
                    'unidades_ganadas': 'unidades',
                })
                df_nba['modelo'] = 'Ridge + Poisson V2'
                nba_norm = normalize(df_nba, sport='NBA', market=None, identity=['id_partido_nba'], american=True, verified=True)
                frame = pd.concat([frame, nba_norm], ignore_index=True)
        except Exception:
            pass
        return frame,errors
    except Exception:return pd.DataFrame(columns=COLUMNS),['Datos guardados']
    finally:
        if conn is not None:conn.close()


def render_comparison(show_title=True):
    apply_mobile_layout()
    if show_title:st.title('Comparador de rendimiento')
    else:st.subheader('Comparación de mercados y modelos')
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
            with st.expander('Ver tabla de comparación'):
                st.dataframe(visible,hide_index=True,use_container_width=True)
            st.download_button('Descargar comparación filtrada',result.to_csv(index=False),'comparacion_modelos.csv','text/csv')
            identities=set(zip(result.Deporte,result.Mercado,result.Modelo,result.Procedencia))
            graph_frame=frame[[tuple(row) in identities for row in frame[['deporte','mercado','modelo','procedencia']].itertuples(index=False,name=None)]]
            render_visual_performance(graph_frame,date_col='fecha',profit_col='unidades',result_col='resultado',
                group_cols=('deporte','mercado','modelo_visible','procedencia'),key='comparison_visual')
            with st.expander('Versiones e identificadores de los modelos'):
                versions=frame[['deporte','modelo_visible','modelo']].drop_duplicates()
                st.dataframe(versions.rename(columns={'deporte':'Deporte','modelo_visible':'Modelo','modelo':'Identificador original'}),
                    hide_index=True,use_container_width=True)
    with st.expander('Cómo interpretar la comparación'):
        st.write('Procedencia distingue los registros verificados antes del inicio de aquellos cuya hora no podemos comprobar. '
                 'Las versiones se mantienen separadas. Para comparar mercados completos, deja Resultado en Todos.')
        st.caption('Moneyline excluye dobles carteleras ambiguas. NFL no certifica hora de publicación. '
                   'Liga MX carece de cuotas históricas para calcular ROI; su validación se consulta en Rendimiento.')
