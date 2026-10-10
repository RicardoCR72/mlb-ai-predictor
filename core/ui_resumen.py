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
    """Compatibilidad para las vistas que todavía usan esta entrada."""
    from core.ui_inicio import render_home as render
    return render()
