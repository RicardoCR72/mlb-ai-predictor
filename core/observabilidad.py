"""Estado verificable de datos y ejecuciones; lectura sin consumir cuotas."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd
from core.bankroll import rows

WORKFLOWS = {'MLB':'bot_diario.yml', 'NFL totales':'nfl_predicciones.yml',
             'NFL props':'bot_nfl_props.yml', 'Liga MX':'liga_mx_espn.yml', 'MySQL':'validacion_mysql.yml'}


def workflow_status(filename, opener=urlopen):
    url = f'https://api.github.com/repos/RicardoCR72/mlb-ai-predictor/actions/workflows/{filename}/runs?per_page=20&branch=main'
    with opener(Request(url, headers={'Accept':'application/vnd.github+json', 'User-Agent':'Oraculo-integraciones'}), timeout=10) as response:
        runs = json.load(response).get('workflow_runs', [])
    latest = runs[0] if runs else {}
    success = next((r for r in runs if r.get('conclusion') == 'success'), {})
    return {'ultima_ejecucion':latest.get('created_at'), 'resultado':latest.get('conclusion') or latest.get('status') or 'Sin ejecuciones',
            'ultimo_exito':success.get('updated_at'), 'enlace':latest.get('html_url')}


def age_status(timestamp, max_hours=48, now=None):
    if timestamp is None or pd.isna(timestamp): return 'Sin datos'
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None: value = value.tz_localize('UTC')
    hours = (now-value.tz_convert('UTC')).total_seconds()/3600
    if hours < -1: return 'Fecha futura: revisar reloj'
    return 'Actualizado' if hours <= max_hours else 'Datos antiguos: revisar calendario'


def data_status(conn, root):
    queries = {
        'MLB V2':('SELECT MAX(recorded_utc) AS actualizado FROM mlb_totales_predicciones',
                  "SELECT MAX(timestamp_captura) AS actualizado FROM lineas_props WHERE tipo_prop='totales_carreras' AND LOWER(TRIM(casa_apuestas))='draftkings'"),
        'NFL totales':('SELECT MAX(actualizado_en) AS actualizado FROM nfl_predicciones_totales',
                       "SELECT MAX(actualizado_en) AS actualizado FROM nfl_predicciones_totales"),
        'NFL props':('SELECT MAX(actualizado_en) AS actualizado FROM nfl_proyecciones_props',
                    "SELECT MAX(timestamp_captura) AS actualizado FROM nfl_lineas_props WHERE LOWER(TRIM(casa_apuestas))='draftkings'"),
    }
    results = []
    for module, statements in queries.items():
        item = {'Integración':module, 'Último dato':None, 'Última cuota DraftKings':None, 'Detalle':''}
        if conn is None:
            item['Detalle'] = 'MySQL sin conexión'
        else:
            for label, sql in zip(('Último dato', 'Última cuota DraftKings'), statements):
                try:
                    data = rows(conn, sql)
                    item[label] = str(data.iloc[0,0]) if not data.empty and pd.notna(data.iloc[0,0]) else None
                except Exception as exc:
                    item['Detalle'] += f'{label}: {type(exc).__name__}. '
        if module == 'NFL totales':
            item['Detalle'] += 'Fecha de cuota: actualización de la predicción; captura independiente no disponible. '
        item['Estado de datos'] = age_status(item['Último dato'])
        results.append(item)
    from futbol_liga_mx.datos import complete, regular_counts
    try:
        data = pd.read_csv(Path(root)/'futbol_liga_mx/data/partidos.csv')
        season = data[data.season.eq('2025-26')]
        latest = data.fecha.max()
        from futbol_liga_mx.continuidad import upcoming_ready,frozen_model
        state = 'Bloqueada: 2025–26 incompleta'
        if complete(season):
            try:
                _,report = frozen_model(Path(root)/'futbol_liga_mx/modelos')
                future = pd.read_csv(Path(root)/'futbol_liga_mx/data/proximos.csv')
                ready = upcoming_ready(data,future,report,datetime.now(timezone.utc))
                state = f'Lista: {len(ready)} próximos partidos en 7 días'
            except ValueError as exc: state = f'Bloqueada: {exc}'
        results.append({'Integración':'Liga MX', 'Último dato':latest, 'Última cuota DraftKings':None,
                        'Estado de datos':state,
                        'Detalle':f"2025–26: {len(season)} partidos; {regular_counts(season)}. Fecha corresponde a partidos, no a ejecución."})
    except Exception as exc:
        results.append({'Integración':'Liga MX','Estado de datos':'Sin datos','Detalle':type(exc).__name__})
    return pd.DataFrame(results)
