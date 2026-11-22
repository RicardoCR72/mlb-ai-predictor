"""Módulo Central de CLV (Closing Line Value), Líneas de Cierre y Validación de Vig.

El Closing Line Value (CLV) es la métrica reina para auditar modelos cuantitativos:
1. CLV en Cuota: (Cuota_tomada / Cuota_cierre) - 1.0 (o diferencia de probabilidad implícita).
2. CLV en Línea:
   - Para OVER: Linea_cierre - Linea_tomada (ej. Tomada 2.5, Cierre 3.5 -> CLV = +1.0)
   - Para UNDER: Linea_tomada - Linea_cierre (ej. Tomada 40.5, Cierre 38.5 -> CLV = +2.0)
3. Vig de Mercado: (1 / Cuota_Over) + (1 / Cuota_Under) debe oscilar entre 1.02 y 1.15.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np
import pandas as pd

from core.calibracion_probabilidades import parsear_cuota_decimal

logger = logging.getLogger(__name__)

# Rango estándar de comisión del bookmaker (Vig) en mercados de dos lados
VIG_MIN = 1.02  # Mercados muy líquidos / reducidos (ej. Pinnacle -104/-104)
VIG_MAX = 1.15  # Mercados de props recreativos típicos (-115/-115 a -120/-120)

# Rango de cuotas permitidas para evitar aberraciones estadísticas
CUOTA_DEC_MIN = 1.25
CUOTA_DEC_MAX = 5.00


def calcular_vig(cuota_over: Any, cuota_under: Any) -> Optional[float]:
    """Calcula el vigorish (margen o overround de la casa) en un mercado de 2 lados:
    Vig = (1 / cuota_dec_over) + (1 / cuota_dec_under)
    Ejemplo: -110 / -110 (1.909 / 1.909) -> 0.5238 + 0.5238 = 1.0476 (4.76% de vig).
    """
    c_over = parsear_cuota_decimal(cuota_over)
    c_under = parsear_cuota_decimal(cuota_under)
    if c_over is None or c_under is None or c_over <= 1.0 or c_under <= 1.0:
        return None
    vig = (1.0 / c_over) + (1.0 / c_under)
    return round(float(vig), 4)


def validar_mercado_dos_lados(
    cuota_over: Any,
    cuota_under: Any,
    min_vig: float = VIG_MIN,
    max_vig: float = VIG_MAX,
) -> Tuple[bool, Optional[float], str]:
    """Valida automáticamente si las cuotas provienen de un mercado balanceado de 2 lados.
    Retorna (es_valido, vig, motivo).
    """
    c_over = parsear_cuota_decimal(cuota_over)
    c_under = parsear_cuota_decimal(cuota_under)

    if c_over is None or c_under is None:
        return False, None, "Cuotas inválidas o nulas"

    if c_over < CUOTA_DEC_MIN or c_over > CUOTA_DEC_MAX:
        return False, None, f"Cuota over fuera de rango permitido [{CUOTA_DEC_MIN}, {CUOTA_DEC_MAX}]: {c_over}"

    if c_under < CUOTA_DEC_MIN or c_under > CUOTA_DEC_MAX:
        return False, None, f"Cuota under fuera de rango permitido [{CUOTA_DEC_MIN}, {CUOTA_DEC_MAX}]: {c_under}"

    vig = calcular_vig(c_over, c_under)
    if vig is None:
        return False, None, "No se pudo computar el vig"

    if vig < min_vig:
        return False, vig, f"Vig anormalmente bajo ({vig:.3f} < {min_vig:.2f}): posible arbitraje o error de captura"

    if vig > max_vig:
        return False, vig, f"Vig excesivo ({vig:.3f} > {max_vig:.2f}): mercado sin liquidez o cuotas distorsionadas"

    return True, vig, "Mercado válido"


def calcular_clv_cuota(cuota_tomada: Any, cuota_cierre: Any) -> Optional[float]:
    """Calcula el porcentaje de ventaja de precio frente al cierre del mercado:
    CLV = (Cuota_tomada / Cuota_cierre) - 1.0
    Ejemplo: Tomada 2.10, Cerró 1.90 -> (2.10 / 1.90) - 1 = +10.53% de valor.
    """
    c_t = parsear_cuota_decimal(cuota_tomada)
    c_c = parsear_cuota_decimal(cuota_cierre)
    if c_t is None or c_c is None or c_t <= 1.0 or c_c <= 1.0:
        return None
    clv = (c_t / c_c) - 1.0
    return round(float(clv), 4)


def calcular_clv_probabilidad(cuota_tomada: Any, cuota_cierre: Any) -> Optional[float]:
    """Calcula la diferencia de probabilidad implícita frente al cierre:
    CLV_prob = (1 / Cuota_cierre) - (1 / Cuota_tomada)
    Ejemplo: Tomada a 2.10 (47.6%) y cerró a 1.90 (52.6%) -> +5.0% de probabilidad ganada.
    """
    c_t = parsear_cuota_decimal(cuota_tomada)
    c_c = parsear_cuota_decimal(cuota_cierre)
    if c_t is None or c_c is None or c_t <= 1.0 or c_c <= 1.0:
        return None
    p_t = 1.0 / c_t
    p_c = 1.0 / c_c
    return round(float(p_c - p_t), 4)


def calcular_clv_linea(
    linea_tomada: Union[float, int, None],
    linea_cierre: Union[float, int, None],
    seleccion: str,
) -> Optional[float]:
    """Calcula la ventaja obtenida en la línea del prop o spread:
    - Para OVER / MÁS DE: Linea_cierre - Linea_tomada
      (Si tomaste 2.5 y cerró en 3.5 -> +1.0)
    - Para UNDER / MENOS DE: Linea_tomada - Linea_cierre
      (Si tomaste 40.5 y cerró en 38.5 -> +2.0)
    """
    if linea_tomada is None or linea_cierre is None:
        return None
    try:
        lt = float(linea_tomada)
        lc = float(linea_cierre)
    except (ValueError, TypeError):
        return None

    sel_norm = str(seleccion).upper()
    if "OVER" in sel_norm or "MÁS" in sel_norm or "MAS" in sel_norm:
        return round(lc - lt, 2)
    elif "UNDER" in sel_norm or "MENOS" in sel_norm:
        return round(lt - lc, 2)
    return None


def auditar_balance_diario(picks: list[Dict[str, Any]], umbral_sesgo: float = 0.70) -> Tuple[bool, str, Dict[str, Any]]:
    """Valida la regla de alerta de desbalance diario:
    Alerta si más del 70% de los picks del día van al mismo lado (ej. > 70% overs).
    Retorna (es_balanceado, mensaje, estadisticas).
    """
    if not picks:
        return True, "Sin picks para auditar", {"total": 0, "overs": 0, "unders": 0, "pct_overs": 0.0}

    total = len(picks)
    overs = sum(1 for p in picks if "OVER" in str(p.get("seleccion", "")).upper() or "MÁS" in str(p.get("seleccion", "")).upper() or "MAS" in str(p.get("seleccion", "")).upper())
    unders = sum(1 for p in picks if "UNDER" in str(p.get("seleccion", "")).upper() or "MENOS" in str(p.get("seleccion", "")).upper())

    otros = total - (overs + unders)
    pct_overs = (overs / total) if total > 0 else 0.0
    pct_unders = (unders / total) if total > 0 else 0.0

    stats = {
        "total": total,
        "overs": overs,
        "unders": unders,
        "otros": otros,
        "pct_overs": round(pct_overs, 3),
        "pct_unders": round(pct_unders, 3)
    }

    if total >= 4:
        if pct_overs > umbral_sesgo:
            return False, f"⚠️ ALERTA DE SESGO: {pct_overs*100:.1f}% de las selecciones son OVER (> {umbral_sesgo*100:.0f}% permitido). Riesgo de sobreexposición sistémica.", stats
        if pct_unders > umbral_sesgo:
            return False, f"⚠️ ALERTA DE SESGO: {pct_unders*100:.1f}% de las selecciones son UNDER (> {umbral_sesgo*100:.0f}% permitido). Riesgo de sobreexposición sistémica.", stats

    return True, "Balance equilibrado de selecciones", stats


def calcular_metricas_clv_resumen(df: pd.DataFrame) -> Dict[str, Any]:
    """Genera el reporte ejecutivo de CLV a partir de un DataFrame con histórico de picks."""
    if df.empty or "clv_cuota" not in df.columns:
        return {
            "total_picks": len(df),
            "picks_con_clv": 0,
            "pct_beat_clv": 0.0,
            "clv_cuota_promedio": 0.0,
            "clv_linea_promedio": 0.0,
            "roi_esperado_clv": 0.0
        }

    s_clv = pd.to_numeric(df["clv_cuota"], errors="coerce")
    valid_mask = s_clv.notna() & np.isfinite(s_clv)
    valid_clv = df[valid_mask].copy()
    valid_clv["clv_cuota"] = s_clv[valid_mask]
    n_valid = len(valid_clv)
    if n_valid == 0:
        return {
            "total_picks": len(df),
            "picks_con_clv": 0,
            "picks_con_clv_positivo": 0,
            "pct_beat_clv": 0.0,
            "clv_cuota_promedio": 0.0,
            "clv_linea_promedio": 0.0,
            "roi_esperado_clv": 0.0
        }

    beat_clv = (valid_clv["clv_cuota"] > 0).sum()
    pct_beat = (beat_clv / n_valid) * 100.0
    prom_clv_cuota = float(valid_clv["clv_cuota"].mean() * 100.0)

    # CLV de línea si existe
    prom_clv_linea = 0.0
    if "clv_linea" in valid_clv.columns:
        s_line = pd.to_numeric(valid_clv["clv_linea"], errors="coerce").dropna()
        if not s_line.empty:
            prom_clv_linea = float(s_line.mean())

    return {
        "total_picks": len(df),
        "picks_con_clv": n_valid,
        "picks_con_clv_positivo": int(beat_clv),
        "pct_beat_clv": round(pct_beat, 1),
        "clv_cuota_promedio": round(prom_clv_cuota, 2),
        "clv_linea_promedio": round(prom_clv_linea, 2),
        "roi_esperado_clv": round(prom_clv_cuota, 2)
    }
