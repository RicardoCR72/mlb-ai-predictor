"""Comparación fijada por anticipado: control de equipos vs abridores/bullpen."""
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.optimize import minimize_scalar
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from mlb_totales.core import FEATURES, distribution, probabilities
from mlb_totales.entrenar import score, LINES
from mlb_totales.pitcheo_features import PITCH_FEATURES, audit, pitching_features


def train(directory,output,v1_directory):
    root,out = Path(directory),Path(output)
    out.mkdir(parents=True,exist_ok=True)
    if not (root/'partidos_pitcheo.csv').exists():
        raise FileNotFoundError('Primero ejecuta python -m mlb_totales.descargar_pitcheo --hasta YYYY-MM-DD '
                                'para recuperar los datos fuente antes de reentrenar.')
    hist = pd.read_csv(root / 'partidos_pitcheo.csv')
    pitches = pd.read_csv(root / 'apariciones_pitcheo.csv')
    if hist.game_id.duplicated().any():
        raise ValueError('Calendario duplicado.')
    errors = audit(hist,pitches)
    errors.to_csv(out / 'auditoria_pitcheo.csv',index=False)
    # Cuarentena explícita, nunca completar inconsistencias con promedios inventados.
    excluded=set(errors.game_id)
    if len(excluded)/len(hist)>.005:
        raise ValueError('Más del 0.5% de juegos presenta incidencias. Revisa la descarga antes de entrenar.')
    if excluded:
        print(f'Cuarentena: {len(excluded)} juegos inconsistentes; ver auditoria_pitcheo.csv.',flush=True)
        hist=hist[~hist.game_id.isin(excluded)].copy()
        pitches=pitches[~pitches.game_id.isin(excluded)].copy()
    df = pitching_features(hist,pitches)
    # Los partidos a 7 innings sí aportan historial, no objetivos para totales de 9 innings.
    df = df[df.scheduled_innings == 9].reset_index(drop=True)
    df.to_csv(out / 'dataset_features.csv',index=False)
    y = df.home_runs + df.away_runs
    train_mask = df.season.between(2012,2023)
    regular = df.game_type == 'R'
    dates = sorted(df.loc[(df.season==2024)&regular,'fecha'].unique())
    if len(dates)<60:
        raise ValueError('Se requieren los juegos completos de 2024 para calibración/selección.')
    cut = dates[int(len(dates)*.6)]
    cal = (df.season==2024)&regular&(df.fecha<cut)
    sel = (df.season==2024)&regular&(df.fecha>=cut)
    columns = {'control_ridge':FEATURES+['is_playoff'],
               'control_histgb':FEATURES+['is_playoff'],
               'pitcheo_ridge':PITCH_FEATURES+['is_playoff'],
               'pitcheo_histgb':PITCH_FEATURES+['is_playoff']}
    def tree():
        return HistGradientBoostingRegressor(loss='poisson',max_iter=150,max_leaf_nodes=7,
             min_samples_leaf=150,learning_rate=.04,l2_regularization=20,
             early_stopping=False,random_state=42)
    models = {'control_ridge':make_pipeline(StandardScaler(),Ridge(alpha=100)),
              'control_histgb':tree(),
              'pitcheo_ridge':make_pipeline(StandardScaler(),Ridge(alpha=100)),
              'pitcheo_histgb':tree()}
    selection,alphas = {},{}
    for name,model in models.items():
        c=columns[name]
        model.fit(df.loc[train_mask,c],y[train_mask])
        mu=np.clip(model.predict(df.loc[cal,c]),.05,40)
        alpha=minimize_scalar(lambda a:-distribution(mu,a).logpmf(y[cal]).mean(),
                             bounds=(.0001,2),method='bounded').x
        alphas[name]=float(alpha)
        pred=np.clip(model.predict(df.loc[sel,c]),.05,40)
        selection[name]=dict(score(y[sel],pred,alpha),alpha=float(alpha))
        print(name,selection[name],flush=True)
    winner=min(selection,key=lambda k:selection[k]['logloss_grid'])
    enhanced=min((k for k in models if k.startswith('pitcheo_')),
                 key=lambda k:selection[k]['logloss_grid'])
    control=min((k for k in models if k.startswith('control_')),
                key=lambda k:selection[k]['logloss_grid'])
    report=dict(version=2,winner=winner,best_pitcheo=enhanced,best_control=control,
        selection_2024_last40=selection,train_games=int(train_mask.sum()),
        train_playoff_games=int((train_mask&~regular).sum()),calibration_games=int(cal.sum()),
        calibration_until_exclusive=str(pd.Timestamp(cut).date()),
        sklearn_version=sklearn.__version__,grid_lines=LINES.tolist(),
        data_until=str(df.fecha.max().date()),features=columns[winner],
        audit_errors=len(errors),quarantined_game_ids=sorted(excluded),
        regular={},playoffs={},v1_comparison={},
        note='Sin cuotas históricas: no mide ROI. Abridor real conocido como supuesto retrospectivo. '
             '2025/2026 ya se observaron en v1: se requiere evaluación futura para confirmar.',
        experimental=True,playoffs_experimental=True)
    for season in (2025,2026):
        all_mask=df.season==season
        if not all_mask.any():
            continue
        evaluated={}
        for name,model in models.items():
            mu=np.clip(model.predict(df.loc[all_mask,columns[name]]),.05,40)
            evaluated[name]=pd.Series(mu,index=df.index[all_mask])
        for label,mask in [('regular',all_mask&regular),('playoffs',all_mask&~regular)]:
            if mask.any():
                report[label][str(season)]={name:score(y[mask],values.loc[mask[mask].index],alphas[name])
                                               for name,values in evaluated.items()}
        pred=df.loc[all_mask,['game_id','fecha','home','away','game_type',
                            'home_pitcher_id','away_pitcher_id']].copy()
        pred['total_real']=y[all_mask].to_numpy()
        pred['total_pred']=evaluated[winner].to_numpy()
        for line in LINES:
            pred[f'p_over_{line}']=probabilities(pred.total_pred.to_numpy(),alphas[winner],line)[0]
        pred.to_csv(out / f'validacion_{season}.csv',index=False)
        old=Path(v1_directory)/f'validacion_{season}.csv'
        if old.exists():
            common=pred[pred.game_type=='R'].merge(pd.read_csv(old),on='game_id',suffixes=('_v2','_v1'),
                                                validate='one_to_one')
            # Comparación emparejada: mismos juegos y mismas líneas de evaluación.
            from sklearn.metrics import log_loss,brier_score_loss,mean_absolute_error
            vals={}
            for version in ('v1','v2'):
                ll,bs=[],[]
                for line in LINES:
                    probability=common[f'p_over_{line}_{version}']
                    truth=(common.total_real_v2>line).astype(int)
                    ll.append(log_loss(truth,np.clip(probability,1e-7,1-1e-7),labels=[0,1]))
                    bs.append(brier_score_loss(truth,probability))
                vals[version]=dict(mae=float(mean_absolute_error(common.total_real_v2,common[f'total_pred_{version}'])),
                                    logloss_grid=float(np.mean(ll)),brier_grid=float(np.mean(bs)),n_games=len(common))
            report['v1_comparison'][str(season)]=vals
    # Ganador decidido por 2024. No se cambia tras mirar 2025/2026.
    report['pitcheo_selected']=winner.startswith('pitcheo_')
    joblib.dump(dict(model=models[winner],alpha=alphas[winner],columns=columns[winner],metadata=report),
                out/'modelo_totales.joblib')
    # Guardar también challenger fijo para investigar si no ganó, sin sustituir al ganador.
    joblib.dump(dict(model=models[enhanced],alpha=alphas[enhanced],columns=columns[enhanced],metadata=report),
                out/'challenger_pitcheo.joblib')
    hist.to_csv(out/'historial_modelo.csv.gz',index=False,compression='gzip')
    pitches.to_csv(out/'historial_pitcheo.csv.gz',index=False,compression='gzip')
    coverage=root/'pitcheo.coverage.json'
    if coverage.exists():
        (out/'historial_modelo.coverage.json').write_text(coverage.read_text())
    (out/'metricas.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='features'},indent=2),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--datos',default='mlb_totales/data/pitcheo_v2')
    p.add_argument('--salida',default='mlb_totales/modelos_pitcheo')
    p.add_argument('--v1',default='mlb_totales/modelos')
    a=p.parse_args()
    train(a.datos,a.salida,a.v1)
