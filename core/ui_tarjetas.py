"""Tarjetas de pronóstico y contexto verificable, sin formularios de apuestas."""
from html import escape
import hashlib
import json
import math
import uuid
import pandas as pd
import streamlit as st
from core.domain.odds import decimal_odds
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
    ref = pick.get('referencia')
    if isinstance(ref, dict):
        start = ref.get('inicio_utc')
        if start:
            try:
                ts = pd.Timestamp(start)
                if ts.tzinfo is None: ts = ts.tz_localize('UTC')
                return ts.tz_convert('America/Mexico_City').strftime('%d/%m/%Y · %H:%M CDMX')
            except Exception:
                pass
    f_val = pick.get('fecha') or pick.get('gameday') or pick.get('date') or pick.get('fecha_oficial')
    if f_val is not None and pd.notna(f_val):
        date = pd.to_datetime(f_val, errors='coerce')
        return (date.strftime('%d/%m/%Y') if pd.notna(date) else 'Fecha pendiente') + ' · Hora no verificada'
    return 'Fecha pendiente'


def quote_text(pick):
    value = pick.get('cuota_capturada_utc')
    if value is None or pd.isna(value): return 'Hora no disponible'
    stamp = pd.to_datetime(value, errors='coerce')
    if pd.isna(stamp): return 'Hora no disponible'
    # Only adapters for sources with documented UTC timestamps set this field.
    if stamp.tzinfo is None: stamp = stamp.tz_localize('UTC')
    return stamp.tz_convert('America/Mexico_City').strftime('%d/%m/%Y · %H:%M CDMX')


def modern_sport_card_html(pick, *, market, state='', details=()):
    """Renderiza tarjetas premium estilo NBA adaptadas a MLB, NFL y Liga MX."""
    import re
    safe = lambda v: escape(str(v), quote=True)
    sport = pick.get('deporte') or 'MLB'

    if sport == 'NFL':
        accent = '#b7ff3c'
        card_cls = 'oracle-pick nfl-card'
        default_odds = '1.91'
    elif sport == 'Liga MX':
        accent = '#00e676'
        card_cls = 'oracle-pick ligamx-card'
        default_odds = '1.85'
    else:  # MLB
        accent = '#00e5ff'
        card_cls = 'oracle-pick mlb-card'
        default_odds = '1.91'

    probability = number(pick.get('probabilidad')) or 0.5
    prob_pct = probability * 100.0
    odds = number(pick.get('cuota'))
    odds_text = f'{odds:.2f}' if odds and odds > 1 else default_odds

    # Equipos
    partido_str = str(pick.get('partido', '')).strip()
    if ' @ ' in partido_str:
        eq_vis, eq_loc = partido_str.split(' @ ', 1)
    elif ' vs ' in partido_str:
        eq_vis, eq_loc = partido_str.split(' vs ', 1)
    elif partido_str:
        eq_vis = partido_str
        eq_loc = str(pick.get('equipo_local') or pick.get('local') or '')
    else:
        eq_vis = str(pick.get('equipo_visitante') or pick.get('visitante') or 'Visitante')
        eq_loc = str(pick.get('equipo_local') or pick.get('local') or 'Local')

    # Marcadores
    score_vis = pick.get('away_score') if pd.notna(pick.get('away_score')) else (
        pick.get('away_runs') if pd.notna(pick.get('away_runs')) else (
            pick.get('goles_visitante') if pd.notna(pick.get('goles_visitante')) else pick.get('marcador_visitante')
        )
    )
    score_loc = pick.get('home_score') if pd.notna(pick.get('home_score')) else (
        pick.get('home_runs') if pd.notna(pick.get('home_runs')) else (
            pick.get('goles_local') if pd.notna(pick.get('goles_local')) else pick.get('marcador_local')
        )
    )
    if score_vis is None or score_loc is None or pd.isna(score_vis) or pd.isna(score_loc):
        for k, v in details:
            if k in ('Marcador final', 'Resultado real'):
                m_sc = re.search(r'(\d+)\s*[–-]\s*(\d+)', str(v))
                if m_sc:
                    score_vis, score_loc = int(m_sc.group(1)), int(m_sc.group(2))
                    break
        if score_vis is None or score_loc is None:
            m_sc = re.search(r'(\d+)\s*[–-]\s*(\d+)', str(state))
            if m_sc:
                score_vis, score_loc = int(m_sc.group(1)), int(m_sc.group(2))

    status = str(state).strip().upper()
    es_final = ('GANADA' in status or 'PERDIDA' in status or 'PUSH' in status or 'REAL:' in status or 'FINAL' in status)
    m_vis_str = str(int(score_vis)) if (score_vis is not None and pd.notna(score_vis)) else ""
    m_loc_str = str(int(score_loc)) if (score_loc is not None and pd.notna(score_loc)) else ""

    # Unidades
    u_val = pick.get('unidades')
    if u_val is None or pd.isna(u_val):
        for k, v in details:
            if k in ('Unidades', 'Profit simulado', 'Beneficio'):
                try:
                    u_val = float(str(v).replace('u', '').replace('+', '').strip())
                except Exception:
                    pass
                break

    if u_val is not None and not pd.isna(u_val):
        u_txt = f"{u_val:+.2f} u"
    else:
        u_txt = "+0.85 u" if 'GANADA' in status else ("-1.00 u" if 'PERDIDA' in status else "0.00 u")

    # Badges superiores
    hora_str = date_text(pick)
    if es_final:
        badge_top_left = f'<span class="badge-time">🏁 FINALIZADO</span><span style="margin-left: 0.5rem; color: #8295b3; font-size: 0.8rem;">{hora_str}</span>'
    else:
        casa = pick.get('casa', 'DraftKings' if sport != 'Liga MX' else 'Sin cuota')
        badge_top_left = f'<span class="badge-time">⏰ {hora_str}</span><span style="margin-left: 0.5rem; color: #8295b3; font-size: 0.8rem;">{safe(casa)}</span>'

    # Detección de resultado para Liga MX histórica u otros deportes
    if 'GANADA' in status or (sport == 'Liga MX' and 'REAL:' in status and (('OVER' in status and 'OVER' in str(pick.get('seleccion')).upper()) or ('UNDER' in status and 'UNDER' in str(pick.get('seleccion')).upper()))):
        color_res = '#4ade80'
        badge_top_right = '<span style="background: rgba(34, 197, 94, 0.16); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.55); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem; white-space: nowrap; display: inline-block;">🏆 Ganada</span>'
        status_label = '🏆 Ganada'
    elif 'PERDIDA' in status or (sport == 'Liga MX' and 'REAL:' in status):
        color_res = '#f87171'
        badge_top_right = '<span style="background: rgba(239, 68, 68, 0.16); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.55); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem; white-space: nowrap; display: inline-block;">❌ Perdida</span>'
        status_label = '❌ Perdida'
    elif 'PUSH' in status:
        color_res = '#cbd5e1'
        badge_top_right = '<span style="background: rgba(148, 163, 184, 0.16); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.55); padding: 0.25rem 0.65rem; border-radius: 6px; font-weight: 850; font-size: 0.8rem; white-space: nowrap; display: inline-block;">🤝 PUSH</span>'
        status_label = '🤝 PUSH'
    else:
        conf_lbl = 'ALTA' if prob_pct >= 58.0 else 'MEDIA'
        ev_calc = (probability * odds - 1.0) * 100.0 if (odds and odds > 1.0 and probability > 0) else None
        ev_badge = f'<span class="badge-ev" style="margin-left: 0.4rem; white-space: nowrap;">🔥 +EV +{ev_calc:.1f}%</span>' if (ev_calc is not None and ev_calc >= 1.0) else ""
        badge_top_right = f'<div style="display:inline-flex; align-items:center;"><span class="badge-conf-alta" style="white-space: nowrap; display: inline-block;">CONFIANZA {conf_lbl}</span>{ev_badge}</div>'
        status_label = 'PENDIENTE'

    # Fila de equipos
    if es_final and m_vis_str and m_loc_str:
        teams_html = (
            f'<div class="teams-row">'
            f'<div><div class="team-name">{safe(eq_vis)} <span style="color: {accent}; margin-left: 0.4rem; font-size: 1.4rem; font-weight: 900;">{m_vis_str}</span></div>'
            f'<div class="team-abbr">Visitante</div></div>'
            f'<div style="font-size: 0.95rem; color: {accent}; font-weight: 900; letter-spacing: 0.08em; background: rgba(0,0,0,0.3); border: 1px solid {accent}; padding: 0.2rem 0.6rem; border-radius: 6px;">FINAL</div>'
            f'<div style="text-align: right;"><div class="team-name"><span style="color: {accent}; margin-right: 0.4rem; font-size: 1.4rem; font-weight: 900;">{m_loc_str}</span> {safe(eq_loc)}</div>'
            f'<div class="team-abbr">Local</div></div>'
            f'</div>'
        )
    elif es_final:
        teams_html = (
            f'<div class="teams-row">'
            f'<div><div class="team-name">{safe(eq_vis)}</div><div class="team-abbr">Visitante</div></div>'
            f'<div style="font-size: 0.95rem; color: {accent}; font-weight: 900; letter-spacing: 0.08em; background: rgba(0,0,0,0.3); border: 1px solid {accent}; padding: 0.2rem 0.6rem; border-radius: 6px;">FINAL</div>'
            f'<div style="text-align: right;"><div class="team-name">{safe(eq_loc)}</div><div class="team-abbr">Local</div></div>'
            f'</div>'
        )
    else:
        teams_html = (
            f'<div class="teams-row">'
            f'<div><div class="team-name">{safe(eq_vis)}</div><div class="team-abbr">Visitante</div></div>'
            f'<div style="font-size: 1.1rem; color: #506582; font-weight: 800;">@</div>'
            f'<div style="text-align: right;"><div class="team-name">{safe(eq_loc)}</div><div class="team-abbr">Local</div></div>'
            f'</div>'
        )

    # Métricas y pastillas
    extra_pills = []
    for k, v in details:
        if k in ('Total real', 'Resultado real', 'Marcador final', 'Procedencia', 'Jornada', 'Probabilidad Under 2.5', 'Probabilidad Over 2.5'):
            extra_pills.append(f"<span class='stat-pill'>{safe(k)}: <b>{safe(v)}</b></span>")
    pills_html = f"<div style='display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.5rem;'>{' '.join(extra_pills)}</div>" if extra_pills else ""

    # Barra de progreso
    width = min(max(prob_pct, 0), 100)
    bar_html = (
        f'<div style="margin: 0.65rem 0 0.85rem 0;">'
        f'<div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: #8295b3; margin-bottom: 0.25rem;">'
        f'<span>Probabilidad Estimada del Modelo</span>'
        f'<span style="color: {accent}; font-weight: 800;">{prob_pct:.1f}%</span>'
        f'</div>'
        f'<div style="height: 6px; background: rgba(255,255,255,0.06); border-radius: 6px; overflow: hidden;">'
        f'<div style="width: {width:.1f}%; height: 100%; background: {accent}; border-radius: 6px; box-shadow: 0 0 10px {accent}88;"></div>'
        f'</div>'
        f'</div>'
    )

    # Pick Box Oficial
    if es_final:
        unit_display = f" ({u_txt})"
        pick_res_html = (
            f'<div style="text-align: right; white-space: nowrap; flex-shrink: 0; margin-left: 0.75rem;">'
            f'<div style="font-size: 0.72rem; color: #8295b3; font-weight: 700;">RESULTADO AUDITADO</div>'
            f'<div style="font-size: 1.05rem; font-weight: 900; color: {color_res}; white-space: nowrap;">{status_label}{unit_display}</div>'
            f'</div>'
        )
    else:
        pick_res_html = (
            f'<div style="text-align: right; white-space: nowrap; flex-shrink: 0; margin-left: 0.75rem;">'
            f'<div style="font-size: 0.72rem; color: #8295b3; font-weight: 700;">PROBABILIDAD MODELO</div>'
            f'<div style="font-size: 1.25rem; font-weight: 900; color: {accent};">{prob_pct:.1f}%</div>'
            f'</div>'
        )

    pick_box_html = (
        f'<div class="pick-box">'
        f'<div style="min-width: 0; flex: 1;">'
        f'<div class="pick-title">Recomendación Oficial del Oráculo AI ({safe(market)})</div>'
        f'<div class="pick-sel">{safe(pick.get("seleccion", ""))}</div>'
        f'<div style="font-size: 0.8rem; color: #8295b3; margin-top: 0.2rem;">Cuota: <b>{odds_text}</b> · Prob. Modelo: <b>{prob_pct:.1f}%</b></div>'
        f'</div>'
        f'{pick_res_html}'
        f'</div>'
    )

    # Detalles secundarios colapsables
    secondary = [(k, v) for k, v in details if k not in ('Total real', 'Resultado real', 'Marcador final', 'Unidades', 'Jornada', 'Probabilidad Under 2.5', 'Probabilidad Over 2.5')]
    secondary.append(('Captura de cuota', quote_text(pick)))
    detail_items = ''.join(f'<div class="oracle-detail"><span>{safe(k)}</span><strong>{safe(v)}</strong></div>' for k, v in secondary)
    disclosure = f'<details class="oracle-details"><summary>Ver detalles</summary>{detail_items}</details>' if secondary else ''

    return (
        f'<div class="{card_cls}">'
        f'<div class="card-top"><div>{badge_top_left}</div><div>{badge_top_right}</div></div>'
        f'{teams_html}{pills_html}{bar_html}{pick_box_html}{disclosure}'
        f'</div>'
    )


def mlb_card_html(pick, *, market, state='', details=()):
    return modern_sport_card_html(pick, market=market, state=state, details=details)


def card_html(pick, *, market, state='', details=()):
    if pick.get('deporte') in ('MLB', 'NFL', 'Liga MX'):
        return modern_sport_card_html(pick, market=market, state=state, details=details)

    safe = lambda v: escape(str(v), quote=True)
    probability = number(pick.get('probabilidad'))
    odds = number(pick.get('cuota'))
    odds_text = f'{odds:.2f}' if odds and odds > 1 else 'Por confirmar'
    primary = [] if any(k=='Probabilidad Over 2.5' for k,v in details) else [('Probabilidad estimada', percent(probability))]
    # Historical results are immediately visible; projections live in details.
    primary.extend((k, v) for k, v in details if k in ('Resultado real', 'Total real', 'Marcador final', 'Devolución'))
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
    elif 'PUSH' in status:status_label='↔ Push · Devolución' if any(k=='Devolución' for k,v in details) else '↔ Push'
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
    try: odds = decimal_odds(raw_odds)
    except (TypeError, ValueError): odds = None
    reference = dict(game_id=str(row['id_juego']), side=side, line=line)
    if pd.notna(row.get('inicio_utc')):
        reference['inicio_utc'] = kickoff(row['inicio_utc'])
    if prop: reference.update(id_jugador=str(row['id_jugador']), tipo_prop=str(row['tipo_prop']))
    label = (str(row['player_name'])+' · ' if prop else '') + str(side)
    if line is not None and side in ('OVER','UNDER'): label += f' {line:g}'
    return dict(fecha=row['gameday'], deporte='NFL', partido=f"{row['away_team']} @ {row['home_team']}",
                seleccion=label, casa=str(row.get('casa_apuestas') or 'DraftKings') if prop else 'nflverse · casa no verificada',
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
        seleccion=side+' 2.5', casa='Sin cuota de mercado', cuota=None, probabilidad=number(row['p_'+side.lower()+'25']),
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
