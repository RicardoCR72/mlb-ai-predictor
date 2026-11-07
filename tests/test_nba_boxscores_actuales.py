"""Tests para la sincronización de boxscores oficiales de la temporada actual NBA."""
import pandas as pd
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RUTA_PROCESSED = RAIZ / "data" / "nba" / "processed" / "dataset_partidos_nba.parquet"
RUTA_RAW = RAIZ / "data" / "nba" / "raw" / "partidos_historicos_nba.parquet"


def test_dataset_incluye_temporada_actual():
    """Valida que los datasets raw y processed contengan la temporada 2026-27."""
    assert RUTA_RAW.exists()
    assert RUTA_PROCESSED.exists()

    df_raw = pd.read_parquet(RUTA_RAW)
    seasons_raw = set(df_raw["SEASON"].unique())
    assert "2026-27" in seasons_raw

    df_proc = pd.read_parquet(RUTA_PROCESSED)
    seasons_proc = set(df_proc["SEASON"].unique())
    assert "2026-27" in seasons_proc

    # Debe contener más de 100 partidos oficiales de 2026-27
    partidos_2026 = df_proc[df_proc["SEASON"] == "2026-27"]
    assert len(partidos_2026) >= 100


def test_perfiles_recientes_usan_partidos_2026():
    """Valida que los perfiles de equipo utilicen juegos de noviembre de 2026."""
    from nba.predecir_hoy import cargar_perfiles_recientes_equipos
    perfiles = cargar_perfiles_recientes_equipos()
    assert len(perfiles) == 30

    # Al menos el 80% de los equipos deben tener juegos con fecha en 2026
    equipos_con_2026 = sum(1 for p in perfiles.values() if "2026-" in str(p.get("LAST_DATE", "")))
    assert equipos_con_2026 >= 25
