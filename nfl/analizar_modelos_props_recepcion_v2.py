"""Analiza modelos de recepcion por volumen previo y posicion."""

from pathlib import Path

import pandas as pd


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_DATASET = (
    RAIZ_PROYECTO / "data" / "nfl" / "processed"
    / "nfl_props_recepcion_features_2012_2026.parquet"
)
RUTA_PREDICCIONES = (
    RAIZ_PROYECTO / "modelos_nfl" / "props"
    / "predicciones_validacion_recepcion.csv"
)
RUTA_SALIDA = (
    RAIZ_PROYECTO / "modelos_nfl" / "props"
    / "analisis_segmentos_recepcion.csv"
)


def resumir(df, agrupadores, etiqueta):
    filas = []
    for claves, grupo in df.groupby(agrupadores, dropna=False):
        if not isinstance(claves, tuple):
            claves = (claves,)
        registro = dict(zip(agrupadores, claves))
        registro.update(
            {
                "segmento": etiqueta,
                "filas": len(grupo),
                "mae_modelo": grupo["error_absoluto"].mean(),
                "mae_baseline": (grupo["baseline"] - grupo["valor_real"]).abs().mean(),
                "mejora_mae": (
                    (grupo["baseline"] - grupo["valor_real"]).abs().mean()
                    - grupo["error_absoluto"].mean()
                ),
                "bias": grupo["error"].mean(),
                "media_real": grupo["valor_real"].mean(),
                "media_predicha": grupo["prediccion"].mean(),
            }
        )
        filas.append(registro)
    return pd.DataFrame(filas)


def main():
    for ruta in [RUTA_DATASET, RUTA_PREDICCIONES]:
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontro: {ruta}")

    dataset = pd.read_parquet(
        RUTA_DATASET,
        columns=[
            "game_id", "player_id", "player_targets_avg_5",
            "player_target_share_avg_5",
        ],
    )
    pred = pd.read_csv(RUTA_PREDICCIONES)
    pred = pred.merge(
        dataset,
        on=["game_id", "player_id"],
        how="left",
        validate="many_to_one",
    )
    pred["valor_real"] = pred.apply(
        lambda fila: fila[fila["objetivo"]],
        axis=1,
    )

    resultados = []
    tablas_volumen = []
    for umbral in [1, 3, 5, 7]:
        segmento = pred[pred["player_targets_avg_5"] >= umbral].copy()
        tabla = resumir(
            segmento,
            ["objetivo", "season"],
            f"targets_avg_5 >= {umbral}",
        )
        tabla["umbral_targets"] = umbral
        tablas_volumen.append(tabla)
        resultados.append(tabla)

    por_posicion = resumir(
        pred,
        ["objetivo", "season", "position"],
        "posicion",
    )
    resultados.append(por_posicion)
    salida = pd.concat(resultados, ignore_index=True)
    salida.to_csv(RUTA_SALIDA, index=False)

    volumen = pd.concat(tablas_volumen, ignore_index=True)
    print("=" * 96)
    print("RESULTADOS POR VOLUMEN PREVIO")
    print("=" * 96)
    columnas = [
        "objetivo", "season", "umbral_targets", "filas",
        "mae_modelo", "mae_baseline", "mejora_mae", "bias",
    ]
    print(
        volumen[columnas]
        .round(4)
        .sort_values(["objetivo", "umbral_targets", "season"])
        .to_string(index=False)
    )

    print("\n" + "=" * 96)
    print("RESULTADOS POR POSICION - 2025 Y 2026")
    print("=" * 96)
    columnas_posicion = [
        "objetivo", "season", "position", "filas",
        "mae_modelo", "mae_baseline", "mejora_mae", "bias",
    ]
    print(
        por_posicion[por_posicion["season"].isin([2025, 2026])]
        [columnas_posicion]
        .round(4)
        .sort_values(["objetivo", "season", "position"])
        .to_string(index=False)
    )

    print(f"\nArchivo guardado en:\n{RUTA_SALIDA}")


if __name__ == "__main__":
    main()
