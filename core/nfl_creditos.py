"""Actualización pagada explícita; la consulta previa de eventos cuesta cero."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import requests
from nfl.jornada import ahora_mexico, eventos_hoy, MERCADOS_PROPS
from core.actualizacion_manual import child_environment

API_BASE = 'https://api.the-odds-api.com/v4'
RESERVA = 120
LOCK = threading.Lock()


def api_key():
    for name in ('ODDS_API_KEY', 'THE_ODDS_API_KEY', 'odds_api_key'):
        if os.getenv(name):
            return os.environ[name].strip()
    try:
        import streamlit as st
        for name in ('odds_api_key', 'ODDS_API_KEY', 'THE_ODDS_API_KEY'):
            if st.secrets.get(name):
                return str(st.secrets[name]).strip()
    except Exception:
        pass
    raise RuntimeError('Falta ODDS_API_KEY u odds_api_key en la configuración de la página.')


def plan_hoy(now=None):
    key = api_key()
    try:
        response = requests.get(API_BASE+'/sports/americanfootball_nfl/events',
                                params={'apiKey':key}, timeout=30)
    except requests.RequestException:
        raise RuntimeError('No se pudo consultar el calendario de The Odds API.') from None
    if response.status_code != 200:
        raise RuntimeError(f'The Odds API respondió HTTP {response.status_code}; no se solicitaron cuotas.')
    events = eventos_hoy(response.json(), now)
    remaining = response.headers.get('x-requests-remaining')
    remaining = int(remaining) if remaining is not None else None
    return dict(fecha=str(ahora_mexico(now).date()), eventos=events,
                max_creditos=len(events)*len(MERCADOS_PROPS), restantes=remaining, reserva=RESERVA)


def run_predictions(root, plan, on_step=None):
    if not LOCK.acquire(blocking=False):
        return dict(ok=False, detalle='Ya hay una actualización NFL en curso.', reporte=None)
    report = None
    steps = []
    try:
        if plan['fecha'] != str(ahora_mexico().date()):
            raise RuntimeError('Cambió el día; vuelve a consultar los partidos de hoy.')
        events = eventos_hoy(plan['eventos'])
        if not events:
            return dict(ok=True, detalle='No hay partidos NFL de hoy sin iniciar. Consumo: 0 créditos.', reporte=None)
        if plan['restantes'] is None:
            raise RuntimeError('No se recibió el saldo de créditos; no se consultarán cuotas.')
        if plan['restantes'] < RESERVA + len(MERCADOS_PROPS):
            raise RuntimeError('No hay créditos disponibles por encima de la reserva de 120.')
        env = child_environment()
        env['ODDS_API_KEY'] = api_key()
        env['PYTHONUNBUFFERED'] = '1'
        def run(label, script, args=()):
            nonlocal report
            if on_step:
                on_step(label)
            process = subprocess.run([sys.executable, str(Path(root)/script), *args],
                cwd=str(root), env=env, capture_output=True, text=True, timeout=600)
            for line in process.stdout.splitlines():
                if line.startswith('NFL_ODDS_REPORT='):
                    report = json.loads(line.split('=',1)[1])
            steps.append(label)
            if process.returncode:
                raise RuntimeError(f'{label} no terminó (código {process.returncode}). Revisa conexión y dependencias NFL.')
            return process.stdout
        if not (Path(root)/'data/nfl/raw/nfl_player_stats_2012_2026.parquet').exists():
            run('Preparar estadísticas NFL, sin créditos', 'nfl/descargar_datos.py')
        output = run('Actualizar totales de hoy, sin créditos', 'nfl/predecir_semana_actual.py', ('--solo-hoy',))
        if 'MySQL actualizado:' not in output:
            raise RuntimeError('No hay partidos de hoy habilitados por el calendario NFL; no se gastaron créditos.')
        output = run('Comprobar modelos y datos de props, sin créditos', 'nfl/predecir_props_semana_actual.py', ('--solo-hoy',))
        if 'MySQL actualizado:' not in output:
            raise RuntimeError('No se pudieron preparar los props de hoy; no se gastaron créditos.')
        report = dict(fecha=plan['fecha'], solicitados=None, creditos=None, restantes=None,
                      insertadas=0, completo=False)
        run('Consultar líneas DraftKings de hoy, con créditos', 'nfl/actualizar_lineas_props.py',
            ('--solo-hoy', '--solo-draftkings', '--reserva-creditos', str(RESERVA),
             '--max-creditos', str(min(plan['max_creditos'], len(events)*len(MERCADOS_PROPS))),
             '--eventos', ','.join(e['id'] for e in events)))
        run('Guardar predicciones con las líneas actualizadas', 'nfl/predecir_props_semana_actual.py', ('--solo-hoy',))
        partial = report is not None and not report.get('completo')
        return dict(ok=not partial, detalle='Actualización parcial; revisa consumo y partidos omitidos.' if partial else 'Predicciones de hoy actualizadas.', reporte=report)
    except Exception as exc:
        message = str(exc) if type(exc) is RuntimeError else type(exc).__name__
        return dict(ok=False, detalle=message, reporte=report)
    finally:
        LOCK.release()
