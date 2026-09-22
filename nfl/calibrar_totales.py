import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]

RUTA_PREDICCIONES = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "predicciones_totales_validacion.csv"
)

DIRECTORIO_MODELOS = (
    RAIZ_PROYECTO
    / "modelos_nfl"
)

RUTA_CALIBRADOR = (
    DIRECTORIO_MODELOS
    / "calibrador_totales_logistico.joblib"
)

RUTA_SALIDA = (
    DIRECTORIO_MODELOS
    / "predicciones_totales_calibradas.csv"
)

RUTA_METRICAS = (
    DIRECTORIO_MODELOS
    / "metricas_calibracion_totales.json"
)

MODELO_SELECCIONADO = "total_con_mercado"
TEMPORADA_CALIBRACION = 2024
TEMPORADA_CONFIRMACION = 2025
TEMPORADA_OOS = 2026
EDGE_MINIMO = 3.0


def calcular_ece(y_real, probabilidades, bins=10):
    y_real = np.asarray(y_real)
    probabilidades = np.asarray(probabilidades)

    limites = np.linspace(0, 1, bins + 1)

    indices = np.digitize(
        probabilidades,
        limites[1:-1],
        right=True,
    )

    ece = 0.0

    for indice in range(bins):
        mascara = indices == indice

        if not mascara.any():
            continue

        confianza_media = probabilidades[mascara].mean()
        frecuencia_real = y_real[mascara].mean()
        peso = mascara.mean()

        ece += peso * abs(
            confianza_media - frecuencia_real
        )

    return float(ece)


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


def cargar_predicciones():
    if not RUTA_PREDICCIONES.exists():
        raise FileNotFoundError(
            "No se encontró el archivo de predicciones."
        )

    df = pd.read_csv(RUTA_PREDICCIONES)

    df = df[
        df["modelo"] == MODELO_SELECCIONADO
    ].copy()

    columnas_numericas = [
        "season",
        "total_points",
        "total_line",
        "pred_total",
        "over_odds",
        "under_odds",
        "over_result",
        "push_total",
    ]

    for columna in columnas_numericas:
        df[columna] = pd.to_numeric(
            df[columna],
            errors="coerce",
        )

    df = df[
        df["pred_total"].notna()
        & df["total_line"].notna()
        & df["over_result"].notna()
        & df["total_points"].notna()
    ].copy()

    # Los pushes no forman parte de la calibración binaria.
    df = df[
        df["total_points"] != df["total_line"]
    ].copy()

    df["edge"] = (
        df["pred_total"] - df["total_line"]
    )

    df["edge_absoluto"] = df["edge"].abs()

    df["over_result"] = (
        df["over_result"].astype(int)
    )

    return df


def entrenar_calibrador(df):
    calibracion = df[
        df["season"] == TEMPORADA_CALIBRACION
    ].copy()

    if calibracion.empty:
        raise ValueError(
            "No hay predicciones de 2024 para calibrar."
        )

    X = calibracion[["edge"]]
    y = calibracion["over_result"]

    calibrador = LogisticRegression(
        C=1.0,
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )

    calibrador.fit(X, y)

    print(
        f"Calibrador entrenado con "
        f"{len(calibracion)} partidos de 2024."
    )

    print(
        "Intercepto:",
        round(float(calibrador.intercept_[0]), 6)
    )

    print(
        "Coeficiente edge:",
        round(float(calibrador.coef_[0][0]), 6)
    )

    return calibrador


def agregar_probabilidades(df, calibrador):
    resultado = df.copy()

    resultado["prob_over"] = calibrador.predict_proba(
        resultado[["edge"]]
    )[:, 1]

    resultado["prob_under"] = (
        1 - resultado["prob_over"]
    )

    # Conservamos el lado que ya validamos en el backtest:
    # edge positivo = Over, edge negativo = Under.
    resultado["pick"] = np.where(
        resultado["edge"] > 0,
        "OVER",
        "UNDER",
    )

    resultado["prob_pick"] = np.where(
        resultado["pick"] == "OVER",
        resultado["prob_over"],
        resultado["prob_under"],
    )

    resultado["pick_correcto"] = np.where(
        resultado["pick"] == "OVER",
        resultado["over_result"] == 1,
        resultado["over_result"] == 0,
    )

    resultado["odds_pick"] = np.where(
        resultado["pick"] == "OVER",
        resultado["over_odds"],
        resultado["under_odds"],
    )

    resultado["decimal_pick"] = (
        resultado["odds_pick"].apply(
            american_a_decimal
        )
    )

    resultado["prob_break_even"] = np.where(
        resultado["decimal_pick"].notna(),
        1 / resultado["decimal_pick"],
        np.nan,
    )

    resultado["edge_probabilidad"] = (
        resultado["prob_pick"]
        - resultado["prob_break_even"]
    )

    resultado["ev"] = np.where(
        resultado["decimal_pick"].notna(),
        (
            resultado["prob_pick"]
            * resultado["decimal_pick"]
        ) - 1,
        np.nan,
    )

    resultado["profit"] = np.where(
        resultado["pick_correcto"],
        resultado["decimal_pick"] - 1,
        -1.0,
    )

    return resultado


def evaluar_temporada(df, temporada):
    muestra = df[
        df["season"] == temporada
    ].copy()

    if muestra.empty:
        return None

    y = muestra["over_result"]
    prob = muestra["prob_over"]

    pred_clase = (
        prob >= 0.5
    ).astype(int)

    metricas = {
        "season": int(temporada),
        "partidos": int(len(muestra)),
        "logloss": float(log_loss(y, prob)),
        "brier": float(
            brier_score_loss(y, prob)
        ),
        "auc": float(
            roc_auc_score(y, prob)
        ),
        "ece_10": calcular_ece(
            y,
            prob,
            bins=10,
        ),
        "accuracy_calibrador": float(
            accuracy_score(y, pred_clase)
        ),
        "media_prob_over": float(
            prob.mean()
        ),
        "frecuencia_real_over": float(
            y.mean()
        ),
    }

    filtrados = muestra[
        muestra["edge_absoluto"] >= EDGE_MINIMO
    ].copy()

    metricas["edge_minimo"] = EDGE_MINIMO
    metricas["picks_filtrados"] = int(
        len(filtrados)
    )

    if not filtrados.empty:
        metricas["accuracy_filtrada"] = float(
            filtrados["pick_correcto"].mean()
        )

        con_odds = filtrados[
            filtrados["profit"].notna()
        ]

        if not con_odds.empty:
            metricas["roi_filtrado"] = float(
                con_odds["profit"].sum()
                / len(con_odds)
            )

            metricas["ev_promedio"] = float(
                con_odds["ev"].mean()
            )

            metricas["prob_pick_media"] = float(
                con_odds["prob_pick"].mean()
            )

    return metricas


def imprimir_metricas(metricas):
    print("\n" + "-" * 65)
    print(f"TEMPORADA {metricas['season']}")
    print("-" * 65)

    print(f"Partidos: {metricas['partidos']}")
    print(f"Log loss: {metricas['logloss']:.6f}")
    print(f"Brier: {metricas['brier']:.6f}")
    print(f"AUC: {metricas['auc']:.6f}")
    print(f"ECE10: {metricas['ece_10']:.6f}")

    print(
        "Probabilidad Over media:",
        f"{metricas['media_prob_over']:.2%}"
    )

    print(
        "Frecuencia Over real:",
        f"{metricas['frecuencia_real_over']:.2%}"
    )

    print(
        f"Picks con edge >= {EDGE_MINIMO}:",
        metricas["picks_filtrados"]
    )

    if "accuracy_filtrada" in metricas:
        print(
            "Acierto filtrado:",
            f"{metricas['accuracy_filtrada']:.2%}"
        )

    if "roi_filtrado" in metricas:
        print(
            "ROI filtrado:",
            f"{metricas['roi_filtrado']:.2%}"
        )

    if "prob_pick_media" in metricas:
        print(
            "Probabilidad media del pick:",
            f"{metricas['prob_pick_media']:.2%}"
        )

    if "ev_promedio" in metricas:
        print(
            "EV medio estimado:",
            f"{metricas['ev_promedio']:.2%}"
        )


def main():
    DIRECTORIO_MODELOS.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Cargando predicciones...")
    df = cargar_predicciones()

    calibrador = entrenar_calibrador(df)

    calibradas = agregar_probabilidades(
        df,
        calibrador,
    )

    resultados = []

    for temporada in [
        TEMPORADA_CALIBRACION,
        TEMPORADA_CONFIRMACION,
        TEMPORADA_OOS,
    ]:
        metricas = evaluar_temporada(
            calibradas,
            temporada,
        )

        if metricas is not None:
            resultados.append(metricas)
            imprimir_metricas(metricas)

    joblib.dump(
        calibrador,
        RUTA_CALIBRADOR,
    )

    calibradas.to_csv(
        RUTA_SALIDA,
        index=False,
    )

    metadata = {
        "modelo": MODELO_SELECCIONADO,
        "metodo": "logistic_edge_calibration",
        "calibration_season": TEMPORADA_CALIBRACION,
        "confirmation_season": TEMPORADA_CONFIRMACION,
        "oos_season": TEMPORADA_OOS,
        "edge_minimo": EDGE_MINIMO,
        "intercept": float(
            calibrador.intercept_[0]
        ),
        "edge_coefficient": float(
            calibrador.coef_[0][0]
        ),
        "results": resultados,
    }

    with open(
        RUTA_METRICAS,
        "w",
        encoding="utf-8",
    ) as archivo:
        json.dump(
            metadata,
            archivo,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 65)
    print("ARCHIVOS GENERADOS")
    print("=" * 65)
    print(RUTA_CALIBRADOR)
    print(RUTA_SALIDA)
    print(RUTA_METRICAS)


if __name__ == "__main__":
    main()