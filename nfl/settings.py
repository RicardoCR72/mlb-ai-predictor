"""Configuración NFL sin importar entrenadores ni modelos."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TEMPORADA_ACTUAL = 2026
RUTA_CALENDARIO = ROOT / 'data/nfl/raw/nfl_schedules_2012_2026.parquet'
TOTAL_MODEL_VERSION = 'totales_v2_seleccion_automatica'
PROPS_MODEL_VERSION = 'props_nfl_v2'
