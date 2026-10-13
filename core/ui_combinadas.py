"""Ranking y constructor de combinadas; consulta de datos guardados sin créditos."""
from datetime import datetime,timezone
from pathlib import Path
import json
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.combinadas_datos import read_candidates
from core.combinadas import prepare_candidates,recommend,combination
from core.ui_movil import apply_mobile_layout
from core.ui_picks import render_pick

ROOT=Path(__file__).resolve().parents[1]


@st.cache_data(ttl=60,show_spinner=False)
def load_candidates():
    conn=None
    try:
        try:conn=get_db_connection()
        except Exception:pass
        return read_candidates(conn,ROOT)
    finally:
        if conn is not None:conn.close()


def show_pick(pick):
    details=[('Inicio',pick['inicio_utc'].tz_convert('America/Mexico_City').strftime('%d/%m · %H:%M CDMX') if pick['inicio_utc'] is not None else 'Por confirmar'),
             ('Revisión', ' · '.join(pick['notes']) or 'Sin alerta registrada')]
    render_pick(pick,market=pick['mercado'],details=details,allow_register=False)


def render_combinations():
    apply_mobile_layout()
    st.markdown('''<style>
[data-testid="stAppViewContainer"]{background:radial-gradient(circle at 85% 0%,rgba(183,255,60,.06),transparent 30rem),#080c13;color:#eef3f8}
[data-testid="stHeader"]{background:transparent}
.parlay-hero{padding:1.1rem;border:1px solid #35462e;border-radius:14px;background:linear-gradient(130deg,#182719,#101722);margin-bottom:1rem}
.parlay-kicker{font-size:.7rem;font-weight:800;letter-spacing:.13em;color:#b7ff3c}
.parlay-hero p{color:#afbdcc;margin-bottom:0;line-height:1.5}
</style><div class="parlay-hero"><div class="parlay-kicker">MLB · NFL · LIGA MX</div><h2>Arma tu combinada</h2><p>Compara los picks guardados y elige selecciones de partidos distintos.</p></div>''',unsafe_allow_html=True)
    st.title('Combinadas')
    st.caption('Ordenadas por confianza del modelo. Las probabilidades de distintos modelos pueden tener distinta calibración.')
    if st.button('Recargar picks guardados',key='parlay_reload',help='Lee los datos existentes. No genera predicciones ni consulta cuotas.'):
        load_candidates.clear();st.rerun()
    options,errors=load_candidates()
    for error in errors:st.caption(error)
    now=datetime.now(timezone.utc)
    controls=st.columns(3)
    with controls[0]:window=st.selectbox('Partidos', ['Hoy','Próximos 7 días'],key='parlay_window')
    with controls[1]:count=st.selectbox('Selecciones',[2,3,4,5],index=1,key='parlay_count')
    with controls[2]:minimum=st.slider('Confianza mínima (%)',0,95,60,5,key='parlay_confidence')
    candidates=prepare_candidates(options,now,days=1 if window=='Hoy' else 7)
    sports=st.multiselect('Deportes',['MLB','NFL','Liga MX'],default=['MLB','NFL','Liga MX'],key='parlay_sports')
    filtered=[p for p in candidates if p['deporte'] in sports and p['probabilidad']>=minimum/100]
    suggested=recommend(filtered,count,minimum/100)
    with st.container(key='parlay_proposal'):
        st.subheader('Propuesta por confianza')
        st.caption('Una selección por partido; se excluyen inicios sin verificar, alertas de lesión y cuotas con fecha antigua conocida.')
        if len(suggested)<2:
            st.info('Todavía no hay dos partidos distintos elegibles para proponer una combinada con estos filtros.')
        else:
            if len(suggested)<count:st.caption(f'Solo hay {len(suggested)} partidos elegibles; no se completan con picks de menor confianza.')
            lookup={p['id']:p for p in filtered if p['automatic']}
            # El cambio de filtros regenera una propuesta; las ediciones se conservan mientras no cambien.
            signature=json.dumps([window,count,minimum,sports,sorted(lookup)])
            if st.session_state.get('parlay_signature')!=signature:
                st.session_state['parlay_legs']=[p['id'] for p in suggested]
                st.session_state['parlay_signature']=signature
            chosen=st.multiselect('Editar selecciones',list(lookup),key='parlay_legs',max_selections=5,
                format_func=lambda key:f"{lookup[key]['deporte']} · {lookup[key]['partido']} · {lookup[key]['seleccion']} · {lookup[key]['probabilidad']:.1%}")
            selected=[lookup[key] for key in chosen]
            result=combination(selected,datetime.now(timezone.utc))
            if not result['ok']:st.warning(result['reason'])
            else:
                metrics=st.columns(3)
                metrics[0].metric('Selecciones',len(selected))
                metrics[1].metric('Estimación bajo independencia',f"{result['probability']:.1%}",help='Producto de las probabilidades individuales; no es una probabilidad conjunta calibrada.')
                metrics[2].metric('Cuota decimal orientativa',f"{result['odds']:.2f}" if result['odds'] is not None else 'Por confirmar')
                st.caption('La estimación supone independencia y puede ser inexacta. La cuota orientativa es el producto de cuotas guardadas de la misma casa; confirma la combinación y el precio final en tu casa de apuestas.')
                if result['quote_pending']:st.caption('Falta alguna cuota o su casa no está verificada. No se calcula una cuota combinada ni un pago.')
                for i in range(0,len(selected),2):
                    for col,pick in zip(st.columns(2),selected[i:i+2]):
                        with col:show_pick(pick)
                export=pd.DataFrame([{k:p.get(k) for k in ['deporte','partido','mercado','seleccion','probabilidad','cuota','casa','inicio_utc','cuota_capturada_utc']} for p in selected])
                st.download_button('Descargar propuesta',export.to_csv(index=False).encode('utf-8-sig'),'combinada_propuesta.csv','text/csv',key='parlay_export')
    st.subheader('Picks por confianza')
    if not filtered:
        st.caption('No hay picks guardados que cumplan los filtros. Actualiza las predicciones desde la pestaña del deporte correspondiente.')
        return
    table=pd.DataFrame([dict(Deporte=p['deporte'],Partido=p['partido'],Mercado=p['mercado'],Selección=p['seleccion'],
        Confianza=p['probabilidad'],Cuota=p['cuota'],Casa=p['casa'],
        Disponibilidad=' · '.join(p['notes']) or ('Elegible · cuota pendiente' if p['cuota'] is None else 'Elegible')) for p in filtered])
    st.dataframe(table,hide_index=True,width='stretch',
                 column_config={'Confianza':st.column_config.NumberColumn(format='percent',help='Probabilidad estimada por el modelo.')})
    st.caption('El ranking puede incluir picks que requieren revisión. Solo los elegibles entran en la propuesta automática. Esta sección no registra apuestas ni modifica tu bankroll.')
