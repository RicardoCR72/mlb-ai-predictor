"""Calibra probabilidades para props NFL de pase y carrera.

* Yardas: selecciona entre proyeccion original y correccion lineal entrenada
  con 2024, confirmada en 2025. Guarda una distribucion empirica de errores.
* Pases de TD: calibra las lineas 0.5, 1.5 y 2.5 con regresion logistica y
  la compara contra una probabilidad Poisson.
* Anota TD: audita el modelo binario ya calibrado; no lo transforma.

No se guardan estimadores sklearn de calibracion. Los coeficientes se escriben
en JSON para evitar incompatibilidades de versiones en Streamlit Cloud.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    roc_auc_score,
)


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
DIRECTORIO = RAIZ_PROYECTO / "modelos_nfl" / "props"

RUTA_PRED = DIRECTORIO / "predicciones_validacion_pase_carrera.csv"
RUTA_META = DIRECTORIO / "metadata_props_pase_carrera.json"
RUTA_PRED_TD = DIRECTORIO / "predicciones_validacion_anytime_td.csv"
RUTA_META_TD = DIRECTORIO / "metadata_anytime_td.json"

RUTA_CONFIG = DIRECTORIO / "calibracion_props_pase_carrera.json"
RUTA_RESIDUOS = DIRECTORIO / "residuos_props_pase_carrera.npz"
RUTA_METRICAS = DIRECTORIO / "metricas_calibracion_props_pase_carrera.csv"

OBJETIVOS_YARDAS = ["passing_yards", "rushing_yards"]
LINEAS_PASSING_TDS = [0.5, 1.5, 2.5]


def ece(y, probabilidad, bins=10):
    y = np.asarray(y, dtype=float)
    p = np.asarray(probabilidad, dtype=float)
    cortes = np.linspace(0, 1, bins + 1)
    grupos = np.digitize(p, cortes[1:-1], right=True)
    resultado = 0.0
    for grupo in range(bins):
        mascara = grupos == grupo
        if mascara.any():
            resultado += mascara.mean() * abs(y[mascara].mean() - p[mascara].mean())
    return float(resultado)


def metricas_binarias(y, p):
    y = np.asarray(y, dtype=int)
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return {
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else np.nan,
        "ece10": ece(y, p),
        "probabilidad_media": float(p.mean()),
        "frecuencia_real": float(y.mean()),
    }


def cargar():
    for ruta in [RUTA_PRED, RUTA_META, RUTA_PRED_TD, RUTA_META_TD]:
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontro: {ruta}")
    pred = pd.read_csv(RUTA_PRED)
    meta = json.loads(RUTA_META.read_text(encoding="utf-8"))
    pred_td = pd.read_csv(RUTA_PRED_TD)
    meta_td = json.loads(RUTA_META_TD.read_text(encoding="utf-8"))
    return pred, meta, pred_td, meta_td


def variante_objetivo(meta, objetivo):
    return meta["objetivos"][objetivo]["variante_seleccionada"]


def calibrar_yardas(pred, meta, objetivo):
    variante = variante_objetivo(meta, objetivo)
    df = pred[
        (pred["objetivo"] == objetivo) & (pred["variante"] == variante)
    ].copy()
    df[objetivo] = pd.to_numeric(df[objetivo], errors="coerce")
    df["prediccion"] = pd.to_numeric(df["prediccion"], errors="coerce")
    df = df.dropna(subset=[objetivo, "prediccion", "season"])

    ajuste = df[df["season"] == 2024]
    confirmacion = df[df["season"] == 2025]
    regresion = LinearRegression().fit(
        ajuste[["prediccion"]], ajuste[objetivo]
    )
    pendiente = float(regresion.coef_[0])
    intercepto = float(regresion.intercept_)

    pred_raw_2025 = confirmacion["prediccion"].to_numpy()
    pred_cal_2025 = intercepto + pendiente * pred_raw_2025
    mae_raw_2025 = float(mean_absolute_error(
        confirmacion[objetivo], pred_raw_2025
    ))
    mae_cal_2025 = float(mean_absolute_error(
        confirmacion[objetivo], pred_cal_2025
    ))
    usar_lineal = mae_cal_2025 < mae_raw_2025

    if usar_lineal:
        metodo = "lineal_2024_confirmado_2025"
        aplicar = lambda x: intercepto + pendiente * np.asarray(x, dtype=float)
    else:
        metodo = "identidad"
        pendiente, intercepto = 1.0, 0.0
        aplicar = lambda x: np.asarray(x, dtype=float)

    metricas = []
    for temporada in [2024, 2025, 2026]:
        parte = df[df["season"] == temporada]
        corregida = np.maximum(aplicar(parte["prediccion"]), 0.0)
        errores = corregida - parte[objetivo].to_numpy()
        registro = {
            "objetivo": objetivo,
            "linea": np.nan,
            "temporada": temporada,
            "metodo": metodo,
            "filas": int(len(parte)),
            "mae": float(np.abs(errores).mean()),
            "bias": float(errores.mean()),
        }
        metricas.append(registro)
        print(
            f"{objetivo} {temporada}: MAE {registro['mae']:.4f} | "
            f"bias {registro['bias']:+.4f} | {metodo}"
        )

    pred_ajuste = np.maximum(aplicar(ajuste["prediccion"]), 0.0)
    residuos = pred_ajuste - ajuste[objetivo].to_numpy()
    configuracion = {
        "variante": variante,
        "metodo_punto": metodo,
        "pendiente": pendiente,
        "intercepto": intercepto,
        "mae_2025_sin_correccion": mae_raw_2025,
        "mae_2025_con_correccion_lineal": mae_cal_2025,
        "probabilidad": "cdf_empirica_error_pred_menos_real_2024",
        "n_residuos": int(len(residuos)),
    }
    return configuracion, residuos.astype(float), metricas


def probabilidad_poisson(mu, linea):
    mu = np.clip(np.asarray(mu, dtype=float), 1e-6, None)
    return 1.0 - poisson.cdf(np.floor(linea), mu)


def probabilidad_logistica(prediccion, intercepto, coeficiente):
    z = intercepto + coeficiente * np.asarray(prediccion, dtype=float)
    z = np.clip(z, -35, 35)
    return 1.0 / (1.0 + np.exp(-z))


def calibrar_passing_tds(pred, meta):
    objetivo = "passing_tds"
    variante = variante_objetivo(meta, objetivo)
    df = pred[
        (pred["objetivo"] == objetivo) & (pred["variante"] == variante)
    ].copy()
    df[objetivo] = pd.to_numeric(df[objetivo], errors="coerce")
    df["prediccion"] = pd.to_numeric(df["prediccion"], errors="coerce")
    df = df.dropna(subset=[objetivo, "prediccion", "season"])

    configuraciones = {}
    metricas = []
    for linea in LINEAS_PASSING_TDS:
        ajuste = df[df["season"] == 2024]
        y_ajuste = (ajuste[objetivo].to_numpy() > linea).astype(int)
        modelo = LogisticRegression(C=1.0, max_iter=1000)
        modelo.fit(ajuste[["prediccion"]], y_ajuste)
        intercepto = float(modelo.intercept_[0])
        coeficiente = float(modelo.coef_[0, 0])

        confirmacion = df[df["season"] == 2025]
        y_2025 = (confirmacion[objetivo].to_numpy() > linea).astype(int)
        p_log_2025 = probabilidad_logistica(
            confirmacion["prediccion"], intercepto, coeficiente
        )
        p_pois_2025 = probabilidad_poisson(
            confirmacion["prediccion"], linea
        )
        brier_log = brier_score_loss(y_2025, p_log_2025)
        brier_pois = brier_score_loss(y_2025, p_pois_2025)
        metodo = "logistico" if brier_log <= brier_pois else "poisson"

        configuraciones[str(linea)] = {
            "metodo": metodo,
            "intercepto": intercepto,
            "coeficiente": coeficiente,
            "brier_2025_logistico": float(brier_log),
            "brier_2025_poisson": float(brier_pois),
        }

        print(f"\npassing_tds | linea {linea} | metodo: {metodo}")
        for temporada in [2024, 2025, 2026]:
            parte = df[df["season"] == temporada]
            y = (parte[objetivo].to_numpy() > linea).astype(int)
            if metodo == "logistico":
                p = probabilidad_logistica(
                    parte["prediccion"], intercepto, coeficiente
                )
            else:
                p = probabilidad_poisson(parte["prediccion"], linea)
            m = metricas_binarias(y, p)
            registro = {
                "objetivo": objetivo,
                "linea": linea,
                "temporada": temporada,
                "metodo": metodo,
                "filas": int(len(parte)),
                **m,
            }
            metricas.append(registro)
            print(
                f"  {temporada}: Brier {m['brier']:.5f} | "
                f"LogLoss {m['log_loss']:.5f} | AUC {m['auc']:.4f} | "
                f"ECE {m['ece10']:.4f}"
            )
    return {
        "variante": variante,
        "lineas": configuraciones,
    }, metricas


def auditar_anytime_td(pred_td, meta_td):
    variante = meta_td["variante_seleccionada"]
    df = pred_td[pred_td["variante"] == variante].copy()
    metricas = []
    print(f"\nanytime_td | variante: {variante} | probabilidad directa")
    for temporada in [2024, 2025, 2026]:
        parte = df[df["season"] == temporada]
        m = metricas_binarias(parte["anytime_td"], parte["probabilidad"])
        metricas.append({
            "objetivo": "anytime_td",
            "linea": np.nan,
            "temporada": temporada,
            "metodo": "clasificador_directo",
            "filas": int(len(parte)),
            **m,
        })
        print(
            f"  {temporada}: Brier {m['brier']:.5f} | "
            f"LogLoss {m['log_loss']:.5f} | AUC {m['auc']:.4f} | "
            f"ECE {m['ece10']:.4f}"
        )
    return {
        "variante": variante,
        "metodo": "predict_proba_sin_calibrador_adicional",
    }, metricas


def main():
    print("Cargando predicciones de validacion...")
    pred, meta, pred_td, meta_td = cargar()
    configuracion = {
        "version": "props_nfl_calibracion_v1",
        "yardas": {},
    }
    residuos = {}
    metricas = []

    print("\n" + "=" * 76)
    print("CALIBRACION DE YARDAS")
    print("=" * 76)
    for objetivo in OBJETIVOS_YARDAS:
        config, errores, resultados = calibrar_yardas(pred, meta, objetivo)
        configuracion["yardas"][objetivo] = config
        residuos[objetivo] = errores
        metricas.extend(resultados)

    print("\n" + "=" * 76)
    print("CALIBRACION DE PASES DE TOUCHDOWN")
    print("=" * 76)
    configuracion["passing_tds"], resultados = calibrar_passing_tds(pred, meta)
    metricas.extend(resultados)

    print("\n" + "=" * 76)
    print("AUDITORIA ANOTA TOUCHDOWN")
    print("=" * 76)
    configuracion["anytime_td"], resultados = auditar_anytime_td(pred_td, meta_td)
    metricas.extend(resultados)

    np.savez_compressed(RUTA_RESIDUOS, **residuos)
    RUTA_CONFIG.write_text(
        json.dumps(configuracion, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame(metricas).to_csv(RUTA_METRICAS, index=False)

    print("\n" + "=" * 76)
    print("ARCHIVOS GENERADOS")
    print("=" * 76)
    print(RUTA_CONFIG)
    print(RUTA_RESIDUOS)
    print(RUTA_METRICAS)
    print("\nCalibracion terminada correctamente.")


if __name__ == "__main__":
    main()
