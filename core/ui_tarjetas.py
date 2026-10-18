"""Tarjetas de pronóstico y contexto verificable, sin formularios de apuestas."""
from html import escape
import hashlib
import json
import math
import uuid
import pandas as pd
import streamlit as st
from core import bankroll as bank
from core.db import get_db_connection


from core.ui_diseno import CSS



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


def quote_text(pick):
    value = pick.get('cuota_capturada_utc')
    if value is None or pd.isna(value): return 'Hora no disponible'
    stamp = pd.to_datetime(value, errors='coerce')
    if pd.isna(stamp): return 'Hora no disponible'
    # Only adapters for sources with documented UTC timestamps set this field.
    if stamp.tzinfo is None: stamp = stamp.tz_localize('UTC')
    return stamp.tz_convert('America/Mexico_City').strftime('%d/%m/%Y · %H:%M CDMX')


def card_html(pick, *, market, state='', details=()):
    safe = lambda v: escape(str(v), quote=True)
    probability = number(pick.get('probabilidad'))
    odds = number(pick.get('cuota'))
    odds_text = f'{odds:.2f}' if odds and odds > 1 else 'Por confirmar'
    primary = [] if any(k=='Probabilidad Over 2.5' for k,v in details) else [('Probabilidad estimada', percent(probability))]
    # Historical results are immediately visible; projections live in details.
    primary.extend((k, v) for k, v in details if k in ('Unidades', 'Profit simulado', 'Stake simulado', 'Beneficio', 'Monto apostado'))
    # Liga MX has no market quote: keep both probabilities on its single card.
    primary.extend((k, v) for k, v in details if k in ('Probabilidad Over 2.5', 'Probabilidad Under 2.5'))
    values = ''.join(f'<div><span>{safe(k)}</span><strong>{safe(v)}</strong></div>' for k,v in primary)
    secondary = [(k, v) for k, v in details if (k, v) not in primary]
    secondary.append(('Captura de cuota',quote_text(pick)))
    detail_html = ''.join(f'<div class="oracle-detail"><span>{safe(k)}</span><strong>{safe(v)}</strong></div>' for k,v in secondary)
    disclosure = f'<details class="oracle-details"><summary>Ver detalles</summary>{detail_html}</details>' if secondary else ''
    status = str(state).upper()
    css = 'won' if 'GANADA' in status else 'lost' if 'PERDIDA' in status else 'push' if 'PUSH' in status else 'pending' if 'PENDIENTE' in status else ''
    status_label=state
    if 'GANADA' in status:status_label='✅ Ganada'
    elif 'PERDIDA' in status:status_label='❌ Perdida'
    elif 'PUSH' in status:status_label='↔ Push'
    elif 'PENDIENTE' in status:status_label='Pendiente'
    width = min(max((probability or 0)*100, 0), 100)
    return (f'<div class="oracle-pick {css}"><div class="context">{safe(pick["deporte"])} · {safe(market)} · {safe(pick["casa"])}</div>'
        f'<h3>{safe(pick["partido"])}</h3><div class="context">{safe(date_text(pick))}</div>'
        f'<div class="oracle-selection"><span>{safe(pick["seleccion"])}</span><span class="oracle-odds">Cuota {safe(odds_text)}</span></div>'
        f'<div class="oracle-values">{values}</div><div class="oracle-bar"><i style="width:{width:.1f}%"></i></div>'
        f'<div class="oracle-result">{safe(status_label)}</div>'
        + (f'<div class="context oracle-confidence-context">{safe(pick["contexto_confianza"])}</div>' if pick.get('contexto_confianza') else '') +
        f'{disclosure}</div>')


def pick_key(pick):
    identity = [pick['origen'], pick['referencia'], pick['seleccion']]
    return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:20]


def render_pick(pick, *, market, state='', details=(), allow_register=True):
    from core.ui_diseno import apply_design
    st.markdown(CSS, unsafe_allow_html=True)
    apply_design()
    if allow_register:
        from core.contexto_confianza import for_pick,text
        pick=dict(pick,contexto_confianza=text(for_pick(pick)))
    st.markdown(card_html(pick, market=market, state=state, details=details), unsafe_allow_html=True)



def registration(pick):
    """Compatibilidad para vistas antiguas: el registro de apuestas fue retirado."""
    return None


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
                origen='nfl_prop' if prop else 'nfl_total', referencia=reference,
                modelo=row.get('modelo_version'),mercado_confianza=row.get('tipo_prop') if prop else 'Totales',
                cuota_capturada_utc=row.get('timestamp_captura') if prop else None)


def mlb_total_pick(row):
    side = row['seleccion']
    return dict(fecha=row.get('fecha_oficial', row.get('fecha', pd.Timestamp(row['start_utc']).date())), deporte='MLB',
        partido=f"{row['visitante']} @ {row['local']}", seleccion=f"{side} {float(row['linea']):g}",
        casa='DraftKings', cuota=number(row['cuota_'+side.lower()]), probabilidad=number(row['prob_seleccion']),
        cuota_capturada_utc=row.get('captured_utc'),modelo=row.get('model_id'),p_push=row.get('p_push'),mercado_confianza='Totales',
        origen='mlb_total', referencia=dict(game_id=str(row['game_id']),side=side,line=float(row['linea']),inicio_utc=kickoff(row['start_utc'])))


def liga_pick(row, side):
    date = pd.Timestamp(row['fecha']).date().isoformat()
    return dict(fecha=date, deporte='Liga MX', partido=f"{row['visitante']} @ {row['local']}",
        seleccion=side+' 2.5', casa='DraftKings', cuota=None, probabilidad=number(row['p_'+side.lower()+'25']),
        origen='liga_mx', referencia=dict(fecha=date,local=row['local'],visitante=row['visitante'],
            side=side,line=2.5,inicio_utc=kickoff(row['inicio_utc'])))


def render_liga_matches(frame):
    """Una tarjeta por encuentro, con ambas probabilidades y sin registro de apuestas."""
    for offset in range(0, len(frame), 2):
        columns = st.columns(2)
        for column, (_, row) in zip(columns, frame.iloc[offset:offset+2].iterrows()):
            with column:
                side = 'OVER' if row['p_over25'] >= row['p_under25'] else 'UNDER'
                render_pick(liga_pick(row, side), market='Total de goles', state='Modelo congelado',
                    details=[('Probabilidad Over 2.5', percent(row['p_over25'])),
                             ('Probabilidad Under 2.5', percent(row['p_under25']))])
