"""Tarjetas y registro explícito de apuestas realizadas, sin consultar cuotas."""
from html import escape
import hashlib
import json
import math
import uuid
import pandas as pd
import streamlit as st
from core import bankroll as bank
from core.db import get_db_connection


CSS = '''<style>
.oracle-pick{background:#111720;border:1px solid #273245;border-top:3px solid #b7ff3c;border-radius:14px;padding:1rem;margin:.4rem 0;overflow-wrap:anywhere;color:#eef3f8}
.oracle-pick .context{color:#a8b4c5;font-size:.82rem;line-height:1.5}
.oracle-pick h3{font-size:1.15rem;margin:.35rem 0 .6rem;color:#eef3f8}
.oracle-selection{display:flex;justify-content:space-between;gap:1rem;font-size:1.1rem;font-weight:800;margin:.65rem 0}
.oracle-values{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem}
.oracle-values span{display:block;color:#a8b4c5;font-size:.72rem}.oracle-values strong{font-size:.95rem;color:#eef3f8}
.oracle-bar{height:5px;background:#273245;border-radius:5px;margin:.8rem 0}.oracle-bar i{display:block;height:5px;background:#b7ff3c;border-radius:5px}
.oracle-pick.lost{border-top-color:#ff6b76}.oracle-pick.push{border-top-color:#f6c761}.oracle-pick.pending{border-top-color:#8994a5}
@media(max-width:760px){.oracle-values{grid-template-columns:repeat(2,minmax(0,1fr))}.oracle-selection{flex-wrap:wrap}}
</style>'''


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def percent(value):
    value = number(value)
    return f'{value:.1%}' if value is not None and 0 <= value <= 1 else 'N/D'


def kickoff(value):
    if value is None or pd.isna(value): return None
    t = pd.Timestamp(value)
    return (t.tz_localize('UTC') if t.tzinfo is None else t.tz_convert('UTC')).isoformat()


def date_text(pick):
    start = pick.get('referencia', {}).get('inicio_utc')
    if start:
        return pd.Timestamp(start).tz_convert('America/Mexico_City').strftime('%d/%m/%Y · %H:%M CDMX')
    date = pd.to_datetime(pick['fecha'], errors='coerce')
    return (date.strftime('%d/%m/%Y') if pd.notna(date) else 'Fecha pendiente') + ' · Hora no verificada'


def card_html(pick, *, market, state='', details=()):
    safe = lambda v: escape(str(v), quote=True)
    probability = number(pick.get('probabilidad'))
    odds = number(pick.get('cuota'))
    cells = [('Probabilidad', percent(probability)), ('Cuota decimal', f'{odds:.2f}' if odds and odds > 1 else 'Por confirmar')]
    cells.extend(details)
    values = ''.join(f'<div><span>{safe(k)}</span><strong>{safe(v)}</strong></div>' for k,v in cells)
    width = min(max((probability or 0)*100, 0), 100)
    status = str(state).upper()
    css = 'lost' if 'PERDIDA' in status else 'push' if 'PUSH' in status else 'pending' if 'PENDIENTE' in status else ''
    return (f'<div class="oracle-pick {css}"><div class="context">{safe(pick["deporte"])} · {safe(market)} · {safe(pick["casa"])} · {safe(state)}</div>'
            f'<h3>{safe(pick["partido"])}</h3><div class="context">{safe(date_text(pick))}</div>'
            f'<div class="oracle-selection">{safe(pick["seleccion"])}</div><div class="oracle-values">{values}</div>'
            f'<div class="oracle-bar"><i style="width:{width:.1f}%"></i></div></div>')


def pick_key(pick):
    identity = [pick['origen'], pick['referencia'], pick['seleccion']]
    return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:20]


def render_pick(pick, *, market, state='', details=(), allow_register=True):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(card_html(pick, market=market, state=state, details=details), unsafe_allow_html=True)
    if allow_register: registration(pick)


def registration(pick):
    key = pick_key(pick)
    start = pick.get('referencia', {}).get('inicio_utc')
    if start and pd.Timestamp(start) <= pd.Timestamp.now(tz='UTC'):
        st.caption('El partido ya comenzó. Registra apuestas anteriores desde Bankroll.'); return
    if st.button('Registrar en bankroll', key='open_'+key, icon='💼'):
        st.session_state['pick_draft'] = dict(pick)
        st.session_state.setdefault('pick_receipt_'+key, str(uuid.uuid4()))
    draft = st.session_state.get('pick_draft')
    if not draft or pick_key(draft) != key: return
    st.caption('Registra únicamente una apuesta que realizaste. Se conservará la confianza de esta tarjeta.')
    if not start: st.caption('La fuente no proporciona una hora verificada. Confirma que corresponde a tu apuesta.')
    with st.form('bet_'+key):
        st.write(draft['partido']+' · '+draft['seleccion'])
        odds = number(draft.get('cuota'))
        taken = st.number_input('Cuota decimal tomada', min_value=1.01, value=odds if odds and odds>1 else None, step=.01)
        amount = st.number_input('Monto apostado (MXN)', min_value=1.0, value=None, step=10.0)
        house = st.text_input('Casa donde apostaste', value=draft['casa'])
        ticket = st.text_input('Ticket o referencia (opcional)')
        confirm = st.checkbox('Confirmo que realicé esta apuesta con la cuota y el monto indicados')
        save = st.form_submit_button('Guardar apuesta realizada')
        cancel = st.form_submit_button('Cancelar')
    if cancel:
        st.session_state.pop('pick_draft', None); st.rerun()
    if not save: return
    if not confirm or taken is None or amount is None:
        st.warning('Introduce cuota y monto, y confirma la apuesta realizada.'); return
    conn = None
    try:
        conn = get_db_connection()
        bank.prepare(conn)
        bet = dict(draft, cuota=taken, monto=amount, casa=house, ticket=ticket.strip(), estado='Pendiente')
        bank.save_bet(conn, bet, st.session_state['pick_receipt_'+key])
        st.success('Apuesta guardada en Bankroll.')
        st.session_state.pop('pick_draft', None)
        st.session_state.pop('pick_receipt_'+key, None)
        st.session_state.pop('bankroll_predictions', None)
        st.cache_data.clear()
        st.page_link('pages/0_💼_Bankroll.py', label='Ver mi bankroll', icon='💼')
    except ValueError as exc:
        st.warning(str(exc))
    except Exception as exc:
        st.error(f'No se pudo guardar la apuesta ({type(exc).__name__}). Puedes reintentar.')
    finally:
        if conn is not None: conn.close()


def nfl_pick(row, prop=False):
    side = row['seleccion'] if prop else row['pick']
    line = number(row['linea'] if prop else row['total_line'])
    raw_odds = row.get('cuota_pick') if prop else row.get('odds_pick')
    try: odds = bank.decimal_odds(raw_odds)
    except (TypeError, ValueError): odds = None
    reference = dict(game_id=str(row['id_juego']), side=side, line=line)
    if prop: reference.update(id_jugador=str(row['id_jugador']), tipo_prop=str(row['tipo_prop']))
    label = (str(row['player_name'])+' · ' if prop else '') + str(side)
    if line is not None and side in ('OVER','UNDER'): label += f' {line:g}'
    return dict(fecha=row['gameday'], deporte='NFL', partido=f"{row['away_team']} @ {row['home_team']}",
                seleccion=label, casa=str(row.get('casa_apuestas') or 'DraftKings') if prop else 'DraftKings',
                cuota=odds, probabilidad=number(row['probabilidad_pick'] if prop else row['prob_pick']),
                origen='nfl_prop' if prop else 'nfl_total', referencia=reference)


def mlb_total_pick(row):
    side = row['seleccion']
    return dict(fecha=row.get('fecha_oficial', row.get('fecha', pd.Timestamp(row['start_utc']).date())), deporte='MLB',
        partido=f"{row['visitante']} @ {row['local']}", seleccion=f"{side} {float(row['linea']):g}",
        casa='DraftKings', cuota=number(row['cuota_'+side.lower()]), probabilidad=number(row['prob_seleccion']),
        origen='mlb_total', referencia=dict(game_id=str(row['game_id']),side=side,line=float(row['linea']),inicio_utc=kickoff(row['start_utc'])))


def liga_pick(row, side):
    date = pd.Timestamp(row['fecha']).date().isoformat()
    return dict(fecha=date, deporte='Liga MX', partido=f"{row['visitante']} @ {row['local']}",
        seleccion=side+' 2.5', casa='DraftKings', cuota=None, probabilidad=number(row['p_'+side.lower()+'25']),
        origen='liga_mx', referencia=dict(fecha=date,local=row['local'],visitante=row['visitante'],
            side=side,line=2.5,inicio_utc=kickoff(row['inicio_utc'])))
