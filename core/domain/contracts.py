"""Contratos explícitos en los límites de datos del proyecto."""
from dataclasses import dataclass
from datetime import datetime
import math
import pandas as pd


def probabilities(values, *, scale):
    if scale not in (1, 100):
        raise ValueError('La escala debe ser 1 o 100.')
    result = pd.to_numeric(values, errors='coerce') / scale
    return result.where(result.between(0, 1))


@dataclass(frozen=True)
class Prediction:
    game_id: str
    market: str
    selection: str
    probability: float
    model: str
    start_utc: datetime
    generated_utc: datetime
    provider: str
    line: float | None = None
    decimal_odds: float | None = None
    captured_utc: datetime | None = None

    def __post_init__(self):
        if not all((self.game_id, self.market, self.selection, self.model, self.provider)):
            raise ValueError('Pronóstico sin identidad, modelo o proveedor.')
        if not math.isfinite(self.probability) or not 0 <= self.probability <= 1:
            raise ValueError('Probabilidad fuera de 0–1.')
        for value in (self.start_utc, self.generated_utc, self.captured_utc):
            if value is not None and (value.tzinfo is None or value.utcoffset().total_seconds() != 0):
                raise ValueError('Los instantes del contrato deben estar en UTC.')
        if self.generated_utc >= self.start_utc:
            raise ValueError('No se permiten nuevos pronósticos prepartido después del inicio.')
        if self.captured_utc is not None and self.captured_utc > self.generated_utc:
            raise ValueError('La captura no puede ser posterior al pronóstico.')
        if self.decimal_odds is not None and (not math.isfinite(self.decimal_odds) or self.decimal_odds <= 1):
            raise ValueError('Cuota decimal inválida.')


def require_columns(frame, columns, *, source):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f'{source}: faltan columnas {", ".join(sorted(missing))}')
    return frame
