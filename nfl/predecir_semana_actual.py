from pathlib import Path

import joblib
import nflreadpy as nfl
import numpy as np
import pandas as pd

from construir_dataset_partidos import (
    convertir_formato_equipo,
    construir_features_equipos,
    unir_features_partidos,
)

from entrenar_totales import (
    FEATURES_BASE,
    FEATURES_CATEGORICAS,
    FEATURES_MERCADO,
)


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]

RUTA_CALENDARIO = (
    RAIZ_PROYECTO
    / "data"
    / "nfl"
    / "raw"
    / "nfl_schedules_2012_2026.parquet"
)

RUTA_MODELO_MERCADO = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "total_con_mercado.joblib"
)

RUTA_MODELO_BASE = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "total_sin_mercado.joblib"
)

RUTA_CALIBRADOR = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "calibrador_pick_totales.joblib"
)

DIRECTORIO_PREDICCIONES = (
    RAIZ_PROYECTO
    / "data"
    / "nfl"
    / "predictions"
)

TEMPORADA_ACTUAL = 2026
EDGE_MINIMO = 3.0


def american_a_decimal(odds):
    if pd.isna(odds):
        return np.nan

    odds = float(odds)

    if odds >= 100:
        return 1 + odds / 100

    if odds <= -100:
        return 1 + 100 / abs(odds)

    if odds > 1:
        return odds

    return np.nan


def actualizar_calendario():
    if not RUTA_CALENDARIO.exists():
        raise FileNotFoundError(
            f"No existe el calendario: {RUTA_CALENDARIO}"
        )

    print(
        f"Actualizando calendario de "
        f"{TEMPORADA_ACTUAL}..."
    )

    historico = pd.read_parquet(
        RUTA_CALENDARIO
    )

    actual = nfl.load_schedules(
        [TEMPORADA_ACTUAL]
    ).to_pandas()

    historico_anterior = historico[
        historico["season"] != TEMPORADA_ACTUAL
    ].copy()

    calendario = pd.concat(
        [historico_anterior, actual],
        ignore_index=True,
    )

    calendario["gameday"] = pd.to_datetime(
        calendario["gameday"],
        errors="coerce",
    )

    calendario = calendario.sort_values(
        ["season", "week", "gameday", "game_id"]
    ).drop_duplicates(
        subset=["game_id"],
        keep="last",
    ).reset_index(drop=True)

    calendario.to_parquet(
        RUTA_CALENDARIO,
        index=False,
    )

    return calendario


def obtener_proxima_semana(calendario):
    pendientes = calendario[
        (calendario["season"] == TEMPORADA_ACTUAL)
        & (calendario["game_type"] == "REG")
        & (
            calendario["home_score"].isna()
            | calendario["away_score"].isna()
        )
    ].copy()

    if pendientes.empty:
        raise ValueError(
            "No se encontraron partidos pendientes."
        )

    proxima_semana = int(
        pendientes["week"].min()
    )

    return proxima_semana


def preparar_features(calendario, proxima_semana):
    regulares = calendario[
        calendario["game_type"] == "REG"
    ].copy()

    terminados = regulares[
        regulares["home_score"].notna()
        & regulares["away_score"].notna()
    ].copy()

    proximos = regulares[
        (regulares["season"] == TEMPORADA_ACTUAL)
        & (regulares["week"] == proxima_semana)
        & (
            regulares["home_score"].isna()
            | regulares["away_score"].isna()
        )
    ].copy()

    if proximos.empty:
        raise ValueError(
            f"No hay partidos pendientes en Semana "
            f"{proxima_semana}."
        )

    # Únicamente agregamos la siguiente semana.
    # Así, ningún partido futuro intermedio contamina
    # las medias móviles de otro encuentro.
    base = pd.concat(
        [terminados, proximos],
        ignore_index=True,
    )

    base = base.sort_values(
        ["season", "week", "gameday", "game_id"]
    ).reset_index(drop=True)

    equipos = convertir_formato_equipo(base)
    equipos = construir_features_equipos(equipos)

    dataset = unir_features_partidos(
        base,
        equipos,
    )

    prediccion = dataset[
        (dataset["season"] == TEMPORADA_ACTUAL)
        & (dataset["week"] == proxima_semana)
        & (
            dataset["home_score"].isna()
            | dataset["away_score"].isna()
        )
    ].copy()

    return prediccion


def cargar_modelos():
    rutas = [
        RUTA_MODELO_MERCADO,
        RUTA_MODELO_BASE,
        RUTA_CALIBRADOR,
    ]

    for ruta in rutas:
        if not ruta.exists():
            raise FileNotFoundError(
                f"No se encontró: {ruta}"
            )

    modelo_mercado = joblib.load(
        RUTA_MODELO_MERCADO
    )

    modelo_base = joblib.load(
        RUTA_MODELO_BASE
    )

    calibrador = joblib.load(
        RUTA_CALIBRADOR
    )

    return (
        modelo_mercado,
        modelo_base,
        calibrador,
    )


def generar_predicciones(
    df,
    modelo_mercado,
    modelo_base,
    calibrador,
):
    resultado = df.copy()

    columnas_mercado = (
        FEATURES_MERCADO
        + FEATURES_CATEGORICAS
    )

    columnas_base = (
        FEATURES_BASE
        + FEATURES_CATEGORICAS
    )

    resultado["pred_total_base"] = (
        modelo_base.predict(
            resultado[columnas_base]
        )
    )

    resultado["pred_total"] = np.nan
    resultado["edge"] = np.nan
    resultado["edge_absoluto"] = np.nan
    resultado["pick"] = "SIN LÍNEA"
    resultado["prob_pick"] = np.nan
    resultado["prob_over"] = np.nan
    resultado["prob_under"] = np.nan
    resultado["odds_pick"] = np.nan
    resultado["decimal_pick"] = np.nan
    resultado["prob_break_even"] = np.nan
    resultado["ev"] = np.nan
    resultado["estado"] = "SIN LÍNEA"

    con_linea = resultado[
        resultado["total_line"].notna()
    ].index

    if len(con_linea) == 0:
        return resultado

    X_mercado = resultado.loc[
        con_linea,
        columnas_mercado,
    ]

    predicciones = modelo_mercado.predict(
        X_mercado
    )

    resultado.loc[
        con_linea,
        "pred_total"
    ] = predicciones

    resultado.loc[
        con_linea,
        "edge"
    ] = (
        resultado.loc[
            con_linea,
            "pred_total"
        ]
        - resultado.loc[
            con_linea,
            "total_line"
        ]
    )

    resultado.loc[
        con_linea,
        "edge_absoluto"
    ] = (
        resultado.loc[
            con_linea,
            "edge"
        ].abs()
    )

    resultado.loc[
        con_linea,
        "pick"
    ] = np.where(
        resultado.loc[con_linea, "edge"] > 0,
        "OVER",
        "UNDER",
    )

    probabilidades = calibrador.predict_proba(
        resultado.loc[
            con_linea,
            ["edge_absoluto"]
        ]
    )[:, 1]

    resultado.loc[
        con_linea,
        "prob_pick"
    ] = probabilidades

    resultado.loc[
        con_linea,
        "prob_over"
    ] = np.where(
        resultado.loc[con_linea, "pick"] == "OVER",
        probabilidades,
        1 - probabilidades,
    )

    resultado.loc[
        con_linea,
        "prob_under"
    ] = (
        1
        - resultado.loc[
            con_linea,
            "prob_over"
        ]
    )

    resultado.loc[
        con_linea,
        "odds_pick"
    ] = np.where(
        resultado.loc[con_linea, "pick"] == "OVER",
        resultado.loc[con_linea, "over_odds"],
        resultado.loc[con_linea, "under_odds"],
    )

    resultado.loc[
        con_linea,
        "decimal_pick"
    ] = resultado.loc[
        con_linea,
        "odds_pick"
    ].apply(american_a_decimal)

    resultado.loc[
        con_linea,
        "prob_break_even"
    ] = (
        1
        / resultado.loc[
            con_linea,
            "decimal_pick"
        ]
    )

    resultado.loc[
        con_linea,
        "ev"
    ] = (
        resultado.loc[
            con_linea,
            "prob_pick"
        ]
        * resultado.loc[
            con_linea,
            "decimal_pick"
        ]
        - 1
    )

    cumple_edge = (
        resultado["edge_absoluto"] >= EDGE_MINIMO
    )

    cumple_ev = (
        resultado["ev"] > 0
    )

    resultado.loc[
        con_linea,
        "estado"
    ] = "NO PICK"

    resultado.loc[
        cumple_edge & cumple_ev,
        "estado"
    ] = "PICK"

    return resultado


def mostrar_resultados(df, semana):
    columnas = [
        "gameday",
        "away_team",
        "home_team",
        "total_line",
        "pred_total",
        "pred_total_base",
        "edge",
        "pick",
        "prob_pick",
        "prob_over",
        "prob_under",
        "odds_pick",
        "ev",
        "estado",
    ]

    tabla = df[columnas].copy()

    redondear = [
        "total_line",
        "pred_total",
        "pred_total_base",
        "edge",
        "odds_pick",
    ]

    for columna in redondear:
        tabla[columna] = (
            tabla[columna].round(2)
        )

    porcentajes = [
        "prob_pick",
        "prob_over",
        "prob_under",
        "ev",
    ]

    for columna in porcentajes:
        tabla[columna] = (
            tabla[columna] * 100
        ).round(2)

    tabla = tabla.sort_values(
        ["estado", "prob_pick"],
        ascending=[True, False],
    )

    print("\n" + "=" * 100)
    print(
        f"PREDICCIONES NFL - "
        f"TEMPORADA {TEMPORADA_ACTUAL} "
        f"SEMANA {semana}"
    )
    print("=" * 100)

    print(tabla.to_string(index=False))


def main():
    DIRECTORIO_PREDICCIONES.mkdir(
        parents=True,
        exist_ok=True,
    )

    calendario = actualizar_calendario()

    proxima_semana = obtener_proxima_semana(
        calendario
    )

    print(
        f"Próxima semana detectada: "
        f"{proxima_semana}"
    )

    print("Construyendo variables previas...")
    proximos = preparar_features(
        calendario,
        proxima_semana,
    )

    (
        modelo_mercado,
        modelo_base,
        calibrador,
    ) = cargar_modelos()

    print("Generando predicciones...")
    predicciones = generar_predicciones(
        proximos,
        modelo_mercado,
        modelo_base,
        calibrador,
    )

    ruta_salida = (
        DIRECTORIO_PREDICCIONES
        / (
            f"nfl_totales_"
            f"{TEMPORADA_ACTUAL}_"
            f"semana_{proxima_semana}.csv"
        )
    )

    predicciones.to_csv(
        ruta_salida,
        index=False,
    )

    mostrar_resultados(
        predicciones,
        proxima_semana,
    )

    print("\nArchivo guardado:")
    print(ruta_salida)


if __name__ == "__main__":
    main()