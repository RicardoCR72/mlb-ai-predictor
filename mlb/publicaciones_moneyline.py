"""Primera publicación Moneyline por evento/modelo; reloj UTC de MySQL."""
import hashlib
import inspect
import math
import pickle
import pandas as pd

DDL = ["""
CREATE TABLE IF NOT EXISTS mlb_moneyline_mercado (
 id_juego VARCHAR(128) NOT NULL PRIMARY KEY,
 start_utc DATETIME(6) NOT NULL, equipo_local VARCHAR(128) NOT NULL,
 equipo_visitante VARCHAR(128) NOT NULL, cuota_local DOUBLE NOT NULL,
 cuota_visitante DOUBLE NOT NULL, quote_utc DATETIME(6) NOT NULL,
 captured_utc DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""", """
CREATE TABLE IF NOT EXISTS mlb_publicaciones_moneyline (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 id_juego VARCHAR(128) NOT NULL, modelo CHAR(64) NOT NULL,
 fecha DATE NOT NULL, equipo_local VARCHAR(128) NOT NULL,
 equipo_visitante VARCHAR(128) NOT NULL, pick_ia VARCHAR(128) NOT NULL,
 probabilidad DOUBLE NOT NULL, cuota DOUBLE NOT NULL,
 start_utc DATETIME(6) NOT NULL, quote_utc DATETIME(6) NOT NULL,
 captured_utc DATETIME(6) NOT NULL, publicada_utc DATETIME(6) NOT NULL,
 UNIQUE KEY uq_mlb_moneyline_original (id_juego,modelo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""]


def prepare(conn):
    cursor=conn.cursor()
    try:
        for sql in DDL:cursor.execute(sql)
        conn.commit()
    finally:cursor.close()


def utc(value):
    stamp=pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError('Se requiere una hora explícita con zona.')
    return stamp.tz_convert('UTC').tz_localize(None).to_pydatetime()


def market_values(game):
    """Solo DraftKings y su hora de actualización; no inventar horas históricas."""
    try:
        start=utc(game['commence_time'])
        home,away=game['home_team'],game['away_team']
        for book in game.get('bookmakers',[]):
            if book.get('key')!='draftkings':continue
            for market in book.get('markets',[]):
                if market.get('key')!='h2h':continue
                quote=utc(market.get('last_update') or book.get('last_update'))
                prices={o['name']:float(o['price']) for o in market['outcomes']}
                h,a=prices[home],prices[away]
                if not all(math.isfinite(v) and v>1 for v in (h,a)) or quote>=start:return None
                return str(game['id']),start,home,away,h,a,quote
    except (KeyError,TypeError,ValueError,OverflowError):return None
    return None


MARKET_SQL="""
INSERT INTO mlb_moneyline_mercado
(id_juego,start_utc,equipo_local,equipo_visitante,cuota_local,cuota_visitante,quote_utc,captured_utc)
VALUES (%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE
 start_utc=IF(VALUES(quote_utc)>=quote_utc,VALUES(start_utc),start_utc),
 equipo_local=IF(VALUES(quote_utc)>=quote_utc,VALUES(equipo_local),equipo_local),
 equipo_visitante=IF(VALUES(quote_utc)>=quote_utc,VALUES(equipo_visitante),equipo_visitante),
 cuota_local=IF(VALUES(quote_utc)>=quote_utc,VALUES(cuota_local),cuota_local),
 cuota_visitante=IF(VALUES(quote_utc)>=quote_utc,VALUES(cuota_visitante),cuota_visitante),
 captured_utc=IF(VALUES(quote_utc)>quote_utc,UTC_TIMESTAMP(6),captured_utc),
 quote_utc=GREATEST(quote_utc,VALUES(quote_utc))
"""


def fingerprint(model,scaler,columns,adjustments):
    digest=hashlib.sha256()
    for weight in model.get_weights():
        digest.update(str(weight.shape).encode());digest.update(weight.tobytes())
    digest.update(pickle.dumps((scaler,list(columns)),protocol=4))
    for function in adjustments:digest.update(inspect.getsource(function).encode())
    return digest.hexdigest()


TODAY_SQL="""
SELECT j.id_juego,j.fecha AS Fecha,j.equipo_local AS `Equipo Local`,
 j.equipo_visitante AS `Equipo Visitante`,m.cuota_local AS `Paga Local`,
 m.cuota_visitante AS `Paga Visitante`
FROM juegos j JOIN mlb_moneyline_mercado m ON m.id_juego=j.id_juego
 AND m.equipo_local=j.equipo_local AND m.equipo_visitante=j.equipo_visitante
WHERE j.marcador_local IS NULL AND j.marcador_visitante IS NULL
 AND DATE(j.fecha)=%s AND m.start_utc>UTC_TIMESTAMP(6)
 AND m.quote_utc<=UTC_TIMESTAMP(6) AND m.captured_utc<=UTC_TIMESTAMP(6)
"""

# INSERT SELECT verifica el reloj de la BD y la captura exacta usada por la IA.
# Reintentos/otras visitas nunca cambian el original.
SAVE_SQL="""
INSERT INTO mlb_publicaciones_moneyline
(id_juego,modelo,fecha,equipo_local,equipo_visitante,pick_ia,probabilidad,cuota,
 start_utc,quote_utc,captured_utc,publicada_utc)
SELECT m.id_juego,%s,%s,m.equipo_local,m.equipo_visitante,%s,%s,%s,
 m.start_utc,m.quote_utc,m.captured_utc,UTC_TIMESTAMP(6)
FROM mlb_moneyline_mercado m WHERE m.id_juego=%s
 AND m.equipo_local=%s AND m.equipo_visitante=%s
 AND m.cuota_local=%s AND m.cuota_visitante=%s
 AND m.start_utc>UTC_TIMESTAMP(6) AND m.quote_utc<=UTC_TIMESTAMP(6)
 AND m.captured_utc<=UTC_TIMESTAMP(6)
 AND m.quote_utc<m.start_utc AND m.captured_utc<m.start_utc
ON DUPLICATE KEY UPDATE id=mlb_publicaciones_moneyline.id
"""


def save(conn,*,game_id,model_id,day,home,away,pick,confidence,home_odds,away_odds):
    p=float(confidence)/100
    h,a=float(home_odds),float(away_odds)
    if pick not in (home,away) or not math.isfinite(p) or not 0<=p<=1:
        raise ValueError('Predicción Moneyline inválida.')
    if not all(math.isfinite(v) and v>1 for v in (h,a)):
        raise ValueError('Cuotas Moneyline inválidas.')
    if len(model_id)!=64 or any(c not in '0123456789abcdef' for c in model_id):
        raise ValueError('Versión del modelo inválida.')
    cursor=conn.cursor()
    try:
        cursor.execute(SAVE_SQL,(model_id,day,pick,p,h if pick==home else a,
            str(game_id),home,away,h,a))
        count=cursor.rowcount
        conn.commit()
        return count==1
    except Exception:
        conn.rollback();raise
    finally:cursor.close()


HISTORY_SQL="""
SELECT s.*,CASE WHEN j.marcador_local IS NULL OR j.marcador_visitante IS NULL THEN 'PENDIENTE'
 WHEN j.marcador_local=j.marcador_visitante THEN 'REVISAR'
 WHEN (s.pick_ia=s.equipo_local AND j.marcador_local>j.marcador_visitante)
 OR (s.pick_ia=s.equipo_visitante AND j.marcador_visitante>j.marcador_local)
 THEN 'GANADA' ELSE 'PERDIDA' END AS resultado
FROM mlb_publicaciones_moneyline s JOIN juegos j ON j.id_juego=s.id_juego
 AND j.equipo_local=s.equipo_local AND j.equipo_visitante=s.equipo_visitante
WHERE s.publicada_utc<s.start_utc AND s.quote_utc<s.start_utc
 AND s.captured_utc<s.start_utc AND s.quote_utc<=s.publicada_utc
 AND s.captured_utc<=s.publicada_utc
ORDER BY s.publicada_utc ASC
"""
