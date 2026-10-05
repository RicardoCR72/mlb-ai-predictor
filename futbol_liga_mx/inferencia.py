"""Una sola ruta de variables e inferencia para CLI, pantalla y bankroll."""
from datetime import datetime, timezone
import pandas as pd
from .modelo import build_features
from .continuidad import portable_probability, upcoming_features, upcoming_ready
from .proveedor_espn import canonical


def normalize_teams(frame):
    result = frame.copy()
    for column in ('local', 'visitante'):
        if column in result:
            result[column] = result[column].map(lambda name: canonical(name) or str(name).strip())
    return result


def historical_probabilities(games, params):
    # build_features actualiza el estado después de procesar toda la fecha.
    features = build_features(normalize_teams(games))
    features['p_over25'] = portable_probability(features, params)
    return features


def upcoming_probabilities(games, fixtures, params, metrics, now=None):
    now = now or datetime.now(timezone.utc)
    games = normalize_teams(games)
    fixtures = normalize_teams(fixtures)
    ready = upcoming_ready(games, fixtures, metrics, now)
    rows = []
    for fixture in ready.to_dict('records'):
        history = games[pd.to_datetime(games.fecha).lt(pd.Timestamp(fixture['fecha']))]
        p = float(portable_probability(upcoming_features(history, fixture), params)[0])
        rows.append({**fixture, 'p_over25': p, 'p_under25': 1 - p})
    return pd.DataFrame(rows, columns=list(ready.columns) + ['p_over25', 'p_under25'])
