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

from features_lesiones import FEATURES_LESIONES_MODELO





RAIZ_PROYECTO = Path(__file__).resolve().parents[1]



RUTA_DATASET = (

    RAIZ_PROYECTO

    / "data"

    / "nfl"

    / "processed"

    / "nfl_games_features_2012_2026.parquet"

)



DIRECTORIO_MODELOS = (

    RAIZ_PROYECTO

    / "modelos_nfl"

)



RUTA_PREDICCIONES = (

    DIRECTORIO_MODELOS

    / "predicciones_totales_validacion.csv"

)



TEMPORADAS_ENTRENAMIENTO = list(range(2012, 2024))

TEMPORADA_SELECCION = 2024

TEMPORADA_CONFIRMACION = 2025

TEMPORADA_OOS = 2026





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



if len(FEATURES_BASE) != len(set(FEATURES_BASE)):

    raise ValueError(

        "FEATURES_BASE contiene columnas duplicadas."

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





def cargar_dataset():

    if not RUTA_DATASET.exists():

        raise FileNotFoundError(

            f"No se encontró el dataset: {RUTA_DATASET}"

        )



    df = pd.read_parquet(RUTA_DATASET)



    df["gameday"] = pd.to_datetime(

        df["gameday"],

        errors="coerce"

    )



    df = df.sort_values(

        ["season", "week", "gameday", "game_id"]

    ).reset_index(drop=True)



    return df





def validar_features(df, features):

    faltantes = [

        columna

        for columna in features + FEATURES_CATEGORICAS

        if columna not in df.columns

    ]



    if faltantes:

        raise KeyError(

            "Faltan columnas en el dataset: "

            + ", ".join(faltantes)

        )





def construir_pipeline(features_numericas):

    preprocesador = ColumnTransformer(

        transformers=[

            (

                "numericas",

                SimpleImputer(

                    strategy="median",

                    add_indicator=True

                ),

                features_numericas,

            ),

            (

                "categoricas",

                Pipeline(

                    steps=[

                        (

                            "imputar",

                            SimpleImputer(

                                strategy="most_frequent"

                            ),

                        ),

                        (

                            "one_hot",

                            OneHotEncoder(

                                handle_unknown="ignore",

                                sparse_output=False

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

        loss="squared_error",

        learning_rate=0.04,

        max_iter=350,

        max_leaf_nodes=15,

        min_samples_leaf=30,

        l2_regularization=2.0,

        early_stopping=False,

        random_state=42,

    )



    return Pipeline(

        steps=[

            ("preprocesamiento", preprocesador),

            ("modelo", modelo),

        ]

    )





def dividir_dataset(df):

    train = df[

        df["season"].isin(TEMPORADAS_ENTRENAMIENTO)

    ].copy()



    seleccion = df[

        df["season"] == TEMPORADA_SELECCION

    ].copy()



    confirmacion = df[

        df["season"] == TEMPORADA_CONFIRMACION

    ].copy()



    oos = df[

        df["season"] == TEMPORADA_OOS

    ].copy()



    return train, seleccion, confirmacion, oos





def evaluar_predicciones(df, predicciones, nombre_modelo):

    evaluacion = df.copy()

    evaluacion["modelo"] = nombre_modelo

    evaluacion["pred_total"] = predicciones



    evaluacion["error"] = (

        evaluacion["pred_total"]

        - evaluacion["total_points"]

    )



    evaluacion["error_absoluto"] = (

        evaluacion["error"].abs()

    )



    mae = mean_absolute_error(

        evaluacion["total_points"],

        evaluacion["pred_total"],

    )



    rmse = np.sqrt(

        mean_squared_error(

            evaluacion["total_points"],

            evaluacion["pred_total"],

        )

    )



    bias = evaluacion["error"].mean()



    resultado = {

        "modelo": nombre_modelo,

        "temporada": int(evaluacion["season"].iloc[0]),

        "partidos": int(len(evaluacion)),

        "mae": float(mae),

        "rmse": float(rmse),

        "bias": float(bias),

        "media_real": float(

            evaluacion["total_points"].mean()

        ),

        "media_predicha": float(

            evaluacion["pred_total"].mean()

        ),

    }



    con_linea = evaluacion[

        evaluacion["total_line"].notna()

    ].copy()



    if not con_linea.empty:

        resultado["mae_linea_mercado"] = float(

            mean_absolute_error(

                con_linea["total_points"],

                con_linea["total_line"],

            )

        )



        sin_push = con_linea[

            con_linea["total_points"]

            != con_linea["total_line"]

        ].copy()



        if not sin_push.empty:

            pick_over = (

                sin_push["pred_total"]

                > sin_push["total_line"]

            )



            resultado["acierto_lado_total"] = float(

                (

                    pick_over.astype(int)

                    == sin_push["over_result"].astype(int)

                ).mean()

            )



            resultado["apuestas_evaluadas"] = int(

                len(sin_push)

            )



    columnas_salida = [

        "game_id",

        "season",

        "week",

        "gameday",

        "away_team",

        "home_team",

        "total_points",

        "total_line",

        "over_odds",

        "under_odds",

        "modelo",

        "pred_total",

        "error",

        "error_absoluto",

        "over_result",

        "push_total",

    ]



    columnas_disponibles = [

        columna

        for columna in columnas_salida

        if columna in evaluacion.columns

    ]



    return resultado, evaluacion[columnas_disponibles]





def imprimir_resultado(resultado):

    print("-" * 65)

    print(

        f"{resultado['modelo']} | "

        f"Temporada {resultado['temporada']}"

    )

    print("-" * 65)

    print(f"Partidos: {resultado['partidos']}")

    print(f"MAE modelo: {resultado['mae']:.4f}")

    print(f"RMSE: {resultado['rmse']:.4f}")

    print(f"Bias: {resultado['bias']:+.4f}")

    print(

        f"Media real: "

        f"{resultado['media_real']:.4f}"

    )

    print(

        f"Media predicha: "

        f"{resultado['media_predicha']:.4f}"

    )



    if "mae_linea_mercado" in resultado:

        print(

            f"MAE línea mercado: "

            f"{resultado['mae_linea_mercado']:.4f}"

        )

    if "acierto_lado_total" in resultado:
        print(
            f"Acierto Over/Under: "
            f"{resultado['acierto_lado_total'] * 100:.2f}%"
        )
        print(
            f"Partidos O/U evaluados: "
            f"{resultado['apuestas_evaluadas']}"
        )


def comparar_con_control(control, lesiones):
    """Muestra el cambio de MAE; negativo significa mejora."""
    por_temporada = {
        resultado["temporada"]: resultado
        for resultado in control
    }

    print("\n" + "=" * 70)
    print("IMPACTO DE LAS VARIABLES DE LESIONES")
    print("=" * 70)

    cambios = {}
    for resultado in lesiones:
        referencia = por_temporada.get(resultado["temporada"])
        if referencia is None:
            continue

        delta_mae = resultado["mae"] - referencia["mae"]
        cambios[resultado["temporada"]] = delta_mae
        print(
            f"{resultado['temporada']}: "
            f"MAE control {referencia['mae']:.4f} | "
            f"MAE lesiones {resultado['mae']:.4f} | "
            f"cambio {delta_mae:+.4f}"
        )

    aprobado = (
        cambios.get(TEMPORADA_SELECCION, np.inf) < 0
        and cambios.get(TEMPORADA_CONFIRMACION, np.inf) <= 0
    )
    if aprobado:
        print("RECOMENDACIÓN: adoptar el modelo con lesiones.")
    else:
        print(
            "ADVERTENCIA: las lesiones no mejoraron 2024 y confirmaron "
            "en 2025. Revisa los resultados antes de publicar los modelos."
        )
    return aprobado
def entrenar_modelo(

    nombre,

    features,

    train,

    conjuntos_evaluacion,

):

    print("\n" + "=" * 70)

    print(f"ENTRENANDO: {nombre}")

    print("=" * 70)



    validar_features(train, features)



    columnas_modelo = features + FEATURES_CATEGORICAS



    train_limpio = train[

        train["total_points"].notna()

    ].copy()



    X_train = train_limpio[columnas_modelo]

    y_train = train_limpio["total_points"]



    pipeline = construir_pipeline(features)



    print(

        f"Entrenando con {len(train_limpio):,} partidos..."

    )



    pipeline.fit(X_train, y_train)



    resultados = []

    predicciones_guardadas = []



    for nombre_conjunto, conjunto in conjuntos_evaluacion.items():

        if conjunto.empty:

            print(

                f"\nSin partidos disponibles para "

                f"{nombre_conjunto}."

            )

            continue



        X = conjunto[columnas_modelo]

        predicciones = pipeline.predict(X)



        resultado, detalle = evaluar_predicciones(

            conjunto,

            predicciones,

            nombre,

        )



        resultado["conjunto"] = nombre_conjunto



        resultados.append(resultado)

        predicciones_guardadas.append(detalle)



        imprimir_resultado(resultado)



    return (

        pipeline,

        resultados,

        predicciones_guardadas,

    )





def main():
    DIRECTORIO_MODELOS.mkdir(parents=True, exist_ok=True)

    print("Cargando dataset...")
    df = cargar_dataset()
    train, seleccion, confirmacion, oos = dividir_dataset(df)

    print("\nDivisión temporal:")
    print(f"Train 2012-2023: {len(train):,}")
    print(f"Selección 2024: {len(seleccion):,}")
    print(f"Confirmación 2025: {len(confirmacion):,}")
    print(f"OOS 2026: {len(oos):,}")

    conjuntos = {
        "seleccion_2024": seleccion,
        "confirmacion_2025": confirmacion,
        "oos_2026": oos,
    }

    print(
        f"\nFeatures base: {len(FEATURES_BASE_SIN_LESIONES)} "
        f"+ {len(FEATURES_LESIONES_MODELO)} compactas de lesiones"
    )

    modelo_base_control, resultados_base_control, pred_base_control = (
        entrenar_modelo(
            nombre="total_sin_mercado_control",
            features=FEATURES_BASE_SIN_LESIONES,
            train=train,
            conjuntos_evaluacion=conjuntos,
        )
    )
    modelo_mercado_control, resultados_mercado_control, pred_mercado_control = (
        entrenar_modelo(
            nombre="total_con_mercado_control",
            features=FEATURES_MERCADO_SIN_LESIONES,
            train=train,
            conjuntos_evaluacion=conjuntos,
        )
    )
    modelo_base_lesiones, resultados_base_lesiones, pred_base_lesiones = (
        entrenar_modelo(
            nombre="total_sin_mercado_lesiones_compactas",
            features=FEATURES_BASE,
            train=train,
            conjuntos_evaluacion=conjuntos,
        )
    )
    modelo_mercado_lesiones, resultados_mercado_lesiones, pred_mercado_lesiones = (
        entrenar_modelo(
            nombre="total_con_mercado_lesiones_compactas",
            features=FEATURES_MERCADO,
            train=train,
            conjuntos_evaluacion=conjuntos,
        )
    )

    print("\nCOMPARACIÓN DEL MODELO SIN MERCADO")
    base_aprobado = comparar_con_control(
        resultados_base_control,
        resultados_base_lesiones,
    )
    print("\nCOMPARACIÓN DEL MODELO CON MERCADO")
    mercado_aprobado = comparar_con_control(
        resultados_mercado_control,
        resultados_mercado_lesiones,
    )

    if base_aprobado:
        modelo_base = modelo_base_lesiones
        pred_base = pred_base_lesiones
        features_base_produccion = FEATURES_BASE
        version_base = "lesiones_compactas"
    else:
        modelo_base = modelo_base_control
        pred_base = pred_base_control
        features_base_produccion = FEATURES_BASE_SIN_LESIONES
        version_base = "control_sin_lesiones"

    if mercado_aprobado:
        modelo_mercado = modelo_mercado_lesiones
        pred_mercado = pred_mercado_lesiones
        features_mercado_produccion = FEATURES_MERCADO
        version_mercado = "lesiones_compactas"
    else:
        modelo_mercado = modelo_mercado_control
        pred_mercado = pred_mercado_control
        features_mercado_produccion = FEATURES_MERCADO_SIN_LESIONES
        version_mercado = "control_sin_lesiones"

    print("\n" + "=" * 70)
    print("MODELOS SELECCIONADOS PARA PRODUCCIÓN")
    print("=" * 70)
    print(f"Sin mercado: {version_base}")
    print(f"Con mercado: {version_mercado}")

    ruta_modelo_base = DIRECTORIO_MODELOS / "total_sin_mercado.joblib"
    ruta_modelo_mercado = DIRECTORIO_MODELOS / "total_con_mercado.joblib"
    joblib.dump(modelo_base, ruta_modelo_base)
    joblib.dump(modelo_mercado, ruta_modelo_mercado)

    for detalle in pred_base:
        detalle["modelo"] = "total_sin_mercado"
    for detalle in pred_mercado:
        detalle["modelo"] = "total_con_mercado"

    todas_predicciones = pred_base + pred_mercado
    if todas_predicciones:
        pd.concat(todas_predicciones, ignore_index=True).to_csv(
            RUTA_PREDICCIONES,
            index=False,
        )

    metadata = {
        "target": "total_points",
        "train_seasons": TEMPORADAS_ENTRENAMIENTO,
        "selection_season": TEMPORADA_SELECCION,
        "confirmation_season": TEMPORADA_CONFIRMACION,
        "oos_season": TEMPORADA_OOS,
        "features_base": features_base_produccion,
        "features_market": features_mercado_produccion,
        "injury_features_tested": FEATURES_LESIONES_MODELO,
        "base_model_selected": version_base,
        "market_model_selected": version_mercado,
        "categorical_features": FEATURES_CATEGORICAS,
        "results": (
            resultados_base_control
            + resultados_mercado_control
            + resultados_base_lesiones
            + resultados_mercado_lesiones
        ),
    }



    ruta_metadata = (

        DIRECTORIO_MODELOS

        / "metadata_totales.json"

    )



    with open(

        ruta_metadata,

        "w",

        encoding="utf-8"

    ) as archivo:

        json.dump(

            metadata,

            archivo,

            ensure_ascii=False,

            indent=2

        )



    print("\n" + "=" * 70)

    print("ARCHIVOS GENERADOS")

    print("=" * 70)

    print(ruta_modelo_base)

    print(ruta_modelo_mercado)

    print(RUTA_PREDICCIONES)

    print(ruta_metadata)

    print("\nEntrenamiento terminado correctamente.")





if __name__ == "__main__":

    main()
