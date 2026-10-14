"""Registro inmutable de nuevas publicaciones antes del inicio del partido."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import mysql.connector

TABLE = 'nfl_publicaciones_props'


def future_game_ids(games, now=None):
    now = now or datetime.now(timezone.utc)
    ids = set()
    for row in games.to_dict('records'):
        try:
            if pd.isna(row.get('gametime')): continue
            start = datetime.fromisoformat(str(pd.Timestamp(row['gameday']).date())+'T'+str(row['gametime']))
            start = start.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
            if start > now: ids.add(str(row['game_id']))
        except (TypeError,ValueError,KeyError): continue
    return ids


def publication_rows(frame, games, model, now=None):
    future = future_game_ids(games,now)
    recs = frame[frame.tipo_prop.eq('receptions')].drop_duplicates(['game_id','player_id']).set_index(['game_id','player_id'])
    rows = []
    fields = ['linea','proyeccion','seleccion','probabilidad_pick','cuota_pick','estado_pick',
        'contexto_lesiones','dependencia_lesion','proyeccion_juegan','proyeccion_no_juegan']
    for row in frame.to_dict('records'):
        if (str(row['game_id']) not in future or row['tipo_prop'] not in {'receiving_yards','receptions','rushing_yards','passing_yards','passing_tds','anytime_td'}
                or row['estado_pick'] not in ['CANDIDATO','REVISAR LESION'] or pd.isna(row.get('id_linea'))): continue
        payload = {key:row[key] for key in fields if key in row and pd.notna(row[key])}
        injury=row.get('player_injury_status')
        payload['estado_lesion']=str(injury) if injury is not None and pd.notna(injury) else 'unknown'
        key = (row['game_id'],row['player_id'])
        if key in recs.index and pd.notna(recs.loc[key,'proyeccion']):
            payload['recepciones_proyectadas'] = float(recs.loc[key,'proyeccion'])
        rows.append((str(row['game_id']),str(row['player_id']),row['tipo_prop'],model,int(row['id_linea']),
                     json.dumps(payload,ensure_ascii=False,allow_nan=False,default=lambda v:v.item())))
    return rows


def save_publications(conn, frame, games, model, now=None):
    rows = publication_rows(frame,games,model,now)
    if not rows: return
    cursor = conn.cursor()
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS nfl_publicaciones_props (
            id_juego VARCHAR(64) NOT NULL, id_jugador VARCHAR(64) NOT NULL,
            tipo_prop VARCHAR(40) NOT NULL, modelo_version VARCHAR(100) NOT NULL,
            id_linea BIGINT NOT NULL, publicada_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            payload JSON NOT NULL,
            PRIMARY KEY(id_juego,id_jugador,tipo_prop,modelo_version,id_linea)
        )''')
        cursor.executemany('''INSERT INTO nfl_publicaciones_props
            (id_juego,id_jugador,tipo_prop,modelo_version,id_linea,payload)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE id_linea=nfl_publicaciones_props.id_linea''',rows)
        conn.commit()
    finally:
        cursor.close()


def attach_publications(conn, records):
    """Consulta opcional: la tabla puede no existir antes de la primera publicación."""
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id_juego,id_jugador,tipo_prop,modelo_version,id_linea,payload FROM nfl_publicaciones_props')
        saved = {(r['id_juego'],r['id_jugador'],r['tipo_prop'],r['modelo_version'],r['id_linea']):r['payload'] for r in cursor.fetchall()}
    except mysql.connector.Error as exc:
        if exc.errno != 1146: raise
        saved = {}
    finally:
        cursor.close()
    for row in records:
        row['auditoria_payload'] = saved.get(tuple(row[k] for k in ['id_juego','id_jugador','tipo_prop','modelo_version','id_linea']))
    return records
