"""Resumen del inicio y estado visible junto a cada botón de actualización."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.resumen import read_summary
from core.observabilidad import age_status

ROOT=Path(__file__).resolve().parents[1]


@st.cache_data(ttl=60,show_spinner=False)
def load_snapshot(day):
    conn=None
    try:
        try: conn=get_db_connection()
        except Exception: pass
        return read_summary(conn,ROOT)
    finally:
        if conn is not None: conn.close()


def snapshot():
    return load_snapshot(datetime.now(ZoneInfo('America/Mexico_City')).date().isoformat())


def count(value):
    return 'No disponible' if value is None else str(value)


def timestamp(value, date_only=False, assume_utc=True):
    if value is None: return 'Sin registro disponible'
    stamp=pd.to_datetime(value,errors='coerce')
    if pd.isna(stamp): return 'Sin registro disponible'
    if date_only: return stamp.strftime('%d/%m/%Y')
    if stamp.tzinfo is None:
        if not assume_utc: return stamp.strftime('%d/%m/%Y · %H:%M')+' · zona no verificada'
        stamp=stamp.tz_localize('UTC')
    return stamp.tz_convert('America/Mexico_City').strftime('%d/%m/%Y · %H:%M CDMX')


def render_service_status(service, data=None):
    data=data or snapshot()
    sources=['mlb','mlb_total'] if service=='mlb' else [service]
    with st.container(border=True):
        st.markdown('**Estado de los datos guardados**')
        for source in sources:
            item=data['services'][source]
            st.caption(f"{item['label']} · Picks hoy: {count(item['picks_today'])} · "
                f"{'Apuestas pendientes' if source=='bankroll' else 'Registros por revisar'}: {count(item['pending'])}")
            st.caption('Último dato: '+timestamp(item['last_data'],source=='mlb',source in ('mlb_total','liga_mx')))
            if item['errors']: st.warning('Información parcial o no disponible. Revisa el detalle o vuelve a consultar.')
        with st.expander('Qué falta y cómo interpretar las fechas'):
            for source in sources:
                item=data['services'][source]
                st.write(item['label']+' · '+item['detail'])
                st.write('Antigüedad del último dato: '+age_status(item['last_data']))
                if item['last_result']:
                    st.write('Último resultado registrado: '+timestamp(item['last_result'],source in ('mlb','nfl_totales','liga_mx'),source=='mlb_total'))
                if item['errors']: st.caption(' · '.join(item['errors']))
                if item['pending_items']:
                    st.dataframe(pd.DataFrame(item['pending_items']).sort_values('Fecha').head(10),hide_index=True,use_container_width=True)
                    st.caption('Hasta 10 registros pendientes; consulta el historial para ver el resto.')
            st.caption('Los pendientes de deportes son registros sin resultado de días anteriores o de partidos marcados finalizados. '
                'Los partidos de hoy aún en juego pueden seguir sin resultado. Una fecha antigua puede corresponder a días sin partidos. '
                'La última actualización manual aparece arriba; no se confunde con la fecha del dato. '
                'Consulta en caché hasta 60 segundos. No se consultan APIs de cuotas.')


def partial_count(items, field):
    values=[item[field] for item in items]
    known=sum(v for v in values if v is not None)
    return f'{known} · parcial' if any(v is None for v in values) else str(known)


def render_home():
    st.subheader('Tu resumen del día')
    data=snapshot()
    st.caption(f"{data['today']} · CDMX · Lectura del resumen: {timestamp(data['at'])}")
    if st.button('Volver a consultar el resumen',key='home_refresh',icon='🔄'):
        load_snapshot.clear();st.rerun()
    services=data['services']
    calendars=[services[k] for k in ('mlb','nfl_totales','liga_mx')]
    sports=[services[k] for k in ('mlb','mlb_total','nfl_totales','nfl_props','liga_mx')]
    finance=services['bankroll'].get('finance')
    cols=st.columns(4)
    cols[0].metric('Partidos de hoy registrados',partial_count(calendars,'games_today'))
    cols[1].metric('Picks disponibles hoy',partial_count(sports,'picks_today'))
    cols[2].metric('Registros de deportes por revisar',partial_count(sports,'pending'))
    cols[3].metric('Banca disponible',f"${finance['disponible']:,.2f} MXN" if finance else 'No disponible')
    st.caption('Calendario guardado: MLB, NFL y Liga MX habilitada. Picks filtrados guardados; en Liga MX se cuentan las dos selecciones O/U por partido. '
               'Pendientes cuenta registros por servicio, por lo que un mismo partido puede tener varias selecciones. NFL no tiene hora verificada.')
    with st.container(border=True):
        st.markdown('**Tu bankroll**')
        if finance:
            cols=st.columns(3)
            cols[0].metric('Saldo',f"${finance['saldo']:,.2f} MXN")
            cols[1].metric('Dinero comprometido',f"${finance['pendientes']:,.2f} MXN")
            cols[2].metric('Apuestas pendientes',count(services['bankroll']['pending']))
        else: st.info('No se pudo consultar tu banca. No se muestra un saldo estimado.')
        st.page_link('pages/0_💼_Bankroll.py',label='Abrir Bankroll',icon='💼')
    st.markdown('**Disponibilidad por servicio**')
    table=[]
    for item in sports:
        table.append({'Servicio':item['label'],'Picks hoy':count(item['picks_today']),
            'Registros por revisar':count(item['pending']),
            'Último dato':timestamp(item['last_data'],item['service']=='mlb',item['service'] in ('mlb_total','liga_mx')),
            'Estado':'Consulta parcial: revisar' if item['errors'] else age_status(item['last_data'])})
    st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
    st.markdown('**Próximos partidos · siete días incluido hoy**')
    games=[]
    for source,sport in [('mlb','MLB'),('nfl_totales','NFL'),('liga_mx','Liga MX')]:
        games.extend(dict(Deporte=sport,**g) for g in services[source]['games'])
    if games:
        st.dataframe(pd.DataFrame(games).sort_values(['Fecha','Deporte','Partido']),hide_index=True,use_container_width=True)
    else: st.info('No hay próximos partidos disponibles en los calendarios consultados.')
    if any(item['errors'] for item in sports):
        st.warning('El resumen está incompleto. Las fuentes disponibles siguen visibles; revisa el estado en la pestaña correspondiente.')
    st.caption('Este inicio no actualiza resultados, no liquida apuestas ni genera predicciones. Usa el botón de actualización dentro de cada deporte.')
