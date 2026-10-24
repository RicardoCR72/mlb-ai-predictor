"""Calibración visible, con separación de fuentes y prueba posterior congelada."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.confianza_datos import read_confidence
from core.confianza import prepare,reliability,temporal_trial,price_comparison
from core.diagnostico_confianza import market_summary
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
    from datetime import datetime
    from zoneinfo import ZoneInfo
    hora_cdmx = datetime.now(ZoneInfo('America/Mexico_City')).strftime('%H:%M')

    st.markdown(
        '<div class="calib-shell">'
        '<div class="calib-brand">'
        '<span class="calib-logo">📐</span>'
        '<div>'
        '<div>ORÁCULO <span class="calib-accent">CALIBRACIÓN AI</span></div>'
        '<div class="calib-status">Reliability Deciles · Brier Score & Log-Loss · Diagnóstico Probabilístico</div>'
        '</div>'
        '</div>'
        f'<div style="text-align:right;">'
        f'<span style="background:#1f132e;color:#c084fc;padding:.3rem .75rem;border-radius:8px;font-size:.78rem;font-weight:800;border:1px solid #3b2057;">'
        f'🕒 {hora_cdmx} CDMX'
        f'</span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )

    st.caption('Compara probabilidades proyectadas con resultados históricos reales para evaluar la fiabilidad matemática del modelo.')
    if st.button('Recargar historial guardado',key='confidence_refresh',type='primary'):
        load.clear();st.rerun()
    raw,errors=load()
    for error in errors:st.caption(error)
    clean,excluded=prepare(raw)
    if clean.empty:
        state_message('Aún no hay resultados decididos con probabilidades válidas para evaluar.');return
    with st.expander('Diagnóstico por mercado y versión'):
        overview=pd.DataFrame(market_summary(clean))
        st.caption('Cada fila mantiene separados deporte, mercado, versión y procedencia. Diferencia = acierto real menos confianza; un valor negativo indica que la confianza fue mayor que el acierto observado.')
        over_cfg = {
            'deporte': st.column_config.TextColumn('Deporte', width='small'),
            'mercado': st.column_config.TextColumn('Mercado', width='medium'),
            'modelo': st.column_config.TextColumn('Modelo', width='medium'),
            'procedencia': st.column_config.TextColumn('Procedencia', width='medium'),
            'picks': st.column_config.NumberColumn('Picks', format='%d'),
            'confianza': st.column_config.ProgressColumn('Confianza Estimada', format='%.1%', min_value=0.0, max_value=1.0),
            'acierto': st.column_config.ProgressColumn('Acierto Real', format='%.1%', min_value=0.0, max_value=1.0),
            'diferencia': st.column_config.NumberColumn('Diferencia (pp)', format='%+.1%'),
            'brier': st.column_config.NumberColumn('Brier Score', format='%.4f'),
            'logloss': st.column_config.NumberColumn('Log-Loss', format='%.4f'),
        }
        st.dataframe(overview, hide_index=True, width='stretch', column_config=over_cfg)
        st.caption('La señal describe estos datos; con una muestra limitada no basta para concluir que el modelo cambió ni para recalibrarlo. Brier y log-loss menores son mejores, pero no garantizan rentabilidad.')
        st.download_button('Descargar resumen por mercado',overview.to_csv(index=False),'confianza_por_mercado.csv','text/csv')
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
    rel_cfg = {
        'rango': st.column_config.TextColumn('Rango de Confianza', width='medium'),
        'picks': st.column_config.NumberColumn('Picks', format='%d'),
        'partidos': st.column_config.NumberColumn('Partidos', format='%d'),
        'confianza': st.column_config.ProgressColumn('Confianza Media', format='%.1%', min_value=0.0, max_value=1.0),
        'acierto': st.column_config.ProgressColumn('Acierto Observado', format='%.1%', min_value=0.0, max_value=1.0),
        'diferencia': st.column_config.NumberColumn('Diferencia', format='%+.1%'),
        'evidencia': st.column_config.TextColumn('Evidencia Muestra', width='medium'),
    }
    st.dataframe(table, hide_index=True, width='stretch', column_config=rel_cfg)
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
        price_cfg = {
            'fecha': st.column_config.TextColumn('Fecha', width='small'),
            'deporte': st.column_config.TextColumn('Deporte', width='small'),
            'mercado': st.column_config.TextColumn('Mercado', width='medium'),
            'probabilidad': st.column_config.ProgressColumn('Probabilidad IA', format='%.1%', min_value=0.0, max_value=1.0),
            'cuota': st.column_config.NumberColumn('Cuota', format='%.2f'),
            'probabilidad_implicita': st.column_config.ProgressColumn('Prob. Implícita Casa', format='%.1%', min_value=0.0, max_value=1.0),
            'ventaja_estimacion': st.column_config.NumberColumn('Ventaja (+Edge)', format='%+.1%'),
            'ev_estimado': st.column_config.NumberColumn('EV Estimado', format='%+.1%'),
        }
        st.dataframe(prices[columns], hide_index=True, width='stretch', column_config=price_cfg)
    with st.expander('Prueba temporal de recalibración'):
        trials=temporal_trial(f)
        st.caption('Solo publicaciones verificadas y candidatos sin alerta de lesión: primeras fechas para ajuste (60%), posteriores para selección (20%) y últimas para prueba (20%). Cada versión y mercado se evalúa por separado.')
        st.caption('Mínimos: 200/100/100 picks y 30/20/20 partidos; al menos 20 ganadas y 20 perdidas por bloque. Se comparan identidad, temperatura y Platt sin consultar el bloque de prueba al seleccionar.')
        for trial in trials:
            if trial.get('motivo'):st.write('Evaluación pendiente: '+trial['motivo']+'.')
        st.json(trials,expanded=False)
        st.caption('El ajuste es experimental. No cambia la confianza publicada, los picks. Una validación favorable requiere mejora de log-loss y un intervalo de la diferencia Brier completamente bajo cero.')
        st.download_button('Descargar evaluación temporal',json.dumps(trials,ensure_ascii=False,allow_nan=False,indent=2),'calibracion_temporal.json','application/json')
    with st.expander('Datos, límites y metodología'):
        st.json(excluded)
        st.write('Los registros sin hora comprobable y la confirmación histórica Liga MX sirven para diagnóstico; no entrenan el recalibrador. Se excluyen pushes, pendientes, revisiones y probabilidades fuera de [0,1].')
        st.write('MLB Totales se evalúa condicionado a no push usando la masa guardada. NFL Totales con línea entera se excluye porque no conserva esa masa. No se mezclan versiones ni procedencias.')
        st.write('Un Brier o log-loss menor no garantiza mayor acierto ni rentabilidad. Los intervalos y resultados históricos tampoco garantizan resultados futuros.')
        st.markdown('[Documentación de calibración de scikit-learn](https://scikit-learn.org/stable/modules/calibration.html)')
        st.download_button('Descargar datos para Orange / validación',f.to_csv(index=False),'confianza_datos.csv','text/csv')
