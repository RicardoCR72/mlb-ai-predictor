"""Resultados oficiales: una fila por gamePk, temporada regular, nueve innings programados."""
import argparse
import json
import time
import urllib.request
from pathlib import Path
import pandas as pd


def descargar(inicio, fin, hasta, destino):
    destino = Path(destino)
    cache = destino.parent / 'cache_schedule'
    cache.mkdir(parents=True, exist_ok=True)
    filas = []
    for temporada in range(inicio, fin + 1):
        archivo = cache / f'{temporada}_{hasta}.json'
        if archivo.exists():
            datos = json.loads(archivo.read_text())
        else:
            url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&season={temporada}&gameType=R'
            for intento in range(4):
                try:
                    with urllib.request.urlopen(url, timeout=60) as respuesta:
                        datos = json.load(respuesta)
                    archivo.write_text(json.dumps(datos), encoding='utf-8')
                    break
                except Exception:
                    if intento == 3:
                        raise
                    time.sleep(2 ** intento)
        n = 0
        for dia in datos.get('dates', []):
            for g in dia['games']:
                if (g.get('gameType') != 'R' or g['status'].get('abstractGameState') != 'Final'
                    or g.get('scheduledInnings', 9) != 9
                    or any(g.get(k) for k in ('resumeDate', 'resumedFrom', 'resumedFromDate'))):
                    continue
                fecha = g.get('officialDate', dia['date'])
                if fecha > hasta:
                    continue
                h, a = g['teams']['home'], g['teams']['away']
                if 'score' not in h or 'score' not in a:
                    continue
                filas.append(dict(game_id=g['gamePk'], fecha=fecha, season=temporada,
                                  home_id=h['team']['id'], away_id=a['team']['id'],
                                  home=h['team']['name'], away=a['team']['name'],
                                  home_runs=h['score'], away_runs=a['score'],
                                  venue_id=g['venue']['id'], scheduled_innings=9))
                n += 1
        print(f'{temporada}: {n} partidos', flush=True)
    df = pd.DataFrame(filas).drop_duplicates('game_id').sort_values(['fecha', 'game_id'])
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False)
    destino.with_suffix('.coverage.json').write_text(
        json.dumps({'hasta': hasta, 'inicio': inicio, 'fin': fin}), encoding='utf-8')
    return df


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--inicio', type=int, default=2012)
    p.add_argument('--fin', type=int, default=2026)
    p.add_argument('--hasta', required=True, help='YYYY-MM-DD, último día completo')
    p.add_argument('--salida', default='mlb_totales/data/partidos.csv')
    a = p.parse_args()
    descargar(a.inicio, a.fin, a.hasta, a.salida)
