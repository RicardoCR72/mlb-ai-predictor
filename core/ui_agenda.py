"""Agenda y disponibilidad del inicio; presentación sobre datos ya consultados."""
from html import escape
import pandas as pd
import streamlit as st

CSS='''<style>
.st-key-home_agenda_controls{padding:1.1rem 1.25rem;border:1px solid #1e2c3f;border-radius:15px;background:linear-gradient(135deg,#101826,#090e17);margin-bottom:.65rem;box-shadow:0 4px 18px rgba(0,0,0,0.25)}
.st-key-home_agenda_controls [data-testid="stRadio"] [role="radiogroup"]{width:100%;background:#060a10;border:1px solid #1c2738;border-radius:10px;margin-bottom:0;gap:.4rem;padding:.3rem}
.st-key-home_agenda_controls [data-testid="stRadio"] label{min-height:38px;font-variant-numeric:tabular-nums;border-radius:8px;padding:0 .75rem;font-weight:700}
.agenda-kicker{font-size:.68rem;letter-spacing:.15em;color:#b7ff3c;font-weight:850;text-transform:uppercase}
.agenda-heading{display:flex;justify-content:space-between;align-items:center;gap:.7rem;margin-bottom:.45rem}
.agenda-heading strong{font-size:1.1rem;color:#ffffff;font-weight:850}.agenda-note{color:#94a3b8;font-size:.8rem;line-height:1.5}
.agenda-count{color:#b7ff3c;background:rgba(183,255,60,0.12);border:1px solid rgba(183,255,60,0.35);padding:.25rem .65rem;border-radius:20px;white-space:nowrap;font-size:.75rem;font-weight:800}
.agenda-day{display:flex;gap:.6rem;align-items:center;margin:1.15rem 0 .55rem;color:#edf3f8;font-size:.92rem;font-weight:800}
.agenda-day::after{content:"";height:1px;background:#202c3e;flex:1}
.agenda-match{display:grid;grid-template-columns:56px minmax(0,1fr) auto;gap:1rem;align-items:center;padding:0.95rem 1.1rem;margin:.55rem 0;background:linear-gradient(135deg,#101826,#090e17);border:1px solid #1e2c3f;border-radius:14px;border-left:4px solid #b7ff3c;color:#eef3f8;transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease}
.agenda-match:hover{transform:translateY(-2px);box-shadow:0 6px 22px rgba(0,0,0,0.35);border-color:#2a3b52}
.agenda-date{border-right:1px solid #1e2c3f;padding-right:.75rem;text-align:center}.agenda-date b{display:block;font-size:1.4rem;line-height:1.1;color:#ffffff;font-weight:850}.agenda-date span{color:#8fa0b5;font-size:.68rem;text-transform:uppercase;font-weight:750}
.agenda-teams{font-size:1rem;font-weight:800;color:#f1f5f9;overflow-wrap:anywhere;margin-top:.25rem}.agenda-sport{display:inline-block;font-size:.68rem;font-weight:850;letter-spacing:.08em;text-transform:uppercase}
.agenda-match.nfl{border-left-color:#b7ff3c}.agenda-match.nfl .agenda-sport{color:#b7ff3c}
.agenda-match.liga{border-left-color:#00e676}.agenda-match.liga .agenda-sport{color:#00e676}
.agenda-match.futbol{border-left-color:#00e676}.agenda-match.futbol .agenda-sport{color:#00e676}
.agenda-match.nba{border-left-color:#ff6b35}.agenda-match.nba .agenda-sport{color:#ff6b35}
.agenda-match.mlb{border-left-color:#00e5ff}.agenda-match.mlb .agenda-sport{color:#00e5ff}
.agenda-time{font-size:.8rem;color:#cbd5e1;background:rgba(0,0,0,0.45);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:.45rem .75rem;max-width:210px;text-align:right;font-weight:750}
.st-key-home_calendar_full [data-testid="stExpander"],.st-key-home_availability_full [data-testid="stExpander"]{border:1px solid #1e2c3f!important;border-radius:14px!important;background:linear-gradient(135deg,#101826,#090e17)!important}
.st-key-home_calendar_full [data-testid="stExpander"] summary,.st-key-home_availability_full [data-testid="stExpander"] summary{min-height:52px;padding:.85rem 1rem;color:#edf3f8;font-weight:750}
.st-key-home_calendar_full [data-testid="stExpander"] summary:hover,.st-key-home_availability_full [data-testid="stExpander"] summary:hover{background:#152033;border-radius:13px}
.availability-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.85rem;margin:.75rem 0}
.availability-card{padding:1.1rem;border:1px solid #1e2c3f;border-radius:14px;background:linear-gradient(135deg,#101826,#090e17);color:#edf3f8;overflow-wrap:anywhere;box-shadow:0 4px 14px rgba(0,0,0,0.2);transition:transform .2s ease}
.availability-card:hover{transform:translateY(-2px);border-color:#2b3e58}
.availability-head{display:flex;justify-content:space-between;gap:.5rem;align-items:center;font-weight:800;font-size:.92rem}.availability-state{font-size:.68rem;border-radius:20px;padding:.25rem .6rem;font-weight:800;letter-spacing:.04em;white-space:nowrap}
.availability-state.fresh{border:1px solid rgba(0,230,118,0.35);color:#00e676;background:rgba(0,230,118,0.12)}
.availability-state.review{border:1px solid rgba(255,170,0,0.35);color:#ffaa00;background:rgba(255,170,0,0.12)}
.availability-values{display:flex;gap:1.8rem;margin:.85rem 0}.availability-values strong{display:block;font-size:1.35rem;font-weight:850;color:#ffffff}.availability-values span{font-size:.72rem;color:#8fa0b5;font-weight:700}
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
        sport=str(row['Deporte']);css={'NFL':'nfl','Liga MX':'liga','Fútbol':'futbol','NBA':'nba'}.get(sport,'mlb')
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
        with st.expander('Detalle de disponibilidad y estado de fuentes'):
            st.markdown(header('Monitor de Fuentes y Datos','Consulta los picks, pendientes y la fecha del último registro de cada deporte.',f'{len(table)} servicios'),unsafe_allow_html=True)
            cards=[]
            for row in table:
                state=row['Estado']
                css='fresh' if state=='Actualizado' else 'review' if state!='Sin datos' else ''
                label='● Actualizado' if state=='Actualizado' else '● Consulta parcial' if state=='Consulta parcial' else '● Sin datos' if state=='Sin datos' else '● Revisar fecha'
                cards.append('<div class="availability-card"><div class="availability-head">'
                    f'<span>{escape(row["Servicio"])}</span><span class="availability-state {css}">{label}</span></div>'
                    f'<div class="availability-values"><div><strong>{escape(row["Picks hoy"])}</strong><span>Picks hoy</span></div>'
                    f'<div><strong>{escape(row["Por revisar"])}</strong><span>Por revisar</span></div></div>'
                    f'<div class="agenda-note" style="border-top:1px solid rgba(255,255,255,0.06); padding-top:0.4rem; margin-top:0.3rem;">Último registro · <b style="color:#ffffff;">{escape(row["Último registro"])}</b></div></div>')
            st.markdown('<div class="availability-grid">'+''.join(cards)+'</div>',unsafe_allow_html=True)
            st.caption('Por revisar cuenta selecciones sin resultado. Una fecha antigua puede corresponder a días sin partidos.')
            with st.expander('Ver disponibilidad en tabla'):
                st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)

