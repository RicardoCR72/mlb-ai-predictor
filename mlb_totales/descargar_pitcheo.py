"""Descarga reanudable por lotes: resultados oficiales y apariciones de pitchers.

No utiliza las estadísticas agregadas de temporada como variables: esa consulta
solo enumera IDs. Los valores numéricos se reconstruyen desde gameLog por fecha.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import pandas as pd

TYPES = 'R,F,D,L,W'
PITCH_COLS = ['game_id','pitcher_id','pitcher','team_id','fecha_log','season',
              'game_type','started','outs','earned_runs','runs','hits','walks',
              'strikeouts','home_runs','pitches','batters_faced']


def fetch_json(endpoint, params, attempts=5):
    url = 'https://statsapi.mlb.com/api/v1/' + endpoint + '?' + urllib.parse.urlencode(params)
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'MLB-Totales-Research/2.0'})
            with urllib.request.urlopen(req, timeout=60) as response:
                obj = json.load(response)
            if obj.get('messageNumber') or 'error' in obj:
                raise ValueError(f'Respuesta API no válida: {obj.get("message", "error")}')
            return obj
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            if attempt == attempts - 1:
                raise
            delay = 2 ** attempt
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                try:
                    delay = min(60, max(delay, float(exc.headers.get('Retry-After', 10))))
                except ValueError:
                    delay = max(delay, 10)
            time.sleep(delay)


def atomic_csv(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    frame.to_csv(tmp, index=False)
    tmp.replace(path)


def innings_outs(value):
    whole, _, fraction = str(value).partition('.')
    fraction = fraction or '0'
    if fraction not in ('0','1','2'):
        raise ValueError(f'Innings MLB inválidos: {value}')
    return int(whole) * 3 + int(fraction)


def parse_people(data):
    rows = []
    for person in data.get('people', []):
        for block in person.get('stats', []):
            if block.get('group', {}).get('displayName') != 'pitching':
                continue
            for split in block.get('splits', []):
                if split.get('gameType') not in TYPES.split(','):
                    continue
                stat = split['stat']
                # Cero outs también es una aparición válida: no se descarta.
                outs = int(stat['outs']) if 'outs' in stat else innings_outs(stat['inningsPitched'])
                rows.append(dict(game_id=int(split['game']['gamePk']),
                    pitcher_id=int(person['id']), pitcher=person['fullName'],
                    team_id=int(split['team']['id']), fecha_log=split['date'],
                    season=int(split['season']), game_type=split['gameType'],
                    started=int(stat['gamesStarted']), outs=outs,
                    earned_runs=int(stat['earnedRuns']), runs=int(stat['runs']),
                    hits=int(stat['hits']), walks=int(stat['baseOnBalls']),
                    strikeouts=int(stat['strikeOuts']), home_runs=int(stat['homeRuns']),
                    pitches=stat.get('numberOfPitches'), batters_faced=stat.get('battersFaced')))
    return pd.DataFrame(rows, columns=PITCH_COLS)


def download_season(season, hasta, root, workers, batch_size):
    stamp = 'final' if season < int(hasta[:4]) else hasta
    cache = root / 'cache_pitcheo_v2' / str(season) / stamp
    cache.mkdir(parents=True, exist_ok=True)
    schedule_path = cache / 'schedule.json'
    if schedule_path.exists():
        schedule = json.loads(schedule_path.read_text(encoding='utf-8'))
    else:
        schedule = fetch_json('schedule', {'sportId':1,'season':season,'gameType':TYPES})
        schedule_path.write_text(json.dumps(schedule), encoding='utf-8')
    games = []
    excluded_resumes = set()
    for day in schedule.get('dates', []):
        for g in day['games']:
            if g['status'].get('abstractGameState') != 'Final':
                continue
            fecha = g.get('officialDate', day['date'])
            if fecha > hasta:
                continue
            if any(g.get(k) for k in ('resumeDate','resumedFrom','resumedFromDate')):
                excluded_resumes.add(g['gamePk'])
                continue
            h, a = g['teams']['home'], g['teams']['away']
            if 'score' not in h or 'score' not in a:
                continue
            games.append(dict(game_id=g['gamePk'],fecha=fecha,season=season,
                home_id=h['team']['id'],away_id=a['team']['id'],home=h['team']['name'],
                away=a['team']['name'],home_runs=h['score'],away_runs=a['score'],
                venue_id=g['venue']['id'],scheduled_innings=g.get('scheduledInnings',9),
                game_type=g['gameType']))
    ids_path = cache / 'pitcher_ids.json'
    if ids_path.exists():
        ids = json.loads(ids_path.read_text())
    else:
        # Enumera todos los que lanzaron, incluidos jugadores de posición.
        leaders = fetch_json('stats', {'stats':'season','group':'pitching','season':season,
                              'playerPool':'ALL','gameType':TYPES,'limit':2000})
        blocks = leaders.get('stats', [])
        if not blocks or not blocks[0].get('splits'):
            raise ValueError(f'Sin pitchers para {season}.')
        splits = blocks[0]['splits']
        if blocks[0].get('totalSplits',len(splits)) > len(splits):
            raise ValueError('Lista de pitchers truncada; revisa paginación antes de continuar.')
        ids = sorted(set(int(s['player']['id']) for s in splits))
        ids_path.write_text(json.dumps(ids))
    batches = [ids[i:i+batch_size] for i in range(0,len(ids),batch_size)]

    def part(batch):
        digest = hashlib.sha256(','.join(map(str,batch)).encode()).hexdigest()[:16]
        path = cache / f'logs_{digest}.csv'
        if path.exists():
            return pd.read_csv(path)
        data = fetch_json('people', {'personIds':','.join(map(str,batch)),
            'hydrate':f'stats(group=[pitching],type=[gameLog],season={season},gameType=[{TYPES}])'})
        returned = {int(p['id']) for p in data.get('people',[])}
        if returned != set(batch):
            raise ValueError('Respuesta de jugadores incompleta; no se guarda el lote.')
        df = parse_people(data)
        if df.empty:
            raise ValueError('Lote vacío: no se guarda como completado.')
        atomic_csv(df, path)
        return df

    frames = []
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        jobs = {executor.submit(part,batch):batch for batch in batches}
        for i,f in enumerate(as_completed(jobs),1):
            try:
                frames.append(f.result())
            except Exception as exc:
                failures.append({'season':season,'ids':jobs[f],'error':str(exc)})
            if i % 10 == 0 or i == len(jobs):
                print(f'{season}: lotes {i}/{len(jobs)}', flush=True)
    if failures:
        (root / 'errores_descarga_pitcheo.json').write_text(json.dumps(failures,indent=2))
        raise RuntimeError('Hubo lotes fallidos. Repite el comando; reutilizará los lotes completos.')
    pitches = pd.concat(frames,ignore_index=True).drop_duplicates(['game_id','pitcher_id','team_id'])
    games = pd.DataFrame(games).drop_duplicates('game_id').sort_values(['fecha','game_id'])
    # Solo resultados finalizados del calendario que no presentan reanudación ambigua.
    pitches = pitches[pitches.game_id.isin(games.game_id)].copy()
    pitches = pitches.merge(games[['game_id','fecha']],on='game_id',validate='many_to_one')
    pitches['fecha'] = pd.to_datetime(pitches.fecha)
    print(f'{season}: {len(games)} juegos, {len(pitches)} apariciones, '
          f'{len(excluded_resumes)} reanudaciones excluidas', flush=True)
    return games, pitches


def download(start,end,hasta,directory,workers=3,batch_size=30):
    date.fromisoformat(hasta)
    if not (2012 <= start <= end <= int(hasta[:4])):
        raise ValueError('Rango de temporadas inválido.')
    root = Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    games, pitches = [], []
    for season in range(start,end+1):
        g,p = download_season(season,hasta,root,workers,batch_size)
        games.append(g); pitches.append(p)
    g = pd.concat(games,ignore_index=True).drop_duplicates('game_id').sort_values(['fecha','game_id'])
    p = pd.concat(pitches,ignore_index=True).drop_duplicates(['game_id','pitcher_id','team_id'])
    p = p.sort_values(['fecha','game_id','team_id','pitcher_id'])
    atomic_csv(g,root / 'partidos_pitcheo.csv')
    atomic_csv(p,root / 'apariciones_pitcheo.csv')
    (root / 'pitcheo.coverage.json').write_text(json.dumps(
        {'inicio':start,'fin':end,'hasta':hasta,'schema':2,'game_types':TYPES},indent=2))
    return g,p


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inicio',type=int,default=2012)
    parser.add_argument('--fin',type=int,default=2026)
    parser.add_argument('--hasta',required=True)
    parser.add_argument('--directorio',default='mlb_totales/data/pitcheo_v2')
    parser.add_argument('--workers',type=int,choices=range(1,5),default=3)
    parser.add_argument('--lote',type=int,choices=range(5,51),default=30)
    a = parser.parse_args()
    download(a.inicio,a.fin,a.hasta,a.directorio,a.workers,a.lote)
