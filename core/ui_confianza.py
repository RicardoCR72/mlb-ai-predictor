"""Calibración visible, con separación de fuentes y prueba posterior congelada."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.confianza_datos import read_confidence
from core.confianza import prepare,reliability,temporal_trial,price_comparison
from core.ui_diseno import apply_design
from core.ui_controles import state_message
from core.ui_movil import apply_mobile_layout
from core.ui_rendimiento_diseno import safe_select

ROOT=Path(__file__).resolve().parents[1]


@st.cache_data(ttl=300,show_spinner=False)
def load():
    conn=None
    try:
        try:conn=get_db_connection()
        except Exception:pass
        return read_confidence(conn,ROOT)
    finally:
        if conn is not None:conn.close()


def render():
    apply_mobile_layout();apply_design()
    st.title('Calibración de confianza')
    st.caption('Compara probabilidades guardadas con resultados. Una muestra grande no demuestra calibración ni rentabilidad.')
    if st.button('Recargar historial guardado',key='confidence_refresh'):
        load.clear();st.rerun()
    raw,errors=load()
    for error in errors:st.caption(error)
    clean,excluded=prepare(raw)
    if clean.empty:
        state_message('Aún no hay resultados decididos con probabilidades válidas para evaluar.');return
    sport=safe_select('Deporte',sorted(clean.deporte.unique()),key='confidence_sport')
    f=clean[clean.deporte.eq(sport)]
    market=safe_select('Mercado',sorted(f.mercado.unique()),key='confidence_market')
    f=f[f.mercado.eq(market)]
    model=safe_select('Versión del modelo',sorted(f.modelo.unique()),key='confidence_model')
    f=f[f.modelo.eq(model)]
    if 'tipo_probabilidad' in f and f.tipo_probabilidad.eq('Condicional a no push').any():
        st.caption('Totales MLB usa probabilidad condicionada a no push para evaluar ganadas y perdidas.')
    table=reliability(f)
    st.subheader('Confianza frente a acierto real')
    st.caption('Rangos de 10 puntos. Los intervalos remuestrean partidos para considerar picks relacionados; con un solo partido no se calculan.')
    st.dataframe(table,hide_index=True,width='stretch',column_config={c:st.column_config.NumberColumn(format='percent') for c in ['confianza','acierto','diferencia','intervalo_inferior','intervalo_superior']})
    import altair as alt
    chart=alt.Chart(table).mark_line(point=True).encode(x=alt.X('confianza:Q',scale=alt.Scale(domain=[0,1]),title='Probabilidad media estimada'),
        y=alt.Y('acierto:Q',scale=alt.Scale(domain=[0,1]),title='Acierto observado'),color='procedencia:N',
        tooltip=['rango','procedencia','picks','partidos','confianza','acierto','evidencia'])
    diagonal=alt.Chart(pd.DataFrame({'x':[0,1],'y':[0,1]})).mark_line(strokeDash=[4,4],color='#8994a5').encode(x='x:Q',y='y:Q')
    st.altair_chart(chart+diagonal,width='stretch')
    st.caption('Menos de 100 picks o 30 partidos por rango se señala como muestra limitada. Son umbrales orientativos, no una certificación estadística.')
    st.download_button('Descargar diagnóstico por rangos',table.to_csv(index=False),'calibracion_rangos.csv','text/csv')
    with st.expander('Probabilidad y cuota guardada'):
        prices=price_comparison(f)
        st.caption('Probabilidad implícita = 1 / cuota. Ventaja y EV usan la estimación guardada, sin probar una ventaja rentable ni ajustar el margen de la casa. Sin cuota válida no se calculan.')
        columns=['fecha','deporte','mercado','modelo','procedencia','identidad','probabilidad','cuota','probabilidad_implicita','ventaja_estimacion','ev_estimado']
        st.dataframe(prices[columns],hide_index=True,width='stretch')
    with st.expander('Prueba temporal de recalibración'):
        trials=temporal_trial(f)
        st.caption('Solo publicaciones verificadas y candidatos sin alerta de lesión: primeras fechas para ajuste (60%), posteriores para selección (20%) y últimas para prueba (20%). Cada versión y mercado se evalúa por separado.')
        st.caption('Mínimos: 200/100/100 picks y 30/20/20 partidos; al menos 20 ganadas y 20 perdidas por bloque. Se comparan identidad, temperatura y Platt sin consultar el bloque de prueba al seleccionar.')
        st.json(trials,expanded=False)
        st.caption('El ajuste es experimental. No cambia la confianza publicada, los picks, Combinadas ni Bankroll. Una validación favorable requiere mejora de log-loss y un intervalo de la diferencia Brier completamente bajo cero.')
        st.download_button('Descargar evaluación temporal',json.dumps(trials,ensure_ascii=False,allow_nan=False,indent=2),'calibracion_temporal.json','application/json')
    with st.expander('Datos, límites y metodología'):
        st.json(excluded)
        st.write('Los registros sin hora comprobable y la confirmación histórica Liga MX sirven para diagnóstico; no entrenan el recalibrador. Se excluyen pushes, pendientes, revisiones y probabilidades fuera de [0,1].')
        st.write('MLB Totales se evalúa condicionado a no push usando la masa guardada. NFL Totales con línea entera se excluye porque no conserva esa masa. No se mezclan versiones ni procedencias.')
        st.write('Un Brier o log-loss menor no garantiza mayor acierto ni rentabilidad. Los intervalos y resultados históricos tampoco garantizan resultados futuros.')
        st.markdown('[Documentación de calibración de scikit-learn](https://scikit-learn.org/stable/modules/calibration.html)')
        st.download_button('Descargar datos para Orange / validación',f.to_csv(index=False),'confianza_datos.csv','text/csv')
