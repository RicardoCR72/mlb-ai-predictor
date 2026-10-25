"""Entrenamiento del modelo de Totales (Over / Under de Puntos) para la NBA (V2).

Innovaciones V2:
1. Ensamble híbrido: HistGradientBoostingRegressor (65%) + RidgeCV (35%).
2. Shrinkage Bayesiano hacia la línea de mercado de DraftKings (55% mercado, 45% ensamble),
   eliminando la compresión artificial en partidos de ritmo acelerado.
3. Desviación condicional calibrada (sigma = 13.5 pts) en lugar de la varianza residual pura sin anclaje.
4. Filtro Dead Zone (exige |Edge| >= 2.5 pts y P >= 53.5%) para evitar pérdidas por vig.
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
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
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
    """Entrena y valida el ensamble de Over/Under de puntos con split temporal."""
    logger.info("🏀 Iniciando entrenamiento del Ensamble de Totales NBA V2...")

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

    val_hgb = HistGradientBoostingRegressor(
        max_iter=100,
        max_leaf_nodes=20,
        min_samples_leaf=35,
        learning_rate=0.05,
        l2_regularization=2.0,
        random_state=42
    )
    val_hgb.fit(X_train, y_train)

    val_ridge = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20)))
    val_ridge.fit(X_train, y_train)

    preds_val = 0.65 * val_hgb.predict(X_test) + 0.35 * val_ridge.predict(X_test)
    mae_val = mean_absolute_error(y_test, preds_val)
    rmse_val = np.sqrt(np.mean((y_test - preds_val) ** 2))
    r2_val = r2_score(y_test, preds_val)
    media_real = float(y_test.mean())
    media_pred = float(preds_val.mean())

    logger.info("--- MÉTRICAS ENSAMBLE OUT-OF-SAMPLE TOTALES (Temporada 2024-25) ---")
    logger.info(f"MAE Puntos Totales: {mae_val:.2f} pts")
    logger.info(f"RMSE Puntos Totales: {rmse_val:.2f} pts")
    logger.info(f"R²: {r2_val:.4f}")
    logger.info(f"Media Real: {media_real:.2f} pts | Media Proyectada: {media_pred:.2f} pts")

    # 2. Entrenar Modelos de Producción sobre el 100% de los datos
    logger.info("⚡ Entrenando modelos de producción final con el 100% del histórico...")
    prod_hgb = HistGradientBoostingRegressor(
        max_iter=100,
        max_leaf_nodes=20,
        min_samples_leaf=35,
        learning_rate=0.05,
        l2_regularization=2.0,
        random_state=42
    )
    prod_hgb.fit(df[FEATURES_TOTALES], df["TOTAL_PTS"])

    prod_ridge = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20)))
    prod_ridge.fit(df[FEATURES_TOTALES], df["TOTAL_PTS"])

    preds_prod = 0.65 * prod_hgb.predict(df[FEATURES_TOTALES]) + 0.35 * prod_ridge.predict(df[FEATURES_TOTALES])
    residuales = df["TOTAL_PTS"] - preds_prod
    sigma_residual = float(np.std(residuales))
    logger.info(f"Desviación estándar de residuales (sigma): {sigma_residual:.2f} pts")

    bundle = {
        "model": prod_hgb,
        "model_hgb": prod_hgb,
        "model_ridge": prod_ridge,
        "features": FEATURES_TOTALES,
        "sigma_residual": sigma_residual,
        "sigma_condicional": 13.5,
        "peso_hgb": 0.65,
        "peso_ridge": 0.35,
        "metrics_val": {
            "mae": float(mae_val),
            "rmse": float(rmse_val),
            "r2": float(r2_val),
            "media_real": float(media_real),
            "media_pred": float(media_pred),
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
    linea_total: float = 225.0
) -> Dict[str, Any]:
    """Calcula los puntos proyectados con Shrinkage Bayesiano y probabilidades Over/Under."""
    features = bundle.get("features", FEATURES_TOTALES)
    sigma = bundle.get("sigma_condicional", 13.5)

    DEFAULTS_TOTALES = {
        "PACE_PROYECTADO_L10": 100.2, "HOME_PACE_L5": 100.2, "AWAY_PACE_L5": 100.2,
        "HOME_PACE_L10": 100.2, "AWAY_PACE_L10": 100.2,
        "HOME_PTS_L10": 114.5, "AWAY_PTS_L10": 114.5, "HOME_OPP_PTS_L10": 114.5, "AWAY_OPP_PTS_L10": 114.5,
        "HOME_ORTG_L10": 114.5, "AWAY_ORTG_L10": 114.5, "HOME_DRTG_L10": 114.5, "AWAY_DRTG_L10": 114.5,
        "HOME_EFG_PCT_L10": 0.54, "AWAY_EFG_PCT_L10": 0.54,
        "HOME_TOV_PCT_L10": 0.135, "AWAY_TOV_PCT_L10": 0.135,
        "HOME_REST_DAYS": 2.0, "AWAY_REST_DAYS": 2.0,
        "HOME_IS_B2B": 0, "AWAY_IS_B2B": 0
    }

    X = pd.DataFrame([{col: features_dict.get(col) or DEFAULTS_TOTALES.get(col, 0.0) for col in features}])

    if "model_hgb" in bundle and "model_ridge" in bundle:
        pred_hgb = float(bundle["model_hgb"].predict(X)[0])
        pred_ridge = float(bundle["model_ridge"].predict(X)[0])
        w_hgb = bundle.get("peso_hgb", 0.65)
        w_ridge = bundle.get("peso_ridge", 0.35)
        raw_pred = (w_hgb * pred_hgb) + (w_ridge * pred_ridge)
    elif "model_hgb" in bundle:
        raw_pred = float(bundle["model_hgb"].predict(X)[0])
    elif "model" in bundle:
        raw_pred = float(bundle["model"].predict(X)[0])
    else:
        raw_pred = 225.0

    # Shrinkage Bayesiano: 45% Modelo cuantitativo + 55% Línea consensuada del mercado
    if linea_total > 0:
        total_pred = 0.45 * raw_pred + 0.55 * linea_total
    else:
        total_pred = raw_pred

    edge_puntos = total_pred - linea_total

    # P(Under) = Phi((linea - total_pred) / sigma)
    # P(Over) = 1.0 - P(Under)
    z_score = (linea_total - total_pred) / sigma
    prob_under = float(norm.cdf(z_score))
    prob_over = 1.0 - prob_under

    # Dead Zone: Si la diferencia con la línea es menor a 2.5 pts o prob < 53.5%, PASAR
    if edge_puntos >= 2.5 and prob_over >= 0.535:
        recom = "OVER"
    elif edge_puntos <= -2.5 and prob_under >= 0.535:
        recom = "UNDER"
    else:
        recom = "PASAR"

    return {
        "total_proyectado": round(total_pred, 1),
        "total_raw_modelo": round(raw_pred, 1),
        "linea_mercado": linea_total,
        "edge_puntos": round(edge_puntos, 1),
        "prob_over": round(prob_over, 4),
        "prob_under": round(prob_under, 4),
        "recomendacion": recom,
    }


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    bundle = entrenar_modelo_totales()
    m = bundle["metrics_val"]
    print("\n✅ Resumen de Entrenamiento del Ensamble de Totales NBA V2:")
    print(f"Error Medio Absoluto (MAE): {m['mae']:.2f} puntos")
    print(f"RMSE: {m['rmse']:.2f} puntos")
    print(f"R²: {m['r2']:.4f}")
    print(f"Calibración Media Real vs Predicha: {m['media_real']:.2f} vs {m['media_pred']:.2f} pts")
