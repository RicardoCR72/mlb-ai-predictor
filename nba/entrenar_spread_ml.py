"""Entrenamiento del modelo de Spread (Margen de Victoria) y Moneyline para la NBA.

Utiliza HistGradientBoostingRegressor (equivalente C-optimizado de LightGBM) para estimar:
1. Margen de victoria esperado del equipo local (MARGIN_HOME).
2. Probabilidad de victoria de cada franquicia mediante distribución Normal ajustada a los residuales.
3. Probabilidad de cubrir cualquier línea de Spread (Hándicap).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

RUTA_DATASET = RAIZ / "data" / "nba" / "processed" / "dataset_partidos_nba.parquet"
RUTA_MODELOS = RAIZ / "modelos_nba"
RUTA_MODELOS.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Features predictivas seleccionadas basadas en Basketball Analytics
FEATURES_SPREAD = [
    # Diferenciales clave (Matchup Differentials)
    "DIFF_NET_RTG_L5", "DIFF_NET_RTG_L10", "DIFF_NET_RTG_L20",
    "DIFF_ORTG_L10", "DIFF_DRTG_L10", "DIFF_EFG_L10", "DIFF_WIN_L10",
    "DIFF_REST",
    # Ventana L10 de cada equipo
    "HOME_NET_RTG_L10", "AWAY_NET_RTG_L10",
    "HOME_ORTG_L10", "AWAY_ORTG_L10",
    "HOME_DRTG_L10", "AWAY_DRTG_L10",
    "HOME_EFG_PCT_L10", "AWAY_EFG_PCT_L10",
    "HOME_WIN_L10", "AWAY_WIN_L10",
    # Fatiga y descanso
    "HOME_REST_DAYS", "AWAY_REST_DAYS",
    "HOME_IS_B2B", "AWAY_IS_B2B",
    # Enfrentamiento directo proyectado
    "OFF_VS_DEF_HOME", "OFF_VS_DEF_AWAY"
]


def entrenar_modelo_spread() -> Dict[str, Any]:
    """Entrena y valida el modelo de Spread y Moneyline con split temporal estricto."""
    logger.info("🏀 Iniciando entrenamiento del Modelo de Spread & Moneyline NBA...")
    
    if not RUTA_DATASET.exists():
        raise FileNotFoundError(f"No existe el dataset procesado en {RUTA_DATASET}. Ejecuta nba/construir_dataset.py primero.")

    df = pd.read_parquet(RUTA_DATASET)
    logger.info(f"Dataset cargado con {len(df):,} partidos.")

    # 1. Validación Temporal Out-of-Sample (Entrenamiento: < 2024-25, Validación: 2024-25)
    train_mask = df["SEASON"] < "2024-25"
    test_mask = df["SEASON"] == "2024-25"

    X_train = df.loc[train_mask, FEATURES_SPREAD]
    y_train = df.loc[train_mask, "MARGIN_HOME"]
    X_test = df.loc[test_mask, FEATURES_SPREAD]
    y_test = df.loc[test_mask, "MARGIN_HOME"]

    logger.info(f"Partidos de entrenamiento: {len(X_train):,} | Partidos de prueba (2024-25): {len(X_test):,}")

    # Modelo con regularización L2 para evitar sobreajuste en varianza alta de la NBA
    val_model = HistGradientBoostingRegressor(
        max_iter=120,
        max_leaf_nodes=24,
        min_samples_leaf=30,
        learning_rate=0.06,
        l2_regularization=1.8,
        random_state=42
    )
    val_model.fit(X_train, y_train)

    # Evaluación Out-of-Sample
    preds_val = val_model.predict(X_test)
    mae_val = mean_absolute_error(y_test, preds_val)
    rmse_val = np.sqrt(np.mean((y_test - preds_val) ** 2))
    r2_val = r2_score(y_test, preds_val)
    
    # Acierto en ganador directo (Moneyline)
    acc_win = np.mean((preds_val > 0) == (y_test > 0))

    logger.info("--- MÉTRICAS OUT-OF-SAMPLE (Temporada 2024-25) ---")
    logger.info(f"MAE Margen: {mae_val:.2f} pts")
    logger.info(f"RMSE Margen: {rmse_val:.2f} pts")
    logger.info(f"R² Margen: {r2_val:.4f}")
    logger.info(f"Precisión Ganador Directo (Moneyline): {acc_win * 100:.2f}%")

    # 2. Entrenar Modelo de Producción sobre el 100% de los datos
    logger.info("⚡ Entrenando modelo de producción final con el 100% del histórico...")
    prod_model = HistGradientBoostingRegressor(
        max_iter=120,
        max_leaf_nodes=24,
        min_samples_leaf=30,
        learning_rate=0.06,
        l2_regularization=1.8,
        random_state=42
    )
    prod_model.fit(df[FEATURES_SPREAD], df["MARGIN_HOME"])

    # Calcular la desviación estándar de los residuales (sigma) para derivar probabilidades normales
    residuales = df["MARGIN_HOME"] - prod_model.predict(df[FEATURES_SPREAD])
    sigma_residual = float(np.std(residuales))
    logger.info(f"Desviación estándar de residuales (sigma): {sigma_residual:.2f} pts")

    # Guardar bundle completo
    bundle = {
        "model": prod_model,
        "features": FEATURES_SPREAD,
        "sigma_residual": sigma_residual,
        "metrics_val": {
            "mae": float(mae_val),
            "rmse": float(rmse_val),
            "r2": float(r2_val),
            "win_accuracy": float(acc_win),
            "test_season": "2024-25",
            "test_samples": int(len(X_test)),
        },
        "fecha_entrenamiento": datetime.now().isoformat(),
        "total_partidos_entrenamiento": int(len(df)),
    }

    ruta_joblib = RUTA_MODELOS / "modelo_spread_ml.joblib"
    joblib.dump(bundle, ruta_joblib)
    logger.info(f"💾 Modelo guardado en {ruta_joblib}")

    # Guardar reporte de métricas en JSON
    ruta_json = RUTA_MODELOS / "metricas_spread_ml.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(bundle["metrics_val"], f, indent=2)
    logger.info(f"💾 Reporte guardado en {ruta_json}")

    return bundle


def proyectar_partido_spread(
    bundle: Dict[str, Any],
    features_dict: Dict[str, float],
    spread_line: float = 0.0
) -> Dict[str, Any]:
    """Calcula el margen esperado y las probabilidades de cubrir el spread y ganar Moneyline."""
    model = bundle["model"]
    features = bundle["features"]
    sigma = bundle["sigma_residual"]

    # Crear vector de entrada en el orden exacto de features
    X = pd.DataFrame([{col: features_dict.get(col, 0.0) for col in features}])
    margen_pred = float(model.predict(X)[0])

    # Probabilidad de que el local gane el partido (margen > 0)
    # P(Home Win) = Phi(margen / sigma)
    prob_home_win = float(norm.cdf(margen_pred / sigma))
    prob_away_win = 1.0 - prob_home_win

    # Probabilidad de cubrir el spread
    # Si la línea es BOS -6.5 (spread_line = -6.5 para el local), el local cubre si MARGIN_HOME > 6.5
    prob_cover_home = float(norm.cdf((margen_pred + spread_line) / sigma))
    prob_cover_away = 1.0 - prob_cover_home

    return {
        "margen_local_esperado": round(margen_pred, 2),
        "prob_local_win": round(prob_home_win, 4),
        "prob_visita_win": round(prob_away_win, 4),
        "prob_cover_home": round(prob_cover_home, 4),
        "prob_cover_away": round(prob_cover_away, 4),
    }


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    bundle = entrenar_modelo_spread()
    m = bundle["metrics_val"]
    print("\n✅ Resumen de Entrenamiento del Modelo de Spread & Moneyline:")
    print(f"Precisión Out-of-Sample: {m['win_accuracy'] * 100:.2f}%")
    print(f"Error Medio Absoluto (MAE): {m['mae']:.2f} puntos")
    print(f"RMSE: {m['rmse']:.2f} puntos")
    print(f"Sigma de incertidumbre residual: {bundle['sigma_residual']:.2f} pts")
