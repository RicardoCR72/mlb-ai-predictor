"""Entrenamiento del modelo de Totales (Over / Under de Puntos) para la NBA.

Utiliza HistGradientBoostingRegressor para predecir los puntos totales combinados (TOTAL_PTS)
a partir del ritmo (Pace) y la eficiencia combinada de ambos equipos.
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

# Features clave para proyectar puntos totales en la NBA
FEATURES_TOTALES = [
    # Ritmo (Pace) de ambos equipos
    "PACE_PROYECTADO_L10", "HOME_PACE_L5", "AWAY_PACE_L5", "HOME_PACE_L10", "AWAY_PACE_L10",
    # Puntos anotados y permitidos
    "HOME_PTS_L10", "AWAY_PTS_L10", "HOME_OPP_PTS_L10", "AWAY_OPP_PTS_L10",
    # Eficiencia ofensiva y defensiva (Ratings)
    "HOME_ORTG_L10", "AWAY_ORTG_L10", "HOME_DRTG_L10", "AWAY_DRTG_L10",
    # Tiro y Pérdidas (Four Factors)
    "HOME_EFG_PCT_L10", "AWAY_EFG_PCT_L10", "HOME_TOV_PCT_L10", "AWAY_TOV_PCT_L10",
    # Fatiga y descanso
    "HOME_REST_DAYS", "AWAY_REST_DAYS", "HOME_IS_B2B", "AWAY_IS_B2B"
]


def entrenar_modelo_totales() -> Dict[str, Any]:
    """Entrena y valida el modelo de Over/Under de puntos con split temporal."""
    logger.info("🏀 Iniciando entrenamiento del Modelo de Totales (Over/Under) NBA...")

    if not RUTA_DATASET.exists():
        raise FileNotFoundError(f"No existe el dataset procesado en {RUTA_DATASET}. Ejecuta nba/construir_dataset.py primero.")

    df = pd.read_parquet(RUTA_DATASET)
    logger.info(f"Dataset cargado con {len(df):,} partidos.")

    # 1. Validación Temporal Out-of-Sample (Temporada 2024-25 como test)
    train_mask = df["SEASON"] < "2024-25"
    test_mask = df["SEASON"] == "2024-25"

    X_train = df.loc[train_mask, FEATURES_TOTALES]
    y_train = df.loc[train_mask, "TOTAL_PTS"]
    X_test = df.loc[test_mask, FEATURES_TOTALES]
    y_test = df.loc[test_mask, "TOTAL_PTS"]

    logger.info(f"Partidos de entrenamiento: {len(X_train):,} | Partidos de prueba (2024-25): {len(X_test):,}")

    val_model = HistGradientBoostingRegressor(
        max_iter=100,
        max_leaf_nodes=20,
        min_samples_leaf=35,
        learning_rate=0.05,
        l2_regularization=2.0,
        random_state=42
    )
    val_model.fit(X_train, y_train)

    preds_val = val_model.predict(X_test)
    mae_val = mean_absolute_error(y_test, preds_val)
    rmse_val = np.sqrt(np.mean((y_test - preds_val) ** 2))
    r2_val = r2_score(y_test, preds_val)
    media_real = float(y_test.mean())
    media_pred = float(preds_val.mean())

    logger.info("--- MÉTRICAS OUT-OF-SAMPLE TOTALES (Temporada 2024-25) ---")
    logger.info(f"MAE Puntos Totales: {mae_val:.2f} pts")
    logger.info(f"RMSE Puntos Totales: {rmse_val:.2f} pts")
    logger.info(f"Media Real: {media_real:.2f} pts | Media Proyectada: {media_pred:.2f} pts")

    # 2. Entrenar Modelo de Producción sobre el 100% de los datos
    logger.info("⚡ Entrenando modelo de producción final con el 100% del histórico...")
    prod_model = HistGradientBoostingRegressor(
        max_iter=100,
        max_leaf_nodes=20,
        min_samples_leaf=35,
        learning_rate=0.05,
        l2_regularization=2.0,
        random_state=42
    )
    prod_model.fit(df[FEATURES_TOTALES], df["TOTAL_PTS"])

    residuales = df["TOTAL_PTS"] - prod_model.predict(df[FEATURES_TOTALES])
    sigma_residual = float(np.std(residuales))
    logger.info(f"Desviación estándar de residuales (sigma): {sigma_residual:.2f} pts")

    bundle = {
        "model": prod_model,
        "features": FEATURES_TOTALES,
        "sigma_residual": sigma_residual,
        "metrics_val": {
            "mae": float(mae_val),
            "rmse": float(rmse_val),
            "r2": float(r2_val),
            "media_real": media_real,
            "media_pred": media_pred,
            "test_season": "2024-25",
            "test_samples": int(len(X_test)),
        },
        "fecha_entrenamiento": datetime.now().isoformat(),
        "total_partidos_entrenamiento": int(len(df)),
    }

    ruta_joblib = RUTA_MODELOS / "modelo_totales.joblib"
    joblib.dump(bundle, ruta_joblib)
    logger.info(f"💾 Modelo guardado en {ruta_joblib}")

    ruta_json = RUTA_MODELOS / "metricas_totales.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(bundle["metrics_val"], f, indent=2)
    logger.info(f"💾 Reporte guardado en {ruta_json}")

    return bundle


def proyectar_partido_totales(
    bundle: Dict[str, Any],
    features_dict: Dict[str, float],
    linea_total: float
) -> Dict[str, Any]:
    """Calcula los puntos proyectados y las probabilidades de Over y Under vs la línea de la casa."""
    model = bundle["model"]
    features = bundle["features"]
    sigma = bundle["sigma_residual"]

    X = pd.DataFrame([{col: features_dict.get(col, 0.0) for col in features}])
    total_pred = float(model.predict(X)[0])

    edge_puntos = total_pred - linea_total

    # P(Over) = 1 - Phi((linea - total_pred) / sigma)
    # P(Under) = Phi((linea - total_pred) / sigma)
    z_score = (linea_total - total_pred) / sigma
    prob_under = float(norm.cdf(z_score))
    prob_over = 1.0 - prob_under

    return {
        "total_proyectado": round(total_pred, 1),
        "linea_mercado": linea_total,
        "edge_puntos": round(edge_puntos, 1),
        "prob_over": round(prob_over, 4),
        "prob_under": round(prob_under, 4),
        "recomendacion": "OVER" if edge_puntos > 2.0 and prob_over >= 0.54 else ("UNDER" if edge_puntos < -2.0 and prob_under >= 0.54 else "PASAR")
    }


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    bundle = entrenar_modelo_totales()
    m = bundle["metrics_val"]
    print("\n✅ Resumen de Entrenamiento del Modelo de Totales:")
    print(f"Error Medio Absoluto (MAE): {m['mae']:.2f} puntos")
    print(f"RMSE: {m['rmse']:.2f} puntos")
    print(f"Calibración Media Real vs Predicha: {m['media_real']:.2f} vs {m['media_pred']:.2f} pts")
    print(f"Sigma de incertidumbre residual: {bundle['sigma_residual']:.2f} pts")
