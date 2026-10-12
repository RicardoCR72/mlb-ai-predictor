"""Experimento temporal de yardas. No escribe modelos de producción ni consulta APIs."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

KEYS = ['game_id','player_id']
LINES = np.array([10.5,20.5,30.5,40.5,60.5,80.5,100.5])
ALPHAS = [0,.25,.5,.75,1]


def load_frames(dataset, predictions):
    if dataset.duplicated(KEYS).any() or predictions.duplicated(KEYS+['objetivo']).any():
        raise ValueError('IDs duplicados; no es posible comparar muestras equivalentes.')
    receptions = predictions[predictions.objetivo.eq('receptions')][KEYS+['prediccion']].rename(columns={'prediccion':'pred_rec'})
    yards = predictions[predictions.objetivo.eq('receiving_yards')].copy()
    if not yards.season.isin([2024,2025,2026]).all(): raise ValueError('Temporada de evaluación no prevista.')
    columns = KEYS+['player_receptions_avg_5','player_receiving_yards_avg_5','team_receptions_avg_5',
                    'player_targets_avg_5','player_injury_status']
    frame = yards.merge(receptions,on=KEYS,validate='one_to_one').merge(dataset[columns],on=KEYS,validate='one_to_one')
    if len(frame)!=len(yards): raise ValueError('Faltan recepciones o features para algunos jugadores.')
    frame['gameday'] = pd.to_datetime(frame.gameday)
    train = dataset[dataset.season.between(2012,2023)]
    sums = train.groupby('position')[['receiving_yards','receptions']].sum()
    prior = sums.receiving_yards/sums.receptions.replace(0,np.nan)
    frame['prior_ypr'] = frame.position.map(prior)
    if frame.prior_ypr.isna().any(): raise ValueError('No hay referencia de entrenamiento para una posición.')
    frame['recent_ypr'] = (frame.player_receiving_yards_avg_5/frame.player_receptions_avg_5.replace(0,np.nan)).fillna(frame.prior_ypr).clip(lower=0)
    frame['eligible'] = frame.player_targets_avg_5.ge(3) & ~frame.player_injury_status.isin(['out','doubtful'])
    if not np.isfinite(frame[['prediccion','pred_rec','receiving_yards','recent_ypr','prior_ypr']]).all().all():
        raise ValueError('Faltan predicciones, resultados o ratios finitos.')
    return frame


def alternative(frame, alpha, cap):
    rec = frame.pred_rec.clip(lower=0).copy()
    if cap:
        total = rec.groupby([frame.game_id,frame.team]).transform('sum')
        budget = frame.team_receptions_avg_5.clip(lower=0)
        scale = (budget/total.replace(0,np.nan)).clip(upper=1).fillna(1)
        rec *= scale
    return rec*(alpha*frame.recent_ypr+(1-alpha)*frame.prior_ypr)


def select_configuration(frame):
    selection = frame.season.eq(2024) & frame.eligible
    if not selection.any(): raise ValueError('Selección 2024 sin jugadores elegibles.')
    results = []
    for alpha in ALPHAS:
        for cap in [False,True]:
            prediction = alternative(frame,alpha,cap)
            results.append(dict(alpha=alpha,cap=cap,mae_2024=float((prediction[selection]-frame.loc[selection,'receiving_yards']).abs().mean())))
    return min(results,key=lambda r:(r['mae_2024'],r['alpha'],r['cap'])),results


def point_metrics(frame, prediction):
    error = prediction-frame.receiving_yards
    return dict(n=len(frame),mae=float(error.abs().mean()),rmse=float(np.sqrt((error**2).mean())),bias=float(error.mean()))


def clustered_interval(frame, delta, repetitions=2000):
    """Diferencia alternativa−actual; remuestreo por partido, no por pick."""
    summary = pd.DataFrame(dict(game=frame.game_id,delta=delta)).groupby('game').agg(total=('delta','sum'),n=('delta','size'))
    rng = np.random.default_rng(72)
    draws = rng.integers(0,len(summary),(repetitions,len(summary)))
    estimates = summary.total.to_numpy()[draws].sum(axis=1)/summary.n.to_numpy()[draws].sum(axis=1)
    return [float(x) for x in np.quantile(estimates,[.025,.975])]


def empirical_over(reference, target, column):
    result = np.empty((len(target),len(LINES)))
    all_residuals = reference.receiving_yards-reference[column]
    for position in target.position.unique():
        errors = reference.loc[reference.position.eq(position),'receiving_yards']-reference.loc[reference.position.eq(position),column]
        if len(errors)<100: errors=all_residuals
        if errors.empty: raise ValueError('No hay residuales para calibrar.')
        errors = np.sort(errors.to_numpy())
        mask = target.position.eq(position).to_numpy()
        # P(real > línea), con resultados enteros y líneas de media yarda: sin pushes.
        thresholds = LINES[None,:]-target.loc[mask,column].to_numpy()[:,None]
        result[mask] = 1-np.searchsorted(errors,thresholds,side='right')/len(errors)
    return np.clip(result,1e-6,1-1e-6)


def transform_probabilities(probabilities, mode, fitted=None):
    logits = np.log(probabilities/(1-probabilities))
    if mode=='platt': return fitted.predict_proba(logits.reshape(-1,1))[:,1].reshape(probabilities.shape)
    return 1/(1+np.exp(-logits/float(mode)))


def probability_metrics(frame, probabilities):
    actual = (frame.receiving_yards.to_numpy()[:,None]>LINES).astype(int)
    p = np.clip(probabilities,1e-6,1-1e-6)
    return dict(players=len(frame),cases=p.size,brier=float(((p-actual)**2).mean()),
                logloss=float(-(actual*np.log(p)+(1-actual)*np.log1p(-p)).mean()))


def select_calibration(frame, column):
    selection = frame[frame.season.eq(2024)].sort_values(['gameday','game_id','player_id'])
    dates = sorted(selection.gameday.unique())
    cutoff = dates[int(len(dates)*.5)]
    fit = selection[selection.gameday<cutoff]; validation = selection[(selection.gameday>=cutoff)&selection.eligible]
    if fit.empty or validation.empty: raise ValueError('No hay dos bloques temporales de selección.')
    fit_eligible = fit[fit.eligible]
    train_prob = empirical_over(fit,fit_eligible,column)
    train_label = (fit_eligible.receiving_yards.to_numpy()[:,None]>LINES).astype(int).ravel()
    platt = LogisticRegression(C=1,random_state=72).fit(np.log(train_prob/(1-train_prob)).reshape(-1,1),train_label)
    raw = empirical_over(fit,validation,column)
    choices=[]
    for mode in ['1.0','1.25','1.5','2.0','platt']:
        metrics = probability_metrics(validation,transform_probabilities(raw,mode,platt))
        choices.append(dict(mode=mode,**metrics))
    best = min(choices,key=lambda x:(x['logloss'],x['brier']))['mode']
    # Solo 2024 entra al ajuste final; 2025 y 2026 no modifican parámetros.
    full_eligible = selection[selection.eligible]
    full_prob = empirical_over(selection,full_eligible,column)
    labels = (full_eligible.receiving_yards.to_numpy()[:,None]>LINES).astype(int).ravel()
    final_platt = LogisticRegression(C=1,random_state=72).fit(np.log(full_prob/(1-full_prob)).reshape(-1,1),labels)
    return best,final_platt,choices,str(pd.Timestamp(cutoff).date())


def experiment(dataset, predictions):
    frame = load_frames(dataset,predictions)
    configuration,grid = select_configuration(frame)
    frame['alternative'] = alternative(frame,configuration['alpha'],configuration['cap'])
    point=[];probability=[];choices={};modes={}
    for column in ['prediccion','alternative']:
        mode,fitted,calibrations,cutoff = select_calibration(frame,column)
        choices[column]=dict(cutoff=cutoff,candidates=calibrations)
        modes[column]=mode
        reference = frame[frame.season.eq(2024)]
        for season in [2024,2025,2026]:
            for subset in ['all','eligible']:
                sample=frame[frame.season.eq(season)]
                if subset=='eligible':sample=sample[sample.eligible]
                if sample.empty:continue
                point.append(dict(model=column,season=season,subset=subset,**point_metrics(sample,sample[column])))
            if season==2024:continue # selección interna arriba, nunca presentada como confirmación
            sample=frame[frame.season.eq(season)&frame.eligible]
            if sample.empty:continue
            raw = empirical_over(reference,sample,column)
            for calibration,p in [('empirical',raw),(mode,transform_probabilities(raw,mode,fitted))]:
                probability.append(dict(model=column,season=season,calibration=calibration,**probability_metrics(sample,p)))
    confirmation=frame[frame.season.eq(2025)&frame.eligible]
    if confirmation.empty:raise ValueError('Falta confirmación 2025.')
    delta=(confirmation.alternative-confirmation.receiving_yards).abs()-(confirmation.prediccion-confirmation.receiving_yards).abs()
    interval=clustered_interval(confirmation,delta)
    # Confirmar el ajuste de probabilidades sobre jugadores emparejados y agrupando por partido.
    reference=frame[frame.season.eq(2024)]
    raw=empirical_over(reference,confirmation,'prediccion')
    chosen,model,_,_=select_calibration(frame,'prediccion')
    calibrated=transform_probabilities(raw,chosen,model)
    actual=(confirmation.receiving_yards.to_numpy()[:,None]>LINES).astype(int)
    def losses(p):
        p=np.clip(p,1e-6,1-1e-6)
        return -(actual*np.log(p)+(1-actual)*np.log1p(-p)).mean(axis=1)
    logloss_delta=pd.Series(losses(calibrated)-losses(raw),index=confirmation.index)
    probability_confirmation=dict(mode=chosen,logloss_difference=float(logloss_delta.mean()),
        game_bootstrap_95=clustered_interval(confirmation,logloss_delta))
    report=dict(selection=configuration,configuration_grid=grid,calibration_selection=choices,
        calibration_modes=modes,probability_confirmation=probability_confirmation,confirmation_mae_difference=float(delta.mean()),confirmation_game_bootstrap_95=interval,
        point_upgrade_confirmed=interval[1]<0,
        historical_market_roi=None,historical_market_roi_reason='No hay líneas/cuotas históricas verificadas de 2024–2025. La cuadrícula de líneas es sintética y no se usa para afirmar rentabilidad.',
        synthetic_lines=LINES.tolist(),oos_2026_first=str(frame[frame.season.eq(2026)].gameday.min().date()),
        oos_2026_last=str(frame[frame.season.eq(2026)].gameday.max().date()),
        production_changed=False)
    return report,pd.DataFrame(point),pd.DataFrame(probability)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=Path('data/nfl/processed/nfl_props_recepcion_features_2012_2026.parquet'))
    parser.add_argument('--predictions',type=Path,default=Path('modelos_nfl/props/predicciones_validacion_recepcion.csv'))
    parser.add_argument('--output',type=Path,default=Path('reports/nfl_yardas_validacion'))
    parser.add_argument('--source-ref',default='unspecified')
    parser.add_argument('--audit-file',type=Path)
    args=parser.parse_args()
    report,point,probability=experiment(pd.read_parquet(args.dataset),pd.read_csv(args.predictions))
    report['sources']={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in [args.dataset,args.predictions]}
    if args.audit_file:
        audit=pd.read_csv(args.audit_file)
        if not audit.resultado_pick.isin(['GANADA','PERDIDA','PUSH']).all():
            raise ValueError('La auditoría debe contener resultados evaluados.')
        mode=report['calibration_modes']['prediccion']
        if mode=='platt':
            report['live_audit']='No aplicado: falta probabilidad OVER y lado para reproducir Platt asimétrico.'
        else:
            live=audit[audit.resultado_pick.ne('PUSH')].copy()
            p=pd.to_numeric(live.probabilidad_pick,errors='raise').to_numpy()
            if not np.isfinite(p).all() or ((p<0)|(p>1)).any(): raise ValueError('Probabilidades inválidas en auditoría.')
            q=transform_probabilities(np.clip(p,1e-6,1-1e-6),mode)
            actual=live.resultado_pick.eq('GANADA').astype(int).to_numpy()
            live['brier_actual']=(p-actual)**2
            live['brier_candidato']=(q-actual)**2
            live['probabilidad_candidata']=q
            decimal=np.where(live.cuota_pick>0,1+live.cuota_pick/100,1+100/live.cuota_pick.abs())
            live['mantener_candidato']=(q>=.57)&(q*decimal-1>0)
            replay=[]
            for (season,week),group in live.groupby(['season','week']):
                kept=group[group.mantener_candidato]
                replay.append(dict(season=int(season),week=int(week),picks_actual=len(group),picks_candidato=len(kept),
                    unidades_actual=float(group['Unidades conocidas'].sum()),
                    unidades_candidato=float(kept['Unidades conocidas'].sum()),
                    roi_actual=float(group['Unidades conocidas'].mean()*100),
                    roi_candidato=float(kept['Unidades conocidas'].mean()*100) if len(kept) else None))
            args.output.mkdir(parents=True,exist_ok=True)
            pd.DataFrame(replay).to_csv(args.output/'live_replay_unverified.csv',index=False)

            grouped=live.groupby(['season','week']).agg(Picks=('week','size'),Brier_actual=('brier_actual','mean'),
                Brier_candidato=('brier_candidato','mean'),Confianza_actual=('probabilidad_pick','mean'),
                Confianza_candidata=('probabilidad_candidata','mean'))
            args.output.mkdir(parents=True,exist_ok=True)
            grouped.to_csv(args.output/'live_audit_metrics.csv')
            report['live_audit']=dict(rows=len(live),mode=mode,parameters_chosen_using_2026=False,
                original_publications_verified=bool(live.Fuente.eq('Publicación conservada').all()),
                brier_actual=float(live.brier_actual.mean()),brier_candidato=float(live.brier_candidato.mean()),
                sha256=hashlib.sha256(args.audit_file.read_bytes()).hexdigest())
    report['source_ref']=args.source_ref
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'decision.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    point.to_csv(args.output/'point_metrics.csv',index=False)
    probability.to_csv(args.output/'probability_metrics.csv',index=False)
    print(point.to_string(index=False));print(probability.to_string(index=False))
    print('Cambio de producción:',report['production_changed'],'| Confirmación MAE:',report['confirmation_mae_difference'],report['confirmation_game_bootstrap_95'])


if __name__=='__main__':main()
