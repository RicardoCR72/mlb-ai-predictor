"""Módulo de Inteligencia Artificial y Analítica Predictiva para la NBA."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RUTA_NBA = RAIZ / "nba"
RUTA_DATA_NBA = RAIZ / "data" / "nba"
RUTA_MODELOS_NBA = RAIZ / "modelos_nba"

for p in [
    RUTA_DATA_NBA / "raw",
    RUTA_DATA_NBA / "processed",
    RUTA_DATA_NBA / "predictions",
    RUTA_DATA_NBA / "cache",
    RUTA_MODELOS_NBA,
]:
    p.mkdir(parents=True, exist_ok=True)
