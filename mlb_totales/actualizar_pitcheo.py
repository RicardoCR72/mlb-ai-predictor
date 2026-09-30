"""Actualizar calendario/pitcheo de la versión 2 manteniendo pesos congelados."""
import argparse
import json
from pathlib import Path
import pandas as pd
from mlb_totales.descargar_pitcheo import download
from mlb_totales.pitcheo_features import audit


def update(hasta,modelos,directory):
    root=Path(modelos)
    coverage=json.loads((root/'historial_modelo.coverage.json').read_text())
    if hasta<coverage['hasta']:
        raise ValueError('La actualización no puede retroceder.')
    history=pd.read_csv(root/'historial_modelo.csv.gz')
    pitching=pd.read_csv(root/'historial_pitcheo.csv.gz')
    g,p=download(int(history.season.max()),int(hasta[:4]),hasta,directory)
    errors=audit(g,p)
    errors.to_csv(Path(directory)/'auditoria_actualizacion.csv',index=False)
    if len(errors)/max(len(g),1)>.005:
        raise ValueError('Demasiadas incidencias de cobertura; no se modifica el historial del modelo.')
    excluded=set(errors.game_id)
    g=g[~g.game_id.isin(excluded)].copy();p=p[~p.game_id.isin(excluded)].copy()
    # Normalizar antes de concatenar strings antiguos y Timestamps descargados.
    for frame in (history,pitching,g,p):
        frame['fecha']=pd.to_datetime(frame.fecha,format='ISO8601',errors='raise').dt.strftime('%Y-%m-%d')
    history=pd.concat([history,g],ignore_index=True).drop_duplicates('game_id',keep='last').sort_values(['fecha','game_id'])
    pitching=pd.concat([pitching,p],ignore_index=True).drop_duplicates(['game_id','team_id','pitcher_id'],keep='last')
    # Archivos completos antes de sustituir; coverage es lo último que se actualiza.
    for name,frame in [('historial_modelo.csv.gz',history),('historial_pitcheo.csv.gz',pitching)]:
        tmp=root/(name+'.tmp')
        frame.to_csv(tmp,index=False,compression='gzip')
    for name in ('historial_modelo.csv.gz','historial_pitcheo.csv.gz'):
        (root/(name+'.tmp')).replace(root/name)
    coverage['hasta']=hasta;coverage['fin']=int(hasta[:4])
    (root/'historial_modelo.coverage.json').write_text(json.dumps(coverage,indent=2))
    print(f'Historial actualizado hasta {hasta}; modelo y calibración conservados.')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--hasta',required=True)
    p.add_argument('--modelos',default='mlb_totales/modelos_pitcheo')
    p.add_argument('--directorio',default='mlb_totales/data/pitcheo_v2')
    a=p.parse_args()
    update(a.hasta,a.modelos,a.directorio)
