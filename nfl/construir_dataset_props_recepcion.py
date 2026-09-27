"""Construye el dataset jugador-partido para recepciones y yardas recibidas."""

from pathlib import Path

import numpy as np
import pandas as pd

from features_lesiones import normalizar_lesiones


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RAW = RAIZ_PROYECTO / "data" / "nfl" / "raw"
PROCESSED = RAIZ_PROYECTO / "data" / "nfl" / "processed"

RUTA_JUGADORES = RAW / "nfl_player_stats_2012_2026.parquet"
RUTA_PARTIDOS = RAW / "nfl_schedules_2012_2026.parquet"
RUTA_LESIONES = RAW / "nfl_injuries_2012_2026.parquet"
RUTA_SALIDA = PROCESSED / "nfl_props_recepcion_features_2012_2026.parquet"

POSICIONES = ["WR", "TE", "RB", "FB"]
VENTANAS = [3, 5, 8]

METRICAS_JUGADOR = [
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_air_yards",
    "receiving_yards_after_catch",
    "target_share",
    "air_yards_share",
]


def cargar_datos():
    for ruta in [RUTA_JUGADORES, RUTA_PARTIDOS, RUTA_LESIONES]:
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontro: {ruta}")

    jugadores = pd.read_parquet(RUTA_JUGADORES)
    partidos = pd.read_parquet(RUTA_PARTIDOS)
    lesiones = pd.read_parquet(RUTA_LESIONES)

    partidos["gameday"] = pd.to_datetime(partidos["gameday"], errors="coerce")
    partidos = partidos[
        (partidos["game_type"] == "REG")
        & partidos["home_score"].notna()
        & partidos["away_score"].notna()
    ].copy()

    jugadores = jugadores[jugadores["position"].isin(POSICIONES)].copy()
    jugadores = jugadores.merge(
        partidos[
            [
                "game_id", "gameday", "home_team", "away_team",
                "home_qb_id", "away_qb_id", "home_rest", "away_rest",
                "roof", "surface", "temp", "wind",
            ]
        ],
        on="game_id",
        how="inner",
        validate="many_to_one",
    )

    jugadores["is_home"] = jugadores["team"].eq(jugadores["home_team"]).astype(int)
    jugadores["rest"] = np.where(
        jugadores["is_home"].eq(1),
        jugadores["home_rest"],
        jugadores["away_rest"],
    )
    jugadores["starting_qb_id"] = np.where(
        jugadores["is_home"].eq(1),
        jugadores["home_qb_id"],
        jugadores["away_qb_id"],
    )

    numericas = list(dict.fromkeys(
        METRICAS_JUGADOR
        + [
            "season", "week", "receptions", "receiving_yards",
            "receiving_tds", "rest", "temp", "wind",
        ]
    ))
    for columna in numericas:
        if columna in jugadores.columns:
            jugadores[columna] = pd.to_numeric(jugadores[columna], errors="coerce")

    jugadores = jugadores.sort_values(
        ["player_id", "gameday", "game_id"]
    ).reset_index(drop=True)
    return jugadores, partidos, lesiones


def media_previa(serie, ventana):
    return serie.shift(1).rolling(ventana, min_periods=1).mean()


def desviacion_previa(serie, ventana):
    return serie.shift(1).rolling(ventana, min_periods=2).std()


def agregar_forma_jugador(df):
    resultado = df.copy()
    grupo = resultado.groupby("player_id", group_keys=False)
    grupo_temporada = resultado.groupby(
        ["player_id", "season"], group_keys=False
    )

    resultado["player_games_before"] = grupo.cumcount()
    resultado["player_games_before_season"] = grupo_temporada.cumcount()

    for metrica in METRICAS_JUGADOR:
        for ventana in VENTANAS:
            resultado[f"player_{metrica}_avg_{ventana}"] = (
                grupo[metrica].transform(
                    lambda serie, w=ventana: media_previa(serie, w)
                )
            )
        resultado[f"player_{metrica}_avg_season"] = (
            grupo_temporada[metrica].transform(
                lambda serie: serie.shift(1).expanding(min_periods=1).mean()
            )
        )

    resultado["player_receiving_yards_std_5"] = (
        grupo["receiving_yards"].transform(
            lambda serie: desviacion_previa(serie, 5)
        )
    )
    resultado["player_receiving_yards_std_8"] = (
        grupo["receiving_yards"].transform(
            lambda serie: desviacion_previa(serie, 8)
        )
    )

    targets_previos = resultado["player_targets_avg_5"].replace(0, np.nan)
    resultado["player_catch_rate_5"] = (
        resultado["player_receptions_avg_5"] / targets_previos
    )
    resultado["player_yards_per_target_5"] = (
        resultado["player_receiving_yards_avg_5"] / targets_previos
    )

    resultado["previous_starting_qb_id"] = grupo["starting_qb_id"].shift(1)
    resultado["qb_change"] = np.where(
        resultado["previous_starting_qb_id"].isna(),
        np.nan,
        resultado["starting_qb_id"].astype(str).ne(
            resultado["previous_starting_qb_id"].astype(str)
        ).astype(int),
    )
    return resultado


def agregar_contexto_equipo(df):
    totales = (
        df.groupby(["game_id", "gameday", "season", "week", "team"], as_index=False)
        .agg(
            team_targets=("targets", "sum"),
            team_receptions=("receptions", "sum"),
            team_receiving_yards=("receiving_yards", "sum"),
        )
        .sort_values(["team", "gameday", "game_id"])
    )
    grupo = totales.groupby("team", group_keys=False)
    for metrica in ["team_targets", "team_receptions", "team_receiving_yards"]:
        for ventana in [3, 5, 8]:
            totales[f"{metrica}_avg_{ventana}"] = grupo[metrica].transform(
                lambda serie, w=ventana: media_previa(serie, w)
            )

    columnas = [
        columna for columna in totales.columns
        if columna in ["game_id", "team"] or "_avg_" in columna
    ]
    return df.merge(
        totales[columnas],
        on=["game_id", "team"],
        how="left",
        validate="many_to_one",
    )


def agregar_defensa_rival(df):
    permitidos = (
        df.groupby(
            [
                "game_id", "gameday", "season", "week",
                "opponent_team", "position",
            ],
            as_index=False,
        )
        .agg(
            allowed_targets=("targets", "sum"),
            allowed_receptions=("receptions", "sum"),
            allowed_receiving_yards=("receiving_yards", "sum"),
        )
        .sort_values(["opponent_team", "position", "gameday", "game_id"])
    )
    grupo = permitidos.groupby(["opponent_team", "position"], group_keys=False)
    for metrica in [
        "allowed_targets", "allowed_receptions", "allowed_receiving_yards"
    ]:
        for ventana in [3, 5, 8]:
            permitidos[f"opp_pos_{metrica}_avg_{ventana}"] = (
                grupo[metrica].transform(
                    lambda serie, w=ventana: media_previa(serie, w)
                )
            )

    columnas = [
        columna for columna in permitidos.columns
        if columna in ["game_id", "opponent_team", "position"]
        or columna.startswith("opp_pos_")
    ]
    return df.merge(
        permitidos[columnas],
        on=["game_id", "opponent_team", "position"],
        how="left",
        validate="many_to_one",
    )


def agregar_lesiones_companeros(df, lesiones):
    reportes = normalizar_lesiones(lesiones)
    reportes = reportes[reportes["position"].isin(POSICIONES)].copy()

    resumen = (
        reportes.groupby(["season", "week", "team"], as_index=False)
        .agg(
            team_skill_injury_score=("injury_weight", "sum"),
            team_skill_injury_count=("player_key", "nunique"),
        )
    )
    propias = reportes[
        ["season", "week", "team", "gsis_id", "injury_weight", "report_status_norm"]
    ].rename(
        columns={
            "gsis_id": "player_id",
            "injury_weight": "player_injury_score",
            "report_status_norm": "player_injury_status",
        }
    )
    propias["player_id"] = propias["player_id"].astype(str)

    resultado = df.merge(
        resumen,
        on=["season", "week", "team"],
        how="left",
        validate="many_to_one",
    ).merge(
        propias,
        on=["season", "week", "team", "player_id"],
        how="left",
        validate="many_to_one",
    )
    resultado[
        ["team_skill_injury_score", "team_skill_injury_count", "player_injury_score"]
    ] = resultado[
        ["team_skill_injury_score", "team_skill_injury_count", "player_injury_score"]
    ].fillna(0.0)
    resultado["player_injury_status"] = (
        resultado["player_injury_status"].fillna("healthy_or_unlisted")
    )
    resultado["teammate_skill_injury_score"] = (
        resultado["team_skill_injury_score"] - resultado["player_injury_score"]
    ).clip(lower=0)
    return resultado


def validar_dataset(df):
    print("\n" + "=" * 72)
    print("VALIDACION DATASET PROPS DE RECEPCION")
    print("=" * 72)
    print(f"Filas totales: {len(df):,}")
    print(f"Columnas: {len(df.columns):,}")
    print(f"Duplicados jugador-partido: {df.duplicated(['player_id', 'game_id']).sum():,}")

    elegibles = df[
        (df["player_games_before"] >= 3)
        & (df["player_targets_avg_5"] >= 1.0)
    ]
    print(f"Filas elegibles (3 juegos previos, targets avg >= 1): {len(elegibles):,}")
    print("\nFilas elegibles por temporada:")
    print(elegibles.groupby("season").size().to_string())
    print("\nObjetivos en muestra elegible:")
    print(f"Recepciones promedio: {elegibles['receptions'].mean():.3f}")
    print(f"Yardas promedio: {elegibles['receiving_yards'].mean():.3f}")
    print(
        "Con lesiones relevantes de compañeros: "
        f"{(elegibles['teammate_skill_injury_score'] > 0).sum():,}"
    )

    columnas_control = [
        "player_targets_avg_5", "player_receptions_avg_5",
        "player_receiving_yards_avg_5", "player_target_share_avg_5",
        "opp_pos_allowed_receiving_yards_avg_5",
        "teammate_skill_injury_score",
    ]
    print("\nNulos en features principales (%):")
    print(
        elegibles[columnas_control].isna().mean().mul(100).round(2).to_string()
    )


def main():
    print("Cargando datos...")
    jugadores, _, lesiones = cargar_datos()

    print("Calculando forma previa del jugador...")
    dataset = agregar_forma_jugador(jugadores)

    print("Calculando volumen previo del equipo...")
    dataset = agregar_contexto_equipo(dataset)

    print("Calculando defensa rival por posicion...")
    dataset = agregar_defensa_rival(dataset)

    print("Agregando lesiones de compañeros...")
    dataset = agregar_lesiones_companeros(dataset, lesiones)

    dataset = dataset.sort_values(
        ["season", "week", "gameday", "game_id", "team", "player_id"]
    ).reset_index(drop=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(RUTA_SALIDA, index=False)
    validar_dataset(dataset)
    print(f"\nDataset guardado en:\n{RUTA_SALIDA}")
    print("\nConstruccion terminada correctamente.")


if __name__ == "__main__":
    main()
