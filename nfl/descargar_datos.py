from pathlib import Path

import nflreadpy as nfl


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
DIRECTORIO_RAW = RAIZ_PROYECTO / "data" / "nfl" / "raw"

TEMPORADAS = list(range(2012, 2027))


def descargar_calendario():
    print("Descargando calendario 2012-2026...")

    calendario = nfl.load_schedules(TEMPORADAS).to_pandas()
    ruta = DIRECTORIO_RAW / "nfl_schedules_2012_2026.parquet"

    calendario.to_parquet(ruta, index=False)

    print(f"Calendario guardado: {ruta}")
    print(f"Partidos: {len(calendario):,}")
    print(f"Columnas: {len(calendario.columns)}")

    return calendario


def descargar_jugadores():
    print("\nDescargando estadísticas semanales de jugadores...")

    jugadores = nfl.load_player_stats(
        TEMPORADAS,
        summary_level="week"
    ).to_pandas()

    ruta = DIRECTORIO_RAW / "nfl_player_stats_2012_2026.parquet"
    jugadores.to_parquet(ruta, index=False)

    print(f"Estadísticas guardadas: {ruta}")
    print(f"Registros: {len(jugadores):,}")
    print(f"Columnas: {len(jugadores.columns)}")

    return jugadores


def main():
    DIRECTORIO_RAW.mkdir(parents=True, exist_ok=True)

    calendario = descargar_calendario()
    jugadores = descargar_jugadores()

    print("\nResumen por temporada del calendario:")
    print(
        calendario.groupby("season")
        .size()
        .rename("partidos")
        .to_string()
    )

    print("\nResumen por temporada de jugadores:")
    print(
        jugadores.groupby("season")
        .size()
        .rename("registros")
        .to_string()
    )

    print("\nDescarga terminada correctamente.")


if __name__ == "__main__":
    main()