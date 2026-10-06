"""Apuestas realizadas: snapshots independientes del modelo y persistencia MySQL."""
from datetime import datetime, timezone
import json
import hashlib
from decimal import Decimal, ROUND_HALF_UP
import math
import uuid
from pathlib import Path
import pandas as pd

STATES = ('Pendiente', 'Ganada', 'Perdida', 'Push', 'Anulada')
COLUMNS = ['id', 'fecha', 'deporte', 'partido', 'seleccion', 'casa', 'cuota',
           'monto', 'estado', 'ganancia_neta', 'probabilidad', 'origen', 'referencia']
DDL = """
CREATE TABLE IF NOT EXISTS bankroll_apuestas (
 id CHAR(36) NOT NULL PRIMARY KEY, fecha DATE NOT NULL,
 deporte VARCHAR(20) NOT NULL, partido VARCHAR(255) NOT NULL,
 seleccion VARCHAR(255) NOT NULL, casa VARCHAR(80) NOT NULL,
 cuota DOUBLE NOT NULL, monto DOUBLE NOT NULL,
 estado VARCHAR(20) NOT NULL, ganancia_neta DOUBLE NOT NULL DEFAULT 0,
 probabilidad DOUBLE NULL, origen VARCHAR(30) NOT NULL DEFAULT 'manual',
 referencia TEXT NULL, creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 actualizado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 KEY ix_bankroll_estado (estado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def prepare(conn):
    cursor = conn.cursor()
    try:
        cursor.execute(DDL)
        cursor.execute("""CREATE TABLE IF NOT EXISTS bankroll_config (
            id TINYINT NOT NULL PRIMARY KEY, capital_inicial DOUBLE NOT NULL
        ) ENGINE=InnoDB""")
        cursor.execute('INSERT IGNORE INTO bankroll_config VALUES (1, 10000)')
        cursor.execute("""CREATE TABLE IF NOT EXISTS bankroll_recibos (
            huella CHAR(64) PRIMARY KEY, apuesta_id CHAR(36) NOT NULL UNIQUE,
            ticket VARCHAR(120) NULL
        ) ENGINE=InnoDB""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bankroll_auditoria (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, apuesta_id CHAR(36) NULL,
            accion VARCHAR(30) NOT NULL, actor VARCHAR(30) NOT NULL,
            motivo VARCHAR(500) NOT NULL, anterior TEXT NULL, posterior TEXT NOT NULL,
            creado_en TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            KEY ix_auditoria_apuesta (apuesta_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bankroll_migraciones (
            version VARCHAR(50) PRIMARY KEY
        ) ENGINE=InnoDB""")
        # Migración única: conserva apuestas antiguas e indexa sus recibos sin borrarlas.
        cursor.execute('SELECT capital_inicial FROM bankroll_config WHERE id=1 FOR UPDATE')
        cursor.fetchone()
        cursor.execute("SELECT version FROM bankroll_migraciones WHERE version='recibos_v1'")
        if cursor.fetchone() is None:
            legacy = load_ledger(conn)
            for bet in legacy.to_dict('records'):
                cursor.execute('INSERT IGNORE INTO bankroll_recibos (huella,apuesta_id,ticket) VALUES (%s,%s,%s)',
                               (fingerprint(bet), bet['id'], ''))
            cursor.execute("INSERT INTO bankroll_migraciones VALUES ('recibos_v1')")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def audit_event(cursor, identifier, action, before, after, actor='manual', reason='Registro de apuesta realizada'):
    cursor.execute("""INSERT INTO bankroll_auditoria
        (apuesta_id,accion,actor,motivo,anterior,posterior) VALUES (%s,%s,%s,%s,%s,%s)""",
        (identifier, action, actor, reason,
         json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
         json.dumps(after, ensure_ascii=False, default=str)))


def load_audit(conn):
    return rows(conn, 'SELECT * FROM bankroll_auditoria ORDER BY id DESC')


def export_bundle(conn):
    import io, zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('apuestas.csv', load_ledger(conn).to_csv(index=False))
        archive.writestr('auditoria.csv', load_audit(conn).to_csv(index=False))
        archive.writestr('recibos.csv', rows(conn, 'SELECT * FROM bankroll_recibos').to_csv(index=False))
        archive.writestr('config.json', json.dumps({'capital_inicial':capital(conn)}, ensure_ascii=False))
    return buffer.getvalue()


def fingerprint(bet):
    # Un ticket distinto permite registrar dos apuestas reales idénticas.
    data = {key: bet.get(key) for key in ('deporte','partido','seleccion','casa','origen','referencia','ticket')}
    for key in ('partido','seleccion','casa'):
        data[key] = str(data.get(key, '')).strip().casefold()
    data['origen'] = data.get('origen') or 'manual'
    data['ticket'] = str(data.get('ticket') or '').strip()
    reference = data.get('referencia') or {}
    if isinstance(reference, str): reference = json.loads(reference)
    data['referencia'] = {key:reference[key] for key in ('game_id','id_jugador','tipo_prop','side','line','fecha','local','visitante') if key in reference} or None
    data['fecha'] = pd.Timestamp(bet['fecha']).date().isoformat()
    data['monto'] = f"{float(bet['monto']):.2f}"
    data['cuota'] = f"{float(bet['cuota']):.6f}"
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def rows(conn, sql, params=()):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return pd.DataFrame(cursor.fetchall())
    finally:
        cursor.close()


def load_ledger(conn):
    frame = rows(conn, 'SELECT ' + ','.join(COLUMNS) + ' FROM bankroll_apuestas ORDER BY fecha DESC, creado_en DESC')
    if frame.empty:
        return pd.DataFrame(columns=COLUMNS)
    frame['fecha'] = pd.to_datetime(frame['fecha'], errors='raise')
    for col in ('cuota', 'monto', 'ganancia_neta', 'probabilidad'):
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    return frame


def net_profit(state, amount, odds):
    if state not in STATES:
        raise ValueError('Estado inválido.')
    if state == 'Ganada': return float((Decimal(str(amount)) * (Decimal(str(odds)) - 1)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    if state == 'Perdida': return -round(float(amount), 2)
    return 0.0


def save_bet(conn, bet, receipt=None):
    amount, odds = float(bet['monto']), float(bet['cuota'])
    if not math.isfinite(amount) or amount <= 0 or not math.isfinite(odds) or odds <= 1:
        raise ValueError('Monto y cuota decimal deben ser positivos; cuota mayor que 1.')
    for col in ('partido', 'seleccion', 'casa'):
        if not str(bet.get(col, '')).strip(): raise ValueError('Completa partido, selección y casa.')
    if bet['deporte'] not in ('MLB', 'NFL', 'Liga MX'): raise ValueError('Deporte inválido.')
    state = bet.get('estado', 'Pendiente')
    p = bet.get('probabilidad')
    p = None if p is None or pd.isna(p) else float(p)
    if p is not None and (not math.isfinite(p) or not 0 <= p <= 1):
        raise ValueError('Probabilidad fuera de rango.')
    amount = round(amount, 2)
    identifier = receipt or str(uuid.uuid4())
    reference = dict(bet.get('referencia') or {})
    reference.setdefault('registrado_utc', datetime.now(timezone.utc).isoformat())
    values = (identifier, pd.Timestamp(bet['fecha']).date(), bet['deporte'],
              bet['partido'].strip(), bet['seleccion'].strip(), bet['casa'].strip(), odds, amount,
              state, net_profit(state, amount, odds), p, bet.get('origen', 'manual'),
              json.dumps(reference, ensure_ascii=False))
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id FROM bankroll_apuestas WHERE id=%s FOR UPDATE', (identifier,))
        if cursor.fetchone():
            conn.commit()
            return identifier
        # La clave única hace atómico el control de duplicados entre sesiones.
        from mysql.connector import IntegrityError
        try:
            cursor.execute('INSERT INTO bankroll_recibos (huella,apuesta_id,ticket) VALUES (%s,%s,%s)',
                           (fingerprint(bet), identifier, str(bet.get('ticket') or '')[:120]))
        except IntegrityError as exc:
            if exc.errno != 1062: raise
            raise ValueError('Esta apuesta ya está registrada. Si son dos apuestas reales, introduce un ticket distinto.') from exc
        # Idempotencia del envío del formulario; nunca reescribe un snapshot existente.
        cursor.execute('INSERT INTO bankroll_apuestas (' + ','.join(COLUMNS) + ') VALUES (' +
                       ','.join(['%s'] * len(COLUMNS)) + ') ON DUPLICATE KEY UPDATE id=id', values)
        audit_event(cursor, identifier, 'registro', None, dict(zip(COLUMNS, values)))
        conn.commit()
        return identifier
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def update_state(conn, identifier, state, only_pending=False, reason='Actualización manual'):
    if state not in STATES: raise ValueError('Estado inválido.')
    if not str(reason).strip(): raise ValueError('Indica el motivo de la corrección.')
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT monto,cuota,estado,ganancia_neta FROM bankroll_apuestas WHERE id=%s FOR UPDATE', (identifier,))
        row = cursor.fetchone()
        if not row: raise ValueError('La apuesta ya no existe.')
        if row['estado'] == state or (only_pending and row['estado'] != 'Pendiente'):
            conn.commit()
            return 0
        profit = net_profit(state, row['monto'], row['cuota'])
        cursor.execute('UPDATE bankroll_apuestas SET estado=%s,ganancia_neta=%s WHERE id=%s', (state, profit, identifier))
        changed = cursor.rowcount
        if changed:
            audit_event(cursor, identifier, 'estado', row, {'estado':state, 'ganancia_neta':profit},
                        'automatico' if only_pending else 'manual', str(reason).strip()[:500])
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def capital(conn, value=None):
    if value is not None:
        value = float(value)
        if not math.isfinite(value) or value < 0: raise ValueError('Capital inicial inválido.')
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT capital_inicial FROM bankroll_config WHERE id=1 FOR UPDATE')
            previous = cursor.fetchone()[0]
            cursor.execute('UPDATE bankroll_config SET capital_inicial=%s WHERE id=1', (value,))
            if float(previous) != value:
                audit_event(cursor, None, 'capital', {'capital_inicial':float(previous)}, {'capital_inicial':value}, reason='Cambio de capital inicial')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    return float(rows(conn, 'SELECT capital_inicial FROM bankroll_config WHERE id=1').iloc[0, 0])


def metrics(frame, initial=0):
    settled = frame[frame.estado.isin(['Ganada', 'Perdida', 'Push'])]
    risk = float(frame.loc[frame.estado.eq('Pendiente'), 'monto'].sum())
    invested = float(settled.monto.sum())
    profit = float(settled.ganancia_neta.sum())
    won = int(settled.estado.eq('Ganada').sum())
    decided = int(settled.estado.isin(['Ganada', 'Perdida']).sum())
    return dict(apostado=invested, beneficio=profit, roi=100*profit/invested if invested else 0,
                win_rate=100*won/decided if decided else 0, pendientes=risk,
                saldo=initial+profit, disponible=initial+profit-risk, apuestas=len(frame))


def decimal_odds(american):
    value = float(american)
    if not math.isfinite(value) or abs(value) < 100: raise ValueError('Momio americano inválido.')
    return 1 + (value/100 if value > 0 else 100/abs(value))


def total_state(total, line, selection):
    if selection not in ('OVER', 'UNDER'): return None
    if float(total) == float(line): return 'Push'
    won = float(total) > float(line) if selection == 'OVER' else float(total) < float(line)
    return 'Ganada' if won else 'Perdida'


def model_options(conn, root, now=None):
    """Lee los módulos sin convertir sus predicciones en dinero apostado."""
    now = now or datetime.now(timezone.utc)
    options, errors = [], []
    queries = {
        'mlb_total': """SELECT id,game_pk AS game_id,fecha_oficial AS fecha,equipo_local AS local,
            equipo_visitante AS visitante,seleccion,linea,start_utc AS inicio_utc,cuota_seleccion AS cuota,confianza AS probabilidad
            FROM mlb_totales_predicciones WHERE start_utc>UTC_TIMESTAMP()
            AND LOWER(TRIM(casa_apuestas))='draftkings'""",
        'mlb_ml': """SELECT j.id_juego AS game_id,p.fecha,p.equipo_local AS local,
            p.equipo_visitante AS visitante,p.pick_ia AS seleccion,p.cuota,p.confianza/100 AS probabilidad
            FROM registro_picks_ia p JOIN juegos j ON DATE(j.fecha)=p.fecha
            AND j.equipo_local=p.equipo_local AND j.equipo_visitante=p.equipo_visitante
            WHERE j.fecha>NOW()""",
        'nfl_total': """SELECT p.id_juego AS game_id,j.fecha,j.equipo_local AS local,
            j.equipo_visitante AS visitante,p.seleccion,p.linea_total AS linea,
            p.cuota_pick AS american,p.probabilidad_pick/100 AS probabilidad
            FROM nfl_predicciones_totales p JOIN nfl_juegos j ON j.id_juego=p.id_juego
            WHERE LOWER(j.estado)='programado' AND DATE(j.fecha)>=CURRENT_DATE()
            ORDER BY p.actualizado_en DESC""",
        'nfl_prop': """SELECT p.id_juego AS game_id,p.id_jugador,p.tipo_prop,j.fecha,
            j.equipo_local AS local,j.equipo_visitante AS visitante,u.nombre AS jugador,
            p.seleccion,p.linea,p.cuota_pick AS american,p.probabilidad_pick AS probabilidad
            FROM nfl_proyecciones_props p JOIN nfl_juegos j ON j.id_juego=p.id_juego
            JOIN nfl_jugadores u ON u.id_jugador=p.id_jugador
            JOIN nfl_lineas_props l ON l.id_linea=p.id_linea
            WHERE LOWER(j.estado)='programado' AND DATE(j.fecha)>=CURRENT_DATE()
            AND LOWER(TRIM(l.casa_apuestas))='draftkings'
            ORDER BY p.actualizado_en DESC""",
    }
    for source, sql in queries.items():
        try:
            data = rows(conn, sql)
            if data.empty: continue
            # No importar moneyline ambiguo (doble cartelera sin identificador en el registro).
            if source == 'mlb_ml':
                data = data[~data.duplicated(['fecha', 'local', 'visitante'], keep=False)]
            for row in data.to_dict('records'):
                selection = row['seleccion']
                if source != 'mlb_ml' and selection not in ('OVER', 'UNDER', 'ANOTA'): continue
                raw_odds = row.get('american', row.get('cuota'))
                if raw_odds is None or pd.isna(raw_odds): continue
                try:
                    odds = decimal_odds(raw_odds) if 'american' in row else float(raw_odds)
                except (ValueError, TypeError):
                    continue
                if not math.isfinite(odds) or odds <= 1: continue
                ref = {key: str(row[key]) for key in ('game_id', 'id_jugador', 'tipo_prop') if key in row}
                if source == 'mlb_total':
                    ref['inicio_utc'] = pd.Timestamp(row['inicio_utc']).tz_localize('UTC').isoformat() if pd.Timestamp(row['inicio_utc']).tzinfo is None else pd.Timestamp(row['inicio_utc']).isoformat()
                ref.update(side=selection, line=float(row['linea']) if 'linea' in row and pd.notna(row['linea']) else None)
                label = selection if source == 'mlb_ml' else f"{row.get('jugador', '')} {row.get('tipo_prop', 'Total')} {selection} {row.get('linea', '')}".strip()
                options.append(dict(fecha=row['fecha'], deporte='MLB' if source.startswith('mlb') else 'NFL',
                                    partido=f"{row['visitante']} @ {row['local']}", seleccion=label,
                                    casa='DraftKings', cuota=odds, probabilidad=row['probabilidad'],
                                    origen=source, referencia=ref))
        except Exception as exc:
            errors.append(f'{source}: {type(exc).__name__}')
    try:
        from futbol_liga_mx.continuidad import frozen_model
        from futbol_liga_mx.inferencia import upcoming_probabilities
        folder = Path(root)/'futbol_liga_mx'
        params, report = frozen_model(folder/'modelos')
        future = upcoming_probabilities(pd.read_csv(folder/'data/partidos.csv'),
                                        pd.read_csv(folder/'data/proximos.csv'), params, report, now)
        for row in future.to_dict('records'):
            for side in ('OVER', 'UNDER'):
                options.append(dict(fecha=row['fecha'], deporte='Liga MX',
                    partido=f"{row['visitante']} @ {row['local']}", seleccion=side+' 2.5',
                    casa='DraftKings', cuota=None, probabilidad=row['p_'+side.lower()+'25'],
                    origen='liga_mx', referencia=dict(fecha=row['fecha'], local=row['local'],
                        visitante=row['visitante'], inicio_utc=str(row['inicio_utc']), side=side, line=2.5)))
    except Exception as exc:
        errors.append(f'Liga MX: {exc}')
    return options, errors


def settle_pending(conn, root):
    """Liquida la línea realmente registrada y conserva su cuota/confianza originales."""
    pending = load_ledger(conn)
    pending = pending[pending.estado.eq('Pendiente') & pending.origen.ne('manual')]
    changed, errors = 0, []
    for bet in pending.to_dict('records'):
        try:
            ref = json.loads(bet['referencia'])
            source, state = bet['origen'], None
            if source == 'mlb_total':
                data = rows(conn, 'SELECT home_runs,away_runs,revision_reglas FROM mlb_totales_resultados WHERE game_pk=%s', (ref['game_id'],))
                if not data.empty and not data.iloc[0].revision_reglas:
                    r = data.iloc[0];state = total_state(r.home_runs+r.away_runs, ref['line'], ref['side'])
            elif source in ('nfl_total', 'mlb_ml'):
                table = 'nfl_juegos' if source == 'nfl_total' else 'juegos'
                data = rows(conn, f"SELECT marcador_local,marcador_visitante,equipo_local,equipo_visitante FROM {table} WHERE id_juego=%s AND LOWER(estado)='finalizado'", (ref['game_id'],))
                if not data.empty:
                    r = data.iloc[0]
                    if pd.notna(r.marcador_local) and pd.notna(r.marcador_visitante):
                        if source == 'nfl_total': state = total_state(r.marcador_local+r.marcador_visitante, ref['line'], ref['side'])
                        elif r.marcador_local != r.marcador_visitante:
                            winner = r.equipo_local if r.marcador_local > r.marcador_visitante else r.equipo_visitante
                            state = 'Ganada' if ref['side'] == winner else 'Perdida'
            elif source == 'nfl_prop':
                data = rows(conn, 'SELECT DISTINCT valor_real FROM nfl_proyecciones_props WHERE id_juego=%s AND id_jugador=%s AND tipo_prop=%s AND valor_real IS NOT NULL', (ref['game_id'],ref['id_jugador'],ref['tipo_prop']))
                if len(data) == 1:
                    value = float(data.iloc[0].valor_real)
                    state = ('Ganada' if value >= 1 else 'Perdida') if ref['side'] == 'ANOTA' else total_state(value, ref['line'], ref['side'])
            elif source == 'liga_mx':
                from futbol_liga_mx.inferencia import normalize_teams
                data = normalize_teams(pd.read_csv(Path(root)/'futbol_liga_mx/data/partidos.csv'))
                data = data[(data.fecha == ref['fecha']) & (data.local == ref['local']) & (data.visitante == ref['visitante'])]
                if len(data) == 1:
                    r = data.iloc[0];state = total_state(r.goles_local+r.goles_visitante, ref['line'], ref['side'])
            if state: changed += update_state(conn, bet['id'], state, only_pending=True, reason='Resultado oficial disponible; línea original conservada')
        except Exception as exc:
            errors.append(f"{bet['partido']}: {type(exc).__name__}")
    return changed, errors
