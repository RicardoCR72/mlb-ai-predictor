"""Entrenamiento del Modelo de Moneyline NFL V2 (Ensamble EPA + LightGBM + Logistic Regression).

Incorpora:
1. Métricas causales avanzadas de EPA (Expected Points Added) de nflverse/nflreadpy:
   - Passing EPA rodante (8 partidos)
   - Rushing EPA rodante (8 partidos)
   - Total Offensive EPA rodante (8 partidos)
   - Sacks sufridos rodante (8 partidos)
2. Salud posicional diferencial:
   - Lesión de Mariscal de Campo titular (QB)
   - Lesión de Línea Ofensiva (OL) - factor crítico de protección y bolsa de pase
   - Lesión en Defensiva (Front 7 y Secundaria)
3. Ensamble ponderado calibrado:
   - Logistic Regression regularizada L2 (C=0.08)
   - LightGBM Classifier con calibración de probabilidad sigmoidea
4. Filtro de Zona Muerta / Números Clave para evitar picks con EV negativo.
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
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nfl.ensamble_moneyline_v2 import EnsambleMoneylineNFLv2

RUTA_GAMES = RAIZ / "data" / "nfl" / "processed" / "nfl_games_features_2012_2026.parquet"
RUTA_PLAYERS = RAIZ / "data" / "nfl" / "raw" / "nfl_player_stats_2012_2026.parquet"
RUTA_EPA_ROLLING = RAIZ / "data" / "nfl" / "processed" / "nfl_team_epa_rolling.parquet"
RUTA_MODELO = RAIZ / "modelos_nfl" / "modelo_moneyline_nfl.joblib"
RUTA_METADATA = RAIZ / "modelos_nfl" / "metadata_moneyline_nfl.json"

FEATURES_MONEYLINE_V2 = [
    "spread_line",
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


def calcular_epa_rodante_equipos(df_games: pd.DataFrame, df_players: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula métricas rodantes causales de EPA por equipo y las une a cada juego."""
    print("📊 Agregando estadísticas de jugadores y calculando EPA causal por equipo...")
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

    # Causalidad estricta (shift 1): solo partidos previos al juego actual
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

    # Guardar archivo de consulta rápida para inferencia
    RUTA_EPA_ROLLING.parent.mkdir(parents=True, exist_ok=True)
    team_stats.to_parquet(RUTA_EPA_ROLLING, index=False)
    print(f"💾 Métricas rodantes de EPA guardadas en {RUTA_EPA_ROLLING}")

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

    return df_full, team_stats


def entrenar_modelo_moneyline_v2():
    """Ejecuta el pipeline completo de entrenamiento y validación de Moneyline V2."""
    if not RUTA_GAMES.exists():
        raise FileNotFoundError(f"No se encontró el dataset en {RUTA_GAMES}")
    if not RUTA_PLAYERS.exists():
        raise FileNotFoundError(f"No se encontró el archivo de jugadores en {RUTA_PLAYERS}")

    df_games = pd.read_parquet(RUTA_GAMES)
    df_games = df_games.dropna(subset=["home_win", "spread_line"]).sort_values(["season", "week"]).reset_index(drop=True)

    df_players = pd.read_parquet(RUTA_PLAYERS)

    df, _ = calcular_epa_rodante_equipos(df_games, df_players)

    print(f"🏈 Partidos históricos con variables V2 preparadas: {len(df):,}")

    X = df[FEATURES_MONEYLINE_V2].fillna(0).copy()
    y = df["home_win"].astype(int)

    # Partición temporal de validación out-of-sample (Train < 2024, Test >= 2024)
    train_mask = df["season"] < 2024
    test_mask = df["season"] >= 2024

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    print(f"📊 Train set: {len(X_train)} partidos | Test set: {len(X_test)} partidos")

    # 1. Regresión Logística Calibrada (regularizada)
    base_lr = LogisticRegression(C=0.08, max_iter=1000, random_state=42)
    lr_cal = CalibratedClassifierCV(estimator=base_lr, method="sigmoid", cv=5)
    lr_cal.fit(X_train, y_train)

    # 2. LightGBM Calibrado
    lgb_base = lgb.LGBMClassifier(
        n_estimators=120,
        learning_rate=0.025,
        max_depth=3,
        num_leaves=7,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=1.0,
        reg_lambda=2.0,
        random_state=42,
        verbose=-1,
    )
    lgb_cal = CalibratedClassifierCV(estimator=lgb_base, method="sigmoid", cv=5)
    lgb_cal.fit(X_train, y_train)

    # Ensamble de validación
    ensamble_val = EnsambleMoneylineNFLv2(
        modelo_lr=lr_cal,
        modelo_lgb=lgb_cal,
        features=FEATURES_MONEYLINE_V2,
        peso_lr=0.65,
        peso_lgb=0.35,
    )

    probs_test = ensamble_val.predict_proba(X_test)[:, 1]
    preds_test = (probs_test >= 0.50).astype(int)

    auc = roc_auc_score(y_test, probs_test)
    brier = brier_score_loss(y_test, probs_test)
    ll = log_loss(y_test, probs_test)
    acc = accuracy_score(y_test, preds_test)

    print("\n" + "=" * 65)
    print("📈 MÉTRICAS OUT-OF-SAMPLE V2 (Temporadas 2024 - 2026):")
    print(f"   * ROC-AUC:    {auc:.4f}")
    print(f"   * Exactitud:  {acc * 100:.2f}%")
    print(f"   * Brier Score:{brier:.4f}")
    print(f"   * Log-Loss:   {ll:.4f}")
    print("=" * 65)

    # Simulación de rendimiento de apuestas con filtro de convicción
    test_df = df[test_mask].copy().reset_index(drop=True)
    test_df["p_model"] = probs_test

    def ml_to_dec(ml):
        if pd.isna(ml) or ml == 0:
            return 1.91
        return 1 + (100 / abs(ml)) if ml < 0 else 1 + (ml / 100)

    def ml_to_prob(ml):
        if pd.isna(ml) or ml == 0:
            return 0.5
        return abs(ml) / (abs(ml) + 100) if ml < 0 else 100 / (ml + 100)

    p_h = test_df["home_moneyline"].apply(ml_to_prob)
    p_a = test_df["away_moneyline"].apply(ml_to_prob)
    test_df["market_prob_fair"] = p_h / (p_h + p_a)
    test_df["dec_home"] = test_df["home_moneyline"].apply(ml_to_dec)
    test_df["dec_away"] = test_df["away_moneyline"].apply(ml_to_dec)

    picks = []
    for _, row in test_df.iterrows():
        pm = row["p_model"]
        pf = row["market_prob_fair"]
        edge_h = pm - pf
        edge_a = (1.0 - pm) - (1.0 - pf)

        # Regla de convicción: Prob >= 60% con Edge >= 1.0% (evita zona muerta)
        if pm >= 0.60 and edge_h >= 0.01:
            ganada = bool(row["home_win"] == 1)
            beneficio = (row["dec_home"] - 1.0) if ganada else -1.0
            picks.append({"ganada": ganada, "beneficio": beneficio, "cuota": row["dec_home"]})
        elif (1.0 - pm) >= 0.60 and edge_a >= 0.01:
            ganada = bool(row["home_win"] == 0)
            beneficio = (row["dec_away"] - 1.0) if ganada else -1.0
            picks.append({"ganada": ganada, "beneficio": beneficio, "cuota": row["dec_away"]})

    p_df = pd.DataFrame(picks)
    win_rate = float(p_df["ganada"].mean() * 100) if not p_df.empty else 0.0
    u_ganadas = float(p_df["beneficio"].sum()) if not p_df.empty else 0.0
    roi = float((u_ganadas / len(p_df)) * 100) if not p_df.empty else 0.0

    print("🎯 BACKTEST DE PICKS CON ALTA CONVICCIÓN (Prob >= 60% | Edge >= +1.0%):")
    print(f"   * Total Picks Filtrados: {len(p_df)} partidos")
    print(f"   * Win Rate:              {win_rate:.2f}%")
    print(f"   * Unidades Generadas:    {u_ganadas:+.2f} U")
    print(f"   * ROI sobre Bankroll:    {roi:+.2f}%")
    print("=" * 65)

    # Entrenar modelo final con 100% de los datos para producción
    print("\n🚀 Entrenando ensamble final con todo el histórico (2012-2026)...")
    final_lr = CalibratedClassifierCV(estimator=LogisticRegression(C=0.08, max_iter=1000, random_state=42), method="sigmoid", cv=5)
    final_lr.fit(X, y)

    final_lgb = CalibratedClassifierCV(
        estimator=lgb.LGBMClassifier(
            n_estimators=120,
            learning_rate=0.025,
            max_depth=3,
            num_leaves=7,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=1.0,
            reg_lambda=2.0,
            random_state=42,
            verbose=-1,
        ),
        method="sigmoid",
        cv=5,
    )
    final_lgb.fit(X, y)

    modelo_final = EnsambleMoneylineNFLv2(
        modelo_lr=final_lr,
        modelo_lgb=final_lgb,
        features=FEATURES_MONEYLINE_V2,
        peso_lr=0.65,
        peso_lgb=0.35,
        version="v2_ensemble_epa",
    )

    bundle = {
        "modelo": modelo_final,
        "features": FEATURES_MONEYLINE_V2,
        "version": "v2_ensemble_epa",
        "metricas": {
            "auc": round(float(auc), 4),
            "accuracy": round(float(acc), 4),
            "brier": round(float(brier), 4),
            "log_loss": round(float(ll), 4),
            "backtest_picks": len(p_df),
            "backtest_win_rate": round(win_rate, 2),
            "backtest_unidades": round(u_ganadas, 2),
            "backtest_roi": round(roi, 2),
        },
    }

    RUTA_MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, RUTA_MODELO)
    print(f"\n💾 Modelo Ensamble V2 guardado exitosamente en: {RUTA_MODELO}")

    metadata = {
        "modelo": "nfl_moneyline_v2_ensemble",
        "version": "v2_ensemble_epa",
        "algoritmo": "Ensamble Hibrido Ponderado (Calibrated Logistic Regression 65% + Calibrated LightGBM 35%)",
        "variables_clave": FEATURES_MONEYLINE_V2,
        "metricas_out_of_sample": bundle["metricas"],
        "fecha_entrenamiento": pd.Timestamp.now().isoformat(),
        "total_partidos_entrenamiento": len(df),
    }

    with open(RUTA_METADATA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"📋 Metadatos guardados en: {RUTA_METADATA}\n")

    return bundle


if __name__ == "__main__":
    entrenar_modelo_moneyline_v2()
