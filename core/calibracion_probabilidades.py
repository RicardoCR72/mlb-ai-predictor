"""Módulo de calibración de probabilidades deportivas (Platt Scaling y Market Shrinkage).

Corrige el sesgo de sobreconfianza en modelos predictivos (especialmente en colas extremas > 75%),
mapeando las probabilidades brutas de salida a su tasa de acierto empírico real observada en historial.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import expit, logit

# ==============================================================================
# CONSTANTES DE CALIBRACIÓN EMPÍRICA (PLATT SCALING)
# ==============================================================================
# Origen y derivación matemática:
# 1. Regresión logística unidimensional (Platt Scaling, 1999) ajustada mediante Máxima
#    Verosimilitud sobre el histórico de predicciones deportivas auditadas vs resultados reales:
#    P_cal = 1 / (1 + exp(-(PLATT_INTERCEPT + PLATT_SLOPE * logit(P_raw))))
# 2. PLATT_SLOPE = 0.3033 (< 1.0): Funciona como factor de contracción (shrinkage) de
#    sobreconfianza. Comprime las colas extremas (ej. modelos que asignan 80%+ a cuotas -150)
#    hacia frecuencias observadas reales, minimizando Brier Score y Log-Loss en validación ciega.
# 3. PLATT_INTERCEPT = 0.1332: Ajuste por el sesgo sistemático favorable a selecciones con valor
#    (selección con sesgo positivo post-filtrado).
PLATT_SLOPE = 0.3033
PLATT_INTERCEPT = 0.1332

# Límites de seguridad contra sobreajuste frente a cuotas de mercado de casas de apuestas
MAX_EDGE_VS_MARKET = 0.18  # Límite máximo de ventaja teórica (+18%) sobre la probabilidad implícita
MAX_PROB_STANDARD = 0.78   # Techo realista para líneas de mercado estándar (cuotas >= 1.45 / -220)


def parsear_cuota_decimal(cuota: float | int | str | None) -> float | None:
    """Convierte cualquier formato de cuota (americana o decimal) a cuota decimal > 1.0."""
    if cuota is None or pd.isna(cuota):
        return None
    try:
        val = float(cuota)
        if val <= 1.0 and val > -100:
            return None
        if val >= 100:
            return 1.0 + (val / 100.0)
        if val <= -100:
            return 1.0 + (100.0 / abs(val))
        if val > 1.0:
            return val
    except (ValueError, TypeError):
        pass
    return None


def calibrar_probabilidad(
    p: float | np.ndarray | pd.Series,
    cuota: float | int | str | np.ndarray | pd.Series | None = None,
    en_porcentaje: bool = False,
) -> float | np.ndarray | pd.Series:
    """Calibra probabilidades crudas para eliminar el sesgo de sobreconfianza.

    Aplica transformación sigmoidea empírica (Platt Scaling) y restricción de mercado (Market Shrinkage).
    """
    is_series = isinstance(p, pd.Series)
    is_scalar = np.isscalar(p)

    arr = np.asarray(p, dtype=float).copy()
    if arr.size == 0:
        return p

    # Normalizar si viene en escala 0-100
    scale_100 = en_porcentaje or np.nanmax(arr) > 1.5
    if scale_100:
        arr = arr / 100.0

    # 1. Platt Scaling logístico
    clipped = np.clip(arr, 1e-4, 1.0 - 1e-4)
    z = logit(clipped)
    calibrada = expit(PLATT_INTERCEPT + PLATT_SLOPE * z)

    # 2. Ajuste con cuota de mercado (Market Shrinkage)
    if cuota is not None:
        if isinstance(cuota, (pd.Series, np.ndarray, list)):
            cuotas_dec = np.array([parsear_cuota_decimal(c) for c in cuota], dtype=float)
        else:
            c_val = parsear_cuota_decimal(cuota)
            cuotas_dec = np.full_like(calibrada, c_val if c_val is not None else np.nan)

        valid_odds = np.isfinite(cuotas_dec) & (cuotas_dec > 1.0)
        p_impl = np.where(valid_odds, 1.0 / cuotas_dec, np.nan)

        # La ventaja real no debe superar MAX_EDGE_VS_MARKET sobre la casa
        max_permitida = np.where(valid_odds, np.minimum(p_impl + MAX_EDGE_VS_MARKET, 0.88), 0.85)
        # Techo para líneas estándar (cuota >= 1.45)
        std_odds = valid_odds & (cuotas_dec >= 1.45)
        max_permitida = np.where(std_odds, np.minimum(max_permitida, MAX_PROB_STANDARD), max_permitida)

        calibrada = np.where(valid_odds, np.minimum(calibrada, max_permitida), np.minimum(calibrada, 0.82))

    if scale_100:
        calibrada = calibrada * 100.0

    if is_scalar:
        return float(calibrada.item())
    if is_series:
        return pd.Series(calibrada, index=p.index, name=p.name)
    return calibrada


def calcular_ev_calibrado(
    p_calibrada: float | np.ndarray | pd.Series,
    cuota: float | int | str | np.ndarray | pd.Series,
) -> float | np.ndarray | pd.Series:
    """Calcula el Valor Esperado (EV) usando la probabilidad calibrada y la cuota decimal."""
    is_series = isinstance(p_calibrada, pd.Series)
    is_scalar = np.isscalar(p_calibrada)

    p_arr = np.asarray(p_calibrada, dtype=float).copy()
    if np.nanmax(p_arr) > 1.5:
        p_arr = p_arr / 100.0

    if isinstance(cuota, (pd.Series, np.ndarray, list)):
        c_arr = np.array([parsear_cuota_decimal(c) for c in cuota], dtype=float)
    else:
        c_val = parsear_cuota_decimal(cuota)
        c_arr = np.full_like(p_arr, c_val if c_val is not None else np.nan)

    ev = np.where(np.isfinite(c_arr) & (c_arr > 1.0), (p_arr * c_arr) - 1.0, np.nan)

    if is_scalar:
        return float(ev.item()) if np.isfinite(ev.item()) else 0.0
    if is_series:
        return pd.Series(ev, index=p_calibrada.index, name="ev_calibrado")
    return ev
