"""Calendario y pitchers probables, sin asumir ERA actuales como históricos."""
import argparse
from pathlib import Path
import pandas as pd
from mlb_totales.descargar_pitcheo import fetch_json,TYPES


def create(fecha,path):
    data=fetch_json('schedule',{'sportId':1,'date':fecha,'gameType':TYPES,'hydrate':'probablePitcher'})
    rows=[]
    for day in data.get('dates',[]):
        for g in day['games']:
            if g['status'].get('abstractGameState')!='Preview':
                continue
            if (g.get('scheduledInnings',9)!=9 or
                any(g.get(k) for k in ('resumeDate','resumedFrom','resumedFromDate')) or
                any(word in g['status'].get('detailedState','').lower()
                    for word in ('postponed','cancelled','suspended'))):
                continue
            h,a=g['teams']['home'],g['teams']['away']
            rows.append(dict(game_id=g['gamePk'],fecha=g.get('officialDate',day['date']),
                hora_utc=g['gameDate'],local=h['team']['name'],visitante=a['team']['name'],
                game_type=g['gameType'],venue_id=g['venue']['id'],
                home_pitcher_id=h.get('probablePitcher',{}).get('id'),
                away_pitcher_id=a.get('probablePitcher',{}).get('id'),
                abridor_local=h.get('probablePitcher',{}).get('fullName','TBD'),
                abridor_visitante=a.get('probablePitcher',{}).get('fullName','TBD'),
                linea='',cuota_over='',cuota_under=''))
    cols=['game_id','fecha','hora_utc','local','visitante','game_type','venue_id',
          'home_pitcher_id','away_pitcher_id','abridor_local','abridor_visitante',
          'linea','cuota_over','cuota_under']
    df=pd.DataFrame(rows,columns=cols)
    if not len(df):
        print('No hay juegos pendientes para esa fecha. No se sobrescribe el CSV.')
        return df
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        raise FileExistsError('El CSV ya existe; usa otro --salida para no borrar líneas/cuotas ingresadas.')
    df.to_csv(path,index=False)
    print(df.to_string(index=False))
    print(f'Completa linea, cuota_over y cuota_under en {path} antes de predecir.')
    return df


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--fecha',required=True)
    p.add_argument('--salida',default='mlb_totales/partidos_a_predecir.csv')
    a=p.parse_args()
    create(a.fecha,a.salida)
