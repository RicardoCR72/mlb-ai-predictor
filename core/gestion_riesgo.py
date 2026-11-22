"""Módulo de Gestión de Riesgo Cuantitativo: Kelly Fraccional y Control de Correlación.

Estrategia:
1. Criterio de Kelly Fraccional (Quarter Kelly 1/4 o Eighth Kelly 1/8):
   f* = (b * p - q) / b
   donde:
     b = cuota_decimal - 1.0 (ganancia neta por unidad apostada)
     p = probabilidad calibrada del modelo
     q = 1 - p
     f_frac = fraccion * f*
2. Control de Correlación por Partido:
   Los props del mismo juego están fuertemente correlacionados (script de partido, ritmo, prórroga o blowout).
   Por ello, se impone un tope estricto de exposición por juego (ej. máximo 2.5u o 5% del bankroll).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np

from core.calibracion_probabilidades import parsear_cuota_decimal

logger = logging.getLogger(__name__)

# Parámetros estándar de aversión al riesgo institucional
DEFAULT_KELLY_FRACTION = 0.25  # Quarter Kelly (1/4)
CONSERVATIVE_KELLY_FRACTION = 0.125  # Eighth Kelly (1/8)
MAX_STAKE_PER_PICK_PCT = 0.035  # Máximo 3.5% del bankroll por selección individual
MAX_STAKE_PER_GAME_PCT = 0.060  # Máximo 6.0% del bankroll acumulado en el mismo partido


def calcular_kelly_fraccional(
    probabilidad: float,
    cuota: Any,
    fraccion: float = DEFAULT_KELLY_FRACTION,
    max_stake_pct: float = MAX_STAKE_PER_PICK_PCT,
) -> Dict[str, float]:
    """Calcula el porcentaje de bankroll a arriesgar usando Kelly Fraccional.
    
    Retorna un diccionario con:
    - 'f_kelly_puro': Kelly completo teórico.
    - 'f_kelly_fraccional': Fracción ajustada (1/4 o 1/8).
    - 'stake_recomendado_pct': Porcentaje final recortado al límite prudencial.
    - 'ev_esperado_pct': Valor esperado porcentual.
    """
    p = float(probabilidad)
    c_dec = parsear_cuota_decimal(cuota)

    if c_dec is None or c_dec <= 1.0 or p <= 0.0 or p >= 1.0:
        return {
            "f_kelly_puro": 0.0,
            "f_kelly_fraccional": 0.0,
            "stake_recomendado_pct": 0.0,
            "ev_esperado_pct": 0.0
        }

    b = c_dec - 1.0  # Ganancia neta
    q = 1.0 - p
    ev = (p * c_dec) - 1.0

    # Si no hay valor esperado positivo (+EV), el stake es 0
    if ev <= 0.0 or (b * p - q) <= 0.0:
        return {
            "f_kelly_puro": 0.0,
            "f_kelly_fraccional": 0.0,
            "stake_recomendado_pct": 0.0,
            "ev_esperado_pct": round(float(ev * 100.0), 2)
        }

    # Kelly puro: (b * p - q) / b
    f_puro = (b * p - q) / b

    # Kelly fraccional
    f_frac = f_puro * fraccion

    # Recorte por límite individual
    stake_final = min(f_frac, max_stake_pct)

    return {
        "f_kelly_puro": round(float(f_puro), 4),
        "f_kelly_fraccional": round(float(f_frac), 4),
        "stake_recomendado_pct": round(float(stake_final), 4),
        "ev_esperado_pct": round(float(ev * 100.0), 2)
    }


def asignar_stakes_con_tope_de_partido(
    picks: List[Dict[str, Any]],
    fraccion_kelly: float = DEFAULT_KELLY_FRACTION,
    max_partido_pct: float = MAX_STAKE_PER_GAME_PCT,
    bankroll_total: float = 1000.0,
) -> List[Dict[str, Any]]:
    """Asigna stakes fraccionales y aplica el candado de correlación por partido (id_juego).
    Si un juego tiene 3 picks que suman 8% de bankroll, reduce proporcionalmente al 6% máximo.
    """
    if not picks:
        return []

    picks_procesados = []
    # 1. Calcular stake individual preliminar
    for p in picks:
        item = dict(p)
        prob = item.get("probabilidad", 0.50)
        cuota = item.get("cuota", 1.91)
        k_res = calcular_kelly_fraccional(prob, cuota, fraccion=fraccion_kelly)

        item["kelly_stake_pct"] = k_res["stake_recomendado_pct"]
        item["ev_pct"] = k_res["ev_esperado_pct"]
        picks_procesados.append(item)

    # 2. Agrupar por id_juego y aplicar factor de contracción por correlación
    por_juego: Dict[str, List[int]] = {}
    for idx, p in enumerate(picks_procesados):
        j_id = str(p.get("id_juego", "desconocido"))
        por_juego.setdefault(j_id, []).append(idx)

    for j_id, indices in por_juego.items():
        total_stake_juego = sum(picks_procesados[i]["kelly_stake_pct"] for i in indices)
        if total_stake_juego > max_partido_pct:
            factor_escala = max_partido_pct / total_stake_juego
            logger.info(
                f"Reduciendo stakes en juego {j_id} por correlación: "
                f"Suma original={total_stake_juego*100:.1f}%, Factor={factor_escala:.3f}"
            )
            for i in indices:
                picks_procesados[i]["kelly_stake_pct"] = round(
                    picks_procesados[i]["kelly_stake_pct"] * factor_escala, 4
                )
                picks_procesados[i]["alerta_correlacion"] = (
                    f"Stake reducido por correlación en partido ({total_stake_juego*100:.1f}% -> {max_partido_pct*100:.1f}%)"
                )

    # 3. Calcular unidades monetarias finales
    for p in picks_procesados:
        pct = p.get("kelly_stake_pct", 0.0)
        p["unidades_recomendadas"] = round(float(pct * bankroll_total), 2)

    return picks_procesados
