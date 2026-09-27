"""Construye el dataset jugador-partido para el mercado NFL 'anota TD'.

El objetivo es binario y vale 1 cuando un RB, WR, TE o FB registra al menos
un touchdown terrestre o recibido. Los pases de TD del quarterback no cuentan
como touchdown anotado por el quarterback.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from construir_dataset_props_pase_carrera import (
    agregar_lesiones,
    cargar_datos,
    columnas_comunes,
    desviacion_previa,
    media_previa,
)


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
PROCESSED = RAIZ_PROYECTO / "data" / "nfl" / "processed"
RUTA_SALIDA = PROCESSED / "nfl_prop_touchdown_features_2012_2026.parquet"

POSICIONES = ["RB", "FB", "WR", "TE"]
VENTANAS = [3, 5, 8]
METRICAS = [
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_tds",
    "receiving_air_yards",
    "receiving_yards_after_catch",
    "receiving_first_downs",
    "receiving_epa",
    "target_share",
    "air_yards_share",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "rushing_first_downs",
    "rushing_epa",
]


def preparar_base(jugadores):
    df = jugadores[jugadores["position"].isin(POSICIONES)].copy()
    for columna in METRICAS:
        if columna not in df.columns:
            df[columna] = 0.0
        df[columna] = pd.to_numeric(df[columna], errors="coerce").fillna(0.0)

    df["opportunities"] = df["targets"] + df["carries"]
    df["touchdown_count"] = df["receiving_tds"] + df["rushing_tds"]
    df["anytime_td"] = (df["touchdown_count"] >= 1).astype(int)

    columnas = columnas_comunes(df) + METRICAS + [
        "opportunities", "touchdown_count", "anytime_td"
    ]
    return (
        df[columnas]
        .sort_values(["player_id", "gameday", "game_id"])
        .reset_index(drop=True)
    )


def agregar_forma_jugador(df):
    resultado = df.copy()
    grupo = resultado.groupby("player_id", group_keys=False)
    grupo_temporada = resultado.groupby(
        ["player_id", "season"], group_keys=False
    )
    resultado["player_games_before"] = grupo.cumcount()
    resultado["player_games_before_season"] = grupo_temporada.cumcount()

    metricas = METRICAS + ["opportunities", "touchdown_count", "anytime_td"]
    for metrica in metricas:
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

    resultado["player_opportunities_std_5"] = grupo[
        "opportunities"
    ].transform(lambda serie: desviacion_previa(serie, 5))
    resultado["player_touchdown_count_std_8"] = grupo[
        "touchdown_count"
    ].transform(lambda serie: desviacion_previa(serie, 8))

    oportunidades = resultado["player_opportunities_avg_8"].replace(0, np.nan)
    resultado["player_td_per_opportunity_8"] = (
        resultado["player_touchdown_count_avg_8"] / oportunidades
    )
    return resultado


def agregar_contexto_equipo(df):
    totales = (
        df.groupby(
            ["game_id", "gameday", "season", "week", "team"],
            as_index=False,
        )
        .agg(
            team_targets=("targets", "sum"),
            team_carries=("carries", "sum"),
            team_opportunities=("opportunities", "sum"),
            team_receiving_yards=("receiving_yards", "sum"),
            team_rushing_yards=("rushing_yards", "sum"),
            team_touchdowns=("touchdown_count", "sum"),
        )
        .sort_values(["team", "gameday", "game_id"])
    )
    grupo = totales.groupby("team", group_keys=False)
    metricas = [
        "team_targets", "team_carries", "team_opportunities",
        "team_receiving_yards", "team_rushing_yards", "team_touchdowns",
    ]
    for metrica in metricas:
        for ventana in VENTANAS:
            totales[f"{metrica}_avg_{ventana}"] = grupo[metrica].transform(
                lambda serie, w=ventana: media_previa(serie, w)
            )

    columnas = [
        c for c in totales.columns
        if c in ["game_id", "team"] or "_avg_" in c
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
            allowed_carries=("carries", "sum"),
            allowed_opportunities=("opportunities", "sum"),
            allowed_receiving_yards=("receiving_yards", "sum"),
            allowed_rushing_yards=("rushing_yards", "sum"),
            allowed_touchdowns=("touchdown_count", "sum"),
            allowed_td_scorers=("anytime_td", "sum"),
        )
        .sort_values(["opponent_team", "position", "gameday", "game_id"])
    )
    grupo = permitidos.groupby(["opponent_team", "position"], group_keys=False)
    metricas = [
        "allowed_targets", "allowed_carries", "allowed_opportunities",
        "allowed_receiving_yards", "allowed_rushing_yards",
        "allowed_touchdowns", "allowed_td_scorers",
    ]
    for metrica in metricas:
        for ventana in VENTANAS:
            permitidos[f"opp_pos_{metrica}_avg_{ventana}"] = (
                grupo[metrica].transform(
                    lambda serie, w=ventana: media_previa(serie, w)
                )
            )

    columnas = [
        c for c in permitidos.columns
        if c in ["game_id", "opponent_team", "position"]
        or c.startswith("opp_pos_")
    ]
    return df.merge(
        permitidos[columnas],
        on=["game_id", "opponent_team", "position"],
        how="left",
        validate="many_to_one",
    )


def agregar_participacion(df):
    oportunidades_equipo = df["team_opportunities_avg_5"].replace(0, np.nan)
    touchdowns_equipo = df["team_touchdowns_avg_8"].replace(0, np.nan)
    nuevas = pd.DataFrame(
        {
            "player_opportunity_share_5": (
                df["player_opportunities_avg_5"] / oportunidades_equipo
            ),
            "player_td_share_8": (
                df["player_touchdown_count_avg_8"] / touchdowns_equipo
            ),
        },
        index=df.index,
    )
    return pd.concat([df, nuevas], axis=1).copy()


def validar(df):
    print("\n" + "=" * 76)
    print("VALIDACION DATASET PROP ANOTA TOUCHDOWN")
    print("=" * 76)
    print(f"Filas totales: {len(df):,}")
    print(f"Columnas: {len(df.columns):,}")
    print(
        "Duplicados jugador-partido: "
        f"{df.duplicated(['player_id', 'game_id']).sum():,}"
    )

    elegibles = df[
        (df["player_games_before"] >= 3)
        & (df["player_opportunities_avg_5"] >= 2.0)
    ].copy()
    print(
        "Filas elegibles (3 juegos previos, oportunidades avg >= 2): "
        f"{len(elegibles):,}"
    )
    resumen = elegibles.groupby("season").agg(
        filas=("player_id", "size"),
        anotadores=("anytime_td", "sum"),
        tasa_td=("anytime_td", "mean"),
    )
    resumen["tasa_td"] *= 100
    print("\nCobertura y frecuencia por temporada:")
    print(resumen.round(2).to_string())

    print("\nFilas elegibles por posicion:")
    print(elegibles.groupby("position").size().to_string())
    control = [
        "player_opportunities_avg_5",
        "player_anytime_td_avg_8",
        "player_td_per_opportunity_8",
        "team_touchdowns_avg_5",
        "opp_pos_allowed_touchdowns_avg_5",
        "player_injury_score",
    ]
    print("\nNulos en features principales (%):")
    print(elegibles[control].isna().mean().mul(100).round(2).to_string())


def main():
    print("Cargando estadisticas, calendario y lesiones...")
    jugadores, lesiones = cargar_datos()
    print("Construyendo objetivo y forma previa del jugador...")
    dataset = agregar_forma_jugador(preparar_base(jugadores))
    print("Calculando volumen previo del equipo...")
    dataset = agregar_contexto_equipo(dataset)
    print("Calculando touchdowns permitidos por posicion...")
    dataset = agregar_defensa_rival(dataset)
    dataset = agregar_participacion(dataset)
    print("Agregando lesiones propias, ofensivas y defensivas...")
    dataset = agregar_lesiones(dataset, lesiones)
    dataset = dataset.sort_values(
        ["season", "week", "gameday", "game_id", "player_id"]
    ).reset_index(drop=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(RUTA_SALIDA, index=False)
    validar(dataset)
    print(f"\nDataset guardado en:\n{RUTA_SALIDA}")
    print("\nConstruccion terminada correctamente.")


if __name__ == "__main__":
    main()
