import nflreadpy as nfl


def main():
    print("Descargando estadísticas de jugadores...")

    jugadores = nfl.load_player_stats(
        [2024, 2025],
        summary_level="week"
    ).to_pandas()

    columnas = [
        "player_id",
        "player_name",
        "position",
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

    disponibles = [
        columna for columna in columnas
        if columna in jugadores.columns
    ]

    print(f"Registros descargados: {len(jugadores)}")
    print(jugadores[disponibles].head(10))
    print("Estadísticas descargadas correctamente.")


if __name__ == "__main__":
    main()