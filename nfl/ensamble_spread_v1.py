"""Definición del Ensamble Híbrido NFL Spread (ATS) V1.

Combina:
1. Regresión Logística L2 regularizada (C=0.012) para capturar el valor marginal de mercado y números clave.
2. HistGradientBoostingClassifier para capturar interacciones no lineales entre presiones en trincheras,
   salud de la línea ofensiva (OL) y diferenciales de EPA rodante.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _cuota_a_decimal_y_str(odds: float | str | None, fallback_str: str = "-110", fallback_dec: float = 1.9091) -> tuple[float, str]:
    """Convierte un momio americano o decimal a (decimal, texto_americano)."""
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return fallback_dec, fallback_str
    try:
        s = str(odds).strip()
        if not s:
            return fallback_dec, fallback_str
        num = float(s.replace("+", ""))
        if num == 0:
            return fallback_dec, fallback_str
        if abs(num) >= 100:
            dec = 1.0 + (num / 100.0) if num > 0 else 1.0 + (100.0 / abs(num))
            txt = f"+{int(num)}" if num > 0 else f"{int(num)}"
            return round(dec, 4), txt
        if num > 1.0:
            return round(num, 4), s
    except (ValueError, TypeError):
        pass
    return fallback_dec, fallback_str


class EnsambleSpreadNFLv1:
    """Ensamble calibrado para predicción de cobertura de línea de hándicap (Spread / ATS) en la NFL."""

    def __init__(
        self,
        modelo_lr: any,
        modelo_hgb: any,
        features: list[str],
        peso_lr: float = 0.80,
        peso_hgb: float = 0.20,
        umbral_edge: float = 0.530,
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
        odds_home: float | str | None = None,
        odds_away: float | str | None = None,
    ) -> dict[str, any]:
        """Evalúa un partido individual y entrega diagnóstico con EV real y recomendación."""
        df_row = pd.DataFrame([features_dict])
        probs = self.predict_proba(df_row)[0]
        p_away, p_home = float(probs[0]), float(probs[1])

        dec_home, str_home = _cuota_a_decimal_y_str(odds_home)
        dec_away, str_away = _cuota_a_decimal_y_str(odds_away)

        ev_home = (p_home * dec_home) - 1.0
        ev_away = (p_away * dec_away) - 1.0
        bep_home = 1.0 / dec_home
        bep_away = 1.0 / dec_away

        califica_home = (p_home >= self.umbral_edge) and (ev_home > 0.0)
        califica_away = (p_away >= self.umbral_edge) and (ev_away > 0.0)

        if califica_home and (not califica_away or ev_home >= ev_away):
            pick = home_team
            lado = "HOME"
            prob_sel = p_home
            edge = p_home - bep_home
            linea_pick = -spread_line if spread_line > 0 else abs(spread_line)
            rol = "Favorito" if spread_line > 0 else "Underdog"
            ev = ev_home
            cuota_pick = str_home
            cuota_pick_dec = dec_home
            recomendar = True
        elif califica_away:
            pick = away_team
            lado = "AWAY"
            prob_sel = p_away
            edge = p_away - bep_away
            linea_pick = spread_line if spread_line > 0 else -abs(spread_line)
            rol = "Underdog" if spread_line > 0 else "Favorito"
            ev = ev_away
            cuota_pick = str_away
            cuota_pick_dec = dec_away
            recomendar = True
        else:
            pick = None
            lado = "PASS"
            prob_sel = max(p_home, p_away)
            bep_best = bep_home if p_home >= p_away else bep_away
            edge = prob_sel - bep_best
            linea_pick = 0.0
            rol = "Neutral"
            ev = 0.0
            cuota_pick = str_home if p_home >= p_away else str_away
            cuota_pick_dec = dec_home if p_home >= p_away else dec_away
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
            "cuota_pick": cuota_pick,
            "cuota_pick_dec": round(cuota_pick_dec, 4),
        }
