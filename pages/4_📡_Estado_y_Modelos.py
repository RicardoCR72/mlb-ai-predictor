from pathlib import Path
import json
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core import bankroll as bank
from core.observabilidad import WORKFLOWS, workflow_status, data_status
from core.rendimiento import grouped_performance, mlb_snapshot_performance

st.set_page_config(page_title='Estado y modelos',page_icon='📡',layout='wide')
st.title('Estado de integraciones y rendimiento')
ROOT = Path(__file__).resolve().parents[1]

@st.cache_data(ttl=300)
def executions():
    output=[]
    for sport,filename in WORKFLOWS.items():
        try: output.append({'Integración':sport,**workflow_status(filename)})
        except Exception as exc: output.append({'Integración':sport,'resultado':'No consultable','detalle':type(exc).__name__})
    return pd.DataFrame(output)

conn = None
try:
    try: conn = get_db_connection()
    except Exception as exc: st.warning(f'MySQL sin conexión ({type(exc).__name__}). Se muestran los datos locales y las ejecuciones disponibles.')
    health,performance,history = st.tabs(['Integraciones','Registros previos y apuestas','Evaluación histórica'])
    with health:
        st.dataframe(data_status(conn,ROOT),hide_index=True,use_container_width=True)
        st.caption('Un dato antiguo requiere revisar si hubo partidos. La fecha de datos y la ejecución exitosa son medidas distintas. No se consultan APIs de cuotas.')
        st.dataframe(executions(),hide_index=True,use_container_width=True,
                     column_config={'enlace':st.column_config.LinkColumn('Ver ejecución')})
        st.caption('Ejecuciones de main; último éxito encontrado entre las últimas 20 de cada workflow. Actualización cada cinco minutos.')
        if st.button('Actualizar estado'):
            executions.clear();st.rerun()
    with performance:
        if conn is None: st.info('Conecta MySQL para consultar snapshots y apuestas realizadas.')
        else:
            try:
                st.subheader('Predicciones MLB V2 registradas antes del inicio')
                snapshots=mlb_snapshot_performance(conn)
                st.dataframe(snapshots,hide_index=True,use_container_width=True)
                st.caption('ROI teórico con 1 unidad por predicción y cuota del snapshot; no representa dinero apostado. Calibración solo en líneas de media carrera, sin push.')
            except Exception as exc: st.info(f'Snapshots MLB V2 no disponibles ({type(exc).__name__}).')
            try:
                ledger=bank.load_ledger(conn)
                report,bins=grouped_performance(ledger)
                st.subheader('Apuestas realizadas por deporte y mercado')
                st.dataframe(report,hide_index=True,use_container_width=True)
                st.caption('ROI con monto y cuota tomados. Brier, logloss y ECE usan ganadas/perdidas con probabilidad válida. Push, pendientes y anuladas no entran en calibración. La muestra depende de las apuestas que registraste.')
                st.caption('Solo se considera registro previo cuando consta una hora de inicio con zona horaria. NFL y registros antiguos sin hora verificable aparecen separados. Eso no acredita por sí solo que todo el entrenamiento sea fuera de muestra.')
                st.dataframe(bins,hide_index=True,use_container_width=True)
                st.download_button('Descargar métricas',report.to_csv(index=False),'rendimiento_modelos.csv','text/csv')
            except Exception as exc: st.info(f'Bankroll no disponible ({type(exc).__name__}).')
    with history:
        st.caption('Evaluaciones del modelo congelado; estos resultados no se mezclan con apuestas reales ni con registros prospectivos.')
        for name,path in [('MLB V2','mlb_totales/modelos_pitcheo/metricas.json'),('Liga MX','futbol_liga_mx/modelos/metricas.json'),('Liga MX 2025–26','futbol_liga_mx/modelos/confirmacion_2025_26.json')]:
            with st.expander(name):
                file=ROOT/path
                if file.exists(): st.json(json.loads(file.read_text()))
                else: st.info('Evaluación aún no disponible.')
finally:
    if conn is not None: conn.close()
