"""Entrenamiento del Modelo de Spread (ATS) NFL V1.

Enfoque de Ciencia de Datos:
1. Ensamble Híbrido:
   - Logistic Regression L2 calibrada (C=0.012) para anclaje a líneas y valor marginal.
   - HistGradientBoostingClassifier para capturar interacciones no lineales entre presiones
     y salud de la línea ofensiva (OL).
2. Variables de Entrada:
   - Diferencial de EPA ofensivo rodante (Pase, Carrera, Total, Sacks concedidos a 8 partidos).
   - Salud posicional: Diferencial de severidad de lesiones, estado de QB titular, OL y Defensa.
   - Microestructura del mercado: Línea de spread, indicador de local underdog y números clave (3 y 7).
3. Protocolo de Validación:
   - Entrenamiento estricto en temporadas 2012-2023.
   - Prueba out-of-sample sin sesgo retrospectivo en 2024, 2025 y 2026.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nfl.ensamble_spread_v1 import EnsambleSpreadNFLv1

RUTA_GAMES = RAIZ / "data" / "nfl" / "processed" / "nfl_games_features_2012_2026.parquet"
RUTA_PLAYERS = RAIZ / "data" / "nfl" / "raw" / "nfl_player_stats_2012_2026.parquet"
RUTA_EPA_ROLLING = RAIZ / "data" / "nfl" / "processed" / "nfl_team_epa_rolling.parquet"
RUTA_MODELO = RAIZ / "modelos_nfl" / "modelo_spread_nfl.joblib"
RUTA_METADATA = RAIZ / "modelos_nfl" / "metadata_spread_nfl.json"

FEATURES_SPREAD = [
    "spread_line",
    "abs_spread",
    "key_3",
    "key_7",
    "is_home_dog",
    "diff_total_epa_8",
    "diff_pass_epa_8",
    "diff_rush_epa_8",
    "diff_sacks_8",
    "diff_margin_avg_8",
    "diff_points_for_avg_8",
    "diff_points_against_avg_8",
    "diff_win_pct_8",
    "diff_win_pct_season",
    "diff_rest",
    "diff_injury_severity",
    "diff_injury_starting_qb_score",
    "diff_injury_ol_score",
    "diff_injury_defense_score",
    "home_qb_change",
    "away_qb_change",
    "div_game",
]


def asegurar_epa_rodante(df_games: pd.DataFrame, df_players: pd.DataFrame) -> pd.DataFrame:
    """Calcula y une métricas rodantes de EPA de forma estrictamente causal."""
    team_stats = (
        df_players.groupby(["game_id", "team"])
        .agg(
            passing_epa=("passing_epa", "sum"),
            rushing_epa=("rushing_epa", "sum"),
            sacks_suffered=("sacks_suffered", "sum"),
        )
        .reset_index()
    )
    team_stats["total_epa"] = team_stats["passing_epa"] + team_stats["rushing_epa"]

    sched = df_games[["game_id", "season", "week", "gameday", "home_team", "away_team"]].copy()
    team_stats = team_stats.merge(sched[["game_id", "season", "week", "gameday"]], on="game_id")
    team_stats = team_stats.sort_values(["team", "gameday", "week"]).reset_index(drop=True)

    team_stats["roll_pass_epa_8"] = team_stats.groupby("team")["passing_epa"].transform(
        lambda s: s.shift(1).rolling(8, min_periods=1).mean()
    )
    team_stats["roll_rush_epa_8"] = team_stats.groupby("team")["rushing_epa"].transform(
        lambda s: s.shift(1).rolling(8, min_periods=1).mean()
    )
    team_stats["roll_total_epa_8"] = team_stats.groupby("team")["total_epa"].transform(
        lambda s: s.shift(1).rolling(8, min_periods=1).mean()
    )
    team_stats["roll_sacks_8"] = team_stats.groupby("team")["sacks_suffered"].transform(
        lambda s: s.shift(1).rolling(8, min_periods=1).mean()
    )

    RUTA_EPA_ROLLING.parent.mkdir(parents=True, exist_ok=True)
    team_stats.to_parquet(RUTA_EPA_ROLLING, index=False)

    home_epa = team_stats[
        ["game_id", "team", "roll_pass_epa_8", "roll_rush_epa_8", "roll_total_epa_8", "roll_sacks_8"]
    ].copy()
    home_epa.columns = [
        "game_id",
        "home_team",
        "home_pass_epa_8",
        "home_rush_epa_8",
        "home_total_epa_8",
        "home_sacks_8",
    ]

    away_epa = team_stats[
        ["game_id", "team", "roll_pass_epa_8", "roll_rush_epa_8", "roll_total_epa_8", "roll_sacks_8"]
    ].copy()
    away_epa.columns = [
        "game_id",
        "away_team",
        "away_pass_epa_8",
        "away_rush_epa_8",
        "away_total_epa_8",
        "away_sacks_8",
    ]

    df_full = df_games.merge(home_epa, on=["game_id", "home_team"], how="left")
    df_full = df_full.merge(away_epa, on=["game_id", "away_team"], how="left")

    df_full["diff_pass_epa_8"] = (df_full["home_pass_epa_8"] - df_full["away_pass_epa_8"]).fillna(0.0)
    df_full["diff_rush_epa_8"] = (df_full["home_rush_epa_8"] - df_full["away_rush_epa_8"]).fillna(0.0)
    df_full["diff_total_epa_8"] = (df_full["home_total_epa_8"] - df_full["away_total_epa_8"]).fillna(0.0)
    df_full["diff_sacks_8"] = (df_full["home_sacks_8"] - df_full["away_sacks_8"]).fillna(0.0)

    return df_full


def preparar_features_spread(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula las variables situacionales del mercado de spreads."""
    df = df.copy()
    df["abs_spread"] = df["spread_line"].abs().fillna(0.0)
    df["key_3"] = (df["abs_spread"] == 3.0).astype(float)
    df["key_7"] = (df["abs_spread"] == 7.0).astype(float)
    df["is_home_dog"] = (df["spread_line"] < 0).astype(float)
    return df


def entrenar_modelo_spread():
    """Entrena y persiste el modelo de spread NFL V1."""
    print("🏈 Iniciando entrenamiento del Modelo de Spread (ATS) NFL V1...")

    if not RUTA_GAMES.exists():
        raise FileNotFoundError(f"No existe {RUTA_GAMES}")
    if not RUTA_PLAYERS.exists():
        raise FileNotFoundError(f"No existe {RUTA_PLAYERS}")

    df_games = pd.read_parquet(RUTA_GAMES)
    df_games = df_games.dropna(subset=["result", "spread_line"]).sort_values(["season", "week"]).reset_index(drop=True)

    df_players = pd.read_parquet(RUTA_PLAYERS)
    df = asegurar_epa_rodante(df_games, df_players)
    df = preparar_features_spread(df)

    # Margen ATS: result - spread_line
    # result = home_score - away_score
    # ats_margin > 0 => Home cubre
    # ats_margin < 0 => Away cubre
    # ats_margin == 0 => Push (empate con la línea)
    df["ats_margin"] = df["result"] - df["spread_line"]

    train_mask = (df["season"] <= 2023) & (df["ats_margin"] != 0)
    test_mask = (df["season"] >= 2024)

    df_train = df[train_mask].copy()
    df_test = df[test_mask].copy()

    X_train = df_train[FEATURES_SPREAD].fillna(0).values
    y_train = (df_train["ats_margin"] > 0).astype(int).values

    X_test = df_test[FEATURES_SPREAD].fillna(0).values

    print(f"📊 Partidos de entrenamiento (2012-2023, sin empates de línea): {len(X_train):,}")
    print(f"📊 Partidos de prueba out-of-sample (2024-2026): {len(df_test):,}")

    # 1. Regresión Logística L2
    modelo_lr = LogisticRegression(C=0.012, max_iter=1000, random_state=42)
    modelo_lr.fit(X_train, y_train)

    # 2. HistGradientBoostingClassifier regularizado
    modelo_hgb = HistGradientBoostingClassifier(
        max_iter=40,
        max_leaf_nodes=10,
        min_samples_leaf=40,
        l2_regularization=4.0,
        random_state=42,
    )
    modelo_hgb.fit(X_train, y_train)

    # Construir Ensamble V1
    ensamble = EnsambleSpreadNFLv1(
        modelo_lr=modelo_lr,
        modelo_hgb=modelo_hgb,
        features=FEATURES_SPREAD,
        peso_lr=0.80,
        peso_hgb=0.20,
        umbral_edge=0.520,
    )

    # Guardar modelo
    RUTA_MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(ensamble, RUTA_MODELO)
    print(f"💾 Modelo guardado exitosamente en: {RUTA_MODELO}")

    # Evaluar rendimiento en prueba
    p_test = ensamble.predict_proba(df_test[FEATURES_SPREAD])[:, 1]
    
    # Backtest rápido de validación
    picks = []
    for i, (_, row) in enumerate(df_test.iterrows()):
        p_home = p_test[i]
        ats = row["ats_margin"]
        if ats == 0:
            continue
        if p_home >= 0.520:
            win = 1 if ats > 0 else 0
            picks.append({"season": row["season"], "win": win})
        elif (1 - p_home) >= 0.520:
            win = 1 if ats < 0 else 0
            picks.append({"season": row["season"], "win": win})

    df_picks = pd.DataFrame(picks)
    tot = len(df_picks)
    wins = int(df_picks["win"].sum())
    wr = wins / tot if tot > 0 else 0.0
    units = wins * (100 / 110) - (tot - wins)
    roi = units / tot * 100 if tot > 0 else 0.0

    metadata = {
        "modelo": "NFL Spread (ATS) V1",
        "version": ensamble.version,
        "n_features": len(FEATURES_SPREAD),
        "features": FEATURES_SPREAD,
        "peso_lr": ensamble.peso_lr,
        "peso_hgb": ensamble.peso_hgb,
        "umbral_edge_oficial": ensamble.umbral_edge,
        "entrenamiento": {
            "seasons": "2012-2023",
            "n_partidos": len(X_train),
        },
        "prueba_out_of_sample": {
            "seasons": "2024-2026",
            "n_partidos_totales": len(df_test),
            "picks_ejecutados": tot,
            "victorias": wins,
            "win_rate_pct": round(wr * 100, 2),
            "unidades_netas": round(units, 2),
            "roi_pct": round(roi, 2),
        },
    }

    with open(RUTA_METADATA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"📋 Metadatos guardados en: {RUTA_METADATA}")
    print(f"🎯 Validación Out-of-Sample (2024-2026): {wins}/{tot} ({wr*100:.2f}%) | {units:+.2f} U | ROI: {roi:+.2f}%")

    return ensamble


if __name__ == "__main__":
    entrenar_modelo_spread()
