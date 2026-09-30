import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.optimize import minimize_scalar
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, log_loss, brier_score_loss
from mlb_totales.core import FEATURES, features, distribution, probabilities

LINES = np.arange(6.5, 12, 1)


def score(y, mu, alpha):
    result = {'mae': float(mean_absolute_error(y, mu)),
              'rmse': float(np.sqrt(mean_squared_error(y, mu))),
              'bias': float(np.mean(mu - y)), 'n_games': len(y)}
    ll, bs = [], []
    for line in LINES:
        p, _, _ = probabilities(mu, alpha, line)
        target = (np.asarray(y) > line).astype(int)
        ll.append(log_loss(target, np.clip(p, 1e-7, 1-1e-7), labels=[0, 1]))
        bs.append(brier_score_loss(target, p))
    result.update(logloss_grid=float(np.mean(ll)), brier_grid=float(np.mean(bs)))
    return result


def train(csv, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    history = pd.read_csv(csv)
    if history.game_id.duplicated().any():
        raise ValueError('game_id duplicado; revisa el dataset.')
    if not (history.scheduled_innings == 9).all():
        raise ValueError('Este modelo requiere nueve innings programados.')
    df = features(history)
    y = df.home_runs + df.away_runs
    train_mask = df.season.between(2012, 2023)
    dates = sorted(df.loc[df.season == 2024, 'fecha'].unique())
    if len(dates) < 60:
        raise ValueError('Faltan datos de 2024 para calibrar y seleccionar.')
    cutoff = dates[int(len(dates) * .6)]
    cal = (df.season == 2024) & (df.fecha < cutoff)
    select = (df.season == 2024) & (df.fecha >= cutoff)
    candidates = {
        'media_liga': DummyRegressor(strategy='mean'),
        'ridge': make_pipeline(StandardScaler(), Ridge(alpha=100)),
        'histgb_poisson': HistGradientBoostingRegressor(loss='poisson', max_iter=150,
                              max_leaf_nodes=7, min_samples_leaf=150,
                              learning_rate=.04, l2_regularization=20,
                              early_stopping=False, random_state=42),
    }
    models, selection = {}, {}
    for name, model in candidates.items():
        model.fit(df.loc[train_mask, FEATURES], y[train_mask])
        mu_cal = np.clip(model.predict(df.loc[cal, FEATURES]), .05, 40)
        opt = minimize_scalar(lambda a: -distribution(mu_cal, a).logpmf(y[cal]).mean(),
                              bounds=(.0001, 2), method='bounded')
        alpha = float(opt.x)
        mu = np.clip(model.predict(df.loc[select, FEATURES]), .05, 40)
        selection[name] = dict(score(y[select], mu, alpha), alpha=alpha)
        models[name] = (model, alpha)
        print(name, selection[name], flush=True)
    winner = min(selection, key=lambda name: selection[name]['logloss_grid'])
    model, alpha = models[winner]
    report = {'winner': winner, 'selection_2024_last40': selection,
              'train_games': int(train_mask.sum()), 'calibration_games': int(cal.sum()),
              'calibration_until_exclusive': str(pd.Timestamp(cutoff).date()),
              'grid_lines': LINES.tolist(), 'sklearn_version': sklearn.__version__,
              'data_until': str(df.fecha.max().date()),
              'note': 'Grid fijo sin cuotas: no representa ROI ni evaluación contra línea de cierre.'}
    for season in (2025, 2026):
        mask = df.season == season
        if not mask.any():
            continue
        mu = np.clip(model.predict(df.loc[mask, FEATURES]), .05, 40)
        report[str(season)] = score(y[mask], mu, alpha)
        baseline, base_alpha = models['media_liga']
        report[f'baseline_{season}'] = score(y[mask], baseline.predict(df.loc[mask, FEATURES]), base_alpha)
        pred = df.loc[mask, ['game_id', 'fecha', 'home', 'away']].copy()
        pred['total_real'] = y[mask].to_numpy()
        pred['total_pred'] = mu
        for line in LINES:
            pred[f'p_over_{line}'] = probabilities(mu, alpha, line)[0]
        pred.to_csv(out / f'validacion_{season}.csv', index=False)
    report['experimental'] = (winner == 'media_liga' or
        any(report.get(str(s), {}).get('logloss_grid', 1) >= report.get(f'baseline_{s}', {}).get('logloss_grid', 1)
            for s in (2025, 2026) if str(s) in report))
    # El modelo se congela: no se reentrena sobre confirmación/OOS.
    joblib.dump(dict(model=model, alpha=alpha, columns=FEATURES, metadata=report), out / 'modelo_totales.joblib')
    history.to_csv(out / 'historial_modelo.csv', index=False)
    coverage = Path(csv).with_suffix('.coverage.json')
    if coverage.exists():
        (out / 'historial_modelo.coverage.json').write_text(coverage.read_text(), encoding='utf-8')
    (out / 'metricas.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--datos', default='mlb_totales/data/partidos.csv')
    p.add_argument('--salida', default='mlb_totales/modelos')
    a = p.parse_args()
    train(a.datos, a.salida)
