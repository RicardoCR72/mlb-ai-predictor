"""Tareas de GitHub Actions: secretos, historial completo, picks y resultados."""
import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path('mlb_totales/modelos_pitcheo')
MX = ZoneInfo('America/Mexico_City')


def create_secrets(path=Path('.streamlit/secrets.toml')):
    fields = {'host':'DB_HOST', 'port':'DB_PORT', 'user':'DB_USER',
              'password':'DB_PASS', 'database':'DB_NAME'}
    missing = [v for v in fields.values() if not os.environ.get(v)]
    if missing:
        raise ValueError('Faltan secretos: ' + ', '.join(missing))
    values = {k:os.environ[v] for k,v in fields.items()}
    values['port'] = int(values['port'])
    # JSON strings son también cadenas TOML válidas; sin interpolación en shell.
    text = '\n'.join(k+' = '+json.dumps(v,ensure_ascii=False) for k,v in values.items())+'\n'
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(0o600)
    print('Configuración de conexión preparada.')


def connect():
    import mysql.connector
    import streamlit as st
    values = {k:st.secrets[k] for k in ('host','port','user','password','database')}
    for key in ('ssl_ca','ssl_verify_cert','ssl_verify_identity'):
        if key in st.secrets:
            values[key] = st.secrets[key]
    return mysql.connector.connect(**values, connection_timeout=30)


def complete_days(data):
    """Un día en curso no se declara cubierto. Aplazados/cancelados se excluyen."""
    pending = []
    excluded = ('postponed','cancelled','canceled','suspended')
    for day in data.get('dates', []):
        for game in day.get('games', []):
            status = game.get('status', {})
            detail = status.get('detailedState','').lower()
            if status.get('abstractGameState') != 'Final' and not any(x in detail for x in excluded):
                pending.append(game.get('gamePk'))
    if pending:
        raise RuntimeError(f'Hay {len(pending)} partidos sin terminar en el período; historial sin avanzar.')


def update_history(root=ROOT, now=None):
    from mlb_totales.descargar_pitcheo import fetch_json, TYPES
    from mlb_totales.actualizar_pitcheo import update
    root = Path(root)
    now = now or datetime.now(MX)
    target = now.astimezone(MX).date()-timedelta(days=1)
    coverage = json.loads((root/'historial_modelo.coverage.json').read_text())
    covered = datetime.fromisoformat(coverage['hasta']).date()
    if covered > target:
        raise RuntimeError('La cobertura indica un día aún no completo. Revisa el historial antes de predecir.')
    if covered == target:
        print(f'Historial ya actualizado hasta {target}.')
        return
    data = fetch_json('schedule', {'sportId':1, 'startDate':str(covered+timedelta(days=1)),
                                  'endDate':str(target), 'gameType':TYPES})
    complete_days(data)
    # Caché nueva por ejecución para no reutilizar una descarga parcial del día.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='mlb-pitcheo-') as cache:
        update(str(target), str(root), cache)


def predict_today(connection, root=ROOT, now=None):
    from mlb_totales import registro
    from mlb_totales.mercado import calendar, match
    from mlb_totales.predecir_pitcheo import predict
    from mlb_totales.portable import load
    now = now or datetime.now(MX)
    day = now.astimezone(MX).date()
    games = calendar(str(day))
    if games.empty:
        print(f'{day}: no hay partidos pendientes.'); return 0
    quotes = registro.quote_rows(connection, day)
    aligned = match(games, quotes, now=now, max_age_minutes=180,
                    quote_timezone=os.environ.get('MLB_ODDS_CAPTURE_TIMEZONE','America/Mazatlan'))
    if aligned.empty:
        print('Todos los partidos consultados ya comenzaron.'); return 0
    print('Mercado:', json.dumps(aligned.estado_mercado.value_counts().to_dict()))
    ready = aligned[aligned.estado_mercado=='OK'].reset_index(drop=True)
    if ready.empty:
        raise RuntimeError('Hay partidos pendientes pero ninguna cuota reciente y válida. Revisa el scraper.')
    predictions = predict(ready, root, portable=True)
    for key in ('casa_apuestas','odds_game_id','start_utc','captured_utc','estado_mercado'):
        predictions[key] = ready[key].to_numpy()
    if (predictions.estado=='ACTUALIZAR_HISTORIAL').any():
        raise RuntimeError('Historial atrasado: no se registraron predicciones.')
    valid = predictions.estado.isin(['EXPERIMENTAL','PLAYOFFS_EXPERIMENTAL']) & predictions.p_over.notna()
    n = registro.save_snapshots(connection, predictions[valid], load(root)['model_id'])
    print(f'Pronósticos válidos: {int(valid.sum())}; nuevos registros: {n}; '
          f'pendientes de abridor/datos: {int((~valid).sum())}.')
    if not valid.any():
        print('::warning::Aún no hay abridores confirmados suficientes; el siguiente Flash volverá a consultar.')
    return n


def persist_history():
    """Sube solamente los tres históricos; jamás añade secretos ni cachés."""
    import subprocess
    def git(*args, capture=False):
        return subprocess.run(['git', *args], check=True, text=True,
                              stdout=subprocess.PIPE if capture else None)
    branch = os.environ['MLB_DEFAULT_BRANCH']
    git('check-ref-format', '--branch', branch)
    if git('diff','--cached','--name-only',capture=True).stdout.strip():
        raise RuntimeError('Hay cambios ajenos preparados para commit; no se mezclan con el historial.')
    files = [str(ROOT/name) for name in ('historial_modelo.csv.gz',
             'historial_pitcheo.csv.gz','historial_modelo.coverage.json')]
    git('add','--',*files)
    if not git('diff','--cached','--name-only',capture=True).stdout.strip():
        print('Históricos sin cambios para subir.'); return
    git('config','user.name','github-actions[bot]')
    git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('commit','-m','Actualizar historial MLB V2 [skip ci]')
    git('fetch','origin',branch)
    git('rebase','origin/'+branch)
    git('push','origin','HEAD:refs/heads/'+branch)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('task', choices=['secretos','historial','guardar-historial','predecir','resultados'])
    args = parser.parse_args()
    if args.task=='secretos':
        create_secrets(); return
    if args.task=='historial':
        update_history(); return
    if args.task=='guardar-historial':
        persist_history(); return
    from mlb_totales import registro
    connection = connect()
    try:
        registro.prepare(connection)
        if args.task=='resultados':
            print(f'Resultados oficiales procesados: {registro.refresh_results(connection)}.')
        else:
            predict_today(connection)
    finally:
        connection.close()


if __name__=='__main__':
    main()
