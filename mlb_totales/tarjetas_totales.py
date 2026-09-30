"""Tarjetas de totales con las mismas clases visuales de la página MLB."""
from html import escape
from textwrap import dedent
import pandas as pd


EXTRA_CSS = '''<style>
.mlb-total-card { margin-bottom: .8rem; }
.mlb-total-card .mlb-card-title, .mlb-total-card .mlb-audit-match,
.mlb-total-card .mlb-card-meta { overflow-wrap: anywhere; }
.mlb-total-card .mlb-odds { white-space: nowrap; }
.mlb-total-card .mlb-card-meta { line-height: 1.55; }
.mlb-audit-card.push::before { background: #62c4e8; }
.mlb-audit-card.pending::before { background: #8994a5; }
.mlb-audit-card.review::before { background: #f5c36b; }
.mlb-result-badge.push { background: #173444; color: #8bd9f5; }
.mlb-result-badge.pending { background: #28313d; color: #b9c3d1; }
.mlb-result-badge.review { background: #3d321d; color: #f5c36b; }
.mlb-total-footer { margin-top: .65rem; color: #8e99a9; font-size: .72rem; line-height: 1.55; }
.mlb-total-card .mlb-audit-values { grid-template-columns: repeat(4,minmax(0,1fr)); }
@media (max-width: 760px) {
 .mlb-total-card .mlb-audit-values { grid-template-columns: repeat(2,minmax(0,1fr)); }
}
</style>'''


def safe(value):
    return escape(str(value),quote=True)


def cell(label,value,clase=''):
    return (f'<div><span class="mlb-value-label">{safe(label)}</span>'
            f'<span class="mlb-value {clase}">{safe(value)}</span></div>')


def pick_html(r):
    confidence=float(r['prob_seleccion'])*100
    side=str(r['seleccion']).lower()
    odds=float(r['cuota_'+side])
    ev=float(r['ev_'+side])*100
    state='EV POSITIVO' if ev>0 else 'SIN VALOR'
    if r['game_type']!='R':state+=' · PLAYOFFS'
    values=(cell('CONFIANZA',f'{confidence:.1f}%')+
            cell('EV ESTIMADO',f'{ev:+.1f}%')+
            cell('TOTAL PROYECTADO',f"{float(r['total_proyectado']):.2f}"))
    return dedent(f'''
    <div class="mlb-pick-card mlb-total-card">
      <div class="mlb-card-kicker">TOTALES MLB · DRAFTKINGS</div>
      <div class="mlb-card-title">{safe(r['visitante'])} @ {safe(r['local'])}</div>
      <div class="mlb-card-meta">Abridores: {safe(r['abridor_visitante'])} · {safe(r['abridor_local'])}</div>
      <div class="mlb-pick-line"><span class="mlb-pick-name">{safe(r['seleccion'])} {float(r['linea']):g}</span>
        <span class="mlb-odds">Cuota {odds:.2f}</span></div>
      <div class="mlb-card-values">{values}</div>
      <div class="mlb-confidence"><span style="width:{min(max(confidence,0),100):.1f}%"></span></div>
      <div class="mlb-total-footer">OVER {float(r['p_over'])*100:.1f}% · UNDER {float(r['p_under'])*100:.1f}% · Push {float(r['p_push'])*100:.1f}%<br>
        {state} · Cuota capturada hace {max(float(r['age_minutes']),0):.0f} min</div>
    </div>''').strip()


def performance_html(r):
    status=str(r['resultado'])
    css,label={'GANADA':('won','GANADA'),'PERDIDA':('lost','PERDIDA'),
        'PUSH':('push','PUSH'),'PENDIENTE':('pending','PENDIENTE'),
        'REVISAR_REGLAS':('review','REVISAR REGLAS')}.get(status,('pending','PENDIENTE'))
    profit=r['unidades']
    profit_text=f'{float(profit):+.2f} u' if pd.notna(profit) else ('Revisión' if css=='review' else 'Pendiente')
    profit_css=('mlb-profit-positive' if float(profit)>=0 else 'mlb-profit-negative') if pd.notna(profit) else ''
    confidence=float(r['confianza_pct'])
    values=(cell('CONFIANZA ORIGINAL',f'{confidence:.1f}%')+cell('STAKE','1 u')+
        cell('CUOTA ORIGINAL',f"{float(r['cuota_seleccion']):.2f}")+
        cell('UNIDADES',profit_text,profit_css))
    score='Resultado pendiente'
    if pd.notna(r.get('home_runs')) and pd.notna(r.get('away_runs')):
        score=f"Marcador: {int(r['away_runs'])} – {int(r['home_runs'])} · Total {int(r['away_runs']+r['home_runs'])}"
    date=pd.Timestamp(r['fecha_oficial']).strftime('%d/%m/%Y')
    return dedent(f'''
    <div class="mlb-audit-card mlb-total-card {css}">
      <div class="mlb-audit-head"><span class="mlb-audit-date">{date} · DraftKings</span>
        <span class="mlb-result-badge {css}">{label}</span></div>
      <div class="mlb-audit-match">{safe(r['equipo_visitante'])} @ {safe(r['equipo_local'])}</div>
      <div class="mlb-audit-pick">Pick original: {safe(r['seleccion'])} {float(r['linea']):g}</div>
      <div class="mlb-audit-values">{values}</div>
      <div class="mlb-confidence"><span style="width:{min(max(confidence,0),100):.1f}%"></span></div>
      <div class="mlb-total-footer">{safe(score)} · EV original {float(r['ev'])*100:+.1f}%<br>
        Registrado {safe(r['recorded_utc'])} UTC</div>
    </div>''').strip()


def render_cards(frame,performance=False):
    import streamlit as st
    st.markdown(EXTRA_CSS,unsafe_allow_html=True)
    render=performance_html if performance else pick_html
    for start in range(0,len(frame),2):
        columns=st.columns(2,gap='medium')
        for column,(_,row) in zip(columns,frame.iloc[start:start+2].iterrows()):
            with column:st.markdown(render(row),unsafe_allow_html=True)
