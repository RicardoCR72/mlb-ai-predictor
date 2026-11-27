"""Modelo Cuantitativo de Minutos y Descomposición por Minuto para Props NBA.

Arquitectura:
1. Modelo de Minutos Desacoplado:
   Proyecta minutos esperados en función de:
   - Rol del jugador (titular vs suplente)
   - Tendencia reciente L5 (peso 60%) vs promedio de temporada (peso 40%)
   - Riesgo de Blowout según el spread del partido (si spread >= 9.5 pts, reducción esperada en 4Q)
   - Calendario: Back-to-Back (B2B)
   - Riesgo de Faltas (Foul Trouble) si promedia >= 3.4 faltas
2. Descomposición por Minuto:
   Proyección = Tasa por Minuto (con Shrinkage Bayesiano) × Minutos Proyectados
   Separa la incertidumbre de participación (tiempo en cancha) de la eficiencia de producción.
3. Shrinkage Bayesiano hacia Prior de Posición:
   En lugar de forzar un 60/40 estático contra la línea de la casa, aplica actualización Bayesiana:
   Tasa_Ajustada = (N * Tasa_Jugador + M * Prior_Posicion) / (N + M)
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Priors empíricos de liga NBA 2026-27 por posición (por minuto jugado)
# Calculados sobre muestra histórica con min >= 8.0
PRIORS_POSICION = {
    "C": {
        "pts_pm": 0.417, "reb_pm": 0.301, "ast_pm": 0.083, "pra_pm": 0.801,
        "pr_pm": 0.718, "pa_pm": 0.500, "t3_made_pm": 0.023, "min_titular": 28.5, "min_banca": 17.5
    },
    "F": {
        "pts_pm": 0.443, "reb_pm": 0.203, "ast_pm": 0.084, "pra_pm": 0.731,
        "pr_pm": 0.646, "pa_pm": 0.527, "t3_made_pm": 0.051, "min_titular": 31.0, "min_banca": 19.0
    },
    "G": {
        "pts_pm": 0.454, "reb_pm": 0.129, "ast_pm": 0.127, "pra_pm": 0.710,
        "pr_pm": 0.583, "pa_pm": 0.581, "t3_made_pm": 0.064, "min_titular": 32.5, "min_banca": 19.5
    },
    "GLOBAL": {
        "pts_pm": 0.445, "reb_pm": 0.185, "ast_pm": 0.108, "pra_pm": 0.738,
        "pr_pm": 0.630, "pa_pm": 0.553, "t3_made_pm": 0.053, "min_titular": 31.0, "min_banca": 18.5
    }
}

# Peso M de observaciones del prior (reducido a 2.5 para no jalar hacia abajo a titulares consolidados)
M_SHRINKAGE_JUEGOS = 2.5


def proyectar_minutos_jugador(
    min_season: float,
    min_l5: float,
    es_titular: bool,
    spread_partido: float = 0.0,
    es_b2b: bool = False,
    faltas_promedio_l5: Optional[float] = None,
    edad: Optional[int] = None,
) -> Dict[str, Any]:
    """Proyecta los minutos esperados de un jugador en cancha desacoplando factores tácticos y contextuales.
    
    Retorna:
    - 'minutos_proyectados': Minutos finales esperados.
    - 'factor_blowout': Multiplicador por riesgo de juego decidido.
    - 'factor_b2b': Multiplicador por descanso.
    - 'penalizacion_faltas': Minutos reducidos por tendencia de foul trouble.
    """
    # 1. Base ponderada: 60% forma reciente (refleja cambios de rotación inmediatos), 40% temporada
    if min_season <= 0 and min_l5 <= 0:
        base_min = 28.0 if es_titular else 18.0
    elif min_season <= 0:
        base_min = min_l5
    elif min_l5 <= 0:
        base_min = min_season
    else:
        base_min = 0.60 * min_l5 + 0.40 * min_season

    # 2. Descuento por riesgo de blowout (Spread amplio del mercado)
    # Si un equipo es favorito o no-favorito por 10+ puntos, la probabilidad de basura en 4Q sube drásticamente
    abs_spread = abs(float(spread_partido or 0.0))
    if abs_spread >= 13.0 and es_titular:
        factor_blowout = 0.88  # -12% de minutos en blowouts severos
    elif abs_spread >= 9.5 and es_titular:
        factor_blowout = 0.93  # -7% de minutos en juegos con spread amplio
    else:
        factor_blowout = 1.0

    # 3. Factor de Back-to-Back (B2B)
    factor_b2b = 1.0
    if es_b2b:
        # Titulares con alta carga sufren restricción de 4-6%
        factor_b2b = 0.94 if (es_titular or base_min >= 30.0) else 0.97

    # 4. Ajuste por riesgo de problemas de faltas (Foul Trouble)
    # Jugadores que promedian >= 3.5 faltas tienen riesgo alto de sentarse 4-6 min en la primera mitad
    minutos_penalizacion_faltas = 0.0
    if faltas_promedio_l5 is not None:
        if faltas_promedio_l5 >= 3.8:
            minutos_penalizacion_faltas = 2.0
        elif faltas_promedio_l5 >= 3.2:
            minutos_penalizacion_faltas = 1.0

    # Minutos calculados
    min_ajustados = (base_min * factor_blowout * factor_b2b) - minutos_penalizacion_faltas
    min_final = max(8.0, min(min_ajustados, 42.0))

    return {
        "minutos_proyectados": round(float(min_final), 1),
        "base_minutos": round(float(base_min), 1),
        "factor_blowout": factor_blowout,
        "factor_b2b": factor_b2b,
        "penalizacion_faltas_min": minutos_penalizacion_faltas,
        "es_titular": es_titular
    }


def calcular_tasa_por_minuto_bayesiana(
    total_stat: float,
    total_minutos: float,
    partidos_jugados: int,
    posicion: str,
    clave_stat: str,  # 'pts', 'reb', 'ast', 'pra', 'pr', 'pa', 't3_made'
) -> Tuple[float, float, float]:
    """Calcula la tasa de producción por minuto con Shrinkage Bayesiano hacia el prior de la posición.
    
    Retorna:
    - tasa_shrunk: Tasa final por minuto ponderada.
    - tasa_observada: Tasa empírica pura del jugador.
    - prior_pos: Prior de referencia de la liga para esa posición.
    """
    pos_norm = str(posicion).strip().upper()
    if pos_norm not in PRIORS_POSICION:
        # Mapear PG/SG -> G, SF/PF -> F
        if "G" in pos_norm:
            pos_norm = "G"
        elif "F" in pos_norm:
            pos_norm = "F"
        elif "C" in pos_norm:
            pos_norm = "C"
        else:
            pos_norm = "GLOBAL"

    priors = PRIORS_POSICION.get(pos_norm, PRIORS_POSICION["GLOBAL"])
    key_prior = f"{clave_stat}_pm"
    prior_tasa = priors.get(key_prior, PRIORS_POSICION["GLOBAL"].get(key_prior, 0.40))

    if total_minutos > 0:
        tasa_observada = total_stat / total_minutos
    else:
        tasa_observada = prior_tasa

    n = max(1, partidos_jugados)
    m = M_SHRINKAGE_JUEGOS

    # Actualización Bayesiana: (N * Tasa_Obs + M * Prior) / (N + M)
    tasa_shrunk = (n * tasa_observada + m * prior_tasa) / (n + m)

    return float(tasa_shrunk), float(tasa_observada), float(prior_tasa)


def proyectar_prop_por_minuto(
    df_boxscores_jugador: pd.DataFrame,
    posicion: str,
    clave_stat: str,
    spread_partido: float = 0.0,
    total_partido: float = 226.0,
    pace_local: float = 100.0,
    pace_visita: float = 100.0,
    es_b2b: bool = False,
    defensa_rival_factor: float = 1.0,
) -> Dict[str, Any]:
    """Genera la proyección completa desacoplando minutos y tasa por minuto.
    
    Proyección = Tasa_Ajustada_por_Minuto × Minutos_Proyectados × Factor_Pace × Factor_Defensa
    """
    if df_boxscores_jugador.empty or clave_stat not in df_boxscores_jugador.columns:
        return {"proyeccion": 0.0, "minutos_proyectados": 0.0, "tasa_por_minuto": 0.0}

    col_min = "min" if "min" in df_boxscores_jugador.columns else "minutos"
    df_clean = df_boxscores_jugador.dropna(subset=[col_min, clave_stat]).copy()
    df_clean = df_clean[df_clean[col_min] >= 8.0]

    if df_clean.empty:
        return {"proyeccion": 0.0, "minutos_proyectados": 0.0, "tasa_por_minuto": 0.0}

    n_games = len(df_clean)
    min_season = float(df_clean[col_min].mean())
    min_l5 = float(df_clean.tail(5)[col_min].mean())

    es_titular = (min_season >= 24.0) or (min_l5 >= 25.0)

    # 1. Proyectar minutos
    faltas_l5 = None
    if "pf" in df_boxscores_jugador.columns and not df_boxscores_jugador["pf"].dropna().empty:
        faltas_l5 = float(df_boxscores_jugador["pf"].dropna().head(5).mean())

    res_min = proyectar_minutos_jugador(
        min_season=min_season,
        min_l5=min_l5,
        es_titular=es_titular,
        spread_partido=spread_partido,
        es_b2b=es_b2b,
        faltas_promedio_l5=faltas_l5
    )
    min_esperados = res_min["minutos_proyectados"]

    # 2. Calcular tasa por minuto (temporada + L5 reciente)
    total_stat_season = float(df_clean[clave_stat].sum())
    total_min_season = float(df_clean[col_min].sum())

    df_l5 = df_clean.tail(5)
    total_stat_l5 = float(df_l5[clave_stat].sum())
    total_min_l5 = float(df_l5[col_min].sum())

    tasa_season, _, prior_t = calcular_tasa_por_minuto_bayesiana(
        total_stat=total_stat_season,
        total_minutos=total_min_season,
        partidos_jugados=n_games,
        posicion=posicion,
        clave_stat=clave_stat
    )

    tasa_l5 = (total_stat_l5 / total_min_l5) if total_min_l5 > 0 else tasa_season

    # Ponderación temporal de la tasa: 35% L5 / 65% temporada
    tasa_blended = 0.35 * tasa_l5 + 0.65 * tasa_season

    # 3. Factor de Pace (Ritmo de Posesiones): ritmo promedio NBA = ~100.0
    pace_esperado = (pace_local + pace_visita) / 2.0
    factor_pace = float(np.clip(pace_esperado / 100.0, 0.92, 1.08))

    # 4. Total del mercado y factor de entorno sin sobre-escalar ni inflar rebotes por eficiencia ofensiva
    factor_total = float(np.clip(total_partido / 226.0, 0.95, 1.05))
    if clave_stat == "reb":
        factor_entorno = factor_pace * defensa_rival_factor
    else:
        factor_entorno = float(np.sqrt(factor_pace * factor_total)) * defensa_rival_factor

    # 5. Proyección cuantitativa final
    proy_final = tasa_blended * min_esperados * factor_entorno

    return {
        "proyeccion": round(float(proy_final), 1),
        "minutos_proyectados": min_esperados,
        "tasa_por_minuto": round(float(tasa_blended), 4),
        "tasa_l5": round(float(tasa_l5), 4),
        "tasa_season": round(float(tasa_season), 4),
        "prior_posicion": round(float(prior_t), 4),
        "factor_pace": round(factor_pace, 3),
        "factor_total": round(factor_total, 3),
        "factor_blowout": res_min["factor_blowout"],
        "es_titular": es_titular,
        "n_juegos": n_games
    }
