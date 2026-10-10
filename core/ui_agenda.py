"""Agenda y disponibilidad del inicio; presentación sobre datos ya consultados."""
from html import escape
import pandas as pd
import streamlit as st

CSS='''<style>
.st-key-home_agenda_controls{padding:1rem 1.15rem;border:1px solid #2b3a30;border-radius:15px;background:linear-gradient(125deg,#172219,#111720 65%);margin-bottom:.5rem}
.st-key-home_agenda_controls [data-testid="stRadio"] [role="radiogroup"]{width:100%;background:#0c1314;border-color:#314334;margin-bottom:0;gap:.4rem}
.st-key-home_agenda_controls [data-testid="stRadio"] label{min-height:44px;font-variant-numeric:tabular-nums}
.agenda-kicker{font-size:.66rem;letter-spacing:.15em;color:#b7ff3c;font-weight:800}
.agenda-heading{display:flex;justify-content:space-between;align-items:center;gap:.7rem;margin-bottom:.55rem}
.agenda-heading strong{font-size:1rem;color:#eef3f8}.agenda-note{color:#9cabbc;font-size:.78rem;line-height:1.5}
.agenda-count{color:#b7ff3c;background:#20301b;border:1px solid #3a512b;padding:.28rem .6rem;border-radius:20px;white-space:nowrap;font-size:.73rem}
.agenda-day{display:flex;gap:.6rem;align-items:center;margin:1.1rem 0 .55rem;color:#edf3f8;font-size:.92rem;font-weight:750}
.agenda-day::after{content:"";height:1px;background:#273245;flex:1}
.agenda-match{display:grid;grid-template-columns:54px minmax(0,1fr) auto;gap:1rem;align-items:center;padding:1rem;margin:.5rem 0;background:linear-gradient(125deg,#141d29,#0e151f);border:1px solid #2b3748;border-radius:13px;border-left:3px solid #b7ff3c;color:#eef3f8}
.agenda-date{border-right:1px solid #2b3748;padding-right:.75rem;text-align:center}.agenda-date b{display:block;font-size:1.4rem;line-height:1.1}.agenda-date span{color:#9cabbc;font-size:.66rem;text-transform:uppercase}
.agenda-teams{font-size:.98rem;font-weight:750;overflow-wrap:anywhere;margin-top:.35rem}.agenda-sport{display:inline-block;color:#b7ff3c;font-size:.65rem;font-weight:800;letter-spacing:.06em}
.agenda-match.nfl{border-left-color:#73b6ff}.agenda-match.nfl .agenda-sport{color:#73b6ff}.agenda-match.liga{border-left-color:#bc9dff}.agenda-match.liga .agenda-sport{color:#bc9dff}
.agenda-time{font-size:.8rem;color:#a9bacd;background:#1b2634;border-radius:8px;padding:.45rem .65rem;max-width:190px;text-align:right}
.st-key-home_calendar_full [data-testid="stExpander"],.st-key-home_availability_full [data-testid="stExpander"]{border:1px solid #334253!important;border-radius:14px!important;background:linear-gradient(125deg,#131d28,#0e151e)}
.st-key-home_calendar_full [data-testid="stExpander"] summary,.st-key-home_availability_full [data-testid="stExpander"] summary{min-height:58px;padding:.9rem 1rem;color:#edf3f8;font-weight:750}
.st-key-home_calendar_full [data-testid="stExpander"] summary:hover,.st-key-home_availability_full [data-testid="stExpander"] summary:hover{background:#192839;border-radius:13px}
.availability-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.7rem;margin:.7rem 0}
.availability-card{padding:1rem;border:1px solid #2c3849;border-radius:12px;background:#111a25;color:#edf3f8;overflow-wrap:anywhere}
.availability-head{display:flex;justify-content:space-between;gap:.5rem;align-items:flex-start;font-weight:750;font-size:.87rem}.availability-state{font-size:.63rem;border:1px solid #3d4e63;border-radius:20px;padding:.25rem .5rem;color:#adbbcb;white-space:nowrap}
.availability-state.fresh{border-color:#40552d;color:#b7ff3c;background:#1b2915}.availability-state.review{border-color:#69502c;color:#eac384;background:#2b2218}
.availability-values{display:flex;gap:1.5rem;margin:.8rem 0}.availability-values strong{display:block;font-size:1.15rem}.availability-values span{font-size:.7rem;color:#9cabbc}
@media(max-width:760px){.agenda-match{grid-template-columns:40px minmax(0,1fr);gap:.7rem;padding:.85rem}.agenda-time{grid-column:2;justify-self:start;text-align:left;max-width:100%;font-size:.73rem}.agenda-teams{font-size:.92rem}.agenda-heading{align-items:flex-start;flex-wrap:wrap}.availability-grid{grid-template-columns:1fr}.availability-head{flex-wrap:wrap}.st-key-home_agenda_controls{padding:.85rem}}
</style>'''


def header(title, note, badge):
    return ('<div class="agenda-kicker">TU AGENDA</div><div class="agenda-heading">'
            f'<strong>{escape(title)}</strong><span class="agenda-count">{escape(badge)}</span></div>'
            f'<div class="agenda-note">{escape(note)}</div>')


def agenda_html(frame, *, grouped=False):
    days=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    months=['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC']
    parts=[];previous=None
    for row in frame.to_dict('records'):
        stamp=pd.to_datetime(row['Fecha'],errors='coerce')
        day=str(row['Fecha'])
        if grouped and day!=previous:
            label=f'{days[stamp.weekday()]} · {stamp.strftime("%d/%m/%Y")}' if pd.notna(stamp) else day
            parts.append(f'<div class="agenda-day">{escape(label)}</div>')
            previous=day
        number=stamp.strftime('%d') if pd.notna(stamp) else '—'
        month=months[stamp.month-1] if pd.notna(stamp) else ''
        sport=str(row['Deporte']);css={'NFL':'nfl','Liga MX':'liga'}.get(sport,'mlb')
        parts.append(f'<article class="agenda-match {css}"><div class="agenda-date"><b>{number}</b><span>{month}</span></div>'
            f'<div><span class="agenda-sport">{escape(sport)}</span><div class="agenda-teams">{escape(str(row["Partido"]))}</div></div>'
            f'<div class="agenda-time">{escape(str(row["Horario"]))}</div></article>')
    return ''.join(parts)


def render_agenda(calendar):
    st.markdown(CSS,unsafe_allow_html=True)
    with st.container(key='home_agenda_controls'):
        st.markdown(header('Partidos a mostrar','Elige cuánto de tu agenda quieres ver.',f'{len(calendar)} encuentros'),unsafe_allow_html=True)
        # Preserve the existing key and numeric values when changing the control.
        if st.session_state.get('home_calendar_limit',5) not in (5,10,20,'Todos'):
            st.session_state.pop('home_calendar_limit',None)
        limit=st.radio('Partidos a mostrar',[5,10,20,'Todos'],horizontal=True,label_visibility='collapsed',
            format_func=lambda value:f'{value} partidos' if value!='Todos' else 'Todos',key='home_calendar_limit')
    visible=calendar if limit=='Todos' else calendar.head(int(limit))
    st.markdown(agenda_html(visible),unsafe_allow_html=True)
    st.caption(f'{len(visible)} de {len(calendar)} partidos · próximos siete días.')
    with st.container(key='home_calendar_full'):
        with st.expander('Ver calendario completo'):
            st.markdown(header('Agenda de la semana','Encuentros organizados por día.',f'{len(calendar)} partidos'),unsafe_allow_html=True)
            st.markdown(agenda_html(calendar,grouped=True),unsafe_allow_html=True)
            with st.expander('Ver calendario en tabla'):
                st.dataframe(calendar,hide_index=True,use_container_width=True)


def render_availability(table):
    with st.container(key='home_availability_full'):
        with st.expander('Detalle de disponibilidad'):
            st.markdown(header('Disponibilidad de tus deportes','Consulta los picks, pendientes y la fecha del último registro.',f'{len(table)} servicios'),unsafe_allow_html=True)
            cards=[]
            for row in table:
                state=row['Estado']
                css='fresh' if state=='Actualizado' else 'review' if state!='Sin datos' else ''
                label='Dato reciente' if state=='Actualizado' else 'Consulta parcial' if state=='Consulta parcial' else 'Sin datos' if state=='Sin datos' else 'Revisar fecha'
                cards.append('<div class="availability-card"><div class="availability-head">'
                    f'<span>{escape(row["Servicio"])}</span><span class="availability-state {css}">{label}</span></div>'
                    f'<div class="availability-values"><div><strong>{escape(row["Picks hoy"])}</strong><span>Picks hoy</span></div>'
                    f'<div><strong>{escape(row["Por revisar"])}</strong><span>Por revisar</span></div></div>'
                    f'<div class="agenda-note">Último registro<br>{escape(row["Último registro"])}</div></div>')
            st.markdown('<div class="availability-grid">'+''.join(cards)+'</div>',unsafe_allow_html=True)
            st.caption('Por revisar cuenta selecciones sin resultado. Una fecha antigua puede corresponder a días sin partidos.')
            with st.expander('Ver disponibilidad en tabla'):
                st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
