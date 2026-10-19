"""Devoluciones verificadas: no modifican marcadores ni publicaciones originales."""
import json
import logging
import mysql.connector
import pandas as pd
from core.infrastructure.migrations import ensure_schema


def save_refund(conn, *, sport, game_id, reason, source, evidence,
                player_id='', market='', official_id=None, legacy_key=None):
    if sport not in ('MLB','NFL') or not game_id or not reason or not source or not evidence:
        raise ValueError('La devolución requiere identidad, motivo y evidencia.')
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
