"""Análisis de modelos guardados, separado de las vistas operativas por deporte."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.bankroll import rows
from core.ui_controles import state_message,roi_sample
from core.ui_rendimiento_diseno import performance_filters,safe_select
from core.ui_rendimiento_resumen import render_performance_charts
from core.modelos_legibles import model_names,label_models
from core.ui_comparador import load_comparison,render_comparison
from core.comparador import comparison

ROOT=Path(__file__).resolve().parents[1]


def weekly_summary(frame):
    """Semanas NFL oficiales cuando existen; semanas ISO para otros deportes."""
    f=frame[frame.resultado.isin(['GANADA','PERDIDA','PUSH'])].copy()
    if f.empty:return pd.DataFrame()
    date=pd.to_datetime(f.fecha,errors='coerce')
    iso=date.dt.isocalendar()
    default=iso.year.astype('string')+' · ISO '+iso.week.astype('string')
    f['Semana']=f.get('semana_nfl',pd.Series(index=f.index,dtype='object')).fillna(default)
    f['Ganadas']=f.resultado.eq('GANADA').astype(int)
    f['Perdidas']=f.resultado.eq('PERDIDA').astype(int)
    f['Push']=f.resultado.eq('PUSH').astype(int)
    groups=['deporte','mercado','modelo_visible','procedencia','Semana']
    out=f.groupby(groups,dropna=False).agg(Picks=('resultado','size'),Ganadas=('Ganadas','sum'),
        Perdidas=('Perdidas','sum'),Push=('Push','sum'),Muestra_ROI=('unidades','count'),
        Unidades=('unidades',lambda s:s.sum(min_count=1))).reset_index()
    out['Acierto (%)']=100*out.Ganadas/(out.Ganadas+out.Perdidas).replace(0,np.nan)
    out['ROI (%)']=100*out.Unidades/out.Muestra_ROI.replace(0,np.nan)
    return out


@st.cache_data(ttl=120)
def nfl_games():
    conn=None
    try:
        conn=get_db_connection()
        return rows(conn,'SELECT id_juego,temporada,semana FROM nfl_juegos')
    except Exception:return pd.DataFrame()
    finally:
        if conn is not None:conn.close()


@st.cache_data(ttl=120)
def audit_history():
    conn=None
    try:
        conn=get_db_connection()
        frame=rows(conn,'''SELECT p.*,j.temporada AS season,j.semana AS week,j.fecha AS gameday,
            j.equipo_local AS home_team,j.equipo_visitante AS away_team,ju.nombre AS player_name
            FROM nfl_proyecciones_props p JOIN nfl_juegos j ON j.id_juego=p.id_juego
            JOIN nfl_jugadores ju ON ju.id_jugador=p.id_jugador
            ORDER BY p.actualizado_en DESC,p.id_proyeccion DESC''')
        from nfl.publicaciones_props import attach_publications
        return pd.DataFrame(attach_publications(conn,frame.to_dict('records'))) if not frame.empty else frame
    except Exception:return pd.DataFrame()
    finally:
        if conn is not None:conn.close()


def render_overview():
    frame,errors=load_comparison()
    if errors:state_message('Algunas fuentes no están disponibles. Se muestran los registros que pudieron consultarse.',kind='offline')
    if frame.empty:state_message('Aún no hay picks guardados para analizar.');return
    frame=label_models(frame,model_names(frame))
    games=nfl_games()
    if not games.empty:
        mapping={str(r.id_juego):f'{r.temporada} · NFL {int(r.semana):02}' for r in games.itertuples() if pd.notna(r.semana)}
        frame['semana_nfl']=[mapping.get(str(r.identidad).split('|')[0]) if r.deporte=='NFL' else None for r in frame.itertuples()]
    cols=st.columns(2)
    with cols[0]:sport=safe_select('Deporte',['Todos']+sorted(frame.deporte.unique()),key='center_sport')
    if sport!='Todos':frame=frame[frame.deporte.eq(sport)]
    with cols[1]:model=safe_select('Modelo',['Todos']+sorted(frame.modelo_visible.unique()),key='center_model')
    if model!='Todos':frame=frame[frame.modelo_visible.eq(model)]
    frame=performance_filters(frame,'fecha','center',season_col='Temporada',probability_col='probabilidad',
        probability_scale=100,market_col='mercado',result_col='resultado',provenance_col='procedencia')
    if frame.empty:state_message('No hay registros para estos filtros.',kind='filters');return
    settled=frame[frame.resultado.isin(['GANADA','PERDIDA','PUSH'])]
    decided=settled[settled.resultado.isin(['GANADA','PERDIDA'])]
    known=settled[np.isfinite(pd.to_numeric(settled.unidades,errors='coerce'))]
    profit=known.unidades.sum();n=len(known)
    metrics=st.columns(4)
    metrics[0].metric('Picks evaluados',len(settled))
    metrics[1].metric('Acierto',f'{decided.resultado.eq("GANADA").mean():.1%}' if len(decided) else 'N/D')
    metrics[2].metric('Unidades',f'{profit:+.2f} u' if n else 'N/D')
    metrics[3].metric('ROI',f'{100*profit/n:+.1f}%' if n else 'N/D')
    st.caption('Simulación de 1 u por pick. Los resultados agregados dependen de los mercados y versiones seleccionados; no son apuestas realizadas.')
    roi_sample(n)
    render_performance_charts(frame,date_col='fecha',profit_col='unidades',result_col='resultado',
        group_cols=('deporte','mercado','modelo_visible','procedencia'))
    with st.expander('Balance y equivalencia en pesos'):
        st.write(f'✅ {int(settled.resultado.eq("GANADA").sum())} ganadas · ❌ {int(settled.resultado.eq("PERDIDA").sum())} perdidas · {int(settled.resultado.eq("PUSH").sum())} push')
        value=st.number_input('Valor ilustrativo de 1 u (MXN)',min_value=1.0,value=100.0,step=10.0,key='center_unit')
        if n:
            st.write(f'Importe simulado: ${n*value:,.2f} MXN · Beneficio simulado: ${profit*value:+,.2f} MXN')
        st.caption('Conversión local ilustrativa; no guarda movimientos ni modifica las métricas del modelo.')
    with st.expander('Análisis por mercado y semana'):
        st.dataframe(comparison(frame),hide_index=True,width='stretch')
        week=weekly_summary(frame)
        if not week.empty:
            st.dataframe(week,hide_index=True,width='stretch')
            st.download_button('Descargar análisis semanal',week.to_csv(index=False),'rendimiento_semanal.csv','text/csv')
        st.caption('NFL usa su semana oficial cuando está disponible. Para otros deportes se indica la semana ISO. Versiones y procedencias permanecen separadas.')
    with st.expander('Explorar umbrales históricos'):
        st.caption('Exploración descriptiva: elegir el umbral con mayor ROI en estos mismos datos no valida su rendimiento futuro.')
        if st.button('Calcular sensibilidad a la confianza',key='center_threshold'):
            output=[]
            for threshold in range(0,96,5):
                selected=frame[frame.probabilidad.ge(threshold/100)]
                stats=comparison(selected)
                if not stats.empty:stats['Confianza mínima (%)']=threshold;output.append(stats)
            if output:
                result=pd.concat(output,ignore_index=True)
                st.dataframe(result,hide_index=True,width='stretch')
                st.download_button('Descargar umbrales',result.to_csv(index=False),'umbrales_historicos.csv','text/csv')
    with st.expander('Datos de la muestra'):
        st.dataframe(frame,hide_index=True,width='stretch')
        st.download_button('Descargar rendimiento filtrado',frame.to_csv(index=False),'rendimiento_filtrado.csv','text/csv')


def render_audit():
    history=audit_history()
    if history.empty:state_message('La auditoría NFL estará disponible cuando haya datos guardados de props.');return
    picks=history[history.estado_pick.isin(['CANDIDATO','REVISAR LESION']) & history.resultado_pick.isin(['GANADA','PERDIDA','PUSH'])].copy()
    picks=picks.drop_duplicates(['id_juego','id_jugador','tipo_prop','modelo_version'])
    version=safe_select('Versión de props',sorted(picks.modelo_version.dropna().astype(str).unique()),key='center_audit_model') if not picks.empty else None
    if version is not None:
        picks=picks[picks.modelo_version.eq(version)]
        history=history[history.modelo_version.eq(version)]
    picks=performance_filters(picks,'gameday','center_audit',season_col='season',probability_col='probabilidad_pick',probability_scale=100,
        result_col='resultado_pick',week_col='week')
    from core.auditoria_nfl import render_receiving_audit
    render_receiving_audit(picks,history)


def render_liga_validation():
    folder=ROOT/'futbol_liga_mx'
    try:report=json.loads((folder/'modelos/metricas.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):state_message('Las métricas de validación de Liga MX no están disponibles.',kind='offline');return
    st.subheader('Validación del modelo Liga MX')
    st.caption('Confirmación histórica 2024–25. Estas métricas no representan apuestas publicadas en vivo ni un ROI con cuotas reales.')
    records=[]
    for kind,label in [('calibrated','Modelo calibrado'),('baseline','Baseline')]:
        item=report.get('confirmation',{}).get(kind,{})
        if item:records.append(dict(Modelo=label,Partidos=item.get('n'),Brier=item.get('brier'),Logloss=item.get('logloss'),
                                     Probabilidad_media=item.get('prob_media'),Tasa_real_over=item.get('real_over')))
    st.dataframe(pd.DataFrame(records),hide_index=True,width='stretch')
    with st.expander('Metodología y muestra de validación'):
        st.json(report)
    coverage=report.get('coverage',{})
    if coverage:
        table=pd.DataFrame(list(coverage.items()),columns=['Temporada','Partidos'])
        st.bar_chart(table.set_index('Temporada'),color='#b7ff3c')
        st.dataframe(table,hide_index=True,width='stretch')
    try:
        from core.confianza import prepare,reliability
        from core.comparador import normalize
        raw=pd.read_csv(folder/'modelos/confirmacion.csv')
        raw['modelo']='Liga MX · confirmación 2024–25';raw['probabilidad']=raw.p_calibrada
        raw['resultado']=np.where(raw.over25.eq(1),'GANADA','PERDIDA');raw['cuota']=np.nan
        f=normalize(raw,sport='Liga MX',market='Over 2.5',identity=['fecha','local','visitante'])
        f['procedencia']='Confirmación histórica · reconstruida'
        f=performance_filters(f,'fecha','center_liga',probability_col='probabilidad',probability_scale=100,result_col='resultado')
        st.caption('La muestra siguiente corresponde al archivo de confirmación. Sin cuotas históricas no se calcula ROI ni beneficio.')
        prepared,_=prepare(f)
        st.dataframe(reliability(prepared),hide_index=True,width='stretch')
        st.download_button('Descargar confirmación Liga MX',f.to_csv(index=False),'confirmacion_liga_mx.csv','text/csv')
    except (OSError,ValueError,KeyError):state_message('La muestra de confirmación no está disponible.',kind='offline')


def render_center():
    from core.ui_diseno import apply_design
    apply_design()
    st.title('Rendimiento')
    st.caption('Evolución, comparación de mercados y diagnóstico de modelos guardados.')
    if st.button('Actualizar rendimiento',key='center_refresh',type='primary'):
        load_comparison.clear();nfl_games.clear();audit_history.clear()
    view=st.radio('Análisis',['Panorama','Comparación','Auditoría NFL','Validación Liga MX'],horizontal=True,key='center_view',label_visibility='collapsed')
    if view=='Panorama':render_overview()
    elif view=='Comparación':render_comparison(show_title=False)
    elif view=='Auditoría NFL':render_audit()
    else:render_liga_validation()
