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
    """Ejecuta el pipeline de entrenamiento oficial V2 (Ensamble EPA + LightGBM + Logistic Regression)."""
    from nfl.entrenar_moneyline_v2 import entrenar_modelo_moneyline_v2
    return entrenar_modelo_moneyline_v2()


if __name__ == "__main__":
    entrenar_modelo_moneyline()

