"""Modelo Bivariado de Poisson para la Liga MX.

Predice de forma conjunta y matemáticamente consistente:
1. Goles esperados (xG) de equipo local y visitante.
2. Moneyline (1X2): Probabilidad de Victoria Local, Empate y Victoria Visitante.
3. Totales (Over / Under): Probabilidad de Over 2.5 y Under 2.5 (o cualquier línea de mercado).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple
import joblib
import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[1]
RUTA_DATA = RAIZ / "futbol_liga_mx" / "data"
RUTA_MODELOS = RAIZ / "futbol_liga_mx" / "modelos"
RUTA_MODELO_BIVARIADO = RUTA_MODELOS / "modelo_bivariado.joblib"

FEATURES_BIVARIADO = [
    "gf_local_5", "gc_local_5", "gf_visitante_5", "gc_visitante_5",
    "puntos_local_5", "puntos_visitante_5", "descanso_local", "descanso_visitante",
    "media_liga_local", "media_liga_visitante"
]


def construir_features_historicas(partidos: pd.DataFrame) -> pd.DataFrame:
    """Genera las variables predictivas previas al partido asegurando cero data leakage."""
    data = partidos.copy()
    data["fecha"] = pd.to_datetime(data["fecha"], errors="coerce").dt.normalize()
    data = data.sort_values(["fecha", "local", "visitante"]).reset_index(drop=True)

    state = defaultdict(list)
    rows = []
    league = []

    for day, batch in data.groupby("fecha", sort=True):
        league_home = (sum(x[0] for x in league) + 120 * 1.50) / (len(league) + 120)
        league_away = (sum(x[1] for x in league) + 120 * 1.15) / (len(league) + 120)

        for row in batch.itertuples(index=False):
            home_history = state[row.local]
            away_history = state[row.visitante]

            def recent(records: list, target_idx: int, prior: float) -> float:
                last = [r[target_idx] for r in records[-5:]]
                return (sum(last) + 5 * prior) / (len(last) + 5)

            feats = {
                "gf_local_5": recent(home_history, 1, league_home),
                "gc_local_5": recent(home_history, 2, league_away),
                "gf_visitante_5": recent(away_history, 1, league_away),
                "gc_visitante_5": recent(away_history, 2, league_home),
                "puntos_local_5": recent(home_history, 3, 1.4),
                "puntos_visitante_5": recent(away_history, 3, 1.1),
                "descanso_local": min(max((day - home_history[-1][0]).days, 0), 30) if home_history else 7,
                "descanso_visitante": min(max((day - away_history[-1][0]).days, 0), 30) if away_history else 7,
                "media_liga_local": league_home,
                "media_liga_visitante": league_away,
            }
            rows.append({**row._asdict(), **feats})

        # Actualizar estado tras procesar todos los juegos de la fecha
        for row in batch.itertuples(index=False):
            h, a = int(row.goles_local), int(row.goles_visitante)
            pts_h = 3 if h > a else (1 if h == a else 0)
            pts_a = 3 if a > h else (1 if a == h else 0)
            state[row.local].append((day, h, a, pts_h))
            state[row.visitante].append((day, a, h, pts_a))
            league.append((h, a))

    res = pd.DataFrame(rows)
    return res


def entrenar_modelo_bivariado(
    ruta_partidos: Path | str = RUTA_DATA / "partidos.csv",
    guardar: bool = True
) -> Dict[str, Any]:
    """Entrena dos modelos Poisson (Goles Local y Goles Visitante) y empaqueta el bundle."""
    df_partidos = pd.read_csv(ruta_partidos)
    data = construir_features_historicas(df_partidos)

    # Entrenar con historial previo y validar en temporadas recientes
    train = data[data["season"] < "2025-26"].copy()
    test = data[data["season"] >= "2025-26"].copy()
    if test.empty:
        test = data.iloc[-100:].copy()
        train = data.iloc[:-100].copy()

    m_home = make_pipeline(StandardScaler(), PoissonRegressor(alpha=0.45, max_iter=600))
    m_away = make_pipeline(StandardScaler(), PoissonRegressor(alpha=0.45, max_iter=600))

    m_home.fit(train[FEATURES_BIVARIADO], train["goles_local"])
    m_away.fit(train[FEATURES_BIVARIADO], train["goles_visitante"])

    preds_h = m_home.predict(test[FEATURES_BIVARIADO])
    preds_a = m_away.predict(test[FEATURES_BIVARIADO])

    mae_h = float(np.mean(np.abs(test["goles_local"] - preds_h)))
    mae_a = float(np.mean(np.abs(test["goles_visitante"] - preds_a)))

    bundle = {
        "modelo_home": m_home,
        "modelo_away": m_away,
        "features": FEATURES_BIVARIADO,
        "metricas": {
            "mae_home": round(mae_h, 3),
            "mae_away": round(mae_a, 3),
            "media_goles_home": round(float(train["goles_local"].mean()), 2),
            "media_goles_away": round(float(train["goles_visitante"].mean()), 2),
            "partidos_entrenados": len(train),
        }
    }

    if guardar:
        RUTA_MODELOS.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, RUTA_MODELO_BIVARIADO)
        logger.info(f"💾 Modelo Bivariado Liga MX guardado en {RUTA_MODELO_BIVARIADO}")

    return bundle


def proyectar_partido_bivariado(
    bundle: Dict[str, Any],
    feats_dict: Dict[str, float],
    linea_total: float = 2.5
) -> Dict[str, Any]:
    """Calcula la matriz bivariada de Poisson y deriva Moneyline y Totales."""
    df_row = pd.DataFrame([feats_dict])[bundle["features"]]

    lambda_home = float(np.clip(bundle["modelo_home"].predict(df_row)[0], 0.25, 5.0))
    lambda_away = float(np.clip(bundle["modelo_away"].predict(df_row)[0], 0.20, 5.0))

    # Matriz bivariada 10x10 de goles
    max_g = 10
    prob_h = [poisson.pmf(i, lambda_home) for i in range(max_g)]
    prob_a = [poisson.pmf(j, lambda_away) for j in range(max_g)]
    grid = np.outer(prob_h, prob_a)

    # 1. Moneyline (1X2)
    p_home_win = float(np.sum(np.tril(grid, -1)))
    p_draw = float(np.sum(np.diag(grid)))
    p_away_win = float(np.sum(np.triu(grid, 1)))

    # Normalizar suma exactamente a 1.0
    total_ml = p_home_win + p_draw + p_away_win
    if total_ml > 0:
        p_home_win /= total_ml
        p_draw /= total_ml
        p_away_win /= total_ml

    # 2. Totales (Over / Under)
    i_idx, j_idx = np.meshgrid(np.arange(max_g), np.arange(max_g), indexing="ij")
    p_over = float(np.sum(grid[i_idx + j_idx > linea_total]))
    p_under = float(np.sum(grid[i_idx + j_idx < linea_total]))
    p_push = float(np.sum(grid[i_idx + j_idx == linea_total]))

    # Marcador más probable
    max_idx = np.unravel_index(np.argmax(grid), grid.shape)
    marcador_esperado = f"{max_idx[0]} - {max_idx[1]}"

    return {
        "xg_local": round(lambda_home, 2),
        "xg_visita": round(lambda_away, 2),
        "total_proyectado": round(lambda_home + lambda_away, 2),
        "marcador_mas_probable": marcador_esperado,
        "prob_marcador_mas_probable": round(float(grid[max_idx]), 3),
        # Moneyline
        "prob_local": round(p_home_win, 4),
        "prob_empate": round(p_draw, 4),
        "prob_visita": round(p_away_win, 4),
        # Totales
        "linea_total": linea_total,
        "prob_over": round(p_over, 4),
        "prob_under": round(p_under, 4),
        "prob_push_total": round(p_push, 4),
    }


def cargar_perfiles_recientes_equipos_ligamx(ruta_partidos: Path | str = RUTA_DATA / "partidos.csv") -> Dict[str, Dict[str, float]]:
    """Extrae el perfil rodante más reciente de cada franquicia de la Liga MX."""
    df_partidos = pd.read_csv(ruta_partidos)
    data = construir_features_historicas(df_partidos)

    perfiles = {}
    todos_equipos = set(data["local"].unique()).union(set(data["visitante"].unique()))

    for eq in todos_equipos:
        matches = data[(data["local"] == eq) | (data["visitante"] == eq)].sort_values("fecha")
        if matches.empty:
            continue
        last = matches.iloc[-1]
        is_home = (last["local"] == eq)

        perfiles[eq] = {
            "gf_local_5": float(last["gf_local_5"] if is_home else last["gf_visitante_5"]),
            "gc_local_5": float(last["gc_local_5"] if is_home else last["gc_visitante_5"]),
            "gf_visitante_5": float(last["gf_visitante_5"] if not is_home else last["gf_local_5"]),
            "gc_visitante_5": float(last["gc_visitante_5"] if not is_home else last["gc_local_5"]),
            "puntos_local_5": float(last["puntos_local_5"] if is_home else last["puntos_visitante_5"]),
            "puntos_visitante_5": float(last["puntos_visitante_5"] if not is_home else last["puntos_local_5"]),
            "descanso": float(last["descanso_local"] if is_home else last["descanso_visitante"]),
            "ultima_fecha": str(last["fecha"].date()),
        }

    return perfiles


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    bundle = entrenar_modelo_bivariado()
    print("Modelo Bivariado entrenado exitosamente:", bundle["metricas"])
