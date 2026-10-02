"""Baseline de totales 2.5 Liga MX: variables anteriores al juego y evaluación temporal."""
from collections import defaultdict
from datetime import date
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression,PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES=['gf_local_5','gc_local_5','gf_visitante_5','gc_visitante_5',
          'puntos_local_5','puntos_visitante_5','descanso_local','descanso_visitante',
          'media_liga_local','media_liga_visitante','juegos_local','juegos_visitante']


def build_features(games):
    """Mismos partidos de una fecha ven el mismo historial: ninguno usa el marcador del día."""
    data=games.copy()
    required={'season','fecha','local','visitante','goles_local','goles_visitante'}
    if not required.issubset(data):raise ValueError('Faltan columnas: '+str(sorted(required-set(data))))
    data['fecha']=pd.to_datetime(data.fecha,format='ISO8601',errors='raise').dt.normalize()
    if data.duplicated(['fecha','local','visitante']).any():raise ValueError('Hay juegos duplicados.')
    data=data.sort_values(['fecha','local','visitante']).reset_index(drop=True)
    state=defaultdict(list);rows=[];league=[]
    for day,batch in data.groupby('fecha',sort=True):
        league_home=(sum(x[0] for x in league)+120*1.45)/(len(league)+120)
        league_away=(sum(x[1] for x in league)+120*1.20)/(len(league)+120)
        for row in batch.itertuples(index=False):
            home=state[row.local];away=state[row.visitante]
            def recent(records,target,prior):
                last=[r[target] for r in records[-5:]]
                return (sum(last)+5*prior)/(len(last)+5)
            features=dict(
                gf_local_5=recent(home,1,league_home),gc_local_5=recent(home,2,league_away),
                gf_visitante_5=recent(away,1,league_away),gc_visitante_5=recent(away,2,league_home),
                puntos_local_5=recent(home,3,1.3),puntos_visitante_5=recent(away,3,1.1),
                descanso_local=min(max((day-home[-1][0]).days,0),30) if home else 7,
                descanso_visitante=min(max((day-away[-1][0]).days,0),30) if away else 7,
                media_liga_local=league_home,media_liga_visitante=league_away,
                juegos_local=min(len(home),25),juegos_visitante=min(len(away),25))
            rows.append(dict(row._asdict(),**features))
        for row in batch.itertuples(index=False):
            h,a=int(row.goles_local),int(row.goles_visitante)
            state[row.local].append((day,h,a,3 if h>a else 1 if h==a else 0))
            state[row.visitante].append((day,a,h,3 if a>h else 1 if a==h else 0))
            league.append((h,a))
    result=pd.DataFrame(rows)
    result['total']=result.goles_local+result.goles_visitante
    result['over25']=(result.total>2).astype(int)
    return result


def p_over(mu):
    values=np.asarray(mu,dtype=float)
    values=np.clip(values,.05,15)
    return np.clip(1-np.exp(-values)*(1+values+values*values/2),1e-5,1-1e-5)


def score(y,p):
    y=np.asarray(y,dtype=int)
    p=np.clip(np.asarray(p,dtype=float),1e-5,1-1e-5)
    return dict(n=int(len(y)),real_over=float(y.mean()),prob_media=float(p.mean()),
                brier=float(np.mean((y-p)**2)),
                logloss=float(np.mean(-(y*np.log(p)+(1-y)*np.log1p(-p)))))


def fit(games,folder='futbol_liga_mx/modelos',min_games=300):
    data=build_features(games)
    counts=data.groupby('season').size().sort_index()
    if 'ronda' not in data:
        raise ValueError('Falta la columna ronda: vuelve a generar partidos.csv con futbol_liga_mx.datos.')
    stage_counts=data.assign(torneo=data.ronda.str.extract(r'^(Apertura|Clausura),',expand=False))
    stage_counts=stage_counts.groupby(['season','torneo']).size().unstack(fill_value=0)
    for stage in ('Apertura','Clausura'):
        if stage not in stage_counts:stage_counts[stage]=0
    eligible=[season for season,n in counts.items()
              if min_games<=n<=306 and all(150<=int(stage_counts.loc[season,stage])<=153
                                              for stage in ('Apertura','Clausura'))]
    if len(eligible)<6:
        raise ValueError(f'Solo {len(eligible)} temporadas completas (300–306 juegos; '
                         'mínimo 150 en Apertura y Clausura). Ejecuta primero '
                         'python -m futbol_liga_mx.datos y revisa cobertura.csv. '
                         f'Cobertura: {counts.to_dict()}')
    train_seasons=eligible[:-3]
    cal_season,selection_season,test_season=eligible[-3:]
    existing=Path(folder)/'metricas.json'
    if existing.exists() and test_season!='2024-25':
        prior=json.loads(existing.read_text(encoding='utf-8'))
        if prior.get('seasons',{}).get('confirmacion')=='2024-25':
            raise ValueError('Hay un modelo congelado con confirmación 2024-25. '
                             'Antes de reentrenar ejecuta python -m futbol_liga_mx.continuidad evaluar '
                             'para probar 2025-26 sin modificar ese modelo.')
    train=data[data.season.isin(train_seasons)]
    calibration=data[data.season==cal_season]
    selection=data[data.season==selection_season]
    test=data[data.season==test_season]
    model=make_pipeline(StandardScaler(),PoissonRegressor(alpha=.6,max_iter=600))
    model.fit(train[FEATURES],train.total)
    raw_cal=p_over(model.predict(calibration[FEATURES]))
    logit=lambda p:np.log(np.clip(p,1e-5,1-1e-5)/(1-np.clip(p,1e-5,1-1e-5)))
    calibrator=LogisticRegression(C=1.0,max_iter=200)
    if calibration.over25.nunique()<2:
        raise ValueError('Temporada de calibración sin ambas clases OVER/UNDER.')
    calibrator.fit(logit(raw_cal).reshape(-1,1),calibration.over25)
    def evaluate(part):
        raw=p_over(model.predict(part[FEATURES]))
        calibrated=calibrator.predict_proba(logit(raw).reshape(-1,1))[:,1]
        return raw,calibrated
    val_raw,val_cal=evaluate(selection)
    choice='calibrada' if score(selection.over25,val_cal)['logloss']<score(selection.over25,val_raw)['logloss'] else 'sin_calibrar'
    test_raw,test_cal=evaluate(test)
    baseline=float(train.over25.mean())
    report=dict(seasons=dict(entrenamiento=train_seasons,calibracion=cal_season,
                             seleccion=selection_season,confirmacion=test_season),
                train_games=len(train),coverage=counts.to_dict(),winner=choice,
                selection=dict(raw=score(selection.over25,val_raw),
                               calibrated=score(selection.over25,val_cal)),
                confirmation=dict(raw=score(test.over25,test_raw),
                                  calibrated=score(test.over25,test_cal),
                                  baseline=score(test.over25,np.full(len(test),baseline))))
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    (folder/'metricas.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    scaler,poisson=model.steps[0][1],model.steps[1][1]
    params=dict(features=FEATURES,mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),
                coef=poisson.coef_.tolist(),intercept=float(poisson.intercept_),
                calibration=dict(coef=float(calibrator.coef_[0,0]),
                                 intercept=float(calibrator.intercept_[0])),winner=choice,
                train_last=str(train.fecha.max().date()))
    (folder/'modelo_portable.json').write_text(json.dumps(params,indent=2,ensure_ascii=False),encoding='utf-8')
    out=test[['season','fecha','local','visitante','total','over25']].copy()
    out['p_sin_calibrar']=test_raw;out['p_calibrada']=test_cal
    out.to_csv(folder/'confirmacion.csv',index=False)
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return report


def run():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--partidos',default='futbol_liga_mx/data/partidos.csv')
    p.add_argument('--modelos',default='futbol_liga_mx/modelos')
    args=p.parse_args()
    fit(pd.read_csv(args.partidos),args.modelos)


if __name__=='__main__':run()
