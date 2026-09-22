from pathlib import Path

import pandas as pd


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
DIRECTORIO_RAW = RAIZ_PROYECTO / "data" / "nfl" / "raw"

RUTA_CALENDARIO = (
    DIRECTORIO_RAW / "nfl_schedules_2012_2026.parquet"
)

RUTA_JUGADORES = (
    DIRECTORIO_RAW / "nfl_player_stats_2012_2026.parquet"
)


def porcentaje_nulos(df, columnas):
    resultado = {}

    for columna in columnas:
        if columna in df.columns:
            resultado[columna] = round(
                df[columna].isna().mean() * 100,
                2
            )

    return pd.Series(resultado, name="porcentaje_nulos")


def auditar_calendario(calendario):
    print("=" * 70)
    print("AUDITORÍA DEL CALENDARIO")
    print("=" * 70)

    print(f"Filas: {len(calendario):,}")
    print(f"Columnas: {len(calendario.columns)}")
    print(f"Game ID duplicados: {calendario['game_id'].duplicated().sum()}")

    print("\nTodas las columnas del calendario:")

    for columna in calendario.columns:
        print(f"  - {columna}")

    columnas_importantes = [
        "game_id",
        "season",
        "week",
        "game_type",
        "gameday",
        "away_team",
        "home_team",
        "away_score",
        "home_score",
        "spread_line",
        "total_line",
        "away_moneyline",
        "home_moneyline",
        "roof",
        "surface",
        "temp",
        "wind",
        "away_rest",
        "home_rest",
    ]

    print("\nPorcentaje de valores faltantes:")
    print(porcentaje_nulos(calendario, columnas_importantes))

    terminados = calendario[
        calendario["home_score"].notna()
        & calendario["away_score"].notna()
    ]

    print(f"\nPartidos con marcador final: {len(terminados):,}")

    if "game_type" in calendario.columns:
        print("\nPartidos por tipo:")
        print(calendario["game_type"].value_counts(dropna=False))


def auditar_jugadores(jugadores):
    print("\n" + "=" * 70)
    print("AUDITORÍA DE JUGADORES")
    print("=" * 70)

    print(f"Filas: {len(jugadores):,}")
    print(f"Columnas: {len(jugadores.columns)}")

    print("\nColumnas relacionadas con equipos:")

    columnas_equipo = [
        columna
        for columna in jugadores.columns
        if "team" in columna.lower()
    ]

    for columna in columnas_equipo:
        print(f"  - {columna}")

    print("\nColumnas relacionadas con identificadores:")

    columnas_id = [
        columna
        for columna in jugadores.columns
        if "id" in columna.lower()
    ]

    for columna in columnas_id:
        print(f"  - {columna}")

    clave = ["player_id", "season", "week"]

    if all(columna in jugadores.columns for columna in clave):
        duplicados = jugadores.duplicated(clave).sum()
        print(f"\nJugador-temporada-semana duplicados: {duplicados:,}")

    if "position" in jugadores.columns:
        print("\nRegistros por posición:")
        print(
            jugadores["position"]
            .value_counts(dropna=False)
            .head(20)
        )

    columnas_props = [
        "player_id",
        "player_name",
        "position",
        "team",
        "recent_team",
        "season",
        "week",
        "passing_attempts",
        "passing_yards",
        "passing_tds",
        "carries",
        "rushing_yards",
        "targets",
        "receptions",
        "receiving_yards",
    ]

    print("\nPorcentaje de valores faltantes en props:")
    print(porcentaje_nulos(jugadores, columnas_props))


def main():
    if not RUTA_CALENDARIO.exists():
        raise FileNotFoundError(
            "No se encontró el calendario. Ejecuta primero "
            "nfl/descargar_datos.py"
        )

    if not RUTA_JUGADORES.exists():
        raise FileNotFoundError(
            "No se encontraron estadísticas de jugadores."
        )

    calendario = pd.read_parquet(RUTA_CALENDARIO)
    jugadores = pd.read_parquet(RUTA_JUGADORES)

    auditar_calendario(calendario)
    auditar_jugadores(jugadores)

    print("\nAuditoría terminada correctamente.")


if __name__ == "__main__":
    main()