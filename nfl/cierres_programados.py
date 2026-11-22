"""Captura programada de cuotas de cierre (CLV) para NFL props.

Deja este proceso corriendo durante la jornada dominical de NFL:
    python -m nfl.cierres_programados

Para cada partido con picks abiertos, captura UNA vez la cuota vigente cuando faltan
entre VENTANA_MIN (5 min) y 0 minutos para el kickoff. Así el cierre de un partido nunca se mezcla
con el de otro ni se captura después del inicio.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nfl.auditoria_publica import _leer, registrar_cierres
from nfl.servicio_bovada_props import extraer_props_nfl

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("nfl_cierres")

ZONA = ZoneInfo("America/Mexico_City")
VENTANA_MIN = 5          # empieza a capturar cuando faltan <= 5 min
CICLO_SEG = 30           # frecuencia de revisión


def _inicio(p: Dict) -> Optional[datetime]:
    if p.get("commence_ts"):
        try:
            return pd.to_datetime(p["commence_ts"], utc=True).to_pydatetime()
        except Exception:
            pass
    fecha, hora = str(p.get("fecha", ""))[:10], str(p.get("hora") or "").strip()
    if not hora:
        # Por omisión si no hay hora, estimar según ventana típica o juego
        return None
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            t = datetime.strptime(hora.upper(), fmt).time()
            return datetime.combine(datetime.strptime(fecha, "%Y-%m-%d").date(), t, tzinfo=ZONA).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def ciclo(capturados: set, avisados: set, ventana_min: float = VENTANA_MIN) -> int:
    ev = _leer()
    liquidados = {e["pick_id"] for e in ev if e["tipo"] == "LIQUIDACION"}
    cerrados = {e["pick_id"] for e in ev if e["tipo"] == "CIERRE"}
    ahora = datetime.now(timezone.utc)

    grupos: Dict[tuple, list] = {}
    for e in ev:
        if e["tipo"] != "PICK" or e["pick_id"] in liquidados:
            continue
        p = e["payload"]
        ini = _inicio(p)
        if ini is None:
            if e["pick_id"] not in avisados:
                avisados.add(e["pick_id"])
                log.warning(f"Sin hora de inicio parseable para {p.get('player_name')} ({p.get('hora')!r})")
            continue
        grupos.setdefault((p.get("game_id", p.get("player_name")), p.get("fecha"), ini), []).append(e["pick_id"])

    por_capturar = []
    for (game, fecha, ini), pids in grupos.items():
        if (game, fecha) in capturados:
            continue
        faltan = (ini - ahora).total_seconds() / 60.0
        if 0 <= faltan <= ventana_min:
            por_capturar.append(((game, fecha), pids))
        elif faltan < 0 and not any(p in cerrados for p in pids) and (game, fecha) not in avisados:
            avisados.add((game, fecha))
            log.warning(f"⚠️ {game} {fecha}: empezó sin cierre capturado (sin CLV para esos picks)")

    if not por_capturar:
        return 0

    log.info(f"Obteniendo cuotas de cierre frescas de Bovada NFL para {len(por_capturar)} juego(s)...")
    df_b = extraer_props_nfl(usar_cache=False)
    total_cierres = 0
    for clave, pids in por_capturar:
        n = registrar_cierres(df_b, solo_pick_ids=set(pids))
        capturados.add(clave)
        total_cierres += n
        log.info(f"Cierre {clave[0]}: {n}/{len(pids)} picks con cuota comparable")
    return total_cierres


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Captura de cierres NFL")
    parser.add_argument("--una-vez", action="store_true", help="Ejecuta una sola revisión y sale")
    parser.add_argument("--ventana-min", type=float, default=VENTANA_MIN, help="Minutos antes del juego para capturar")
    args = parser.parse_args()

    cap, avi = set(), set()
    if args.una_vez:
        log.info(f"Modo ejecución única NFL (ventana: {args.ventana_min} min)")
        ciclo(cap, avi, ventana_min=args.ventana_min)
        sys.exit(0)

    log.info("Capturador de cierres NFL activo (Ctrl+C para salir)")
    while True:
        try:
            ciclo(cap, avi, ventana_min=args.ventana_min)
        except Exception as exc:
            log.error(f"Error en ciclo NFL: {exc}")
        time.sleep(CICLO_SEG)
