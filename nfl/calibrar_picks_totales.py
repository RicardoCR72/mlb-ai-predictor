import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
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

RUTA_CALIBRADOR = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "calibrador_pick_totales.joblib"
)

RUTA_PREDICCIONES_CALIBRADAS = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "predicciones_picks_totales_calibradas.csv"
)

RUTA_METRICAS = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "metricas_calibrador_pick_totales.json"
)

MODELO = "total_con_mercado"
TEMPORADA_CALIBRACION = 2024
TEMPORADA_CONFIRMACION = 2025
TEMPORADA_OOS = 2026
EDGE_MINIMO = 3.0


def calcular_ece(y_real, probabilidades, bins=10):
    y_real = np.asarray(y_real)
    probabilidades = np.asarray(probabilidades)

    limites = np.linspace(0, 1, bins + 1)

    grupos = np.digitize(
        probabilidades,
        limites[1:-1],
        right=True,
    )

    ece = 0.0

    for grupo in range(bins):
        mascara = grupos == grupo

        if not mascara.any():
            continue

        confianza = probabilidades[mascara].mean()
        frecuencia = y_real[mascara].mean()

        ece += mascara.mean() * abs(
            confianza - frecuencia
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


def cargar_datos():
    if not RUTA_PREDICCIONES.exists():
        raise FileNotFoundError(
            "No se encontró el archivo de predicciones."
        )

    df = pd.read_csv(RUTA_PREDICCIONES)

    df = df[
        df["modelo"] == MODELO
    ].copy()

    numericas = [
        "season",
        "total_points",
        "total_line",
        "pred_total",
        "over_odds",
        "under_odds",
        "over_result",
    ]

    for columna in numericas:
        df[columna] = pd.to_numeric(
            df[columna],
            errors="coerce",
        )

    df = df[
        df["total_points"].notna()
        & df["total_line"].notna()
        & df["pred_total"].notna()
        & df["over_result"].notna()
    ].copy()

    # Excluir pushes.
    df = df[
        df["total_points"] != df["total_line"]
    ].copy()

    df["over_result"] = (
        df["over_result"].astype(int)
    )

    df["edge"] = (
        df["pred_total"] - df["total_line"]
    )

    df["edge_absoluto"] = df["edge"].abs()

    df["pick"] = np.where(
        df["edge"] > 0,
        "OVER",
        "UNDER",
    )

    df["pick_correcto"] = np.where(
        df["pick"] == "OVER",
        df["over_result"] == 1,
        df["over_result"] == 0,
    ).astype(int)

    return df


def entrenar_calibrador(df):
    calibracion = df[
        df["season"] == TEMPORADA_CALIBRACION
    ].copy()

    X = calibracion[["edge_absoluto"]]
    y = calibracion["pick_correcto"]

    calibrador = LogisticRegression(
        C=1.0,
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )

    calibrador.fit(X, y)

    print(
        f"Calibrador entrenado con "
        f"{len(calibracion)} picks de 2024."
    )

    print(
        "Intercepto:",
        round(float(calibrador.intercept_[0]), 6)
    )

    print(
        "Coeficiente edge absoluto:",
        round(float(calibrador.coef_[0][0]), 6)
    )

    return calibrador


def agregar_probabilidades(df, calibrador):
    resultado = df.copy()

    resultado["prob_pick"] = (
        calibrador.predict_proba(
            resultado[["edge_absoluto"]]
        )[:, 1]
    )

    resultado["prob_over"] = np.where(
        resultado["pick"] == "OVER",
        resultado["prob_pick"],
        1 - resultado["prob_pick"],
    )

    resultado["prob_under"] = (
        1 - resultado["prob_over"]
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
        resultado["pick_correcto"] == 1,
        resultado["decimal_pick"] - 1,
        -1.0,
    )

    return resultado


def evaluar(df, temporada):
    muestra = df[
        df["season"] == temporada
    ].copy()

    if muestra.empty:
        return None

    y = muestra["pick_correcto"]
    prob = muestra["prob_pick"]

    metricas = {
        "season": int(temporada),
        "picks_totales": int(len(muestra)),
        "logloss": float(log_loss(y, prob)),
        "brier": float(
            brier_score_loss(y, prob)
        ),
        "auc": float(
            roc_auc_score(y, prob)
        ),
        "ece_10": calcular_ece(y, prob),
        "prob_pick_media": float(prob.mean()),
        "acierto_real": float(y.mean()),
    }

    filtrados = muestra[
        muestra["edge_absoluto"] >= EDGE_MINIMO
    ].copy()

    metricas["edge_minimo"] = EDGE_MINIMO
    metricas["picks_filtrados"] = int(
        len(filtrados)
    )

    if not filtrados.empty:
        metricas["prob_filtrada_media"] = float(
            filtrados["prob_pick"].mean()
        )

        metricas["acierto_filtrado"] = float(
            filtrados["pick_correcto"].mean()
        )

        metricas["overs_filtrados"] = int(
            (filtrados["pick"] == "OVER").sum()
        )

        metricas["unders_filtrados"] = int(
            (filtrados["pick"] == "UNDER").sum()
        )

        con_odds = filtrados[
            filtrados["profit"].notna()
        ].copy()

        if not con_odds.empty:
            metricas["roi_filtrado"] = float(
                con_odds["profit"].sum()
                / len(con_odds)
            )

            metricas["ev_estimado_medio"] = float(
                con_odds["ev"].mean()
            )

    return metricas


def imprimir(metricas):
    print("\n" + "-" * 65)
    print(f"TEMPORADA {metricas['season']}")
    print("-" * 65)

    print(
        f"Picks evaluados: "
        f"{metricas['picks_totales']}"
    )

    print(
        f"Log loss: {metricas['logloss']:.6f}"
    )

    print(
        f"Brier: {metricas['brier']:.6f}"
    )

    print(
        f"AUC: {metricas['auc']:.6f}"
    )

    print(
        f"ECE10: {metricas['ece_10']:.6f}"
    )

    print(
        "Probabilidad media:",
        f"{metricas['prob_pick_media']:.2%}"
    )

    print(
        "Acierto real:",
        f"{metricas['acierto_real']:.2%}"
    )

    print(
        f"Picks edge >= {EDGE_MINIMO}:",
        metricas["picks_filtrados"]
    )

    if "prob_filtrada_media" in metricas:
        print(
            "Probabilidad filtrada media:",
            f"{metricas['prob_filtrada_media']:.2%}"
        )

        print(
            "Acierto filtrado:",
            f"{metricas['acierto_filtrado']:.2%}"
        )

        print(
            "Over/Under filtrados:",
            f"{metricas['overs_filtrados']}/"
            f"{metricas['unders_filtrados']}"
        )

    if "roi_filtrado" in metricas:
        print(
            "ROI filtrado:",
            f"{metricas['roi_filtrado']:.2%}"
        )

        print(
            "EV estimado medio:",
            f"{metricas['ev_estimado_medio']:.2%}"
        )


def main():
    print("Cargando predicciones...")
    df = cargar_datos()

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
        metricas = evaluar(
            calibradas,
            temporada,
        )

        if metricas is not None:
            resultados.append(metricas)
            imprimir(metricas)

    joblib.dump(
        calibrador,
        RUTA_CALIBRADOR,
    )

    calibradas.to_csv(
        RUTA_PREDICCIONES_CALIBRADAS,
        index=False,
    )

    metadata = {
        "modelo": MODELO,
        "objetivo_calibracion": "probabilidad_pick_correcto",
        "feature": "edge_absoluto",
        "calibration_season": TEMPORADA_CALIBRACION,
        "confirmation_season": TEMPORADA_CONFIRMACION,
        "oos_season": TEMPORADA_OOS,
        "edge_minimo": EDGE_MINIMO,
        "intercept": float(
            calibrador.intercept_[0]
        ),
        "coefficient": float(
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
    print(RUTA_PREDICCIONES_CALIBRADAS)
    print(RUTA_METRICAS)


if __name__ == "__main__":
    main()