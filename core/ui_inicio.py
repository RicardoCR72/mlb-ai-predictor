"""Entrada del dashboard independiente de componentes conservados por Streamlit."""
import pandas as pd
import streamlit as st
from core import ui_resumen as summary
from core.ui_resumen import count, timestamp, partial_count
from core.observabilidad import age_status


def render_home():
    from core.ui_movil import apply_mobile_layout
    from core.ui_controles import state_message
    apply_mobile_layout()
    data=summary.snapshot()
    st.caption(f"{data['today']} · CDMX · Consultado: {timestamp(data['at'])}")
    if st.button('Actualizar resumen', key='home_refresh', help='Vuelve a leer los datos guardados. No genera predicciones.'):
        summary.load_snapshot.clear(); st.rerun()
    services=data['services']
    sports=[services[k] for k in ('mlb','mlb_total','nfl_totales','nfl_props','liga_mx','nba') if k in services]
    cols=st.columns(3)
    cols[0].metric('Picks disponibles hoy',partial_count(sports,'picks_today'))
    cols[1].metric('Registros por revisar',partial_count(sports,'pending'))
    cols[2].metric('Partidos pendientes hoy',partial_count([services[k] for k in ('mlb','nfl_totales','liga_mx','nba') if k in services],'games_today'))
    st.markdown('''<style>
.st-key-home_sports [data-testid="stHorizontalBlock"],.st-key-home_tools [data-testid="stHorizontalBlock"]{align-items:stretch}
.st-key-home_sports [data-testid="stColumn"] > [data-testid="stVerticalBlock"],.st-key-home_tools [data-testid="stColumn"] > [data-testid="stVerticalBlock"]{height:100%;flex:1}
.st-key-home_sports [data-testid="stElementContainer"]:has(> [data-testid="stPageLink"]),.st-key-home_tools [data-testid="stElementContainer"]:has(> [data-testid="stPageLink"]){margin-top:auto}
</style>''',unsafe_allow_html=True)
    attention=[]
    for item in sports:
        if item['errors']:attention.append(item['label']+': consulta parcial')
        elif item['pending'] is not None and item['pending']>0:
            attention.append(item['label']+f": {item['pending']} resultados por actualizar")
        elif item['games_today'] is not None and item['games_today']>0 and item['picks_today']==0:
            attention.append(item['label']+': hay partidos hoy y no hay picks disponibles')
    if attention:
        with st.expander('Necesita atención',expanded=False):
            for item in attention:st.write('• '+item)
            st.caption('Abre el deporte para revisar calendario, resultados o predicciones. Una consulta parcial no significa que falten partidos.')
    from core.ui_top_picks import render_top_picks_section
    render_top_picks_section()
    st.subheader('Tu agenda · hoy primero')
    games=[]
    for source,sport in [('mlb','MLB'),('nfl_totales','NFL'),('liga_mx','Fútbol'),('nba','NBA')]:
        if source in services:
            games.extend(dict(Deporte=sport,**g) for g in services[source].get('games', []))
    if games:
        calendar=pd.DataFrame(games).sort_values(['Fecha','Deporte','Partido'])
        dates=pd.to_datetime(calendar.Fecha,errors='coerce').dt.date
        n_today=int(dates.eq(pd.Timestamp(data['today']).date()).sum())
        st.caption(f'{n_today} partidos pendientes hoy · {len(calendar)} en la agenda disponible.')
        from core.ui_agenda import render_agenda
        render_agenda(calendar)
    else:state_message('No hay próximos partidos disponibles en los calendarios consultados.')
    st.subheader('Tus deportes')
    all_groups=[('MLB','⚾','mlb',['mlb','mlb_total'],'pages/1_⚾_MLB.py'),
                ('NFL','🏈','nfl_totales',['nfl_totales','nfl_props'],'pages/2_🏈_NFL.py'),
                ('Fútbol','⚽','liga_mx',['liga_mx'],'pages/3_⚽_Futbol.py'),
                ('NBA','🏀','nba',['nba'],'pages/4_🏀_NBA.py')]
    groups=[g for g in all_groups if g[2] in services]
    with st.container(key='home_sports'):
        for col,(name,icon,calendar,keys,page) in zip(st.columns(len(groups) or 1),groups):
            with col,st.container(border=True,height='stretch',key='home_sport_'+calendar):
                st.markdown(f'### {icon} {name}')
                st.metric('Partidos pendientes hoy',count(services[calendar]['games_today']))
                for key in keys:
                    item=services[key]
                    label=item['label'].split(' · ')[-1]
                    p_today = count(item['picks_today'])
                    t_last = timestamp(item['last_data'],key=='mlb',key in ('mlb_total','liga_mx','nba'))
                    st.markdown(
                        f'<div class="sport-market-chip">'
                        f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                        f'<b style="color:#f1f5f9; font-size:0.82rem;">{label}</b>'
                        f'<span class="sport-chip-badge">{p_today} picks</span>'
                        f'</div>'
                        f'<div style="font-size:0.68rem; color:#8fa0b5; margin-top:0.25rem;">Último registro · {t_last}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                if any(services[key]['errors'] for key in keys):st.caption('Información parcial · vuelve a consultar o actualiza este deporte.')
                st.page_link(page,label='Abrir '+name,use_container_width=True)
    st.caption('Fútbol cubre 8 ligas principales con cuotas oficiales DraftKings. NBA y Fútbol operan sin consumo de créditos.')
    with st.container(key='home_tools'):
        with st.container(border=True,key='home_performance_card'):
            st.markdown(
                '<div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.4rem;">'
                '<div>'
                '<span class="perf-tag-badge">AUDITORÍA Y VALIDACIÓN</span>'
                '<h3 style="margin:0.35rem 0 0.15rem; font-size:1.25rem; font-weight:900; color:#ffffff;">📊 Rendimiento del Oráculo</h3>'
                '<p style="margin:0; font-size:0.84rem; color:#94a3b8;">Evolución de bankroll, comparación de mercados, ROI verificado y validación estadística de todos los modelos.</p>'
                '</div>'
                '</div>',
                unsafe_allow_html=True
            )
            st.page_link('pages/5_📊_Rendimiento.py',label='Abrir Rendimiento',use_container_width=True)
    from core.ui_agenda import render_availability,CSS
    st.markdown(CSS,unsafe_allow_html=True)
    table=[{'Servicio':item['label'],'Picks hoy':count(item['picks_today']),
            'Por revisar':count(item['pending']),
            'Último registro':timestamp(item['last_data'],item['service']=='mlb',item['service'] in ('mlb_total','liga_mx','nba')),
            'Estado':'Consulta parcial' if item['errors'] else age_status(item['last_data'])} for item in sports]
    render_availability(table)
