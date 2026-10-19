"""Devoluciones verificadas: no modifican marcadores ni publicaciones originales."""
import json
import logging
import mysql.connector
import pandas as pd
from core.infrastructure.migrations import ensure_schema


def save_refund(conn, *, sport, game_id, reason, source, evidence,
                player_id='', market='', official_id=None, legacy_key=None, prepare=True):
    if sport not in ('MLB','NFL') or not game_id or not reason or not source or not evidence:
        raise ValueError('La devolución requiere identidad, motivo y evidencia.')
    if prepare:
        ensure_schema(conn, 'refunds')
    cursor=conn.cursor()
    try:
        cursor.execute("""INSERT INTO oracle_devoluciones
            (deporte,id_juego,id_jugador,mercado,id_oficial,clave_legacy,motivo,fuente,evidencia,registrado_utc)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))
            ON DUPLICATE KEY UPDATE motivo=VALUES(motivo),fuente=VALUES(fuente),
                evidencia=VALUES(evidencia),id_oficial=COALESCE(VALUES(id_oficial),id_oficial),
                clave_legacy=COALESCE(VALUES(clave_legacy),clave_legacy)""",
            (sport,str(game_id),str(player_id),str(market),None if official_id is None else str(official_id),
             legacy_key,reason,source,json.dumps(evidence,ensure_ascii=False,default=str)))
        conn.commit()
    finally:cursor.close()


def read_refunds(conn):
    if conn is None:return []
    cursor=conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT deporte,id_juego,id_jugador,mercado,id_oficial,clave_legacy,motivo FROM oracle_devoluciones')
        records=cursor.fetchall()
        required={'deporte','id_juego','id_jugador','mercado','motivo'}
        return records if isinstance(records,list) and all(required.issubset(r) for r in records) else []
    except mysql.connector.Error as error:
        if error.errno!=1146:
            logging.getLogger(__name__).warning('No se pudo leer devoluciones: %s',type(error).__name__)
        return []
    finally:cursor.close()


def apply_refunds(frame, refunds, *, sport=None, game_col='identidad'):
    if frame.empty or not refunds:return frame
    result=frame.copy()
    if 'resuelto' not in result:
        result['resuelto']=False
    else:
        result['resuelto']=result.resuelto.fillna(False).astype(bool)
    index={}
    for record in refunds:
        for alias in (record['id_juego'],record.get('id_oficial'),record.get('clave_legacy')):
            if alias:
                index[(record['deporte'],str(alias),str(record['id_jugador'] or ''),str(record['mercado'] or ''))]=record['motivo']
    for i,row in result.iterrows():
        identity=str(row.get(game_col,''));parts=identity.split('|')
        player=str(row.get('id_jugador',parts[1] if len(parts)>1 and (sport or row.get('deporte'))=='NFL' else ''))
        market=str(row.get('tipo_prop',parts[2] if len(parts)>2 and (sport or row.get('deporte'))=='NFL' else ''))
        current_sport=sport or row.get('deporte')
        keys=[(current_sport,identity,player,market),(current_sport,parts[0],player,market),
              (current_sport,identity,'',''),(current_sport,parts[0],'','')]
        reason=next((index[k] for k in keys if k in index),None)
        if reason:
            result.loc[i,'resultado']='PUSH'
            result.loc[i,'unidades']=0.0
            result.loc[i,'motivo_devolucion']=reason
            result.loc[i,'apto_ajuste']=False
            result.loc[i,'resuelto']=True
    return result


def cancelled_mlb(game):
    status=game.get('status',{})
    detail=str(status.get('detailedState','')).lower()
    # Aplazado, suspendido, en vivo o ausente del feed no prueban cancelación.
    if 'cancelled' not in detail and 'canceled' not in detail:return False
    teams=game.get('teams',{})
    return all(teams.get(side,{}).get('score') is None for side in ('home','away'))


def mlb_refund_reason(game, original_day):
    """La devolución pertenece al pick original, no al nuevo horario."""
    if cancelled_mlb(game):
        return 'Partido cancelado sin disputarse'
    if str(game.get('status', {}).get('detailedState', '')).lower() != 'postponed':
        return None
    teams = game.get('teams', {})
    if any(teams.get(side, {}).get('score') is not None for side in ('home', 'away')):
        return None
    original = pd.Timestamp(original_day).date()
    rescheduled = game.get('rescheduleGameDate')
    try:
        if rescheduled and pd.Timestamp(rescheduled).date() > original:
            return 'Partido aplazado para otro día; devolución del pick original'
    except (ValueError, TypeError):
        pass
    return None


def record_manual_refund(conn, row, reason):
    """Confirmación del usuario, identificada como manual y sin inventar resultados."""
    reasons = ('Jugador no participó', 'Partido no disputado en la fecha del pick',
               'Apuesta anulada por la casa')
    sport = str(row.get('deporte', ''))
    if sport not in ('MLB', 'NFL') or str(row.get('resultado', '')).upper() != 'PENDIENTE':
        raise ValueError('Solo se pueden devolver picks pendientes de MLB o NFL.')
    if reason not in reasons:
        raise ValueError('Selecciona un motivo de devolución válido.')
    identity = str(row.get('identidad', ''))
    if not identity or identity in ('nan', 'None'):
        raise ValueError('El pick no tiene una identidad verificable.')
    parts = identity.split('|')
    kwargs = {}
    if sport == 'NFL' and row.get('mercado') != 'Totales':
        if len(parts) != 3 or not all(parts):
            raise ValueError('No se pudo identificar el jugador y el mercado.')
        game, player, market = parts
        kwargs.update(player_id=player, market=market)
    else:
        game = identity
    save_refund(conn, sport=sport, game_id=game, reason=reason + ' (confirmación manual)',
                source='Confirmación manual del usuario',
                evidence={'confirmation': True, 'identity': identity,
                          'original_date': str(row.get('fecha')), 'market': str(row.get('mercado')),
                          'selection': str(row.get('seleccion')), 'reason': reason}, **kwargs)
