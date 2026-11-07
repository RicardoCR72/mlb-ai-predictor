"""Motor predictivo y de valor esperado (EV) para Player Props NBA.

Combina:
1. Líneas y cuotas en tiempo real de Bovada (0 créditos).
2. Estadísticas de temporada 2026-27 y tendencia reciente (L5) de ESPN.
3. Impacto de lesiones en tiempo real de compañeros de equipo (Usage Boost).
4. Modelado probabilístico (Poisson para Triples/Asistencias/Rebotes, Gaussiano/Empírico para Puntos/PRA).
5. Cálculo de Valor Esperado (EV%) y asignación de estrellas de confianza.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX
from nba.servicio_bovada_props import extraer_props_nba, _limpiar_nombre_jugador
from nba.servicio_jugadores_boxscores import (
    RUTA_PARQUET_JUGADORES,
    sincronizar_boxscores_jugadores,
    calcular_perfil_jugador
)
from nba.servicio_lesiones import obtener_reporte_lesiones_nba

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nba_predecir_props")

DIR_PRED = RAIZ / "data" / "nba" / "predictions"
RUTA_PRED_PARQUET = DIR_PRED / "predicciones_props_nba_hoy.parquet"
RUTA_PRED_JSON = DIR_PRED / "predicciones_props_nba_hoy.json"

MAPA_MERCADOS_COLUMNAS = {
    "Total Points": ("pts", "pts_avg", "pts_std", "pts_l5"),
    "Total Rebounds": ("reb", "reb_avg", "reb_std", "reb_l5"),
    "Total Assists": ("ast", "ast_avg", "ast_std", "ast_l5"),
    "Total Triples": ("t3_made", "t3_avg", "t3_std", "t3_l5"),
    "Total PRA": ("pra", "pra_avg", "pra_std", "pra_l5"),
    "Total PR": ("pr", "pr_avg", None, None),
    "Total PA": ("pa", "pa_avg", None, None),
}


def _calcular_hit_rate(serie: pd.Series, linea: float) -> Tuple[float, int, int]:
    """Calcula el porcentaje de partidos en que el jugador superó la línea."""
    if serie.empty:
        return 0.5, 0, 0
    total = len(serie)
    overs = int((serie > linea).sum())
    return round(overs / total, 3), overs, total


def _calcular_probabilidad_poisson(linea: float, lam: float) -> float:
    """Probabilidad P(X > linea) usando distribución Poisson."""
    if lam <= 0.05:
        return 0.05
    k = math.floor(linea)
    # P(X > k) = 1 - PoissonCDF(k, lam)
    cdf = stats.poisson.cdf(k, mu=lam)
    prob_over = 1.0 - cdf
    return float(np.clip(prob_over, 0.02, 0.98))


def _calcular_probabilidad_normal(linea: float, mu: float, sigma: float) -> float:
    """Probabilidad P(X > linea) usando distribución Normal con corrección continua."""
    if sigma <= 0.1:
        sigma = 1.5
    # P(X > linea) = 1 - Phi((linea - mu) / sigma)
    z = (linea - mu) / sigma
    prob_over = 1.0 - stats.norm.cdf(z)
    return float(np.clip(prob_over, 0.02, 0.98))


def generar_predicciones_props_hoy(
    usar_cache_bovada: bool = True,
    min_juegos_muestra: int = 3
) -> pd.DataFrame:
    """Genera predicciones con Valor Esperado (EV%) para todos los props de hoy."""
    DIR_PRED.mkdir(parents=True, exist_ok=True)

    # 1. Cargar o sincronizar boxscores de jugadores
    if not RUTA_PARQUET_JUGADORES.exists():
        logger.info("Boxscores de jugadores no encontrados. Sincronizando...")
        df_boxscores = sincronizar_boxscores_jugadores()
    else:
        df_boxscores = pd.read_parquet(RUTA_PARQUET_JUGADORES)

    if df_boxscores.empty:
        logger.error("No hay boxscores disponibles para generar predicciones.")
        return pd.DataFrame()

    df_perfiles = calcular_perfil_jugador(df_boxscores)
    # Crear diccionario de acceso rápido por nombre normalizado
    df_boxscores["player_norm"] = df_boxscores["player_name"].apply(_limpiar_nombre_jugador).str.lower()
    df_perfiles["player_norm"] = df_perfiles["player_name"].apply(_limpiar_nombre_jugador).str.lower()

    perfiles_dict = {
        row["player_norm"]: row.to_dict()
        for _, row in df_perfiles.iterrows()
    }

    # 2. Cargar reporte de lesiones para detectar bajas estelares
    bajas_por_equipo: Dict[str, float] = {}
    try:
        reporte_les = obtener_reporte_lesiones_nba()
        for t_abbr, lista_les in reporte_les.items():
            for les in lista_les:
                if les.get("estado") in ["OUT", "DOUBTFUL"]:
                    imp = les.get("impacto_spread", 1.0)
                    bajas_por_equipo[t_abbr] = bajas_por_equipo.get(t_abbr, 0.0) + imp
    except Exception as e:
        logger.warning(f"No se pudo consultar el servicio de lesiones: {e}")

    # 3. Descargar o leer líneas de Bovada
    df_bovada = extraer_props_nba(usar_cache=usar_cache_bovada)
    if df_bovada.empty:
        logger.warning("No se obtuvieron props de Bovada.")
        return pd.DataFrame()

    predicciones: List[Dict[str, Any]] = []

    for _, row in df_bovada.iterrows():
        p_clean = row["player_clean"]
        p_norm = p_clean.lower()
        mercado = row["market"]
        linea = float(row["line"])
        equipo = row["team"]

        # Buscar perfil de estadísticas
        perfil = perfiles_dict.get(p_norm)
        if not perfil or perfil.get("games_played", 0) < min_juegos_muestra:
            continue

        cols_stat = MAPA_MERCADOS_COLUMNAS.get(mercado)
        if not cols_stat:
            continue

        raw_col, avg_col, std_col, l5_col = cols_stat
        
        stat_avg = float(perfil.get(avg_col, 0.0) or 0.0)
        stat_l5 = float(perfil.get(l5_col, stat_avg) or stat_avg) if l5_col else stat_avg
        stat_std = float(perfil.get(std_col, 1.5) or 1.5) if std_col else 1.5

        if stat_avg <= 0:
            continue

        # Filtrar historial de este jugador para calcular hit rate exacto
        hist_player = df_boxscores[df_boxscores["player_norm"] == p_norm].sort_values("fecha")
        serie_stat = hist_player[raw_col].dropna()

        hit_rate_season, ov_season, n_season = _calcular_hit_rate(serie_stat, linea)
        hit_rate_l5, ov_l5, n_l5 = _calcular_hit_rate(serie_stat.tail(5), linea)

        # Proyección ponderada: 60% forma reciente (L5), 40% temporada
        proj_base = 0.60 * stat_l5 + 0.40 * stat_avg

        # Boost de volumen si un compañero estrella está lesionado (OUT)
        impacto_bajas = bajas_por_equipo.get(equipo, 0.0)
        boost_lesion = 1.0
        if impacto_bajas >= 2.0:
            boost_lesion = 1.08  # +8% de volumen / tiros
        elif impacto_bajas >= 3.0:
            boost_lesion = 1.14  # +14%

        proyeccion = round(proj_base * boost_lesion, 1)

        # Cálculo de probabilidades según tipo de estadística
        if mercado in ["Total Triples", "Total Assists", "Total Rebounds"]:
            prob_over = _calcular_probabilidad_poisson(linea, lam=proyeccion)
        else:
            # Puntos, PRA, PR, PA
            prob_over = _calcular_probabilidad_normal(linea, mu=proyeccion, sigma=stat_std)

        # Combinar probabilidad del modelo (70%) con hit rate empírico de temporada (30%)
        prob_over_blended = round(0.70 * prob_over + 0.30 * hit_rate_season, 4)
        prob_under_blended = round(1.0 - prob_over_blended, 4)

        # Cuotas decimales de Bovada
        over_dec = row.get("over_decimal")
        under_dec = row.get("under_decimal")

        # Cálculo de EV%
        # EV = (Prob * Dec - 1) * 100
        ev_over = round((prob_over_blended * over_dec - 1.0) * 100.0, 1) if over_dec else -100.0
        ev_under = round((prob_under_blended * under_dec - 1.0) * 100.0, 1) if under_dec else -100.0

        # Selección del Pick recomendado
        is_milestone = int(row.get("is_milestone", 0))
        if is_milestone:
            # En milestones solo existe la opción Over (+X triples)
            pick_tipo = "OVER"
            pick_ev = ev_over
            pick_prob = prob_over_blended
            pick_cuota_am = row.get("over_american")
            pick_cuota_dec = over_dec
        else:
            if ev_over >= ev_under:
                pick_tipo = "OVER"
                pick_ev = ev_over
                pick_prob = prob_over_blended
                pick_cuota_am = row.get("over_american")
                pick_cuota_dec = over_dec
            else:
                pick_tipo = "UNDER"
                pick_ev = ev_under
                pick_prob = prob_under_blended
                pick_cuota_am = row.get("under_american")
                pick_cuota_dec = under_dec

        # Clasificación por estrellas
        if pick_ev >= 10.0 and (hit_rate_season >= 0.55 if pick_tipo == "OVER" else hit_rate_season <= 0.45):
            estrellas = "⭐⭐⭐"
            confianza = "ALTA"
        elif pick_ev >= 5.0:
            estrellas = "⭐⭐"
            confianza = "MEDIA"
        elif pick_ev >= 1.5:
            estrellas = "⭐"
            confianza = "MODERADA"
        else:
            estrellas = "⚪"
            confianza = "NEUTRAL"

        # Resumen de tendencia
        if pick_tipo == "OVER":
            tendencia = f"Over en {ov_l5}/{n_l5} últimos (promedia {proyeccion:.1f} vs línea {linea})"
        else:
            tendencia = f"Under en {n_l5 - ov_l5}/{n_l5} últimos (promedia {proyeccion:.1f} vs línea {linea})"

        predicciones.append({
            "game": row["game"],
            "fecha": row["fecha"],
            "hora": row["hora"],
            "away_team": row["away_team"],
            "home_team": row["home_team"],
            "player_name": row["player_name"],
            "player_clean": p_clean,
            "team": equipo,
            "position": perfil.get("position", ""),
            "market": mercado,
            "line": linea,
            "projection": proyeccion,
            "stat_avg": stat_avg,
            "stat_l5": stat_l5,
            "games_played": perfil.get("games_played", 0),
            "hit_rate_season": hit_rate_season,
            "hit_rate_l5": hit_rate_l5,
            "pick_type": pick_tipo,
            "pick_odds_american": pick_cuota_am,
            "pick_odds_decimal": pick_cuota_dec,
            "model_prob": pick_prob,
            "implied_prob": round(1.0 / pick_cuota_dec, 4) if pick_cuota_dec else 0.5,
            "ev_pct": pick_ev,
            "stars": estrellas,
            "confidence": confianza,
            "trend": tendencia,
            "boost_lesion_pct": round((boost_lesion - 1.0) * 100.0, 1),
            "is_milestone": is_milestone,
        })

    df_res = pd.DataFrame(predicciones)

    if not df_res.empty:
        # Ordenar por EV% descendente
        df_res.sort_values(by="ev_pct", ascending=False, inplace=True)
        
        df_res.to_parquet(RUTA_PRED_PARQUET, index=False)
        with open(RUTA_PRED_JSON, "w", encoding="utf-8") as f:
            json.dump(df_res.to_dict(orient="records"), f, indent=2, ensure_ascii=False)
        
        logger.info(f"🎯 Generadas exitosamente {len(df_res)} predicciones de props. Top EV: +{df_res['ev_pct'].max()}%")

    return df_res


if __name__ == "__main__":
    t0 = time.time()
    df_preds = generar_predicciones_props_hoy(usar_cache_bovada=True)
    print(f"Predicciones listas en {time.time() - t0:.2f}s. Total: {len(df_preds)}")
    if not df_preds.empty:
        top = df_preds[df_preds["ev_pct"] >= 5.0]
        print(f"\nPicks con EV >= 5%: {len(top)}")
        cols = ["player_name", "team", "market", "line", "projection", "pick_type", "pick_odds_american", "ev_pct", "stars", "trend"]
        print(top.head(15)[cols].to_string())
