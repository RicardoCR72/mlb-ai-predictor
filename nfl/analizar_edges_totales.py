from pathlib import Path

import numpy as np
import pandas as pd


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]

RUTA_PREDICCIONES = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "predicciones_totales_validacion.csv"
)

RUTA_RESULTADOS = (
    RAIZ_PROYECTO
    / "modelos_nfl"
    / "analisis_edges_totales.csv"
)

UMBRALES = [0, 1, 2, 3, 4, 5, 6, 7]


def convertir_ganancia_odds(odds):
    """
    Devuelve la ganancia neta por cada unidad apostada.
    Soporta momios americanos y cuotas decimales.
    """

    if pd.isna(odds):
        return np.nan

    odds = float(odds)

    if odds >= 100:
        return odds / 100

    if odds <= -100:
        return 100 / abs(odds)

    if odds > 1:
        return odds - 1

    return np.nan


def preparar_predicciones(df):
    df = df.copy()

    columnas_numericas = [
        "total_points",
        "total_line",
        "pred_total",
        "over_odds",
        "under_odds",
        "over_result",
        "push_total",
    ]

    for columna in columnas_numericas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(
                df[columna],
                errors="coerce"
            )

    df = df[
        df["total_line"].notna()
        & df["pred_total"].notna()
        & df["total_points"].notna()
    ].copy()

    # No evaluamos pushes.
    df = df[
        df["total_points"] != df["total_line"]
    ].copy()

    df["edge"] = (
        df["pred_total"] - df["total_line"]
    )

    df["edge_absoluto"] = df["edge"].abs()

    df["pick"] = np.where(
        df["edge"] > 0,
        "OVER",
        "UNDER"
    )

    df["pick_correcto"] = np.where(
        df["pick"] == "OVER",
        df["over_result"] == 1,
        df["over_result"] == 0,
    )

    df["pick_odds"] = np.where(
        df["pick"] == "OVER",
        df["over_odds"],
        df["under_odds"],
    )

    df["ganancia_si_acierta"] = (
        df["pick_odds"].apply(
            convertir_ganancia_odds
        )
    )

    df["profit"] = np.where(
        df["pick_correcto"],
        df["ganancia_si_acierta"],
        -1.0,
    )

    return df


def calcular_resultados(df):
    resultados = []

    modelos = sorted(df["modelo"].unique())
    temporadas = sorted(df["season"].unique())

    for modelo in modelos:
        for temporada in temporadas:
            grupo = df[
                (df["modelo"] == modelo)
                & (df["season"] == temporada)
            ].copy()

            for umbral in UMBRALES:
                seleccion = grupo[
                    grupo["edge_absoluto"] >= umbral
                ].copy()

                if seleccion.empty:
                    continue

                con_odds = seleccion[
                    seleccion["profit"].notna()
                ].copy()

                resultado = {
                    "modelo": modelo,
                    "season": int(temporada),
                    "umbral_edge": float(umbral),
                    "apuestas": int(len(seleccion)),
                    "overs": int(
                        (seleccion["pick"] == "OVER").sum()
                    ),
                    "unders": int(
                        (seleccion["pick"] == "UNDER").sum()
                    ),
                    "edge_promedio": float(
                        seleccion["edge_absoluto"].mean()
                    ),
                    "aciertos": int(
                        seleccion["pick_correcto"].sum()
                    ),
                    "accuracy": float(
                        seleccion["pick_correcto"].mean()
                    ),
                }

                if not con_odds.empty:
                    resultado["apuestas_roi"] = int(
                        len(con_odds)
                    )

                    resultado["profit"] = float(
                        con_odds["profit"].sum()
                    )

                    resultado["roi"] = float(
                        con_odds["profit"].sum()
                        / len(con_odds)
                    )

                resultados.append(resultado)

    return pd.DataFrame(resultados)


def imprimir_tabla(resultados):
    for modelo in resultados["modelo"].unique():
        print("\n" + "=" * 80)
        print(f"MODELO: {modelo}")
        print("=" * 80)

        for temporada in sorted(
            resultados["season"].unique()
        ):
            tabla = resultados[
                (resultados["modelo"] == modelo)
                & (resultados["season"] == temporada)
            ].copy()

            if tabla.empty:
                continue

            print(f"\nTemporada {temporada}")

            columnas = [
                "umbral_edge",
                "apuestas",
                "overs",
                "unders",
                "edge_promedio",
                "accuracy",
                "profit",
                "roi",
            ]

            columnas = [
                columna
                for columna in columnas
                if columna in tabla.columns
            ]

            tabla = tabla[columnas].copy()

            tabla["accuracy"] = (
                tabla["accuracy"] * 100
            ).round(2)

            if "roi" in tabla.columns:
                tabla["roi"] = (
                    tabla["roi"] * 100
                ).round(2)

            tabla["edge_promedio"] = (
                tabla["edge_promedio"].round(2)
            )

            if "profit" in tabla.columns:
                tabla["profit"] = (
                    tabla["profit"].round(2)
                )

            print(tabla.to_string(index=False))


def main():
    if not RUTA_PREDICCIONES.exists():
        raise FileNotFoundError(
            "No se encontró el archivo de predicciones."
        )

    predicciones = pd.read_csv(RUTA_PREDICCIONES)

    print(
        f"Predicciones cargadas: "
        f"{len(predicciones):,}"
    )

    predicciones = preparar_predicciones(
        predicciones
    )

    print(
        f"Predicciones evaluables: "
        f"{len(predicciones):,}"
    )

    resultados = calcular_resultados(
        predicciones
    )

    resultados.to_csv(
        RUTA_RESULTADOS,
        index=False
    )

    imprimir_tabla(resultados)

    print("\n" + "=" * 80)
    print("Archivo guardado:")
    print(RUTA_RESULTADOS)


if __name__ == "__main__":
    main()