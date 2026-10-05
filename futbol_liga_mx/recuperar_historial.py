"""Recupera 2025–26 desde fuentes gratuitas sin reemplazar otras temporadas."""
from pathlib import Path
import pandas as pd
from .datos import fetch, fetch_csv, read_season, read_csv_season, complete, audit, COLUMNS
from .inferencia import normalize_teams


def recover(path='futbol_liga_mx/data/partidos.csv', cache='futbol_liga_mx/data/cache'):
    path, cache = Path(path), Path(cache)
    saved = pd.read_csv(path)
    if complete(saved[saved.season == '2025-26']): return True
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
    if complete(combined):
        merged = normalize_teams(pd.concat([saved[saved.season != '2025-26'][COLUMNS], combined[COLUMNS]], ignore_index=True))
        tmp = path.with_suffix('.tmp')
        audit(merged).to_csv(tmp, index=False)
        tmp.replace(path)
        print('2025–26 recuperada. Modelo congelado conservado.')
        return True
    print('::warning::2025–26 sigue incompleta. Las predicciones permanecen suspendidas; no se inventan resultados.')
    return False


if __name__ == '__main__': recover()
