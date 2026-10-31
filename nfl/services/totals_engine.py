"""Servicio extraído del predictor NFL; conserva sus cálculos originales."""
import numpy as np
import pandas as pd
from nfl.feature_spec import FEATURES_BASE, FEATURES_CATEGORICAS, FEATURES_MERCADO
EDGE_MINIMO = 3.0
NFL_TOTALS_INTERCEPT_BIAS = 1.10  # Ajuste de calibración empírica (modelo 2012-2024 vs entorno anotador 2024-2026)

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

def obtener_columnas_modelo(modelo, columnas_respaldo):
    """Lee las columnas reales del joblib seleccionado por el entrenador."""
    columnas = getattr(modelo, "feature_names_in_", None)
    if columnas is None:
        return columnas_respaldo
    return list(columnas)

def generar_predicciones(

    df,

    modelo_mercado,

    modelo_base,

    calibrador,

):

    resultado = df.copy()

    columnas_mercado = obtener_columnas_modelo(
        modelo_mercado,
        FEATURES_MERCADO + FEATURES_CATEGORICAS,
    )

    columnas_base = obtener_columnas_modelo(
        modelo_base,
        FEATURES_BASE + FEATURES_CATEGORICAS,
    )

    faltantes = sorted(
        set(columnas_mercado + columnas_base) - set(resultado.columns)
    )
    if faltantes:
        raise KeyError(
            "Faltan variables requeridas por los modelos: "
            + ", ".join(faltantes)
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

    ] = predicciones - NFL_TOTALS_INTERCEPT_BIAS

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

    es_over = resultado["pick"] == "OVER"
    es_under = resultado["pick"] == "UNDER"

    # Regla Simétrica Cuantitativa para Totales:
    # 1. Ambos lados requieren edge_absoluto >= EDGE_MINIMO y EV > 0.
    # 2. Protección simétrica para extremos de mercado:
    #    - OVER: En líneas infladas (total_line >= 51.5), requiere edge >= 3.5.
    #    - UNDER: En líneas deprimidas (total_line <= 39.5), requiere edge >= 3.5 o viento adverso (>= 12 mph).
    linea_val = pd.to_numeric(resultado["total_line"], errors="coerce").fillna(0.0)
    wind_raw = resultado["wind"] if "wind" in resultado else 0.0
    wind_val = pd.to_numeric(wind_raw, errors="coerce")
    if isinstance(wind_val, pd.Series):
        wind_val = wind_val.fillna(0.0)
    else:
        wind_val = float(wind_val or 0.0)

    over_valido = es_over & ((linea_val < 51.5) | (resultado["edge_absoluto"] >= 3.5))
    under_valido = es_under & ((linea_val > 39.5) | (resultado["edge_absoluto"] >= 3.5) | (wind_val >= 12.0))

    valido_para_pick = (
        cumple_edge
        & cumple_ev
        & (over_valido | under_valido)
    )

    resultado.loc[
        con_linea,
        "estado"
    ] = "NO PICK"

    resultado.loc[
        valido_para_pick,
        "estado"
    ] = "PICK"

    return resultado
