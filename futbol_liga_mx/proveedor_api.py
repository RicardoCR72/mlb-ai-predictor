"""Complemento de resultados y calendario de Liga MX vía API-Football.

API-Football permite la clave gratuita; el proveedor decide qué años expone.
Nunca sustituye una temporada completa por una respuesta parcial.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import argparse
import json
import os
import re
import unicodedata
import pandas as pd
from .datos import COLUMNS, audit, complete, regular_counts


def obtener_api_key_football() -> str:
    """Lee API_FOOTBALL_KEY desde variables de entorno o .streamlit/secrets.toml."""
    # 1. Variable de entorno
    for nombre in ('API_FOOTBALL_KEY', 'api_football_key'):
        valor = os.environ.get(nombre)
        if valor:
            return valor.strip()

    # 2. .streamlit/secrets.toml (para uso local y compatibilidad con Streamlit)
    raiz = Path(__file__).resolve().parents[1]
    rutas_secrets = [
        raiz / '.streamlit' / 'secrets.toml',
        Path.cwd() / '.streamlit' / 'secrets.toml',
    ]
    try:
        import tomllib
    except ImportError:
        tomllib = None  # Python < 3.11 sin tomllib instalado

    if tomllib:
        for ruta in rutas_secrets:
            if ruta.exists():
                try:
                    with ruta.open('rb') as f:
                        secretos = tomllib.load(f)
                    for nombre in ('API_FOOTBALL_KEY', 'api_football_key'):
                        valor = secretos.get(nombre)
                        if valor:
                            return str(valor).strip()
                except Exception:
                    pass

    raise ValueError(
        'Falta API_FOOTBALL_KEY.\n'
        'Opciones para configurarla:\n'
        '  1. Variable de entorno: set API_FOOTBALL_KEY=tu_key\n'
        '  2. En .streamlit/secrets.toml: agrega la línea\n'
        '     API_FOOTBALL_KEY = "tu_key"\n'
        'Regístrate gratis en https://dashboard.api-football.com/register'
    )


BASE='https://v3.football.api-sports.io'
MX=ZoneInfo('America/Mexico_City')
RESULT_COLUMNS=COLUMNS+['fixture_id']
FIXTURE_COLUMNS=['fecha','inicio_utc','local','visitante','season','ronda','fixture_id']

ALIASES={
    'america':'CF América','club america':'CF América','cf america':'CF América',
    'atlas':'Atlas Guadalajara','atlas fc':'Atlas Guadalajara','atlas guadalajara':'Atlas Guadalajara',
    'atletico san luis':'Atlético San Luis','atletico de san luis':'Atlético San Luis',
    'atlante':'Atlante','atlante fc':'Atlante',
    'monterrey':'CF Monterrey','cf monterrey':'CF Monterrey',
    'pachuca':'CF Pachuca','cf pachuca':'CF Pachuca',
    'leon':'Club León','club leon':'Club León',
    'necaxa':'Club Necaxa','club necaxa':'Club Necaxa',
    'tijuana':'Club Tijuana','club tijuana':'Club Tijuana','club tijuana xoloitzcuintles':'Club Tijuana',
    'cruz azul':'Cruz Azul',
    'guadalajara':'Deportivo Guadalajara','chivas':'Deportivo Guadalajara',
    'guadalajara chivas':'Deportivo Guadalajara',
    'deportivo guadalajara':'Deportivo Guadalajara','cd guadalajara':'Deportivo Guadalajara',
    'toluca':'Deportivo Toluca','deportivo toluca':'Deportivo Toluca','cd toluca':'Deportivo Toluca',
    'juarez':'FC Juárez','fc juarez':'FC Juárez',
    'queretaro':'Gallos Blancos','club queretaro':'Gallos Blancos','queretaro fc':'Gallos Blancos',
    'gallos blancos':'Gallos Blancos',
    'mazatlan':'Mazatlán FC','mazatlan fc':'Mazatlán FC',
    'puebla':'Puebla FC','puebla fc':'Puebla FC','club puebla':'Puebla FC',
    'pumas':'Pumas UNAM','pumas unam':'Pumas UNAM','unam pumas':'Pumas UNAM','unam':'Pumas UNAM',
    'santos':'Santos Laguna','santos laguna':'Santos Laguna',
    'tigres':'UANL Tigres','tigres uanl':'UANL Tigres','uanl tigres':'UANL Tigres',
}


def canonical(name):
    key=unicodedata.normalize('NFKD',str(name)).encode('ascii','ignore').decode().lower()
    key=re.sub(r'[^a-z0-9]+',' ',key).strip()
    if key not in ALIASES:
        raise ValueError(f'Equipo desconocido del proveedor: {name!r}. Añade un alias y verifica su identidad.')
    return ALIASES[key]


def get_json(endpoint,key,params=None,opener=urlopen):
    url=f'{BASE}/{endpoint}?{urlencode(params or {})}'
    req=Request(url,headers={'x-apisports-key':key,'User-Agent':'LigaMX-Research/2.0'})
    with opener(req,timeout=35) as response:
        payload=json.load(response)
    if payload.get('errors'):
        raise ValueError(f'API-Football rechazó {endpoint}: {payload["errors"]}')
    if not isinstance(payload.get('response'),list):
        raise ValueError(f'API-Football no devolvió lista para {endpoint}.')
    return payload['response']


def league_id(key,get=get_json):
    rows=get('leagues',key,{'name':'Liga MX','country':'Mexico'})
    valid=[x for x in rows if x.get('league',{}).get('name')=='Liga MX'
           and x.get('country',{}).get('name')=='Mexico']
    if len(valid)!=1:
        raise ValueError('No se identificó una única Liga MX masculina en API-Football.')
    return int(valid[0]['league']['id'])


def parse_round(label):
    label=str(label or '').strip()
    if re.search(r'(?i)play|liguilla|quarter|semi|final|reclass|repech|group|cup',label):
        return None
    match=re.fullmatch(r'(?i)(?:(apertura|clausura|regular season)\s*[-,:]\s*)?(\d{1,2})',label)
    if not match or not 1<=int(match[2])<=17:
        return None
    return match[1].title() if match[1] else None,int(match[2])


def parse_fixtures(payload,cutoff):
    """Filtra Liga MX y fase regular; toma fecha local CDMX y estado final FT."""
    results=[];upcoming=[];unknown_rounds=set()
    for item in payload:
        if item.get('league',{}).get('name')!='Liga MX':continue
        fid=item.get('fixture',{}).get('id')
        label=item.get('league',{}).get('round','')
        parsed=parse_round(label)
        if parsed is None:
            if not re.search(r'(?i)play|liguilla|quarter|semi|final|reclass|repech|group|cup',str(label)):
                unknown_rounds.add(str(label))
            continue
        stage,round_no=parsed
        try:
            utc=datetime.fromisoformat(item['fixture']['date'].replace('Z','+00:00'))
            if utc.tzinfo is None:raise ValueError('Fecha sin zona horaria.')
            local_date=utc.astimezone(MX).date()
            season=f'{local_date.year if local_date.month>=7 else local_date.year-1}-' \
                   f'{((local_date.year+1 if local_date.month>=7 else local_date.year)%100):02d}'
            expected='Apertura' if local_date.month>=7 else 'Clausura'
            if stage and stage!='Regular Season' and stage!=expected:
                raise ValueError(f'{fid}: ronda {label} incompatible con fecha {local_date}.')
            home=canonical(item['teams']['home']['name'])
            away=canonical(item['teams']['away']['name'])
            if home==away:raise ValueError(f'{fid}: equipos iguales.')
            status=item['fixture']['status']['short']
        except (KeyError,TypeError,AttributeError) as exc:
            raise ValueError(f'Fixture {fid} mal formado: {exc}') from exc
        base=dict(fecha=local_date.isoformat(),local=home,visitante=away,
                  season=season,ronda=f'{expected}, Matchday {round_no}',fixture_id=fid)
        if status in ('FT','AET','PEN'):
            if local_date>cutoff:continue
            # FT no incluye la prórroga; nunca usar goles finales de una eliminatoria.
            h,a=item.get('score',{}).get('fulltime',{}).get('home'),item.get('score',{}).get('fulltime',{}).get('away')
            if type(h) is not int or type(a) is not int or min(h,a)<0:
                raise ValueError(f'{fid}: partido terminado sin marcador reglamentario.')
            results.append(dict(base,goles_local=h,goles_visitante=a,
                                source_file='API-Football /fixtures'))
        elif status in ('NS','TBD') and local_date>=cutoff:
            upcoming.append(dict(base,inicio_utc=utc.astimezone(timezone.utc).isoformat()))
    if unknown_rounds:
        raise ValueError('Rondas sin clasificar; revisa si son fase regular: '+repr(sorted(unknown_rounds)))
    past=pd.DataFrame(results,columns=RESULT_COLUMNS)
    future=pd.DataFrame(upcoming,columns=FIXTURE_COLUMNS)
    if past.fixture_id.duplicated().any() or future.fixture_id.duplicated().any():
        raise ValueError('Fixture ID duplicado en respuesta.')
    return past,future


def merge_results(existing,new):
    """Mantiene las temporadas originales y protege la cobertura acumulada."""
    if not {'2025-26','2026-27'}.intersection(set(new.season)):
        raise ValueError('La API no devolvió ningún resultado nuevo de Liga MX.')
    old=existing[existing.season.isin(['2025-26','2026-27'])]
    if old.duplicated(['season','fecha','local','visitante']).any():
        raise ValueError('Resultados nuevos previamente guardados con duplicados.')
    for season in ['2025-26','2026-27']:
        old_n=int((old.season==season).sum());new_n=int((new.season==season).sum())
        if new_n<old_n:
            raise ValueError(f'{season}: proveedor devolvió {new_n} partidos; antes había {old_n}. No sobrescribí datos.')
    updated=pd.concat([existing[~existing.season.isin(['2025-26','2026-27'])][COLUMNS],
                       new[new.season.isin(['2025-26','2026-27'])][COLUMNS]],ignore_index=True)
    return audit(updated)


def run(key=None,partidos='futbol_liga_mx/data/partidos.csv',
        proximos='futbol_liga_mx/data/proximos.csv',cutoff=None,get=get_json):
    key = key or obtener_api_key_football()
    cutoff=cutoff or datetime.now(MX).date()-timedelta(days=1)
    path=Path(partidos)
    if not path.exists():raise ValueError(f'Primero ejecuta futbol_liga_mx.datos: falta {path}')
    existing=pd.read_csv(path)
    lid=league_id(key,get)
    by_id={}
    for year in (2025,2026):
        fixtures=get('fixtures',key,{'league':lid,'season':year})
        for item in fixtures:
            fid=item.get('fixture',{}).get('id')
            if fid is None:raise ValueError('API-Football devolvió fixture sin ID.')
            by_id[fid]=item
    past,future=parse_fixtures(list(by_id.values()),cutoff)
    if not past.empty:
        stages=past.ronda.str.extract(r'^(Apertura|Clausura),',expand=False)
        pairs=past.apply(lambda row:tuple(sorted((row.local,row.visitante))),axis=1)
        if pd.DataFrame({'season':past.season,'stage':stages,'pair':pairs}).duplicated().any():
            raise ValueError('La API repitió un enfrentamiento de fase regular dentro del mismo torneo.')
    new=merge_results(existing,past)
    # Guarda solo cuando todas las validaciones terminaron correctamente.
    future=future[future.season=='2026-27'].sort_values(['inicio_utc','local'])
    if not future.empty and (future.fecha<cutoff.isoformat()).any():
        raise ValueError('Fixture anterior al corte dentro de próximos.')
    coverage_path=path.with_name('cobertura.csv')
    coverage=pd.read_csv(coverage_path) if coverage_path.exists() else pd.DataFrame()
    if not coverage.empty:coverage=coverage[~coverage.season.isin(['2025-26','2026-27'])]
    rows=[]
    for season in ('2025-26','2026-27'):
        frame=new[new.season==season]
        stages=regular_counts(frame)
        rows.append(dict(season=season,found=not frame.empty,regular=len(frame),
                         apertura=stages['Apertura'],clausura=stages['Clausura'],
                         completa=complete(frame),skipped=0,future_excluded=0,
                         source='API-Football /fixtures'))
    coverage=pd.concat([coverage,pd.DataFrame(rows)],ignore_index=True)
    path.parent.mkdir(parents=True,exist_ok=True)
    new.to_csv(path,index=False)
    next_path=Path(proximos);next_path.parent.mkdir(parents=True,exist_ok=True)
    future.to_csv(next_path,index=False)
    coverage.to_csv(coverage_path,index=False)
    summary=new[new.season.isin(['2025-26','2026-27'])].groupby('season').size().to_dict()
    print('Cobertura API:',summary,'próximos:',len(future))
    if not complete(new[new.season=='2025-26']):
        print('2025-26 incompleta: se guardó para auditoría; validación externa y pronósticos bloqueados.')
    return new,future


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--partidos',default='futbol_liga_mx/data/partidos.csv')
    parser.add_argument('--proximos',default='futbol_liga_mx/data/proximos.csv')
    parser.add_argument('--corte',type=date.fromisoformat)
    args=parser.parse_args()
    run(partidos=args.partidos,proximos=args.proximos,cutoff=args.corte)
