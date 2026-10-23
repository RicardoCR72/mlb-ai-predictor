"""Entrenamiento y calibración del modelo de Moneyline para la NFL.

Predice la probabilidad de victoria del equipo local (home_win)
utilizando características avanzadas previas al encuentro y cuotas de mercado.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, accuracy_score

RAIZ = Path(__file__).resolve().parents[1]
RUTA_DATASET = RAIZ / "data" / "nfl" / "processed" / "nfl_games_features_2012_2026.parquet"
RUTA_MODELO = RAIZ / "modelos_nfl" / "modelo_moneyline_nfl.joblib"
RUTA_METADATA = RAIZ / "modelos_nfl" / "metadata_moneyline_nfl.json"

FEATURES_MONEYLINE = [
    "spread_line",
    "diff_margin_avg_8",
    "diff_points_for_avg_8",
    "diff_points_against_avg_8",
    "diff_win_pct_8",
    "diff_rest",
    "diff_injury_severity",
    "home_qb_change",
    "away_qb_change",
    "home_margin_avg_4",
    "away_margin_avg_4",
    "home_points_for_avg_season",
    "away_points_for_avg_season",
    "home_win_pct_season",
    "away_win_pct_season",
]


def entrenar_modelo_moneyline():
    if not RUTA_DATASET.exists():
        raise FileNotFoundError(f"No se encontró el dataset en {RUTA_DATASET}")

    df = pd.read_parquet(RUTA_DATASET)
    df = df.dropna(subset=["home_win", "spread_line"]).sort_values(["season", "week"]).reset_index(drop=True)

    print(f"🏈 Partidos históricos disponibles con etiqueta: {len(df):,}")

    X = df[FEATURES_MONEYLINE].fillna(0).copy()
    y = df["home_win"].astype(int)

    # Validación temporal (Train < 2024, Test >= 2024)
    train_mask = df["season"] < 2024
    test_mask = df["season"] >= 2024

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    print(f"📊 Train set: {len(X_train)} partidos | Test set: {len(X_test)} partidos")

    base_estimator = LogisticRegression(C=0.15, max_iter=1000, random_state=42)
    calibrador = CalibratedClassifierCV(estimator=base_estimator, method="sigmoid", cv=5)
    calibrador.fit(X_train, y_train)

    probs_test = calibrador.predict_proba(X_test)[:, 1]
    preds_test = (probs_test >= 0.50).astype(int)

    auc = roc_auc_score(y_test, probs_test)
    brier = brier_score_loss(y_test, probs_test)
    ll = log_loss(y_test, probs_test)
    acc = accuracy_score(y_test, preds_test)

    print("\n" + "=" * 60)
    print("📈 MÉTRICAS DE VALIDACIÓN OUT-OF-SAMPLE (2024 - 2026):")
    print(f"   * ROC-AUC:    {auc:.4f}")
    print(f"   * Exactitud:  {acc*100:.2f}%")
    print(f"   * Brier Score:{brier:.4f}")
    print(f"   * Log-Loss:   {ll:.4f}")
    print("=" * 60)

    # Entrenar modelo final con todo el histórico disponible para máxima precisión actual
    modelo_final = CalibratedClassifierCV(estimator=LogisticRegression(C=0.15, max_iter=1000, random_state=42), method="sigmoid", cv=5)
    modelo_final.fit(X, y)

    bundle = {
        "modelo": modelo_final,
        "features": FEATURES_MONEYLINE,
        "metricas": {
            "auc": round(float(auc), 4),
            "accuracy": round(float(acc), 4),
            "brier": round(float(brier), 4),
            "log_loss": round(float(ll), 4),
            "n_partidos_historicos": len(df),
        },
    }

    RUTA_MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, RUTA_MODELO)
    print(f"\n💾 Modelo guardado exitosamente en: {RUTA_MODELO}")

    metadata = {
        "modelo_version": "nfl_moneyline_calibrado_v1",
        "fecha_entrenamiento": pd.Timestamp.now().isoformat(),
        "features": FEATURES_MONEYLINE,
        "metricas_out_of_sample": bundle["metricas"],
    }
    with open(RUTA_METADATA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return bundle


if __name__ == "__main__":
    entrenar_modelo_moneyline()
