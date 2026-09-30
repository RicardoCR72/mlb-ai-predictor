"""Actualizar únicamente el historial; conservar pesos y calibración congelados."""
import argparse
from pathlib import Path
import pandas as pd
from mlb_totales.descargar import descargar

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--hasta', required=True)
    p.add_argument('--modelos', default='mlb_totales/modelos')
    a = p.parse_args()
    path = Path(a.modelos) / 'historial_modelo.csv'
    old = pd.read_csv(path)
    year = int(a.hasta[:4])
    if a.hasta < old.fecha.max():
        p.error('La actualización no puede retroceder el historial.')
    fresh = descargar(int(old.season.max()), year, a.hasta, path.parent / 'actualizacion.csv')
    df = pd.concat([old, fresh]).drop_duplicates('game_id', keep='last').sort_values(['fecha', 'game_id'])
    temporary = path.with_suffix('.tmp')
    df.to_csv(temporary, index=False)
    temporary.replace(path)
    coverage = path.parent / 'actualizacion.coverage.json'
    path.with_suffix('.coverage.json').write_text(coverage.read_text(), encoding='utf-8')
    print(f'Historial actualizado: {len(df)} juegos hasta {df.fecha.max()}; modelo sin reentrenar.')
