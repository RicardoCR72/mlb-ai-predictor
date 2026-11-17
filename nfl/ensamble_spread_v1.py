"""Definición del Ensamble Híbrido NFL Spread (ATS) V1.

Combina:
1. Regresión Logística L2 regularizada (C=0.012) para capturar el valor marginal de mercado y números clave.
2. HistGradientBoostingClassifier para capturar interacciones no lineales entre presiones en trincheras,
   salud de la línea ofensiva (OL) y diferenciales de EPA rodante.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class EnsambleSpreadNFLv1:
    """Ensamble calibrado para predicción de cobertura de línea de hándicap (Spread / ATS) en la NFL."""

    def __init__(
        self,
        modelo_lr: any,
        modelo_hgb: any,
        features: list[str],
        peso_lr: float = 0.80,
        peso_hgb: float = 0.20,
        umbral_edge: float = 0.520,
        version: str = "v1_spread_ats_hybrid",
    ):
        self.modelo_lr = modelo_lr
        self.modelo_hgb = modelo_hgb
        self.features = features
        self.peso_lr = peso_lr
        self.peso_hgb = peso_hgb
        self.umbral_edge = umbral_edge
        self.version = version

    def _preparar_features(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        if isinstance(X, pd.DataFrame):
            cols_disponibles = [c for c in self.features if c in X.columns]
            X_eval = X[cols_disponibles].fillna(0).copy()
            if len(cols_disponibles) < len(self.features):
                for c in self.features:
                    if c not in X_eval.columns:
                        X_eval[c] = 0.0
                X_eval = X_eval[self.features]
            return X_eval.values
        return np.nan_to_num(X, 0.0)

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Calcula la probabilidad de cubrir el spread [P(Away cubre), P(Home cubre)].
        
        Nota de convención NFL:
        - Si spread_line = -3.5 (Home favorito por 3.5), Home cubre si gana por 4 o más.
        - Si spread_line = +4.0 (Home underdog por 4.0), Home cubre si pierde por 3 o menos, o gana.
        """
        X_mat = self._preparar_features(X)

        p_lr = self.modelo_lr.predict_proba(X_mat)[:, 1]
        p_hgb = self.modelo_hgb.predict_proba(X_mat)[:, 1]

        # Ponderación calibrada out-of-sample
        p_home_cover = self.peso_lr * p_lr + self.peso_hgb * p_hgb
        p_home_cover = np.clip(p_home_cover, 0.05, 0.95)
        p_away_cover = 1.0 - p_home_cover

        return np.column_stack([p_away_cover, p_home_cover])

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Devuelve 1 si P(Home cubre) >= 0.50, 0 si Away cubre."""
        probs = self.predict_proba(X)[:, 1]
        return (probs >= 0.50).astype(int)

    def evaluar_partido(
        self,
        features_dict: dict[str, float],
        spread_line: float,
        home_team: str,
        away_team: str,
    ) -> dict[str, any]:
        """Evalúa un partido individual y entrega diagnóstico con EV y recomendación."""
        df_row = pd.DataFrame([features_dict])
        probs = self.predict_proba(df_row)[0]
        p_away, p_home = float(probs[0]), float(probs[1])

        # Selección según ventaja estadística
        # Cuota estándar -110 requiere 52.38% para punto de equilibrio (BEP)
        BEP = 0.5238

        if p_home >= self.umbral_edge:
            pick = home_team
            lado = "HOME"
            prob_sel = p_home
            edge = p_home - BEP
            # Línea de spread del pick:
            # Si Home es favorito (spread_line > 0), el spread del mercado suele anotarse -spread_line
            # En la convención nflverse: spread_line = 3.5 significa Home fav por 3.5 (-3.5 en casas)
            linea_pick = -spread_line if spread_line > 0 else abs(spread_line)
            rol = "Favorito" if spread_line > 0 else "Underdog"
            ev = (p_home * 1.9091) - 1.0
            recomendar = True
        elif p_away >= self.umbral_edge:
            pick = away_team
            lado = "AWAY"
            prob_sel = p_away
            edge = p_away - BEP
            linea_pick = spread_line if spread_line > 0 else -abs(spread_line)
            rol = "Underdog" if spread_line > 0 else "Favorito"
            ev = (p_away * 1.9091) - 1.0
            recomendar = True
        else:
            pick = None
            lado = "PASS"
            prob_sel = max(p_home, p_away)
            edge = prob_sel - BEP
            linea_pick = 0.0
            rol = "Neutral"
            ev = 0.0
            recomendar = False

        return {
            "home_team": home_team,
            "away_team": away_team,
            "spread_line_raw": spread_line,
            "p_home_cover": round(p_home, 4),
            "p_away_cover": round(p_away, 4),
            "recomendar": recomendar,
            "pick": pick,
            "lado": lado,
            "rol": rol,
            "linea_pick": linea_pick,
            "prob_seleccion": round(prob_sel, 4),
            "edge_vs_bep": round(edge * 100, 2),
            "ev_esperado_pct": round(ev * 100, 2),
        }
