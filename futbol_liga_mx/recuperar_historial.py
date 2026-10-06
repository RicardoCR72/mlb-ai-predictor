"""Recupera 2025–26 desde fuentes gratuitas sin reemplazar otras temporadas."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
from .datos import fetch, fetch_csv, read_season, read_csv_season, complete, audit, COLUMNS
from .inferencia import normalize_teams


def espn_history(cache):
    """Consulta días de 2025–26; cada respuesta exitosa queda cacheada."""
    from .proveedor_espn import get_scoreboard
    cache = Path(cache)/'espn_2025_26'
    cache.mkdir(parents=True, exist_ok=True)
    days = [date(2025,7,1)+timedelta(days=i) for i in range(365)]
    def load(day):
        path = cache/(day.isoformat()+'.json')
        if path.exists(): return json.loads(path.read_text())
        events = get_scoreboard(day.strftime('%Y%m%d'))
        path.write_text(json.dumps(events),encoding='utf-8')
        return events
    # Cuatro peticiones simultáneas; una falla mantiene el bloqueo de publicación.
    with ThreadPoolExecutor(max_workers=4) as pool:
        events = [event for group in pool.map(load,days) for event in group]
    return read_espn_history(events)


def read_espn_history(events):
    from .proveedor_espn import canonical
    records = {}
    for event in events:
        phase = (event.get('season') or {}).get('slug')
        if phase not in ('torneo-apertura','torneo-clausura'): continue
        comp = (event.get('competitions') or [{}])[0]
        status = event.get('status',comp.get('status',{})).get('type',{})
        if status.get('name') not in ('STATUS_FULL_TIME','STATUS_FINAL'): continue
        try:
            kickoff = datetime.fromisoformat(event['date'].replace('Z','+00:00'))
            if kickoff.tzinfo is None: continue
            day = kickoff.astimezone(ZoneInfo('America/Mexico_City')).date()
            if not date(2025,7,1) <= day <= date(2026,6,30): continue
            stage = 'Apertura' if phase=='torneo-apertura' else 'Clausura'
            if (stage=='Apertura') != (day.month>=7): continue
            teams = {c['homeAway']:c for c in comp['competitors']}
            home,away = canonical(teams['home']['team']['displayName']),canonical(teams['away']['team']['displayName'])
            scores = [int(teams[side]['score']) for side in ('home','away')]
            if not home or not away or home==away or min(scores)<0: continue
            records[event['id']] = dict(season='2025-26',fecha=day.isoformat(),local=home,visitante=away,
                goles_local=scores[0],goles_visitante=scores[1],ronda=stage+', fase regular',
                source_file='ESPN /scoreboard event='+str(event['id']))
        except (KeyError,ValueError,TypeError): continue
    frame = pd.DataFrame(records.values(),columns=COLUMNS)
    # No inferir jornadas por proximidad de fechas: los aplazados conservan fase.
    return frame


def strict_regular_coverage(frame):
    """Dos torneos de 18 equipos: 153 juegos y 17 rivales distintos por equipo."""
    if not complete(frame): return False
    for stage in ('Apertura','Clausura'):
        data = frame[frame.ronda.str.startswith(stage+',')]
        teams = pd.concat([data.local,data.visitante]).value_counts()
        pairs = data.apply(lambda r:tuple(sorted((r.local,r.visitante))),axis=1)
        if len(data)!=153 or len(teams)!=18 or not teams.eq(17).all() or pairs.duplicated().any():
            return False
    return True


def recover(path='futbol_liga_mx/data/partidos.csv', cache='futbol_liga_mx/data/cache'):
    path, cache = Path(path), Path(cache)
    saved = pd.read_csv(path)
    if strict_regular_coverage(normalize_teams(saved[saved.season == '2025-26'])): return True
    candidates = [saved[saved.season == '2025-26']]
    for loader, reader, filename in ((fetch, read_season, '2025-26/mx.1.json'),
                                     (fetch_csv, read_csv_season, '2025-26/mx.1.csv')):
        try:
            payload = loader(2025, cache)
            if payload is not None:
                frame, _ = reader(payload, '2025-26', filename)
                candidates.append(frame)
        except Exception as exc:
            print(f'Fuente no disponible: {type(exc).__name__}')
    combined = normalize_teams(pd.concat(candidates, ignore_index=True))
    combined = combined.drop_duplicates(['fecha','local','visitante'], keep='last')
    if not strict_regular_coverage(combined):
        try:
            # Preferir la temporada ESPN auditada entera; nunca mezclar eliminatorias.
            espn = espn_history(cache)
            if strict_regular_coverage(espn): combined = espn
        except Exception as exc:
            print(f'Historial ESPN no disponible: {type(exc).__name__}')
    if strict_regular_coverage(combined):
        merged = normalize_teams(pd.concat([saved[saved.season != '2025-26'][COLUMNS], combined[COLUMNS]], ignore_index=True))
        tmp = path.with_suffix('.tmp')
        audit(merged).to_csv(tmp, index=False)
        tmp.replace(path)
        coverage = path.with_name('cobertura_2025_26.json')
        coverage.write_text(json.dumps({'season':'2025-26','regular':len(combined),
            'apertura':153,'clausura':153,'teams_per_stage':18,'games_per_team':17,
            'verified_utc':datetime.now(ZoneInfo('UTC')).isoformat(),
            'sources':sorted(combined.source_file.unique().tolist())},ensure_ascii=False,indent=2))
        print('2025–26 recuperada y auditada. Modelo congelado conservado.')
        return True
    print('::warning::2025–26 sigue incompleta. Las predicciones permanecen suspendidas; no se inventan resultados.')
    return False


if __name__ == '__main__': recover()
