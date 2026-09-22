from pathlib import Path

import numpy as np
import pandas as pd


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]

RUTA_RAW = (
    RAIZ_PROYECTO
    / "data"
    / "nfl"
    / "raw"
    / "nfl_schedules_2012_2026.parquet"
)

DIRECTORIO_PROCESADO = (
    RAIZ_PROYECTO
    / "data"
    / "nfl"
    / "processed"
)

RUTA_SALIDA = (
    DIRECTORIO_PROCESADO
    / "nfl_games_features_2012_2026.parquet"
)

VENTANAS = [4, 8]


def cargar_partidos():
    if not RUTA_RAW.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo: {RUTA_RAW}"
        )

    df = pd.read_parquet(RUTA_RAW)

    df["gameday"] = pd.to_datetime(
        df["gameday"],
        errors="coerce"
    )

    # Primera versión: únicamente temporada regular.
    df = df[
        (df["game_type"] == "REG")
        & df["home_score"].notna()
        & df["away_score"].notna()
    ].copy()

    columnas_numericas = [
        "home_score",
        "away_score",
        "home_rest",
        "away_rest",
        "spread_line",
        "total_line",
        "home_moneyline",
        "away_moneyline",
        "home_spread_odds",
        "away_spread_odds",
        "over_odds",
        "under_odds",
        "temp",
        "wind",
    ]

    for columna in columnas_numericas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(
                df[columna],
                errors="coerce"
            )

    df = df.sort_values(
        ["season", "week", "gameday", "game_id"]
    ).reset_index(drop=True)

    return df


def crear_targets(df):
    df = df.copy()

    df["total_points"] = (
        df["home_score"] + df["away_score"]
    )

    df["home_margin"] = (
        df["home_score"] - df["away_score"]
    )

    df["home_win"] = (
        df["home_score"] > df["away_score"]
    ).astype(int)

    df["over_result"] = np.where(
        df["total_line"].notna(),
        (df["total_points"] > df["total_line"]).astype(int),
        np.nan,
    )

    df["push_total"] = np.where(
        df["total_line"].notna(),
        (df["total_points"] == df["total_line"]).astype(int),
        np.nan,
    )

    # spread_line está expresado desde la perspectiva local.
    df["home_cover"] = np.where(
        df["spread_line"].notna(),
        (
            df["home_margin"] > df["spread_line"]
        ).astype(int),
        np.nan,
    )

    df["push_spread"] = np.where(
        df["spread_line"].notna(),
        (
            df["home_margin"] == df["spread_line"]
        ).astype(int),
        np.nan,
    )

    return df


def convertir_formato_equipo(df):
    columnas_comunes = [
        "game_id",
        "season",
        "week",
        "gameday",
    ]

    local = df[
        columnas_comunes
        + [
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "home_rest",
            "home_qb_id",
            "home_coach",
        ]
    ].copy()

    local = local.rename(
        columns={
            "home_team": "team",
            "away_team": "opponent",
            "home_score": "points_for",
            "away_score": "points_against",
            "home_rest": "rest",
            "home_qb_id": "qb_id",
            "home_coach": "coach",
        }
    )

    local["is_home"] = 1

    visitante = df[
        columnas_comunes
        + [
            "away_team",
            "home_team",
            "away_score",
            "home_score",
            "away_rest",
            "away_qb_id",
            "away_coach",
        ]
    ].copy()

    visitante = visitante.rename(
        columns={
            "away_team": "team",
            "home_team": "opponent",
            "away_score": "points_for",
            "home_score": "points_against",
            "away_rest": "rest",
            "away_qb_id": "qb_id",
            "away_coach": "coach",
        }
    )

    visitante["is_home"] = 0

    equipos = pd.concat(
        [local, visitante],
        ignore_index=True
    )

    equipos["win"] = (
        equipos["points_for"]
        > equipos["points_against"]
    ).astype(int)

    equipos["point_margin"] = (
        equipos["points_for"]
        - equipos["points_against"]
    )

    equipos["game_total"] = (
        equipos["points_for"]
        + equipos["points_against"]
    )

    equipos = equipos.sort_values(
        ["season", "team", "gameday", "game_id"]
    ).reset_index(drop=True)

    return equipos


def promedio_previo(serie, ventana):
    return (
        serie
        .shift(1)
        .rolling(
            window=ventana,
            min_periods=1
        )
        .mean()
    )


def desviacion_previa(serie, ventana):
    return (
        serie
        .shift(1)
        .rolling(
            window=ventana,
            min_periods=2
        )
        .std()
    )


def promedio_temporada_previo(serie):
    return (
        serie
        .shift(1)
        .expanding(min_periods=1)
        .mean()
    )


def construir_features_equipos(equipos):
    equipos = equipos.copy()

    # Mantiene el orden cronológico completo de cada equipo.
    equipos = equipos.sort_values(
        ["team", "gameday", "game_id"]
    ).reset_index(drop=True)

    # Este grupo NO se reinicia por temporada.
    # Se usa para últimos 4 y 8 partidos.
    grupo_equipo = equipos.groupby(
        "team",
        group_keys=False
    )

    # Este grupo sí se reinicia cada temporada.
    # Se usa para estadísticas acumuladas de la temporada.
    grupo_temporada = equipos.groupby(
        ["season", "team"],
        group_keys=False
    )

    equipos["games_before_season"] = (
        grupo_temporada.cumcount()
    )

    metricas = {
        "win": "win_pct",
        "points_for": "points_for_avg",
        "points_against": "points_against_avg",
        "point_margin": "margin_avg",
        "game_total": "game_total_avg",
    }

    for columna_origen, nombre_feature in metricas.items():

        # Forma reciente: continúa de una temporada a otra.
        for ventana in VENTANAS:
            equipos[
                f"{nombre_feature}_{ventana}"
            ] = grupo_equipo[columna_origen].transform(
                lambda serie, w=ventana:
                promedio_previo(serie, w)
            )

        # Promedio de temporada: se reinicia cada año.
        equipos[
            f"{nombre_feature}_season"
        ] = grupo_temporada[columna_origen].transform(
            promedio_temporada_previo
        )

    # Volatilidad reciente: también continúa entre temporadas.
    equipos["game_total_std_8"] = (
        grupo_equipo["game_total"].transform(
            lambda serie:
            desviacion_previa(serie, 8)
        )
    )

    # Compara al QB actual con el QB del partido anterior,
    # aunque el encuentro anterior fuera la temporada pasada.
    equipos["previous_qb_id"] = (
        grupo_equipo["qb_id"].shift(1)
    )

    equipos["qb_change"] = np.where(
        equipos["previous_qb_id"].isna(),
        np.nan,
        (
            equipos["qb_id"]
            != equipos["previous_qb_id"]
        ).astype(int),
    )

    return equipos


def unir_features_partidos(df, equipos):
    features_equipo = [
        "games_before_season",
        "win_pct_4",
        "win_pct_8",
        "win_pct_season",
        "points_for_avg_4",
        "points_for_avg_8",
        "points_for_avg_season",
        "points_against_avg_4",
        "points_against_avg_8",
        "points_against_avg_season",
        "margin_avg_4",
        "margin_avg_8",
        "margin_avg_season",
        "game_total_avg_4",
        "game_total_avg_8",
        "game_total_avg_season",
        "game_total_std_8",
        "qb_change",
    ]

    local = equipos[
        equipos["is_home"] == 1
    ][["game_id"] + features_equipo].copy()

    visitante = equipos[
        equipos["is_home"] == 0
    ][["game_id"] + features_equipo].copy()

    local = local.rename(
        columns={
            columna: f"home_{columna}"
            for columna in features_equipo
        }
    )

    visitante = visitante.rename(
        columns={
            columna: f"away_{columna}"
            for columna in features_equipo
        }
    )

    resultado = df.merge(
        local,
        on="game_id",
        how="left",
        validate="one_to_one"
    )

    resultado = resultado.merge(
        visitante,
        on="game_id",
        how="left",
        validate="one_to_one"
    )

    metricas_diferencia = [
        "rest",
        "win_pct_4",
        "win_pct_8",
        "win_pct_season",
        "points_for_avg_4",
        "points_for_avg_8",
        "points_for_avg_season",
        "points_against_avg_4",
        "points_against_avg_8",
        "points_against_avg_season",
        "margin_avg_4",
        "margin_avg_8",
        "margin_avg_season",
        "game_total_avg_4",
        "game_total_avg_8",
        "game_total_avg_season",
    ]

    for metrica in metricas_diferencia:
        resultado[f"diff_{metrica}"] = (
            resultado[f"home_{metrica}"]
            - resultado[f"away_{metrica}"]
        )

    return resultado


def validar_dataset(df):
    print("\n" + "=" * 70)
    print("VALIDACIÓN DEL DATASET")
    print("=" * 70)

    print(f"Partidos: {len(df):,}")
    print(f"Columnas: {len(df.columns)}")
    print(
        "Game ID duplicados:",
        df["game_id"].duplicated().sum()
    )

    print("\nPartidos por temporada:")
    print(
        df.groupby("season")
        .size()
        .rename("partidos")
        .to_string()
    )

    semana_1 = df[df["week"] == 1]

    columnas_temporada = [
    "home_win_pct_season",
    "away_win_pct_season",
    "home_points_for_avg_season",
    "away_points_for_avg_season",
    ]
    print("\nNulos en medias recientes de Semana 1:")
    print(
        semana_1[columnas_temporada]
        .isna()
        .mean()
        .mul(100)
        .round(2)
    )

    print("\nPromedios generales:")

    resumen = {
        "Puntos totales": df["total_points"].mean(),
        "Margen local": df["home_margin"].mean(),
        "Victoria local %": df["home_win"].mean() * 100,
        "Línea total": df["total_line"].mean(),
    }

    for nombre, valor in resumen.items():
        print(f"{nombre}: {valor:.2f}")

    print("\nTemporadas reservadas:")

    for temporada in [2024, 2025, 2026]:
        cantidad = len(df[df["season"] == temporada])
        print(f"{temporada}: {cantidad} partidos")


def main():
    DIRECTORIO_PROCESADO.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Cargando partidos...")
    partidos = cargar_partidos()

    print("Creando variables objetivo...")
    partidos = crear_targets(partidos)

    print("Convirtiendo partidos a formato por equipo...")
    equipos = convertir_formato_equipo(partidos)

    print("Calculando estadísticas previas...")
    equipos = construir_features_equipos(equipos)

    print("Uniendo local y visitante...")
    dataset = unir_features_partidos(
        partidos,
        equipos
    )

    dataset = dataset.sort_values(
        ["season", "week", "gameday", "game_id"]
    ).reset_index(drop=True)

    dataset.to_parquet(
        RUTA_SALIDA,
        index=False
    )

    validar_dataset(dataset)

    print(f"\nDataset guardado en:\n{RUTA_SALIDA}")
    print("\nConstrucción terminada correctamente.")


if __name__ == "__main__":
    main()