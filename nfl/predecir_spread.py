"""Módulo de inferencia en tiempo real para Spread / ATS (Línea de Hándicap) NFL V1.

Combina:
1. Líneas de spread en vivo vía ESPN Scoreboard y casas de apuestas (DraftKings).
2. Modelo predictivo Ensamble Spread V1 (Logistic Regression regularizada + HistGradientBoosting).
3. Variables de eficiencia causal de nflverse: EPA/Play rodante, Passing/Rushing EPA y capturas.
4. Salud posicional diferencial: QB, Línea Ofensiva (OL) y Defensiva.
5. Filtro de Números Clave (3 y 7) y umbral de rentabilidad comprobada (+EV).
6. Persistencia automática en JSON y Parquet para visualización e interfaz de usuario.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import joblib
import numpy as np
import pandas as pd

from nfl.ensamble_spread_v1 import EnsambleSpreadNFLv1
from nfl.predecir_moneyline import (
    calcular_descanso_fecha,
    es_juego_divisional,
    normalizar_equipo,
    obtener_metricas_recientes_equipos,
    DIVISIONES_NFL,
)
from nfl.proveedor_cuotas import american_to_decimal, obtener_jornada_nfl_espn

logger = logging.getLogger("nfl_predecir_spread")
ZONA_CDMX = ZoneInfo("America/Mexico_City")

RUTA_MODELO = RAIZ / "modelos_nfl" / "modelo_spread_nfl.joblib"
RUTA_DATASET_FEATURES = RAIZ / "data" / "nfl" / "processed" / "nfl_games_features_2012_2026.parquet"
RUTA_EPA_ROLLING = RAIZ / "data" / "nfl" / "processed" / "nfl_team_epa_rolling.parquet"
RUTA_PREDICCIONES_DIR = RAIZ / "data" / "nfl" / "predictions"
RUTA_PREDICCIONES_JSON = RUTA_PREDICCIONES_DIR / "predicciones_nfl_spread.json"
RUTA_PREDICCIONES_PARQUET = RUTA_PREDICCIONES_DIR / "predicciones_nfl_spread.parquet"


def generar_predicciones_spread(
    jornada_partidos: Optional[List[Dict[str, Any]]] = None,
    umbral_min_prob: float = 0.530,
) -> List[Dict[str, Any]]:
    """Genera pronósticos ATS para todos los partidos de la jornada actual."""
    if not RUTA_MODELO.exists():
        raise FileNotFoundError(f"No se encontró el modelo de spread en {RUTA_MODELO}")

    ensamble: EnsambleSpreadNFLv1 = joblib.load(RUTA_MODELO)
    if umbral_min_prob is not None:
        ensamble.umbral_edge = float(umbral_min_prob)
    metricas_eq = obtener_metricas_recientes_equipos()

    if jornada_partidos is None:
        jornada_partidos = obtener_jornada_nfl_espn()

    predicciones = []

    for p in jornada_partidos:
        home_raw = p.get("equipo_local") or p.get("home_team", "")
        away_raw = p.get("equipo_visita") or p.get("away_team", "")
        home = normalizar_equipo(home_raw)
        away = normalizar_equipo(away_raw)

        # En nflverse spread_line > 0 significa Home favorito.
        # En ESPN/DraftKings ("equipo_local" presente) el favorito local tiene spread negativo (ej. -3.5 => +3.5 nflverse).
        spread_mercado = p.get("spread_line")
        if spread_mercado is None:
            continue

        spread_val = float(spread_mercado)
        es_formato_espn = ("equipo_local" in p) or bool(p.get("convencion_espn", False))
        spread_line = -spread_val if es_formato_espn else spread_val

        fecha_str = str(
            p.get("fecha_cdmx")
            or p.get("fecha")
            or datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M")
        )

        m_h = metricas_eq.get(home, {})
        m_a = metricas_eq.get(away, {})

        diff_pass_epa_8 = m_h.get("pass_epa_8", 0.0) - m_a.get("pass_epa_8", 0.0)
        diff_rush_epa_8 = m_h.get("rush_epa_8", 0.0) - m_a.get("rush_epa_8", 0.0)
        diff_sacks_8 = m_h.get("sacks_8", 0.0) - m_a.get("sacks_8", 0.0)
        diff_def_pass_epa_8 = m_h.get("def_pass_epa_8", 0.0) - m_a.get("def_pass_epa_8", 0.0)
        diff_def_rush_epa_8 = m_h.get("def_rush_epa_8", 0.0) - m_a.get("def_rush_epa_8", 0.0)
        diff_def_sacks_8 = m_h.get("def_sacks_8", 0.0) - m_a.get("def_sacks_8", 0.0)

        diff_points_for_avg_8 = m_h.get("points_for_avg_8", 21.0) - m_a.get("points_for_avg_8", 21.0)
        diff_points_against_avg_8 = m_h.get("points_against_avg_8", 21.0) - m_a.get("points_against_avg_8", 21.0)
        diff_win_pct_8 = m_h.get("win_pct_8", 0.5) - m_a.get("win_pct_8", 0.5)
        diff_win_pct_season = m_h.get("win_pct_season", 0.5) - m_a.get("win_pct_season", 0.5)

        home_rest = calcular_descanso_fecha(m_h.get("last_gameday"), fecha_str, m_h.get("rest", 7.0))
        away_rest = calcular_descanso_fecha(m_a.get("last_gameday"), fecha_str, m_a.get("rest", 7.0))
        diff_rest = home_rest - away_rest

        diff_injury_severity = m_h.get("injury_severity", 0.0) - m_a.get("injury_severity", 0.0)
        diff_injury_starting_qb_score = m_h.get("injury_starting_qb_score", 0.0) - m_a.get("injury_starting_qb_score", 0.0)
        diff_injury_ol_score = m_h.get("injury_ol_score", 0.0) - m_a.get("injury_ol_score", 0.0)
        diff_injury_defense_score = m_h.get("injury_defense_score", 0.0) - m_a.get("injury_defense_score", 0.0)

        abs_spread = abs(spread_line)
        key_3 = 1.0 if abs_spread == 3.0 else 0.0
        key_7 = 1.0 if abs_spread == 7.0 else 0.0
        is_home_dog = 1.0 if spread_line < 0 else 0.0

        features_dict = {
            "spread_line": spread_line,
            "abs_spread": abs_spread,
            "key_3": key_3,
            "key_7": key_7,
            "is_home_dog": is_home_dog,
            "diff_pass_epa_8": diff_pass_epa_8,
            "diff_rush_epa_8": diff_rush_epa_8,
            "diff_sacks_8": diff_sacks_8,
            "diff_def_pass_epa_8": diff_def_pass_epa_8,
            "diff_def_rush_epa_8": diff_def_rush_epa_8,
            "diff_def_sacks_8": diff_def_sacks_8,
            "diff_points_for_avg_8": diff_points_for_avg_8,
            "diff_points_against_avg_8": diff_points_against_avg_8,
            "diff_win_pct_8": diff_win_pct_8,
            "diff_win_pct_season": diff_win_pct_season,
            "diff_rest": diff_rest,
            "diff_injury_severity": diff_injury_severity,
            "diff_injury_starting_qb_score": diff_injury_starting_qb_score,
            "diff_injury_ol_score": diff_injury_ol_score,
            "diff_injury_defense_score": diff_injury_defense_score,
            "home_qb_change": 0.0,
            "away_qb_change": 0.0,
            "div_game": float(es_juego_divisional(home, away)),
        }

        diag = ensamble.evaluar_partido(
            features_dict,
            spread_line,
            home,
            away,
            odds_home=p.get("spread_home_odds"),
            odds_away=p.get("spread_away_odds"),
        )
        diag["game_id"] = p.get("id_evento") or p.get("game_id", f"{home}_{away}")
        diag["fecha"] = fecha_str
        diag["estado"] = p.get("estado", "PRE")

        predicciones.append(diag)

    # Persistir
    RUTA_PREDICCIONES_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUTA_PREDICCIONES_JSON, "w", encoding="utf-8") as f:
        json.dump(predicciones, f, indent=2, ensure_ascii=False)

    df_out = pd.DataFrame(predicciones)
    if not df_out.empty:
        df_out.to_parquet(RUTA_PREDICCIONES_PARQUET, index=False)

    return predicciones


if __name__ == "__main__":
    preds = generar_predicciones_spread()
    print(f"✅ Se evaluaron {len(preds)} partidos con el modelo Spread NFL V1.")
    recomendados = [p for p in preds if p["recomendar"]]
    print(f"🎯 Picks oficiales con ventaja estadística (+EV): {len(recomendados)}")
    for r in recomendados:
        print(f"  • {r['pick']} {r['linea_pick']:+g} (P={r['prob_seleccion']*100:.1f}%, EV={r['ev_esperado_pct']:+.1f}%)")
