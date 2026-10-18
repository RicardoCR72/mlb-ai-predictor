"""Contrato de variables compartido por entrenamiento e inferencia."""
from nfl.features_lesiones import FEATURES_LESIONES_MODELO

METRICAS_EQUIPO = [

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

METRICAS_DIFERENCIA = [

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

def obtener_features_base():

    features = [

        "home_rest",

        "away_rest",

        "temp",

        "wind",

        "div_game",

    ]



    for lado in ["home", "away"]:

        for metrica in METRICAS_EQUIPO:

            features.append(f"{lado}_{metrica}")



    for metrica in METRICAS_DIFERENCIA:

        features.append(f"diff_{metrica}")



    return list(dict.fromkeys(features))

FEATURES_BASE_SIN_LESIONES = obtener_features_base()

FEATURES_BASE = list(
    dict.fromkeys(
        FEATURES_BASE_SIN_LESIONES
        + FEATURES_LESIONES_MODELO
    )
)

FEATURES_MERCADO = list(

    dict.fromkeys(

        FEATURES_BASE

        + [

            "total_line",

            "spread_line",

        ]

    )

)

FEATURES_MERCADO_SIN_LESIONES = list(
    dict.fromkeys(
        FEATURES_BASE_SIN_LESIONES
        + ["total_line", "spread_line"]
    )
)

FEATURES_CATEGORICAS = [

    "roof",

    "surface",

]
