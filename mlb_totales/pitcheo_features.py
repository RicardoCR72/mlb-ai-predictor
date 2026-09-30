"""Históricos previos al día del juego, con abridor observado/indicado y bullpen."""
from collections import defaultdict
import numpy as np
import pandas as pd
from mlb_totales.core import FEATURES, features

SP = ['sp_era_365','sp_whip_365','sp_k9_365','sp_bb9_365','sp_hr9_365',
      'sp_era_last5','sp_whip_last5','sp_ip_last5','sp_pitches_last5',
      'sp_starts_365','sp_rest_days','sp_ip_365','sp_missing']
BP = ['bp_era_14d','bp_whip_14d','bp_k9_14d','bp_era_season',
      'bp_pitches_1d','bp_pitches_3d','bp_ip_3d','bp_appearances_3d','bp_ip_14d']
PITCH_FEATURES = FEATURES + [f'{s}_{x}' for s in ('home','away') for x in SP+BP]
PITCH_FEATURES += ['pitching_expected_runs']


def rate(records, field, factor, prior, prior_ip):
    ip = sum(r['outs'] for r in records) / 3
    return (sum(r[field] for r in records) * factor + prior_ip * prior) / (ip + prior_ip)


def sp_features(records, fecha, unknown=False):
    last365 = [r for r in records if (fecha - r['fecha']).days <= 365]
    starts = [r for r in last365 if r['started'] == 1]
    last5 = starts[-5:]
    # Constantes de regularización, no ajustes de probabilidad. Se declaran en el manual.
    era = rate(last365,'earned_runs',9,4.3,30)
    whip = (sum(r['hits']+r['walks'] for r in last365) + 30*1.3) / (
        sum(r['outs'] for r in last365)/3 + 30)
    recent_whip = (sum(r['hits']+r['walks'] for r in last5)+15*1.3) / (
        sum(r['outs'] for r in last5)/3 + 15)
    valid_pitches = [r['pitches'] for r in last5 if np.isfinite(r['pitches'])]
    return dict(sp_era_365=era,sp_whip_365=whip,
        sp_k9_365=rate(last365,'strikeouts',9,8.5,30),
        sp_bb9_365=rate(last365,'walks',9,3.2,30),
        sp_hr9_365=rate(last365,'home_runs',9,1.2,30),
        sp_era_last5=rate(last5,'earned_runs',9,4.3,15),sp_whip_last5=recent_whip,
        sp_ip_last5=(sum(r['outs'] for r in last5)/3+10.8)/(len(last5)+2),
        sp_pitches_last5=(sum(valid_pitches)+180)/(len(valid_pitches)+2),
        sp_starts_365=len(starts),
        sp_rest_days=min((fecha-records[-1]['fecha']).days,60) if records else 60,
        sp_ip_365=sum(r['outs'] for r in last365)/3,sp_missing=int(unknown))


def bp_features(records, fecha):
    season = [r for r in records if r['fecha'].year == fecha.year]
    last14 = [r for r in records if (fecha-r['fecha']).days <= 14]
    last3 = [r for r in records if (fecha-r['fecha']).days <= 3]
    last1 = [r for r in records if (fecha-r['fecha']).days == 1]
    return dict(bp_era_14d=rate(last14,'earned_runs',9,4.3,15),
        bp_whip_14d=(sum(r['hits']+r['walks'] for r in last14)+15*1.3)/(
            sum(r['outs'] for r in last14)/3+15),
        bp_k9_14d=rate(last14,'strikeouts',9,8.5,15),
        bp_era_season=rate(season,'earned_runs',9,4.3,30),
        bp_pitches_1d=sum(r['pitches'] for r in last1 if np.isfinite(r['pitches'])),
        bp_pitches_3d=sum(r['pitches'] for r in last3 if np.isfinite(r['pitches'])),
        bp_ip_3d=sum(r['outs'] for r in last3)/3,
        bp_appearances_3d=len(last3),bp_ip_14d=sum(r['outs'] for r in last14)/3)


def audit(history,pitches):
    required = {'game_id','team_id','pitcher_id','started','outs','fecha'}
    if not required.issubset(pitches):
        raise ValueError(f'Faltan columnas de pitcheo: {sorted(required-set(pitches))}')
    if pitches.duplicated(['game_id','team_id','pitcher_id']).any():
        raise ValueError('Apariciones de pitcheo duplicadas.')
    if (pitches.outs < 0).any() or not pitches.started.isin([0,1]).all():
        raise ValueError('Outs o gamesStarted inválidos.')
    groups = pitches.groupby(['game_id','team_id']).agg(starters=('started','sum'),
                         pitchers=('pitcher_id','size'),outs=('outs','sum'),runs=('runs','sum'))
    errors = []
    for g in history.itertuples(index=False):
        for side in ('home','away'):
            team_id = getattr(g,side+'_id')
            key = (g.game_id,team_id)
            if key not in groups.index:
                errors.append(dict(game_id=g.game_id,team_id=team_id,reason='sin_apariciones'))
            elif groups.loc[key,'starters'] != 1:
                errors.append(dict(game_id=g.game_id,team_id=team_id,reason='abridor_ambiguo'))
            elif groups.loc[key,'outs'] <= 0:
                errors.append(dict(game_id=g.game_id,team_id=team_id,reason='sin_outs'))
            elif groups.loc[key,'runs'] != getattr(g,('away' if side=='home' else 'home')+'_runs'):
                errors.append(dict(game_id=g.game_id,team_id=team_id,reason='carreras_no_concilian'))
    return pd.DataFrame(errors,columns=['game_id','team_id','reason'])


def pitching_features(history,pitches,fixtures=None):
    pitches = pitches.copy()
    pitches['fecha'] = pd.to_datetime(pitches.fecha).dt.normalize()
    if pitches.duplicated(['game_id','team_id','pitcher_id']).any():
        raise ValueError('Apariciones duplicadas: no se puede construir el historial.')
    pitchers = defaultdict(list)
    bullpens = defaultdict(list)
    starter_rows = pitches[pitches.started == 1]
    if starter_rows.duplicated(['game_id','team_id']).any():
        raise ValueError('Más de un abridor por equipo/juego; resolver auditoría antes de entrenar.')
    starters = {(int(r.game_id),int(r.team_id)):int(r.pitcher_id)
                for r in starter_rows.itertuples(index=False)}
    # Para pronosticar, actualizar estados históricos sin calcular features de cada juego pasado.
    if fixtures is not None:
        last_date=pd.to_datetime(fixtures.fecha).dt.normalize().max()
        history=history[pd.to_datetime(history.fecha).dt.normalize()<=last_date]
        pitches=pitches[pitches.fecha<last_date]
    # Los juegos a siete innings aportan historial, pero no son objetivos de entrenamiento.
    base = features(history,fixtures,only_fixtures=fixtures is not None)
    base['is_playoff'] = base.get('game_type',pd.Series('R',index=base.index)).fillna('R').ne('R').astype(int)
    rows_by_date = {d:g for d,g in base.groupby('fecha',sort=True)}
    pitch_by_date = {d:g.to_dict('records') for d,g in pitches.groupby('fecha',sort=True)}
    output = []
    for fecha in sorted(set(rows_by_date) | set(pitch_by_date)):
        batch = rows_by_date.get(fecha)
        if batch is not None:
            for _,g in batch.iterrows():
                row = g.to_dict()
                for side in ('home','away'):
                    team = int(g[side+'_id'])
                    if g['is_fixture']:
                        value = g.get(side+'_pitcher_id')
                        pid = None if pd.isna(value) else int(value)
                    else:
                        pid = starters.get((int(g['game_id']),team))
                    row[side+'_pitcher_id'] = pid
                    sp = sp_features(pitchers[pid] if pid is not None else [],fecha,unknown=pid is None)
                    bp = bp_features(bullpens[team],fecha)
                    row.update({side+'_'+k:v for k,v in dict(sp,**bp).items()})
                expected = 0
                for side in ('home','away'):
                    ip = min(max(row[side+'_sp_ip_last5'],1),8)
                    expected += (row[side+'_sp_era_365']*ip + row[side+'_bp_era_14d']*(9-ip))/9
                row['pitching_expected_runs'] = expected
                output.append(row)
        # Ni las estadísticas de hoy ni el primer juego de una doble cartelera entran antes.
        for r in pitch_by_date.get(fecha,[]):
            pitchers[int(r['pitcher_id'])].append(r)
            if r['started'] == 0:
                bullpens[int(r['team_id'])].append(r)
        # Acotar memoria de bullpen: conservar temporada y 14 días que cruzan enero.
        for team in bullpens:
            bullpens[team] = [r for r in bullpens[team]
                             if r['fecha'].year == fecha.year or (fecha-r['fecha']).days <= 14]
    return pd.DataFrame(output)
