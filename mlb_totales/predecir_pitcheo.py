"""Predicciones usando abridores anunciados e historial previo; no consulta cuotas."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from mlb_totales.core import probabilities, decimal_odds
from mlb_totales.predecir import resolve_team
from mlb_totales.pitcheo_features import pitching_features


def predict(fixtures,directory='mlb_totales/modelos_pitcheo',portable=False):
    root=Path(directory)
    if portable:
        from mlb_totales.portable import load
        bundle=load(root)
    else:
        import joblib
        import sklearn
        bundle=joblib.load(root/'modelo_totales.joblib')
        if bundle['metadata']['sklearn_version']!=sklearn.__version__:
            raise RuntimeError('Instala requirements_mlb_totales.txt en el entorno separado; versión sklearn incompatible.')
    hist=pd.read_csv(root/'historial_modelo.csv.gz')
    hist['fecha']=pd.to_datetime(hist.fecha,format='ISO8601',errors='raise').dt.strftime('%Y-%m-%d')
    pitches=pd.read_csv(root/'historial_pitcheo.csv.gz')
    rows=fixtures.copy().reset_index(drop=True)
    required={'fecha','local','visitante','linea','home_pitcher_id','away_pitcher_id'}
    if not required.issubset(rows):
        raise ValueError('Faltan columnas: '+', '.join(sorted(required-set(rows))))
    if rows.empty:
        raise ValueError('No hay partidos.')
    rows['fecha']=pd.to_datetime(rows.fecha,format='ISO8601',errors='raise').dt.normalize()
    if (rows.fecha.dt.year<2024).any():
        raise ValueError('Modelo entrenado hasta 2023; predice desde 2024.')
    rows['linea']=pd.to_numeric(rows.linea,errors='raise')
    if not np.isfinite(rows.linea).all() or (rows.linea<=0).any():
        raise ValueError('Completa línea real positiva para cada juego antes de predecir.')
    for key in ('home_pitcher_id','away_pitcher_id'):
        rows[key]=pd.to_numeric(rows[key],errors='raise')
        bad=rows[key].notna() & ((rows[key]<=0)|(~np.isfinite(rows[key]))|(rows[key]%1!=0))
        if bad.any():
            raise ValueError('ID de abridor inválido.')
    rows['home_id']=rows.local.map(lambda v:resolve_team(v,hist))
    rows['away_id']=rows.visitante.map(lambda v:resolve_team(v,hist))
    if (rows.home_id==rows.away_id).any():
        raise ValueError('Local y visitante deben ser distintos.')
    if 'game_type' not in rows:
        raise ValueError('Incluye game_type: R regular, F/D/L/W playoffs. Usa crear_partidos para consultarlo.')
    if not rows.game_type.isin(['R','F','D','L','W']).all():
        raise ValueError('Tipo de juego no admitido; no incluye pretemporada.')
    for key in ('cuota_over','cuota_under'):
        if key not in rows:
            rows[key]=np.nan
        rows[key]=pd.to_numeric(rows[key],errors='raise').map(decimal_odds)
    if 'venue_id' not in rows:
        rows['venue_id']=np.nan
    for idx,r in rows.iterrows():
        if pd.isna(r.venue_id):
            prior=hist[(hist.home_id==r.home_id)&(hist.fecha<str(r.fecha.date()))]
            rows.loc[idx,'venue_id']=int(prior.iloc[-1].venue_id) if len(prior) else -1
        if 'game_id' in rows and pd.notna(r.get('game_id')):
            g=hist[hist.game_id==int(r.game_id)]
            if len(g) and (g.iloc[0].home_id!=r.home_id or g.iloc[0].away_id!=r.away_id or
                           g.iloc[0].fecha!=str(r.fecha.date())):
                raise ValueError('game_id no coincide con equipos y fecha.')
    rows['fixture_index']=np.arange(len(rows))
    ready=rows.home_pitcher_id.notna() & rows.away_pitcher_id.notna()
    result=rows[[c for c in ('game_id','fecha','local','visitante','game_type','linea',
                          'home_pitcher_id','away_pitcher_id','cuota_over','cuota_under') if c in rows]].copy()
    for key in ('total_proyectado','edge_carreras','p_over','p_under','p_push',
                'ev_over','ev_under','prob_seleccion'):
        result[key]=np.nan
    result['seleccion']='PENDIENTE'
    result['estado']='ABRIDOR_PENDIENTE'
    result['estado_valor']='PENDIENTE'
    result['validacion_mercado']='PENDIENTE'
    result['modelo']=bundle['metadata']['winner']
    if ready.any():
        built=pitching_features(hist,pitches,rows.loc[ready])
        built=built[built.is_fixture].sort_values('fixture_index')
        idx=built.fixture_index.astype(int).to_numpy()
        mu=np.clip(bundle['model'].predict(built[bundle['columns']]),.05,40)
        po,pu,pp=probabilities(mu,bundle['alpha'],rows.loc[idx,'linea'].to_numpy())
        result.loc[idx,'total_proyectado']=mu
        result.loc[idx,'edge_carreras']=mu-rows.loc[idx,'linea'].to_numpy()
        result.loc[idx,'p_over']=po;result.loc[idx,'p_under']=pu;result.loc[idx,'p_push']=pp
        result.loc[idx,'ev_over']=po*(rows.loc[idx,'cuota_over'].to_numpy()-1)-pu
        result.loc[idx,'ev_under']=pu*(rows.loc[idx,'cuota_under'].to_numpy()-1)-po
        for i in idx:
            r=result.loc[i]
            ev={s:r['ev_'+s.lower()] for s in ('OVER','UNDER') if pd.notna(r['ev_'+s.lower()])}
            pick=max(ev,key=ev.get) if ev else ('OVER' if r.p_over>=r.p_under else 'UNDER')
            result.loc[i,'seleccion']=pick
            result.loc[i,'prob_seleccion']=r['p_'+pick.lower()]
            result.loc[i,'estado_valor']=('CANDIDATO' if ev[pick]>0 else 'SIN_VALOR') if ev else 'SIN_CUOTAS'
            result.loc[i,'estado']='PLAYOFFS_EXPERIMENTAL' if r.game_type!='R' else 'EXPERIMENTAL'
        # Mostrar disponibilidad de historial para ambos abridores, sin inventar sus estadísticas.
        result.loc[idx,'home_sp_ip_365']=built.home_sp_ip_365.to_numpy()
        result.loc[idx,'away_sp_ip_365']=built.away_sp_ip_365.to_numpy()
        result.loc[idx,'home_sp_era_previa']=built.home_sp_era_365.to_numpy()
        result.loc[idx,'away_sp_era_previa']=built.away_sp_era_365.to_numpy()
        result.loc[idx,'home_bp_pitches_3d']=built.home_bp_pitches_3d.to_numpy()
        result.loc[idx,'away_bp_pitches_3d']=built.away_bp_pitches_3d.to_numpy()
    coverage=json.loads((root/'historial_modelo.coverage.json').read_text())['hasta']
    result['historial_hasta']=coverage
    stale=(rows.fecha-pd.to_datetime(coverage)).dt.days>1
    result.loc[stale,'estado']='ACTUALIZAR_HISTORIAL'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--entrada',required=True)
    p.add_argument('--modelos',default='mlb_totales/modelos_pitcheo')
    p.add_argument('--salida',default='mlb_totales/predictions/predicciones_pitcheo.csv')
    a=p.parse_args()
    r=predict(pd.read_csv(a.entrada),a.modelos)
    Path(a.salida).parent.mkdir(parents=True,exist_ok=True)
    r.to_csv(a.salida,index=False)
    print(r.round(4).to_string(index=False))
