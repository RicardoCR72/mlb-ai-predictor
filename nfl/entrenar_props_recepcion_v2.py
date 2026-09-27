"""Entrena modelos NFL de recepciones y yardas recibidas."""

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
RUTA_DATASET = (
    RAIZ_PROYECTO
    / "data" / "nfl" / "processed"
    / "nfl_props_recepcion_features_2012_2026.parquet"
)
DIRECTORIO_MODELOS = RAIZ_PROYECTO / "modelos_nfl" / "props"
RUTA_PREDICCIONES = DIRECTORIO_MODELOS / "predicciones_validacion_recepcion.csv"
RUTA_METADATA = DIRECTORIO_MODELOS / "metadata_props_recepcion.json"

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

FEATURES_NUMERICAS_BASE = [
    "player_games_before",
    "player_games_before_season",
    "is_home",
    "rest",
    "temp",
    "wind",
    "qb_change",
    "player_receiving_yards_std_5",
    "player_receiving_yards_std_8",
    "player_catch_rate_5",
    "player_yards_per_target_5",
]

for metrica in [
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_air_yards",
    "receiving_yards_after_catch",
    "target_share",
    "air_yards_share",
]:
    for ventana in [3, 5, 8]:
        FEATURES_NUMERICAS_BASE.append(f"player_{metrica}_avg_{ventana}")
    FEATURES_NUMERICAS_BASE.append(f"player_{metrica}_avg_season")

for metrica in ["team_targets", "team_receptions", "team_receiving_yards"]:
    for ventana in [3, 5, 8]:
        FEATURES_NUMERICAS_BASE.append(f"{metrica}_avg_{ventana}")

for metrica in [
    "allowed_targets",
    "allowed_receptions",
    "allowed_receiving_yards",
]:
    for ventana in [3, 5, 8]:
        FEATURES_NUMERICAS_BASE.append(f"opp_pos_{metrica}_avg_{ventana}")

FEATURES_LESIONES = [
    "player_injury_score",
    "team_skill_injury_score",
    "team_skill_injury_count",
    "teammate_skill_injury_score",
]

FEATURES_BASE = list(dict.fromkeys(FEATURES_NUMERICAS_BASE))
FEATURES_CON_LESIONES = list(dict.fromkeys(FEATURES_BASE + FEATURES_LESIONES))

OBJETIVOS = {
    "receptions": {
        "archivo": "props_receptions.joblib",
        "baseline": "player_receptions_avg_5",
        "loss": "poisson",
    },
    "receiving_yards": {
        "archivo": "props_receiving_yards.joblib",
        "baseline": "player_receiving_yards_avg_5",
        "loss": "squared_error",
    },
}


def cargar_dataset():
    if not RUTA_DATASET.exists():
        raise FileNotFoundError(f"No se encontro: {RUTA_DATASET}")
    df = pd.read_parquet(RUTA_DATASET)
    df["gameday"] = pd.to_datetime(df["gameday"], errors="coerce")
    df = df[
        (df["player_games_before"] >= 3)
        & (df["player_targets_avg_5"] >= 1.0)
    ].copy()
    df = df.replace([np.inf, -np.inf], np.nan)
    return df.sort_values(
        ["season", "week", "gameday", "game_id", "player_id"]
    ).reset_index(drop=True)


def validar_columnas(df):
    requeridas = set(
        FEATURES_CON_LESIONES
        + FEATURES_CATEGORICAS
        + list(OBJETIVOS)
    )
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
    modelo = HistGradientBoostingRegressor(
        loss=loss,
        learning_rate=0.04,
        max_iter=350,
        max_leaf_nodes=23,
        min_samples_leaf=45,
        l2_regularization=3.0,
        early_stopping=False,
        random_state=42,
    )
    return Pipeline(
        steps=[
            ("preprocesamiento", preprocesador),
            ("modelo", modelo),
        ]
    )


def evaluar(conjunto, predicciones, objetivo, variante, baseline_columna):
    detalle = conjunto[
        [
            "game_id", "season", "week", "gameday", "player_id",
            "player_name", "position", "team", "opponent_team", objetivo,
        ]
    ].copy()
    detalle["objetivo"] = objetivo
    detalle["variante"] = variante
    detalle["prediccion"] = np.maximum(predicciones, 0)
    detalle["baseline"] = conjunto[baseline_columna].to_numpy()
    detalle["error"] = detalle["prediccion"] - detalle[objetivo]
    detalle["error_absoluto"] = detalle["error"].abs()

    resultado = {
        "objetivo": objetivo,
        "variante": variante,
        "temporada": int(conjunto["season"].iloc[0]),
        "filas": int(len(conjunto)),
        "mae": float(mean_absolute_error(detalle[objetivo], detalle["prediccion"])),
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
    print("-" * 72)
    print(
        f"{resultado['objetivo']} | {resultado['variante']} | "
        f"Temporada {resultado['temporada']}"
    )
    print("-" * 72)
    print(f"Filas: {resultado['filas']:,}")
    print(f"MAE modelo: {resultado['mae']:.4f}")
    print(f"MAE baseline rolling-5: {resultado['mae_baseline']:.4f}")
    print(f"RMSE: {resultado['rmse']:.4f}")
    print(f"Bias: {resultado['bias']:+.4f}")
    print(f"Media real: {resultado['media_real']:.4f}")
    print(f"Media predicha: {resultado['media_predicha']:.4f}")


def entrenar_variante(
    objetivo,
    variante,
    features,
    train,
    conjuntos,
    baseline_columna,
    loss,
):
    columnas = features + FEATURES_CATEGORICAS
    pipeline = construir_pipeline(features, loss)
    pipeline.fit(train[columnas], train[objetivo])

    resultados = []
    detalles = []
    for _, conjunto in conjuntos.items():
        if conjunto.empty:
            continue
        predicciones = pipeline.predict(conjunto[columnas])
        resultado, detalle = evaluar(
            conjunto,
            predicciones,
            objetivo,
            variante,
            baseline_columna,
        )
        resultados.append(resultado)
        detalles.append(detalle)
        imprimir_resultado(resultado)
    return pipeline, resultados, detalles


def aprobar_lesiones(control, lesiones):
    control_temporada = {r["temporada"]: r for r in control}
    cambios = {}
    for resultado in lesiones:
        referencia = control_temporada[resultado["temporada"]]
        cambio = resultado["mae"] - referencia["mae"]
        cambios[resultado["temporada"]] = cambio
        print(
            f"{resultado['temporada']}: control {referencia['mae']:.4f} | "
            f"lesiones {resultado['mae']:.4f} | cambio {cambio:+.4f}"
        )
    return (
        cambios.get(SELECTION_SEASON, np.inf) < 0
        and cambios.get(CONFIRMATION_SEASON, np.inf) <= 0
    )


def renombrar_detalles(detalles, variante):
    salida = []
    for detalle in detalles:
        copia = detalle.copy()
        copia["variante"] = variante
        salida.append(copia)
    return salida


def main():
    DIRECTORIO_MODELOS.mkdir(parents=True, exist_ok=True)
    print("Cargando dataset de props...")
    df = cargar_dataset()
    validar_columnas(df)

    train = df[df["season"].isin(TRAIN_SEASONS)].copy()
    seleccion = df[df["season"] == SELECTION_SEASON].copy()
    confirmacion = df[df["season"] == CONFIRMATION_SEASON].copy()
    oos = df[df["season"] == OOS_SEASON].copy()
    conjuntos = {
        "seleccion_2024": seleccion,
        "confirmacion_2025": confirmacion,
        "oos_2026": oos,
    }

    print("\nDivision temporal:")
    print(f"Train 2012-2023: {len(train):,}")
    print(f"Seleccion 2024: {len(seleccion):,}")
    print(f"Confirmacion 2025: {len(confirmacion):,}")
    print(f"OOS 2026: {len(oos):,}")
    print(
        f"Features: {len(FEATURES_BASE)} base + "
        f"{len(FEATURES_LESIONES)} de lesiones"
    )

    metadata_objetivos = {}
    predicciones_seleccionadas = []
    todos_resultados = []

    for objetivo, configuracion in OBJETIVOS.items():
        print("\n" + "=" * 72)
        print(f"OBJETIVO: {objetivo}")
        print("=" * 72)

        modelo_control, resultados_control, detalles_control = entrenar_variante(
            objetivo,
            "control",
            FEATURES_BASE,
            train,
            conjuntos,
            configuracion["baseline"],
            configuracion["loss"],
        )
        modelo_lesiones, resultados_lesiones, detalles_lesiones = entrenar_variante(
            objetivo,
            "lesiones",
            FEATURES_CON_LESIONES,
            train,
            conjuntos,
            configuracion["baseline"],
            configuracion["loss"],
        )

        print("\nComparacion lesiones vs control:")
        lesiones_aprobadas = aprobar_lesiones(
            resultados_control,
            resultados_lesiones,
        )

        if lesiones_aprobadas:
            features_seleccionadas = FEATURES_CON_LESIONES
            detalles_seleccionados = detalles_lesiones
            variante_seleccionada = "lesiones"
        else:
            features_seleccionadas = FEATURES_BASE
            detalles_seleccionados = detalles_control
            variante_seleccionada = "control"

        # Reentrena la configuracion elegida con todos los juegos terminados,
        # incluidos los disponibles de 2026, para la prediccion de la semana actual.
        columnas = features_seleccionadas + FEATURES_CATEGORICAS
        modelo_produccion = construir_pipeline(
            features_seleccionadas,
            configuracion["loss"],
        )
        modelo_produccion.fit(df[columnas], df[objetivo])
        ruta_modelo = DIRECTORIO_MODELOS / configuracion["archivo"]
        joblib.dump(modelo_produccion, ruta_modelo)

        predicciones_seleccionadas.extend(
            renombrar_detalles(detalles_seleccionados, variante_seleccionada)
        )
        todos_resultados.extend(resultados_control + resultados_lesiones)
        metadata_objetivos[objetivo] = {
            "variant_selected": variante_seleccionada,
            "features": features_seleccionadas,
            "model_path": str(ruta_modelo),
            "production_rows": int(len(df)),
            "production_last_gameday": str(df["gameday"].max().date()),
            "loss": configuracion["loss"],
        }
        print(f"Modelo seleccionado: {variante_seleccionada}")
        print(f"Guardado en: {ruta_modelo}")

    pd.concat(predicciones_seleccionadas, ignore_index=True).to_csv(
        RUTA_PREDICCIONES,
        index=False,
    )
    metadata = {
        "train_seasons": TRAIN_SEASONS,
        "selection_season": SELECTION_SEASON,
        "confirmation_season": CONFIRMATION_SEASON,
        "oos_season": OOS_SEASON,
        "eligibility": {
            "player_games_before_min": 3,
            "player_targets_avg_5_min": 1.0,
        },
        "categorical_features": FEATURES_CATEGORICAS,
        "injury_features_tested": FEATURES_LESIONES,
        "targets": metadata_objetivos,
        "results": todos_resultados,
    }
    with open(RUTA_METADATA, "w", encoding="utf-8") as archivo:
        json.dump(metadata, archivo, ensure_ascii=False, indent=2)

    print("\n" + "=" * 72)
    print("ARCHIVOS GENERADOS")
    print("=" * 72)
    print(RUTA_PREDICCIONES)
    print(RUTA_METADATA)
    print("\nEntrenamiento terminado correctamente.")


if __name__ == "__main__":
    main()
