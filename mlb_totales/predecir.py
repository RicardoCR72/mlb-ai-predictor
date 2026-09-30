import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from mlb_totales.core import features, probabilities, decimal_odds

IDS = {'ARI':109,'ATL':144,'BAL':110,'BOS':111,'CHC':112,'CWS':145,
       'CIN':113,'CLE':114,'COL':115,'DET':116,'HOU':117,'KC':118,
       'LAA':108,'LAD':119,'MIA':146,'MIL':158,'MIN':142,'NYM':121,
       'NYY':147,'OAK':133,'ATH':133,'PHI':143,'PIT':134,'SD':135,
       'SF':137,'SEA':136,'STL':138,'TB':139,'TEX':140,'TOR':141,'WSH':120}


def resolve_team(value, history):
    key = str(value).strip().upper()
    if key in IDS:
        return IDS[key]
    catalog = pd.concat([history[['home_id', 'home']].rename(columns={'home_id':'id','home':'name'}),
                         history[['away_id', 'away']].rename(columns={'away_id':'id','away':'name'})])
    match = catalog[catalog.name.str.upper() == key]
    if match.empty:
        raise ValueError(f'Equipo desconocido: {value}. Usa abreviaturas MLB como LAD, NYY, ATL.')
    return int(match.iloc[-1].id)


def predict(fixtures, directory):
    directory = Path(directory)
    # Cargar solo el archivo generado por este paquete, no archivos joblib desconocidos.
    bundle = joblib.load(directory / 'modelo_totales.joblib')
    if sklearn.__version__ != bundle['metadata']['sklearn_version']:
        raise RuntimeError('Versión sklearn diferente al entrenamiento. Instala requirements_mlb_totales.txt '
                           'en el entorno separado o reentrena con tu entorno antes de desplegar.')
    history = pd.read_csv(directory / 'historial_modelo.csv')
    rows = fixtures.copy().reset_index(drop=True)
    if not {'fecha', 'local', 'visitante', 'linea'}.issubset(rows):
        raise ValueError('CSV requiere fecha,local,visitante,linea (cuota_over/cuota_under opcionales).')
    if rows.empty:
        raise ValueError('No hay partidos para predecir.')
    rows['fecha'] = pd.to_datetime(rows.fecha, errors='raise').dt.normalize()
    if (rows.fecha.dt.year < 2024).any():
        raise ValueError('Este modelo está entrenado hasta 2023; predice desde 2024.')
    for col in ('cuota_over', 'cuota_under'):
        if col not in rows:
            rows[col] = np.nan
        rows[col] = pd.to_numeric(rows[col], errors='raise').map(decimal_odds)
    rows['linea'] = pd.to_numeric(rows.linea, errors='raise')
    if not np.isfinite(rows.linea).all() or (rows.linea <= 0).any():
        raise ValueError('Línea inválida.')
    rows['fixture_index'] = np.arange(len(rows))
    rows['home_id'] = rows.local.map(lambda v: resolve_team(v, history))
    rows['away_id'] = rows.visitante.map(lambda v: resolve_team(v, history))
    if (rows.home_id == rows.away_id).any():
        raise ValueError('Local y visitante deben ser distintos.')
    if 'tipo_partido' in rows and (rows.tipo_partido != 'R').any():
        raise ValueError('Versión 1 validada solamente en temporada regular; no aplicar a playoffs/pretemporada.')
    if 'venue_id' not in rows:
        rows['venue_id'] = np.nan
    for idx, r in rows.iterrows():
        if pd.isna(r.venue_id):
            prior = history[(history.home_id == r.home_id) & (history.fecha < str(r.fecha.date()))]
            rows.loc[idx, 'venue_id'] = int(prior.iloc[-1].venue_id) if len(prior) else -1
    built = features(history, rows)
    built = built[built.is_fixture].sort_values('fixture_index')
    mu = np.clip(bundle['model'].predict(built[bundle['columns']]), .05, 40)
    po, pu, pp = probabilities(mu, bundle['alpha'], rows.linea.to_numpy())
    result = rows[['fecha', 'local', 'visitante', 'linea', 'cuota_over', 'cuota_under']].copy()
    result['total_proyectado'] = mu
    result['edge_carreras'] = mu - rows.linea
    result['p_over'] = po
    result['p_under'] = pu
    result['p_push'] = pp
    result['ev_over'] = po * (rows.cuota_over - 1) - pu
    result['ev_under'] = pu * (rows.cuota_under - 1) - po
    # Probabilidad condicional sin push para comparar con 1/cuota.
    result['p_over_sin_push'] = po / (1 - pp)
    result['p_under_sin_push'] = pu / (1 - pp)
    picks, states = [], []
    for _, r in result.iterrows():
        if pd.isna(r.ev_over) and pd.isna(r.ev_under):
            picks.append('OVER' if r.p_over >= r.p_under else 'UNDER')
            states.append('SIN_CUOTAS')
        else:
            evs = {'OVER':r.ev_over, 'UNDER':r.ev_under}
            evs = {k:v for k,v in evs.items() if pd.notna(v)}
            pick = max(evs, key=evs.get)
            picks.append(pick)
            states.append('CANDIDATO' if evs[pick] > 0 else 'SIN_VALOR')
    result['seleccion'] = picks
    result['estado'] = states
    result['prob_seleccion'] = np.where(result.seleccion == 'OVER', po, pu)
    result['modelo_experimental'] = bundle['metadata']['experimental']
    result['validacion_mercado'] = 'PENDIENTE'
    if bundle['metadata']['experimental']:
        result['estado'] = 'EXPERIMENTAL'
    coverage_path = directory / 'historial_modelo.coverage.json'
    coverage = json.loads(coverage_path.read_text())['hasta'] if coverage_path.exists() else history.fecha.max()
    result['historial_hasta'] = coverage
    result['dias_desde_historial'] = (rows.fecha - pd.to_datetime(coverage)).dt.days.clip(lower=0)
    stale = result.dias_desde_historial > 1
    result.loc[stale, 'estado'] = 'ACTUALIZAR_HISTORIAL'
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--modelos', default='mlb_totales/modelos')
    p.add_argument('--entrada', help='CSV de partidos y líneas reales')
    p.add_argument('--fecha')
    p.add_argument('--local')
    p.add_argument('--visitante')
    p.add_argument('--linea', type=float)
    p.add_argument('--cuota-over', type=float, default=np.nan)
    p.add_argument('--cuota-under', type=float, default=np.nan)
    p.add_argument('--salida', default='mlb_totales/predictions/predicciones.csv')
    a = p.parse_args()
    if a.entrada:
        fixtures = pd.read_csv(a.entrada)
    else:
        if any(v is None for v in (a.fecha, a.local, a.visitante, a.linea)):
            p.error('Usa --entrada o --fecha --local --visitante --linea.')
        fixtures = pd.DataFrame([dict(fecha=a.fecha, local=a.local, visitante=a.visitante,
                       linea=a.linea, cuota_over=a.cuota_over, cuota_under=a.cuota_under)])
    result = predict(fixtures, a.modelos)
    Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(a.salida, index=False)
    print(result.round(4).to_string(index=False))
