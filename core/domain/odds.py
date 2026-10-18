"""Conversión de cuotas independiente de UI, persistencia y Bankroll."""
import math


def decimal_odds(american):
    value = float(american)
    if not math.isfinite(value) or abs(value) < 100:
        raise ValueError('Cuota americana inválida.')
    return 1 + (value / 100 if value > 0 else 100 / abs(value))
