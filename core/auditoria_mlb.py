"""Auditoría de solo lectura de las primeras publicaciones MLB.

Compara registros existentes durante una actualización; no prueba que un dato
histórico nunca haya sido modificado antes de comenzar esta auditoría.
"""
from collections import Counter
import hashlib
import json
import math
import pandas as pd

SOURCES = {
    'Moneyline': ('mlb_publicaciones_moneyline', ('id_juego', 'modelo')),
    'Totales': ('mlb_totales_predicciones', ('game_pk', 'casa_apuestas', 'model_id')),
}


def valid(row, source):
    try:
        if source == 'Moneyline':
            p, odds = float(row['probabilidad']), float(row['cuota'])
            published = pd.Timestamp(row['publicada_utc'])
            clocks = [pd.Timestamp(row[k]) for k in ('quote_utc', 'captured_utc')]
            if row['pick_ia'] not in (row['equipo_local'], row['equipo_visitante']):return False
        else:
            if row['seleccion'] not in ('OVER', 'UNDER'):return False
            side = row['seleccion'].lower()
            p, odds = float(row['confianza']), float(row['cuota_seleccion'])
            probs = [float(row[k]) for k in ('p_over', 'p_under', 'p_push')]
            if not all(math.isfinite(v) and 0 <= v <= 1 for v in probs):return False
            if abs(sum(probs)-1) > 1e-6:return False
            if abs(p-float(row['p_'+side])) > 1e-6:return False
            if abs(odds-float(row['cuota_'+side])) > 1e-6:return False
            if not math.isfinite(float(row['linea'])):return False
            published = pd.Timestamp(row['recorded_utc'])
            clocks = [pd.Timestamp(row['quote_captured_utc'])]
        start = pd.Timestamp(row['start_utc'])
        return (math.isfinite(p) and 0 <= p <= 1 and math.isfinite(odds) and odds > 1
            and pd.notna(start) and pd.notna(published) and published < start
            and all(pd.notna(t) and t <= published and t < start for t in clocks))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def summarize(records, source):
    keys = SOURCES[source][1]
    identities = [tuple(str(r[k]).lower() if k == 'casa_apuestas' else str(r[k]) for k in keys) for r in records]
    hashes = {key: hashlib.sha256(json.dumps(row, sort_keys=True, default=str,
        ensure_ascii=False).encode()).hexdigest() for key, row in zip(identities, records)}
    return dict(filas=len(records),duplicados=sum(n-1 for n in Counter(identities).values()),
        invalidos=sum(not valid(r,source) for r in records),hashes=hashes)


def capture(conn):
    output = {}
    for source, (table, _) in SOURCES.items():
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT * FROM ' + table)
            output[source] = summarize(cursor.fetchall(), source)
        except Exception as exc:
            # No incluir errores de conexión ni datos privados en los logs.
            output[source] = dict(no_disponible=type(exc).__name__)
        finally:
            cursor.close()
    # Terminar el snapshot de lectura para que la siguiente captura vea cambios.
    conn.commit()
    return output


def compare(before, after):
    report = {}
    for source in SOURCES:
        a,b = before[source],after[source]
        if 'no_disponible' in a or 'no_disponible' in b:
            report[source] = dict(estado='NO_VERIFICABLE')
            continue
        old,new = a['hashes'],b['hashes']
        changed=sum(old[k] != new[k] for k in old.keys() & new.keys())
        removed=len(old.keys()-new.keys())
        report[source] = {k:b[k] for k in ('filas','duplicados','invalidos')}
        report[source].update(modificados=changed,eliminados=removed,nuevos=len(new.keys()-old.keys()))
        report[source]['estado']='REVISAR' if changed or removed or b['duplicados'] or b['invalidos'] else 'OK'
    return report
