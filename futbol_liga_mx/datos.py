"""Resultados de Liga MX, con auditoría de temporadas y partidos incompletos."""
from datetime import date,timedelta,datetime
from pathlib import Path
import json
import csv
import io
import re
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo
import pandas as pd

SOURCE='https://raw.githubusercontent.com/openfootball/football.json/master'
CSV_SOURCE='https://raw.githubusercontent.com/SrChucho/mexico/master'
MIN_YEAR=2018
MAX_YEAR=2026
VALID_ROUND=re.compile(r'(?i)\b(?:matchday|jornada|round|fecha)\s*\d+\b')
EXCLUDE_ROUND=re.compile(r'(?i)liguilla|play.?in|repechaje|reclasificaci[oó]n|final|semi|quarter|octavos|cuartos')
COLUMNS=['season','fecha','local','visitante','goles_local','goles_visitante','ronda','source_file']


def read_season(payload,season,filename):
    if not isinstance(payload,dict) or not isinstance(payload.get('matches'),list):
        raise ValueError(f'{filename}: falta la lista matches.')
    if 'Liga MX' not in str(payload.get('name','')):
        raise ValueError(f'{filename}: no se identifica como Liga MX.')
    rows=[];issues=[]
    for i,m in enumerate(payload['matches']):
        round_name=str(m.get('round',''))
        if EXCLUDE_ROUND.search(round_name):
            issues.append((i,'eliminatoria'));continue
        if not VALID_ROUND.search(round_name):
            issues.append((i,'ronda_desconocida'));continue
        score=m.get('score',{}).get('ft') if isinstance(m.get('score'),dict) else None
        if score is None:
            issues.append((i,'sin_resultado'));continue
        try:
            if (not isinstance(score,list) or len(score)!=2 or
                    any(type(x) is not int or x<0 for x in score)):
                raise ValueError('Marcador inválido.')
            fecha=date.fromisoformat(m['date'])
            home=str(m['team1']).strip();away=str(m['team2']).strip()
            if not home or not away or home==away:raise ValueError('Equipos inválidos.')
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError(f'{filename}: juego {i}, {exc}') from exc
        rows.append(dict(season=season,fecha=fecha.isoformat(),local=home,visitante=away,
                         goles_local=score[0],goles_visitante=score[1],ronda=round_name,
                         source_file=filename))
    return pd.DataFrame(rows,columns=COLUMNS),issues


def read_csv_season(payload,season,filename):
    """Cache CC0 de resultados: solo fase regular con marcador de 90 minutos."""
    rows=[];issues=[]
    for i,m in enumerate(csv.DictReader(io.StringIO(payload))):
        stage=m.get('Stage','').strip()
        round_number=m.get('Round','').strip()
        if stage not in ('Apertura','Clausura') or not round_number.isdigit() or not 1<=int(round_number)<=17:
            issues.append((i,'eliminatoria_o_ronda_desconocida'));continue
        score=re.fullmatch(r'(\d+)\s*-\s*(\d+)',m.get('FT','').strip())
        if not score:
            issues.append((i,'sin_resultado_regular'));continue
        try:
            fecha=datetime.strptime(m['Date'].strip(),'%a %b %d %Y').date()
            home=m['Team 1'].strip();away=m['Team 2'].strip()
            if not home or not away or home==away:raise ValueError('Equipos inválidos.')
        except (ValueError,KeyError,AttributeError) as exc:
            raise ValueError(f'{filename}: juego {i}, {exc}') from exc
        rows.append(dict(season=season,fecha=fecha.isoformat(),local=home,visitante=away,
                         goles_local=int(score[1]),goles_visitante=int(score[2]),
                         ronda=f'{stage}, Matchday {round_number}',source_file=filename))
    return pd.DataFrame(rows,columns=COLUMNS),issues


def audit(frame):
    if frame.empty:raise ValueError('No se encontraron resultados de Liga MX.')
    if frame.duplicated(['fecha','local','visitante']).any():
        duplicates=frame[frame.duplicated(['fecha','local','visitante'],keep=False)]
        raise ValueError('Duplicados fecha/local/visitante; revisa estos partidos:\n'+duplicates.to_string(index=False))
    if frame.duplicated(['season','local','visitante']).any():
        # Apertura y Clausura deben identificarse por fecha/ronda antes de entrenamiento.
        # Dos enfrentamientos en una temporada Liga MX son normales.
        pass
    return frame.sort_values(['fecha','local','visitante']).reset_index(drop=True)


def fetch(year,cache):
    season=f'{year}-{str((year+1)%100).zfill(2)}'
    path=cache/f'{season}_mx.1.json'
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    url=f'{SOURCE}/{season}/mx.1.json'
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'LigaMX-Research/1.0'}),timeout=35) as response:
            payload=json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code==404:return None
        raise
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    return payload


def fetch_csv(year,cache):
    season=f'{year}-{str((year+1)%100).zfill(2)}'
    path=cache/f'{season}_mx.1.csv'
    if path.exists():return path.read_text(encoding='utf-8-sig')
    url=f'{CSV_SOURCE}/{season}/mx.1.csv'
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'LigaMX-Research/1.0'}),timeout=35) as response:
            payload=response.read().decode('utf-8-sig')
    except urllib.error.HTTPError as exc:
        if exc.code==404:return None
        raise
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(payload,encoding='utf-8')
    return payload


def regular_counts(frame):
    return {stage:int(frame.ronda.str.startswith(stage+',').sum())
            for stage in ('Apertura','Clausura')}


def complete(frame):
    """306 juegos esperados; admite uno sin marcador, jamás años a medio jugar."""
    stages=regular_counts(frame)
    return all(150<=n<=153 for n in stages.values()) and 300<=len(frame)<=306


def prepare(output='futbol_liga_mx/data/partidos.csv',cache='futbol_liga_mx/data/cache',
            first=MIN_YEAR,last=MAX_YEAR,cutoff=None):
    output=Path(output);cache=Path(cache)
    if output.exists():
        saved=pd.read_csv(output,usecols=['season','source_file'])
        if saved.source_file.eq('API-Football /fixtures').any():
            raise ValueError('partidos.csv ya contiene partidos API-Football. '
                             'Ejecuta futbol_liga_mx.proveedor_api para actualizar, '
                             'no futbol_liga_mx.datos (sobrescribiría esas temporadas).')
    cutoff=cutoff or (datetime.now(ZoneInfo('America/Mexico_City')).date()-timedelta(days=1))
    frames=[];coverage=[]
    for year in range(first,last+1):
        season=f'{year}-{str((year+1)%100).zfill(2)}'
        payload=fetch(year,cache)
        candidates=[]
        if payload is not None:
            frame,issues=read_season(payload,season,f'{season}/mx.1.json')
            candidates.append((frame,issues,f'{SOURCE}/{season}/mx.1.json'))
        # Si el JSON falta o tiene huecos, buscamos un archivo CSV alternativo.
        if not candidates or not complete(candidates[0][0]):
            csv_payload=fetch_csv(year,cache)
            if csv_payload is not None:
                frame,issues=read_csv_season(csv_payload,season,f'{season}/mx.1.csv')
                candidates.append((frame,issues,f'{CSV_SOURCE}/{season}/mx.1.csv'))
        if not candidates:
            coverage.append(dict(season=season,found=False,regular=0,skipped=0,source='404'))
            continue
        # Preferir una temporada completa; nunca combinar dos copias de un juego.
        candidates.sort(key=lambda item:(complete(item[0]),min(len(item[0]),306)),reverse=True)
        frame,issues,source=candidates[0]
        future=frame.fecha.gt(cutoff.isoformat())
        frame=frame[~future].copy()
        frames.append(frame)
        stages=regular_counts(frame)
        coverage.append(dict(season=season,found=True,regular=len(frame),
                             apertura=stages['Apertura'],clausura=stages['Clausura'],
                             completa=complete(frame),skipped=len(issues),
                             future_excluded=int(future.sum()),
                             source=source))
    if not frames:raise ValueError('No se descargó ningún archivo Liga MX. Comprueba conexión y rutas.')
    games=audit(pd.concat(frames,ignore_index=True))
    output.parent.mkdir(parents=True,exist_ok=True)
    games.to_csv(output,index=False)
    report=output.with_name('cobertura.csv')
    pd.DataFrame(coverage).to_csv(report,index=False)
    print(pd.DataFrame(coverage)[['season','found','regular','apertura','clausura','completa','skipped']].to_string(index=False))
    print(f'Resultados: {len(games)}. Datos: {output}; auditoría: {report}')
    return games,pd.DataFrame(coverage)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--desde',type=int,default=MIN_YEAR)
    parser.add_argument('--hasta',type=int,default=MAX_YEAR)
    parser.add_argument('--salida',default='futbol_liga_mx/data/partidos.csv')
    parser.add_argument('--corte',type=date.fromisoformat,
                        help='Último día totalmente finalizado (AAAA-MM-DD); por defecto ayer en CDMX')
    args=parser.parse_args()
    prepare(output=args.salida,first=args.desde,last=args.hasta,cutoff=args.corte)
