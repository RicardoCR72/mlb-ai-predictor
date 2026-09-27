"""Entrena y valida el modelo binario NFL para 'anota touchdown'."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_DATASET = (
    RAIZ_PROYECTO / "data" / "nfl" / "processed"
    / "nfl_prop_touchdown_features_2012_2026.parquet"
)
DIRECTORIO_MODELOS = RAIZ_PROYECTO / "modelos_nfl" / "props"
RUTA_MODELO = DIRECTORIO_MODELOS / "props_anytime_td.joblib"
RUTA_PREDICCIONES = DIRECTORIO_MODELOS / "predicciones_validacion_anytime_td.csv"
RUTA_METADATA = DIRECTORIO_MODELOS / "metadata_anytime_td.json"

TRAIN_SEASONS = list(range(2012, 2024))
MEJORA_MINIMA_BRIER = 0.0005
FEATURES_CATEGORICAS = ["position", "team", "opponent_team", "roof", "surface"]

METRICAS_JUGADOR = [
    "targets", "receptions", "receiving_yards", "receiving_tds",
    "receiving_air_yards", "receiving_yards_after_catch",
    "receiving_first_downs", "receiving_epa", "target_share",
    "air_yards_share", "carries", "rushing_yards", "rushing_tds",
    "rushing_first_downs", "rushing_epa", "opportunities",
    "touchdown_count", "anytime_td",
]
METRICAS_EQUIPO = [
    "team_targets", "team_carries", "team_opportunities",
    "team_receiving_yards", "team_rushing_yards", "team_touchdowns",
]
METRICAS_DEFENSA = [
    "allowed_targets", "allowed_carries", "allowed_opportunities",
    "allowed_receiving_yards", "allowed_rushing_yards",
    "allowed_touchdowns", "allowed_td_scorers",
]

FEATURES_BASE = [
    "player_games_before", "player_games_before_season", "is_home", "rest",
    "temp", "wind", "spread_line", "total_line", "home_moneyline",
    "away_moneyline", "div_game", "player_opportunities_std_5",
    "player_touchdown_count_std_8", "player_td_per_opportunity_8",
    "player_opportunity_share_5", "player_td_share_8",
]
for metrica in METRICAS_JUGADOR:
    for ventana in [3, 5, 8]:
        FEATURES_BASE.append(f"player_{metrica}_avg_{ventana}")
    FEATURES_BASE.append(f"player_{metrica}_avg_season")
for metrica in METRICAS_EQUIPO:
    for ventana in [3, 5, 8]:
        FEATURES_BASE.append(f"{metrica}_avg_{ventana}")
for metrica in METRICAS_DEFENSA:
    for ventana in [3, 5, 8]:
        FEATURES_BASE.append(f"opp_pos_{metrica}_avg_{ventana}")
FEATURES_BASE = list(dict.fromkeys(FEATURES_BASE))

FEATURES_LESIONES = [
    "player_injury_score",
    "team_skill_injury_score", "team_skill_injury_count",
    "team_ol_injury_score", "team_ol_injury_count",
    "team_qb_injury_score", "team_qb_injury_count",
    "opp_defense_injury_score", "opp_defense_injury_count",
]


def cargar_dataset():
    if not RUTA_DATASET.exists():
        raise FileNotFoundError(f"No se encontro: {RUTA_DATASET}")
    df = pd.read_parquet(RUTA_DATASET)
    df["gameday"] = pd.to_datetime(df["gameday"], errors="coerce")
    df = df[
        (df["player_games_before"] >= 3)
        & (df["player_opportunities_avg_5"] >= 2.0)
    ].copy()
    return (
        df.replace([np.inf, -np.inf], np.nan)
        .sort_values(["season", "week", "gameday", "game_id", "player_id"])
        .reset_index(drop=True)
    )


def construir_pipeline(features):
    columnas = list(dict.fromkeys(features))
    preprocesador = ColumnTransformer(
        transformers=[
            (
                "numericas",
                SimpleImputer(strategy="median", add_indicator=True),
                columnas,
            ),
            (
                "categoricas",
                Pipeline(steps=[
                    ("imputar", SimpleImputer(strategy="most_frequent")),
                    ("one_hot", OneHotEncoder(
                        handle_unknown="ignore", sparse_output=False
                    )),
                ]),
                FEATURES_CATEGORICAS,
            ),
        ],
        remainder="drop",
    )
    modelo = HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=0.035,
        max_iter=350,
        max_leaf_nodes=15,
        min_samples_leaf=70,
        l2_regularization=6.0,
        early_stopping=False,
        random_state=42,
    )
    return Pipeline([
        ("preprocesamiento", preprocesador),
        ("modelo", modelo),
    ])


def ece(y, probabilidad, bins=10):
    cortes = np.linspace(0, 1, bins + 1)
    indices = np.digitize(probabilidad, cortes[1:-1], right=True)
    total = len(y)
    resultado = 0.0
    for indice in range(bins):
        mascara = indices == indice
        if mascara.any():
            resultado += mascara.mean() * abs(
                y[mascara].mean() - probabilidad[mascara].mean()
            )
    return float(resultado) if total else np.nan


def evaluar(conjunto, probabilidades, variante):
    y = conjunto["anytime_td"].to_numpy(dtype=int)
    p = np.clip(probabilidades, 1e-6, 1 - 1e-6)
    baseline = conjunto["player_anytime_td_avg_8"].fillna(
        conjunto["anytime_td"].mean()
    ).clip(0.02, 0.98).to_numpy()
    detalle = conjunto[[
        "game_id", "season", "week", "gameday", "player_id",
        "player_name", "position", "team", "opponent_team", "anytime_td",
    ]].copy()
    detalle["variante"] = variante
    detalle["probabilidad"] = p
    detalle["baseline"] = baseline
    resultado = {
        "variante": variante,
        "temporada": int(conjunto["season"].iloc[0]),
        "filas": int(len(conjunto)),
        "eventos": int(y.sum()),
        "frecuencia_real": float(y.mean()),
        "probabilidad_media": float(p.mean()),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else np.nan,
        "ece10": ece(y, p),
        "baseline_log_loss": float(log_loss(y, baseline, labels=[0, 1])),
        "baseline_brier": float(brier_score_loss(y, baseline)),
    }
    return resultado, detalle


def imprimir(r):
    print("-" * 76)
    print(f"{r['variante']} | Temporada {r['temporada']}")
    print("-" * 76)
    print(f"Filas: {r['filas']:,} | TD: {r['eventos']:,}")
    print(f"Log loss modelo: {r['log_loss']:.6f}")
    print(f"Log loss baseline: {r['baseline_log_loss']:.6f}")
    print(f"Brier modelo: {r['brier']:.6f}")
    print(f"Brier baseline: {r['baseline_brier']:.6f}")
    print(f"AUC: {r['auc']:.6f}")
    print(f"ECE10: {r['ece10']:.6f}")
    print(f"Probabilidad media: {r['probabilidad_media'] * 100:.2f}%")
    print(f"Frecuencia real: {r['frecuencia_real'] * 100:.2f}%")


def entrenar_variante(train, evaluaciones, variante, features):
    columnas = list(dict.fromkeys(features + FEATURES_CATEGORICAS))
    modelo = construir_pipeline(features)
    modelo.fit(train[columnas], train["anytime_td"])
    resultados, detalles = [], []
    for conjunto in evaluaciones:
        probabilidades = modelo.predict_proba(conjunto[columnas])[:, 1]
        resultado, detalle = evaluar(conjunto, probabilidades, variante)
        imprimir(resultado)
        resultados.append(resultado)
        detalles.append(detalle)
    return modelo, resultados, detalles


def por_temporada(resultados, temporada):
    return next(r for r in resultados if r["temporada"] == temporada)


def main():
    print("Cargando dataset de touchdown...")
    df = cargar_dataset()
    requeridas = set(
        FEATURES_BASE + FEATURES_LESIONES + FEATURES_CATEGORICAS + ["anytime_td"]
    )
    faltantes = sorted(requeridas - set(df.columns))
    if faltantes:
        raise KeyError("Faltan columnas: " + ", ".join(faltantes))

    train = df[df["season"].isin(TRAIN_SEASONS)].copy()
    seleccion = df[df["season"] == 2024].copy()
    confirmacion = df[df["season"] == 2025].copy()
    oos = df[df["season"] == 2026].copy()
    print("\nDivision temporal:")
    print(f"Train 2012-2023: {len(train):,}")
    print(f"Seleccion 2024: {len(seleccion):,}")
    print(f"Confirmacion 2025: {len(confirmacion):,}")
    print(f"OOS 2026: {len(oos):,}")

    print("\n" + "=" * 76)
    print("MODELO CONTROL")
    print("=" * 76)
    _, rc, dc = entrenar_variante(
        train, [seleccion, confirmacion, oos], "control", FEATURES_BASE
    )
    print("\n" + "=" * 76)
    print("MODELO CON LESIONES")
    print("=" * 76)
    features_lesiones = list(dict.fromkeys(FEATURES_BASE + FEATURES_LESIONES))
    _, rl, dl = entrenar_variante(
        train, [seleccion, confirmacion, oos], "lesiones", features_lesiones
    )

    ganancia_2024 = (
        por_temporada(rc, 2024)["brier"]
        - por_temporada(rl, 2024)["brier"]
    )
    ganancia_2025 = (
        por_temporada(rc, 2025)["brier"]
        - por_temporada(rl, 2025)["brier"]
    )
    mejora_2024 = ganancia_2024 >= MEJORA_MINIMA_BRIER
    mejora_2025 = ganancia_2025 >= MEJORA_MINIMA_BRIER
    seleccionada = "lesiones" if mejora_2024 and mejora_2025 else "control"
    features_finales = features_lesiones if seleccionada == "lesiones" else FEATURES_BASE
    print("\nComparacion Brier lesiones vs control:")
    for temporada in [2024, 2025, 2026]:
        c = por_temporada(rc, temporada)
        l = por_temporada(rl, temporada)
        print(
            f"{temporada}: control {c['brier']:.6f} | "
            f"lesiones {l['brier']:.6f} | cambio {l['brier'] - c['brier']:+.6f}"
        )
    print(
        "Mejora minima exigida en 2024 y 2025: "
        f"{MEJORA_MINIMA_BRIER:.6f} Brier"
    )
    print(f"Modelo seleccionado: {seleccionada}")

    desarrollo = df[df["season"].between(2012, 2025)].copy()
    columnas_finales = list(dict.fromkeys(features_finales + FEATURES_CATEGORICAS))
    modelo_final = construir_pipeline(features_finales)
    modelo_final.fit(desarrollo[columnas_finales], desarrollo["anytime_td"])
    DIRECTORIO_MODELOS.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo_final, RUTA_MODELO)
    pd.concat(dc + dl, ignore_index=True).to_csv(RUTA_PREDICCIONES, index=False)

    metadata = {
        "objetivo": "anytime_td",
        "definicion": "rushing_tds + receiving_tds >= 1",
        "posiciones": ["RB", "FB", "WR", "TE"],
        "variante_seleccionada": seleccionada,
        "features_numericas": features_finales,
        "features_categoricas": FEATURES_CATEGORICAS,
        "resultados_control": rc,
        "resultados_lesiones": rl,
        "n_train_produccion": int(len(desarrollo)),
    }
    RUTA_METADATA.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nArchivos generados:")
    print(RUTA_MODELO)
    print(RUTA_PREDICCIONES)
    print(RUTA_METADATA)
    print("\nEntrenamiento terminado correctamente.")


if __name__ == "__main__":
    main()
