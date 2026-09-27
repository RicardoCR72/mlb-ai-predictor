"""Entrena modelos NFL para props de pase y carrera.

Division temporal:
* Entrenamiento y desarrollo: 2012-2023
* Seleccion: 2024
* Confirmacion: 2025
* Fuera de muestra: 2026

Para cada objetivo compara una variante base y otra con lesiones. La variante
con lesiones solo se selecciona si reduce MAE tanto en 2024 como en 2025.
Despues de seleccionar, el modelo de produccion se reajusta con 2012-2025.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
PROCESSED = RAIZ_PROYECTO / "data" / "nfl" / "processed"
DIRECTORIO_MODELOS = RAIZ_PROYECTO / "modelos_nfl" / "props"

RUTA_PASE = PROCESSED / "nfl_props_pase_features_2012_2026.parquet"
RUTA_CARRERA = PROCESSED / "nfl_props_carrera_features_2012_2026.parquet"
RUTA_PREDICCIONES = (
    DIRECTORIO_MODELOS / "predicciones_validacion_pase_carrera.csv"
)
RUTA_METADATA = DIRECTORIO_MODELOS / "metadata_props_pase_carrera.json"

TRAIN_SEASONS = list(range(2012, 2024))
SELECTION_SEASON = 2024
CONFIRMATION_SEASON = 2025
OOS_SEASON = 2026

FEATURES_CATEGORICAS = [
    "position",
    "team",
    "opponent_team",
    "roof",
    "surface",
]

FEATURES_COMUNES = [
    "player_games_before",
    "player_games_before_season",
    "is_home",
    "rest",
    "is_starting_qb",
    "temp",
    "wind",
    "spread_line",
    "total_line",
    "home_moneyline",
    "away_moneyline",
    "div_game",
]

METRICAS_PASE = [
    "passing_attempts",
    "passing_completions",
    "passing_yards",
    "passing_tds",
    "interceptions",
    "sacks",
    "passing_air_yards",
    "passing_yards_after_catch",
    "passing_first_downs",
    "passing_epa",
]

METRICAS_CARRERA = [
    "carries",
    "rushing_yards",
    "rushing_tds",
    "rushing_first_downs",
    "rushing_epa",
    "rushing_fumbles",
    "rushing_fumbles_lost",
]

OBJETIVOS = {
    "passing_yards": {
        "dataset": "pase",
        "archivo": "props_passing_yards.joblib",
        "baseline": "player_passing_yards_avg_5",
        "loss": "squared_error",
    },
    "passing_tds": {
        "dataset": "pase",
        "archivo": "props_passing_tds.joblib",
        "baseline": "player_passing_tds_avg_5",
        "loss": "poisson",
    },
    "rushing_yards": {
        "dataset": "carrera",
        "archivo": "props_rushing_yards.joblib",
        "baseline": "player_rushing_yards_avg_5",
        "loss": "squared_error",
    },
    "rushing_tds": {
        "dataset": "carrera",
        "archivo": "props_rushing_tds.joblib",
        "baseline": "player_rushing_tds_avg_5",
        "loss": "poisson",
    },
}


def features_rolling(metricas):
    columnas = []
    for metrica in metricas:
        for ventana in [3, 5, 8]:
            columnas.append(f"player_{metrica}_avg_{ventana}")
        columnas.append(f"player_{metrica}_avg_season")
    return columnas


def features_contexto(metricas):
    columnas = []
    for metrica in metricas:
        for ventana in [3, 5, 8]:
            columnas.append(f"team_{metrica}_avg_{ventana}")
            columnas.append(f"opp_allowed_{metrica}_avg_{ventana}")
    return columnas


FEATURES_PASE = list(dict.fromkeys(
    FEATURES_COMUNES
    + features_rolling(METRICAS_PASE)
    + features_contexto(METRICAS_PASE[:6])
    + [
        "player_passing_yards_std_5",
        "player_passing_yards_std_8",
        "player_completion_rate_5",
        "player_passing_yards_per_attempt_5",
        "player_passing_td_rate_5",
        "player_interception_rate_5",
    ]
))

FEATURES_CARRERA = list(dict.fromkeys(
    FEATURES_COMUNES
    + features_rolling(METRICAS_CARRERA)
    + features_contexto(METRICAS_CARRERA[:4])
    + [
        "player_rushing_yards_std_5",
        "player_rushing_yards_std_8",
        "player_rushing_yards_per_carry_5",
        "player_rushing_td_rate_5",
    ]
))

FEATURES_LESIONES = [
    "player_injury_score",
    "team_qb_injury_score",
    "team_qb_injury_count",
    "team_skill_injury_score",
    "team_skill_injury_count",
    "team_ol_injury_score",
    "team_ol_injury_count",
    "team_defense_injury_score",
    "team_defense_injury_count",
    "opp_qb_injury_score",
    "opp_qb_injury_count",
    "opp_skill_injury_score",
    "opp_skill_injury_count",
    "opp_ol_injury_score",
    "opp_ol_injury_count",
    "opp_defense_injury_score",
    "opp_defense_injury_count",
]


def cargar_datasets():
    for ruta in [RUTA_PASE, RUTA_CARRERA]:
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontro: {ruta}")

    pase = pd.read_parquet(RUTA_PASE)
    carrera = pd.read_parquet(RUTA_CARRERA)
    for df in [pase, carrera]:
        df["gameday"] = pd.to_datetime(df["gameday"], errors="coerce")
        df.replace([np.inf, -np.inf], np.nan, inplace=True)

    pase = pase[
        (pase["player_games_before"] >= 3)
        & (pase["player_passing_attempts_avg_5"] >= 10.0)
    ].copy()
    carrera = carrera[
        (carrera["player_games_before"] >= 3)
        & (carrera["player_carries_avg_5"] >= 2.0)
    ].copy()

    orden = ["season", "week", "gameday", "game_id", "player_id"]
    return {
        "pase": pase.sort_values(orden).reset_index(drop=True),
        "carrera": carrera.sort_values(orden).reset_index(drop=True),
    }


def validar_columnas(df, features, objetivos):
    requeridas = set(features + FEATURES_LESIONES + FEATURES_CATEGORICAS + objetivos)
    faltantes = sorted(requeridas - set(df.columns))
    if faltantes:
        raise KeyError("Faltan columnas: " + ", ".join(faltantes))


def construir_pipeline(features_numericas, loss):
    preprocesador = ColumnTransformer(
        transformers=[
            (
                "numericas",
                SimpleImputer(strategy="median", add_indicator=True),
                features_numericas,
            ),
            (
                "categoricas",
                Pipeline(
                    steps=[
                        ("imputar", SimpleImputer(strategy="most_frequent")),
                        (
                            "one_hot",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                sparse_output=False,
                            ),
                        ),
                    ]
                ),
                FEATURES_CATEGORICAS,
            ),
        ],
        remainder="drop",
    )

    parametros = {
        "learning_rate": 0.04,
        "max_iter": 350,
        "max_leaf_nodes": 23 if loss == "squared_error" else 15,
        "min_samples_leaf": 40 if loss == "squared_error" else 60,
        "l2_regularization": 3.0 if loss == "squared_error" else 5.0,
        "early_stopping": False,
        "random_state": 42,
    }
    modelo = HistGradientBoostingRegressor(loss=loss, **parametros)
    return Pipeline(
        steps=[
            ("preprocesamiento", preprocesador),
            ("modelo", modelo),
        ]
    )


def dividir(df):
    train = df[df["season"].isin(TRAIN_SEASONS)].copy()
    seleccion = df[df["season"] == SELECTION_SEASON].copy()
    confirmacion = df[df["season"] == CONFIRMATION_SEASON].copy()
    oos = df[df["season"] == OOS_SEASON].copy()
    return train, seleccion, confirmacion, oos


def evaluar(conjunto, predicciones, objetivo, variante, baseline_columna):
    columnas = [
        "game_id", "season", "week", "gameday", "player_id",
        "player_name", "position", "team", "opponent_team", objetivo,
    ]
    detalle = conjunto[columnas].copy()
    detalle["objetivo"] = objetivo
    detalle["variante"] = variante
    detalle["prediccion"] = np.maximum(predicciones, 0.0)
    detalle["baseline"] = conjunto[baseline_columna].to_numpy()
    detalle["error"] = detalle["prediccion"] - detalle[objetivo]
    detalle["error_absoluto"] = detalle["error"].abs()

    resultado = {
        "objetivo": objetivo,
        "variante": variante,
        "temporada": int(conjunto["season"].iloc[0]),
        "filas": int(len(conjunto)),
        "mae": float(mean_absolute_error(
            detalle[objetivo], detalle["prediccion"]
        )),
        "rmse": float(np.sqrt(mean_squared_error(
            detalle[objetivo], detalle["prediccion"]
        ))),
        "bias": float(detalle["error"].mean()),
        "mae_baseline": float(mean_absolute_error(
            detalle[objetivo], detalle["baseline"]
        )),
        "media_real": float(detalle[objetivo].mean()),
        "media_predicha": float(detalle["prediccion"].mean()),
    }
    return resultado, detalle


def imprimir_resultado(resultado):
    print("-" * 76)
    print(
        f"{resultado['objetivo']} | {resultado['variante']} | "
        f"Temporada {resultado['temporada']}"
    )
    print("-" * 76)
    print(f"Filas: {resultado['filas']:,}")
    print(f"MAE modelo: {resultado['mae']:.4f}")
    print(f"MAE baseline rolling-5: {resultado['mae_baseline']:.4f}")
    print(f"RMSE: {resultado['rmse']:.4f}")
    print(f"Bias: {resultado['bias']:+.4f}")
    print(f"Media real: {resultado['media_real']:.4f}")
    print(f"Media predicha: {resultado['media_predicha']:.4f}")


def entrenar_variante(
    train,
    evaluaciones,
    objetivo,
    variante,
    features,
    configuracion,
):
    columnas = list(dict.fromkeys(features + FEATURES_CATEGORICAS))
    pipeline = construir_pipeline(features, configuracion["loss"])
    pipeline.fit(train[columnas], train[objetivo])

    resultados = []
    detalles = []
    for conjunto in evaluaciones:
        if conjunto.empty:
            continue
        predicciones = pipeline.predict(conjunto[columnas])
        resultado, detalle = evaluar(
            conjunto,
            predicciones,
            objetivo,
            variante,
            configuracion["baseline"],
        )
        imprimir_resultado(resultado)
        resultados.append(resultado)
        detalles.append(detalle)
    return pipeline, resultados, detalles


def resultado_temporada(resultados, temporada):
    return next(r for r in resultados if r["temporada"] == temporada)


def seleccionar_variante(control, lesiones):
    control_2024 = resultado_temporada(control, 2024)["mae"]
    lesiones_2024 = resultado_temporada(lesiones, 2024)["mae"]
    control_2025 = resultado_temporada(control, 2025)["mae"]
    lesiones_2025 = resultado_temporada(lesiones, 2025)["mae"]
    mejora_2024 = lesiones_2024 < control_2024
    mejora_2025 = lesiones_2025 < control_2025
    return "lesiones" if mejora_2024 and mejora_2025 else "control"


def resumen_division(nombre, df):
    train, seleccion, confirmacion, oos = dividir(df)
    print(f"\nDivision temporal {nombre}:")
    print(f"Train 2012-2023: {len(train):,}")
    print(f"Seleccion 2024: {len(seleccion):,}")
    print(f"Confirmacion 2025: {len(confirmacion):,}")
    print(f"OOS 2026: {len(oos):,}")


def main():
    print("Cargando datasets de pase y carrera...")
    datasets = cargar_datasets()
    resumen_division("pase", datasets["pase"])
    resumen_division("carrera", datasets["carrera"])

    validar_columnas(
        datasets["pase"],
        FEATURES_PASE,
        ["passing_yards", "passing_tds"],
    )
    validar_columnas(
        datasets["carrera"],
        FEATURES_CARRERA,
        ["rushing_yards", "rushing_tds"],
    )

    DIRECTORIO_MODELOS.mkdir(parents=True, exist_ok=True)
    todos_resultados = []
    todos_detalles = []
    metadata = {
        "train_seasons": TRAIN_SEASONS,
        "selection_season": SELECTION_SEASON,
        "confirmation_season": CONFIRMATION_SEASON,
        "oos_season": OOS_SEASON,
        "objetivos": {},
    }

    for objetivo, configuracion in OBJETIVOS.items():
        print("\n" + "=" * 76)
        print(f"OBJETIVO: {objetivo}")
        print("=" * 76)

        df = datasets[configuracion["dataset"]]
        features_base = (
            FEATURES_PASE
            if configuracion["dataset"] == "pase"
            else FEATURES_CARRERA
        )
        features_lesiones = list(dict.fromkeys(features_base + FEATURES_LESIONES))
        train, seleccion, confirmacion, oos = dividir(df)
        evaluaciones = [seleccion, confirmacion, oos]

        _, resultados_control, detalles_control = entrenar_variante(
            train,
            evaluaciones,
            objetivo,
            "control",
            features_base,
            configuracion,
        )
        _, resultados_lesiones, detalles_lesiones = entrenar_variante(
            train,
            evaluaciones,
            objetivo,
            "lesiones",
            features_lesiones,
            configuracion,
        )

        seleccionada = seleccionar_variante(
            resultados_control, resultados_lesiones
        )
        print("\nComparacion lesiones vs control:")
        for temporada in [2024, 2025, 2026]:
            rc = resultado_temporada(resultados_control, temporada)
            rl = resultado_temporada(resultados_lesiones, temporada)
            print(
                f"{temporada}: control {rc['mae']:.4f} | "
                f"lesiones {rl['mae']:.4f} | "
                f"cambio {rl['mae'] - rc['mae']:+.4f}"
            )
        print(f"Modelo seleccionado: {seleccionada}")

        features_produccion = (
            features_lesiones if seleccionada == "lesiones" else features_base
        )
        columnas_produccion = list(dict.fromkeys(
            features_produccion + FEATURES_CATEGORICAS
        ))
        desarrollo_completo = df[df["season"].between(2012, 2025)].copy()
        modelo_produccion = construir_pipeline(
            features_produccion, configuracion["loss"]
        )
        modelo_produccion.fit(
            desarrollo_completo[columnas_produccion],
            desarrollo_completo[objetivo],
        )
        ruta_modelo = DIRECTORIO_MODELOS / configuracion["archivo"]
        joblib.dump(modelo_produccion, ruta_modelo)
        print(f"Modelo de produccion guardado en: {ruta_modelo}")

        todos_resultados.extend(resultados_control + resultados_lesiones)
        todos_detalles.extend(detalles_control + detalles_lesiones)
        metadata["objetivos"][objetivo] = {
            "dataset": configuracion["dataset"],
            "archivo": configuracion["archivo"],
            "loss": configuracion["loss"],
            "baseline": configuracion["baseline"],
            "variante_seleccionada": seleccionada,
            "features_numericas": features_produccion,
            "features_categoricas": FEATURES_CATEGORICAS,
            "n_train_produccion": int(len(desarrollo_completo)),
            "resultados": resultados_control + resultados_lesiones,
        }

    pd.concat(todos_detalles, ignore_index=True).to_csv(
        RUTA_PREDICCIONES, index=False
    )
    metadata["resumen_resultados"] = todos_resultados
    RUTA_METADATA.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 76)
    print("ARCHIVOS GENERADOS")
    print("=" * 76)
    for configuracion in OBJETIVOS.values():
        print(DIRECTORIO_MODELOS / configuracion["archivo"])
    print(RUTA_PREDICCIONES)
    print(RUTA_METADATA)
    print("\nEntrenamiento terminado correctamente.")


if __name__ == "__main__":
    main()
