"""Definición del Ensamble Híbrido NFL Moneyline V2.

Combina:
1. Regresión Logística Calibrada con regularización L2 (anclaje al spread y pendiente de mercado).
2. LightGBM Calibrado (interacciones no lineales entre EPA, lesiones posicionales y clima).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class EnsambleMoneylineNFLv2:
    """Ensamble calibrado de dos vías para predicción de ganador directo (Moneyline) NFL."""

    def __init__(
        self,
        modelo_lr: any,
        modelo_lgb: any,
        features: list[str],
        peso_lr: float = 0.65,
        peso_lgb: float = 0.35,
        version: str = "v2_ensemble_epa",
    ):
        self.modelo_lr = modelo_lr
        self.modelo_lgb = modelo_lgb
        self.features = features
        self.peso_lr = peso_lr
        self.peso_lgb = peso_lgb
        self.version = version

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Calcula la probabilidad de victoria [P(Away), P(Home)]."""
        if isinstance(X, pd.DataFrame):
            # Asegurar que las columnas coincidan con las del entrenamiento
            cols_disponibles = [c for c in self.features if c in X.columns]
            X_eval = X[cols_disponibles].fillna(0)
            if len(cols_disponibles) < len(self.features):
                for c in self.features:
                    if c not in X_eval.columns:
                        X_eval[c] = 0.0
                X_eval = X_eval[self.features]
        else:
            X_eval = np.nan_to_num(X, 0.0)

        p_lr = self.modelo_lr.predict_proba(X_eval)[:, 1]
        p_lgb = self.modelo_lgb.predict_proba(X_eval)[:, 1]

        # Fusión ponderada óptima validada out-of-sample
        p_home = self.peso_lr * p_lr + self.peso_lgb * p_lgb
        p_home = np.clip(p_home, 0.02, 0.98)
        p_away = 1.0 - p_home

        return np.column_stack([p_away, p_home])

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Devuelve 1 si P(Home) >= 0.50, 0 en caso contrario."""
        probs = self.predict_proba(X)[:, 1]
        return (probs >= 0.50).astype(int)
