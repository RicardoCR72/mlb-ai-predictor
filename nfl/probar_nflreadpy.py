import nflreadpy as nfl


def main():
    print("Descargando calendario NFL...")

    calendario = nfl.load_schedules([2024, 2025]).to_pandas()

    print(f"Partidos descargados: {len(calendario)}")
    print(f"Columnas disponibles: {len(calendario.columns)}")

    columnas = [
        "game_id",
        "season",
        "week",
        "game_type",
        "gameday",
        "away_team",
        "home_team",
        "away_score",
        "home_score",
    ]

    disponibles = [
        columna for columna in columnas
        if columna in calendario.columns
    ]

    print(calendario[disponibles].head(10))
    print("Prueba terminada correctamente.")


if __name__ == "__main__":
    main()