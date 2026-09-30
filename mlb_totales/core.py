"""Features causales y probabilidades discretas para totales de partido."""
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson


def features(history, fixtures=None, only_fixtures=False):
    """Todos los juegos de una fecha usan solo resultados de fechas anteriores.

    Dobles carteleras se conservan pero no usan el resultado del primer juego.
    Fixtures no actualizan el estado. No hay identificadores en X.
    """
    hist = history.copy()
    hist['is_fixture'] = False
    if fixtures is not None:
        fix = fixtures.copy()
        fix['is_fixture'] = True
        hist = pd.concat([hist, fix], ignore_index=True)
    hist['fecha'] = pd.to_datetime(hist['fecha']).dt.normalize()
    hist['season'] = hist['fecha'].dt.year
    teams = defaultdict(list)
    parks = defaultdict(list)
    league = defaultdict(list)
    output = []
    for fecha, batch in hist.sort_values('fecha', kind='stable').groupby('fecha', sort=True):
        for _, g in batch.iterrows():
            if only_fixtures and not g['is_fixture']:
                continue
            season = int(g['season'])
            prior = np.mean(league[season]) / 2 if league[season] else 4.5
            row = g.to_dict()
            row['league_runs'] = prior * 2
            for side in ('home', 'away'):
                records = teams[(season, int(g[side + '_id']))]
                scored = [x[1] for x in records]
                allowed = [x[2] for x in records]
                row[side + '_games'] = len(records)
                row[side + '_rest'] = min((fecha - records[-1][0]).days, 10) if records else 7
                for name, vals in [('scored', scored), ('allowed', allowed)]:
                    row[f'{side}_{name}_season'] = (sum(vals) + 20 * prior) / (len(vals) + 20)
                    for window in (7, 30):
                        v = vals[-window:]
                        row[f'{side}_{name}_{window}'] = (sum(v) + 5 * prior) / (len(v) + 5)
            venue = g.get('venue_id', -1)
            venue = -1 if pd.isna(venue) else int(venue)
            past = parks[(season, venue)]
            row['venue_total_prior'] = (sum(past) + 100 * prior * 2) / (len(past) + 100)
            row['month'] = fecha.month
            output.append(row)
        # Actualizar únicamente después de generar todas las filas del día.
        for _, g in batch.iterrows():
            if g['is_fixture']:
                continue
            season = int(g['season'])
            h, a = float(g['home_runs']), float(g['away_runs'])
            teams[(season, int(g['home_id']))].append((fecha, h, a))
            teams[(season, int(g['away_id']))].append((fecha, a, h))
            parks[(season, int(g['venue_id']))].append(h + a)
            league[season].append(h + a)
    return pd.DataFrame(output)


FEATURES = ['league_runs', 'venue_total_prior', 'month'] + [
    f'{side}_{suffix}' for side in ('home', 'away')
    for suffix in ('games', 'rest', 'scored_season', 'scored_7', 'scored_30',
                   'allowed_season', 'allowed_7', 'allowed_30')]


def distribution(mu, alpha):
    mu = np.clip(np.asarray(mu, dtype=float), 0.05, 40)
    return poisson(mu) if alpha < 1e-6 else nbinom(1 / alpha, (1 / alpha) / (1 / alpha + mu))


def probabilities(mu, alpha, line):
    line = np.asarray(line, dtype=float)
    if np.any(~np.isfinite(line)) or np.any(line < 0):
        raise ValueError('La línea debe ser finita y no negativa.')
    d = distribution(mu, alpha)
    over = d.sf(np.floor(line))
    under = d.cdf(np.ceil(line) - 1)
    push = np.where(line == np.floor(line), d.pmf(line), 0.0)
    return over, under, push


def decimal_odds(value):
    if pd.isna(value):
        return np.nan
    value = float(value)
    if value <= -100:
        return 1 + 100 / abs(value)
    if value >= 100:
        return 1 + value / 100
    if 1 < value < 100:
        return value
    raise ValueError(f'Momio inválido: {value}')
