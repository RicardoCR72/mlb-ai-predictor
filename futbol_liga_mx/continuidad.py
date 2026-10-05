"""Confirmación adicional 2025-26 y probabilidades de juegos futuros con modelo congelado."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import argparse
import json
import math
import os
import numpy as np
import pandas as pd
from .datos import COLUMNS, complete
from .modelo import FEATURES,build_features,p_over,score
from .proveedor_api import canonical

MX=ZoneInfo('America/Mexico_City')
ODDS_SPORT='soccer_mexico_ligamx'


def portable_probability(data,params):
    if params['features']!=FEATURES:raise ValueError('Versión del modelo incompatible con variables actuales.')
    x=data[FEATURES].to_numpy(dtype=float)
    mu=np.exp(float(params['intercept'])+
              ((x-np.asarray(params['mean']))/np.asarray(params['scale']))@np.asarray(params['coef']))
    raw=p_over(mu)
    if params['winner']=='sin_calibrar':return raw
    if params['winner']!='calibrada':raise ValueError('Ganador de calibración desconocido.')
    z=np.log(raw/(1-raw))*float(params['calibration']['coef'])+float(params['calibration']['intercept'])
    return np.where(z>=0,1/(1+np.exp(-z)),np.exp(z)/(1+np.exp(z)))


def frozen_model(folder):
    folder=Path(folder)
    params=json.loads((folder/'modelo_portable.json').read_text(encoding='utf-8'))
    metrics=json.loads((folder/'metricas.json').read_text(encoding='utf-8'))
    if metrics['seasons']['confirmacion']!='2024-25':
        raise ValueError('El modelo ya no está congelado en la confirmación 2024-25. '
                         'Recupera el artefacto anterior para probar 2025-26 sin reentrenar.')
    return params,metrics


def evaluate_2025(games,params,metrics,output):
    year=games[games.season=='2025-26']
    if not complete(year):
        raise ValueError(f'2025-26 incompleta ({len(year)} juegos). No evaluar ni predecir todavía.')
    features=build_features(games[games.fecha.le(year.fecha.max())])
    subset=features[features.season=='2025-26']
    probabilities=portable_probability(subset,params)
    base=metrics['confirmation']['baseline']['prob_media']
    report={'season':'2025-26','model':'congelado_2024-25',
            'model_score':score(subset.over25,probabilities),
            'baseline_score':score(subset.over25,np.full(len(subset),base)),
            'baseline_probability':base}
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def upcoming_features(games,fixture):
    # Construimos un solo futuro por vez: un resultado ficticio nunca alimenta otro juego.
    day=fixture['fecha']
    if games.fecha.ge(day).any():
        raise ValueError(f'{day}: hay resultados de ese día o posteriores; usa solo juegos futuros.')
    fake=dict(season=fixture['season'],fecha=day,local=fixture['local'],
              visitante=fixture['visitante'],goles_local=0,goles_visitante=0,
              ronda=fixture['ronda'],source_file='fixture_sin_resultado')
    return build_features(pd.concat([games[COLUMNS],pd.DataFrame([fake])],ignore_index=True)).iloc[-1:]


def fetch_draftkings(key,opener=urlopen):
    """Solo línea principal totals de DraftKings; jamás inferir momios ausentes."""
    base=f'https://api.the-odds-api.com/v4/sports/{ODDS_SPORT}/odds/'
    params={'apiKey':key,'bookmakers':'draftkings','markets':'totals','oddsFormat':'decimal'}
    with opener(base+'?'+urlencode(params),timeout=35) as response:
        events=json.load(response)
    if not isinstance(events,list):raise ValueError('The Odds API no devolvió lista de eventos Liga MX.')
    rows=[]
    for event in events:
        try:
            home,away=canonical(event['home_team']),canonical(event['away_team'])
            kickoff=datetime.fromisoformat(event['commence_time'].replace('Z','+00:00'))
        except (KeyError,ValueError) as exc:
            raise ValueError(f'Partido de odds no reconocido: {event.get("id")} ({exc})') from exc
        for book in event.get('bookmakers',[]):
            if book.get('key')!='draftkings':continue
            for market in book.get('markets',[]):
                if market.get('key')!='totals':continue
                over=[o for o in market.get('outcomes',[]) if o.get('name')=='Over' and o.get('point')==2.5]
                under=[o for o in market.get('outcomes',[]) if o.get('name')=='Under' and o.get('point')==2.5]
                if len(over)==len(under)==1:
                    rows.append(dict(local=home,visitante=away,
                                     inicio_utc=kickoff.astimezone(timezone.utc).isoformat(),
                                     precio_over=float(over[0]['price']),precio_under=float(under[0]['price']),
                                     odds_event_id=event['id'],bookmaker='draftkings'))
    return pd.DataFrame(rows)


def quote_for_fixture(fixture,quotes):
    if quotes.empty:return None
    kickoff=datetime.fromisoformat(fixture['inicio_utc'])
    matches=quotes[(quotes.local==fixture['local']) & (quotes.visitante==fixture['visitante'])]
    matches=matches[matches.inicio_utc.apply(
        lambda d: abs((datetime.fromisoformat(d)-kickoff).total_seconds())<=12*3600)]
    if len(matches)>1:raise ValueError('Más de un mercado DraftKings coincide con el mismo partido.')
    return None if matches.empty else matches.iloc[0]


def upcoming_ready(games,fixtures,metrics,now):
    """Comprueba cobertura y calendario antes de solicitar momios."""
    if now.tzinfo is None:raise ValueError('now requiere zona horaria.')
    if not complete(games[games.season=='2025-26']):
        raise ValueError('2025-26 incompleta: predicción suspendida hasta validar la temporada.')
    current=games[games.season=='2026-27']
    if current.empty or (now.astimezone(MX).date()-pd.to_datetime(current.fecha.max()).date()).days>21:
        raise ValueError('Historial Apertura 2026 ausente o desactualizado (más de 21 días).')
    rounds=current.ronda.str.extract(r'^Apertura, Matchday (\d+)$',expand=False).dropna().astype(int)
    if rounds.empty:raise ValueError('No hay fase regular del Apertura 2026.')
    latest=int(rounds.max())
    if int((rounds<latest).sum()) < 9*(latest-1)-3:
        raise ValueError('Faltan varios resultados en jornadas anteriores del Apertura 2026.')
    if metrics['seasons']['confirmacion']!='2024-25':raise ValueError('No es el modelo congelado.')
    fixtures=fixtures[fixtures.season=='2026-27']
    fechas=pd.to_datetime(fixtures.inicio_utc,utc=True,errors='coerce')
    if fechas.isna().any():raise ValueError('Calendario con inicio_utc inválido.')
    return fixtures[(fechas>now)&(fechas<=now+timedelta(days=7))].copy()


def predict(games,fixtures,params,metrics,quotes=None,now=None,
            output='futbol_liga_mx/predictions/hoy.csv',quote_loader=None):
    now=now or datetime.now(timezone.utc)
    from .inferencia import normalize_teams
    games = normalize_teams(games)
    fixtures = normalize_teams(fixtures)
    fixtures=upcoming_ready(games,fixtures,metrics,now)
    results=[]
    for fixture in fixtures.to_dict('records'):
        history=games[games.fecha.lt(fixture['fecha'])]
        features=upcoming_features(history,fixture)
        p=float(portable_probability(features,params)[0])
        result={**fixture,'p_over25':p,'p_under25':1-p,'estado':'OBSERVACION',
                'capturada_utc':now.isoformat()}
        results.append(result)
    # Una ejecución bloqueada o sin partidos futuros jamás consulta The Odds API.
    if results and quote_loader is not None:
        if quotes is not None:raise ValueError('Usa quotes o quote_loader, no ambos.')
        quotes=quote_loader()
    for result in results:
        fixture=result
        quote=quote_for_fixture(fixture,quotes) if quotes is not None else None
        if quote is not None:
            p=result['p_over25']
            po,pu=float(quote['precio_over']),float(quote['precio_under'])
            if min(po,pu)<=1:raise ValueError('Momios decimales inválidos.')
            result.update(casa='draftkings',linea=2.5,cuota_over=po,cuota_under=pu,
                          ev_over=p*po-1,ev_under=(1-p)*pu-1,
                          odds_event_id=quote['odds_event_id'])
    if fixtures.empty:print('API-Football no informó próximos partidos de temporada regular.')
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    result_frame=pd.DataFrame(results)
    if result_frame.empty:
        result_frame=pd.DataFrame(columns=list(fixtures.columns)+
                                  ['p_over25','p_under25','estado','capturada_utc'])
    result_frame.to_csv(out,index=False)
    print(f'Probabilidades futuras: {len(results)}; guardadas en {out}')
    return result_frame


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('accion',choices=['evaluar','estado','predecir'])
    ap.add_argument('--partidos',default='futbol_liga_mx/data/partidos.csv')
    ap.add_argument('--proximos',default='futbol_liga_mx/data/proximos.csv')
    ap.add_argument('--modelos',default='futbol_liga_mx/modelos')
    ap.add_argument('--sin-momios',action='store_true')
    args=ap.parse_args()
    games=pd.read_csv(args.partidos)
    params,metrics=frozen_model(args.modelos)
    if args.accion=='evaluar':
        evaluate_2025(games,params,metrics,'futbol_liga_mx/modelos/confirmacion_2025_26.json')
    else:
        if not Path(args.proximos).exists():
            raise ValueError(f'Falta {args.proximos}; ejecuta primero futbol_liga_mx.proveedor_api.')
        fixtures=pd.read_csv(args.proximos)
        if args.accion=='estado':
            print(f'Cobertura 2025-26: {len(games[games.season=="2025-26"])} juegos.')
            try:
                ready=upcoming_ready(games,fixtures,metrics,datetime.now(timezone.utc))
            except ValueError as exc:
                print(f'Estado: BLOQUEADO. {exc}')
                print('Consulta de momios: 0 créditos.')
                raise SystemExit(1) from None
            print('Estado: LISTO para generar probabilidades con el modelo congelado.')
            print(f'Partidos próximos siete días: {len(ready)}. Consulta de momios: 0 créditos.')
        else:
            loader=None
            if not args.sin_momios:
                key=os.environ.get('ODDS_API_KEY') or os.environ.get('THE_ODDS_API_KEY')
                if not key:raise ValueError('Falta ODDS_API_KEY; configura tu clave o usa --sin-momios.')
                loader=lambda:fetch_draftkings(key)
            predict(games,fixtures,params,metrics,quote_loader=loader)

