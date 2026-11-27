"""Script Oficial de Backtesting del Modelo de Spread (ATS) NFL V1.

Evalúa el rendimiento fuera de muestra (out-of-sample) en 682 partidos de las
temporadas 2024, 2025 y 2026 sin sesgo de anticipación.
Calcula métricas financieras bajo cuotas estándar de mercado (-110, juice de 4.54%):
- Punto de equilibrio: 52.38%
- Victoria: +0.9091 unidades
- Derrota: -1.0000 unidades
- Push (empate con la línea): 0.0 unidades
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

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nfl.ensamble_spread_v1 import EnsambleSpreadNFLv1
from nfl.entrenar_spread import FEATURES_SPREAD, preparar_features_spread

RUTA_GAMES = RAIZ / "data" / "nfl" / "processed" / "nfl_games_features_2012_2026.parquet"
RUTA_EPA_ROLLING = RAIZ / "data" / "nfl" / "processed" / "nfl_team_epa_rolling.parquet"
RUTA_MODELO = RAIZ / "modelos_nfl" / "modelo_spread_nfl.joblib"
RUTA_REPORTE_JSON = RAIZ / "modelos_nfl" / "reporte_backtest_spread.json"


def cargar_datos_prueba() -> pd.DataFrame:
    """Carga los partidos de prueba (2024-2026) con EPA rodante causal y variables situacionales."""
    df_games = pd.read_parquet(RUTA_GAMES)
    df_games = df_games.dropna(subset=["result", "spread_line"]).sort_values(["season", "week"]).reset_index(drop=True)

    team_stats = pd.read_parquet(RUTA_EPA_ROLLING)

    cols_epa = [
        "game_id", "team",
        "roll_pass_epa_8", "roll_rush_epa_8", "roll_total_epa_8", "roll_sacks_8",
        "roll_def_pass_epa_8", "roll_def_rush_epa_8", "roll_def_sacks_8",
    ]

    home_epa = team_stats[cols_epa].copy()
    home_epa.columns = [
        "game_id",
        "home_team",
        "home_pass_epa_8",
        "home_rush_epa_8",
        "home_total_epa_8",
        "home_sacks_8",
        "home_def_pass_epa_8",
        "home_def_rush_epa_8",
        "home_def_sacks_8",
    ]

    away_epa = team_stats[cols_epa].copy()
    away_epa.columns = [
        "game_id",
        "away_team",
        "away_pass_epa_8",
        "away_rush_epa_8",
        "away_total_epa_8",
        "away_sacks_8",
        "away_def_pass_epa_8",
        "away_def_rush_epa_8",
        "away_def_sacks_8",
    ]

    df = df_games.merge(home_epa, on=["game_id", "home_team"], how="left")
    df = df.merge(away_epa, on=["game_id", "away_team"], how="left")

    df["diff_pass_epa_8"] = (df["home_pass_epa_8"] - df["away_pass_epa_8"]).fillna(0.0)
    df["diff_rush_epa_8"] = (df["home_rush_epa_8"] - df["away_rush_epa_8"]).fillna(0.0)
    df["diff_total_epa_8"] = (df["home_total_epa_8"] - df["away_total_epa_8"]).fillna(0.0)
    df["diff_sacks_8"] = (df["home_sacks_8"] - df["away_sacks_8"]).fillna(0.0)
    df["diff_def_pass_epa_8"] = (df["home_def_pass_epa_8"] - df["away_def_pass_epa_8"]).fillna(0.0)
    df["diff_def_rush_epa_8"] = (df["home_def_rush_epa_8"] - df["away_def_rush_epa_8"]).fillna(0.0)
    df["diff_def_sacks_8"] = (df["home_def_sacks_8"] - df["away_def_sacks_8"]).fillna(0.0)

    df = preparar_features_spread(df)
    df["ats_margin"] = df["result"] - df["spread_line"]

    # Filtrar solo temporadas out-of-sample
    test_df = df[df["season"] >= 2024].copy().reset_index(drop=True)
    return test_df


def simular_estrategia(df_test: pd.DataFrame, ensamble: EnsambleSpreadNFLv1, umbral: float) -> pd.DataFrame:
    """Ejecuta la simulación histórica de selecciones para un umbral determinado."""
    p_home_all = ensamble.predict_proba(df_test[FEATURES_SPREAD])[:, 1]

    picks = []
    for i, row in df_test.iterrows():
        p_home = p_home_all[i]
        p_away = 1.0 - p_home
        ats = row["ats_margin"]
        spread = row["spread_line"]

        # Si ats == 0 es push de mercado
        if p_home >= umbral:
            lado = "HOME"
            prob = p_home
            rol = "FAVORITO" if spread > 0 else ("UNDERDOG" if spread < 0 else "EVEN")
            if ats > 0:
                resultado = "WIN"
                pnl = 100.0 / 110.0  # +0.9091 U
            elif ats < 0:
                resultado = "LOSS"
                pnl = -1.0  # -1.0000 U
            else:
                resultado = "PUSH"
                pnl = 0.0
            picks.append({
                "game_id": row["game_id"],
                "season": int(row["season"]),
                "week": int(row["week"]),
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "spread_line": spread,
                "pick_team": row["home_team"],
                "lado": lado,
                "rol": rol,
                "prob": round(prob, 4),
                "ats_margin": ats,
                "resultado": resultado,
                "pnl": pnl,
                "div_game": int(row.get("div_game", 0)),
                "abs_spread": abs(spread),
            })
        elif p_away >= umbral:
            lado = "AWAY"
            prob = p_away
            rol = "UNDERDOG" if spread > 0 else ("FAVORITO" if spread < 0 else "EVEN")
            if ats < 0:
                resultado = "WIN"
                pnl = 100.0 / 110.0
            elif ats > 0:
                resultado = "LOSS"
                pnl = -1.0
            else:
                resultado = "PUSH"
                pnl = 0.0
            picks.append({
                "game_id": row["game_id"],
                "season": int(row["season"]),
                "week": int(row["week"]),
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "spread_line": spread,
                "pick_team": row["away_team"],
                "lado": lado,
                "rol": rol,
                "prob": round(prob, 4),
                "ats_margin": ats,
                "resultado": resultado,
                "pnl": pnl,
                "div_game": int(row.get("div_game", 0)),
                "abs_spread": abs(spread),
            })

    return pd.DataFrame(picks)


def calcular_metricas(df_picks: pd.DataFrame) -> dict[str, any]:
    """Calcula las métricas financieras y de riesgo de un conjunto de picks."""
    if len(df_picks) == 0:
        return {"total_picks": 0}

    # Separar resultados activos (excluyendo pushes para win rate estándar)
    decididos = df_picks[df_picks["resultado"].isin(["WIN", "LOSS"])]
    pushes = int((df_picks["resultado"] == "PUSH").sum())
    wins = int((decididos["resultado"] == "WIN").sum())
    losses = int((decididos["resultado"] == "LOSS").sum())
    n_decididos = len(decididos)

    win_rate = (wins / n_decididos * 100) if n_decididos > 0 else 0.0
    unidades = float(df_picks["pnl"].sum())
    roi = (unidades / len(df_picks) * 100) if len(df_picks) > 0 else 0.0

    # Racha y Drawdown
    pnl_series = df_picks["pnl"].values
    cum_pnl = np.cumsum(pnl_series)
    peak = np.maximum.accumulate(cum_pnl)
    drawdowns = peak - cum_pnl
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Profit Factor
    ganancias = float(df_picks[df_picks["pnl"] > 0]["pnl"].sum())
    perdidas = float(abs(df_picks[df_picks["pnl"] < 0]["pnl"].sum()))
    profit_factor = (ganancias / perdidas) if perdidas > 0 else 999.0

    # Rachas consecutivas
    max_win_streak = 0
    max_loss_streak = 0
    cur_win = 0
    cur_loss = 0
    for res in decididos["resultado"]:
        if res == "WIN":
            cur_win += 1
            cur_loss = 0
            if cur_win > max_win_streak:
                max_win_streak = cur_win
        elif res == "LOSS":
            cur_loss += 1
            cur_win = 0
            if cur_loss > max_loss_streak:
                max_loss_streak = cur_loss

    return {
        "total_picks": len(df_picks),
        "decididos": n_decididos,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "record": f"{wins}W - {losses}L - {pushes}P",
        "win_rate_pct": round(win_rate, 2),
        "unidades": round(unidades, 2),
        "roi_pct": round(roi, 2),
        "max_drawdown": round(max_drawdown, 2),
        "profit_factor": round(profit_factor, 2),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
    }


def ejecutar_backtest_completo():
    """Ejecuta el backtest multidimensional completo del modelo de Spread NFL."""
    print("=" * 80)
    print("🏈 BACKTEST OFICIAL: MODELO DE SPREAD (ATS) NFL V1")
    print("=" * 80)
    print("Entorno: 682 partidos out-of-sample (Temporadas 2024, 2025 y 2026)")
    print("Líneas de mercado con cuota estándar -110 (BEP = 52.38%)")
    print("-" * 80)

    if not RUTA_MODELO.exists():
        print(f"❌ No se encontró el modelo en {RUTA_MODELO}. Entrenando primero...")
        from nfl.entrenar_spread import entrenar_modelo_spread
        ensamble = entrenar_modelo_spread()
    else:
        ensamble = joblib.load(RUTA_MODELO)

    df_test = cargar_datos_prueba()
    print(f"Partidos totales analizados en ventana de prueba: {len(df_test):,}")

    umbrales = [0.515, 0.520, 0.525, 0.530, 0.540]
    res_umbrales = {}

    print("\n📈 1. COMPARATIVA DE RENDIMIENTO POR UMBRAL DE VENTAJA (EDGE):")
    print(f"{'Umbral':<8} | {'Picks':<6} | {'Récord':<14} | {'Win Rate':<10} | {'Unidades':<10} | {'ROI':<8} | {'Max DD':<8} | {'Prof Fact':<8}")
    print("-" * 85)

    for u in umbrales:
        picks_u = simular_estrategia(df_test, ensamble, u)
        m = calcular_metricas(picks_u)
        res_umbrales[str(u)] = m
        print(
            f"P >= {u:.3f} | {m['total_picks']:<6} | {m['record']:<14} | {m['win_rate_pct']:>6.2f}%   | {m['unidades']:>+7.2f} U  | {m['roi_pct']:>+5.2f}% | {m['max_drawdown']:>6.2f} U | {m['profit_factor']:>6.2f}"
        )

    # Análisis Profundo del Umbral Oficial (0.530)
    u_oficial = float(getattr(ensamble, "umbral_edge", 0.530))
    df_picks_oficial = simular_estrategia(df_test, ensamble, u_oficial)
    m_oficial = calcular_metricas(df_picks_oficial)

    print("\n" + "=" * 80)
    print(f"🎯 2. ANÁLISIS DETALLADO DEL UMBRAL OFICIAL (P >= {u_oficial:.3f})")
    print("=" * 80)

    # Desglose por Temporada
    print("\n📅 A) Rendimiento por Temporada:")
    print(f"{'Temporada':<10} | {'Picks':<6} | {'Récord':<14} | {'Win Rate':<10} | {'Unidades':<10} | {'ROI':<8}")
    print("-" * 65)
    desglose_temporada = {}
    for yr in [2024, 2025, 2026]:
        sub = df_picks_oficial[df_picks_oficial["season"] == yr]
        m_yr = calcular_metricas(sub)
        desglose_temporada[str(yr)] = m_yr
        print(
            f"{yr:<10} | {m_yr['total_picks']:<6} | {m_yr['record']:<14} | {m_yr['win_rate_pct']:>6.2f}%   | {m_yr['unidades']:>+7.2f} U  | {m_yr['roi_pct']:>+5.2f}%"
        )

    # Desglose por Rol (Favorito vs Underdog)
    print("\n🛡️ B) Rendimiento por Rol de Mercado (Underdog vs Favorito):")
    print(f"{'Rol':<12} | {'Picks':<6} | {'Récord':<14} | {'Win Rate':<10} | {'Unidades':<10} | {'ROI':<8}")
    print("-" * 65)
    desglose_rol = {}
    for r in ["UNDERDOG", "FAVORITO"]:
        sub = df_picks_oficial[df_picks_oficial["rol"] == r]
        m_r = calcular_metricas(sub)
        desglose_rol[r] = m_r
        print(
            f"{r:<12} | {m_r['total_picks']:<6} | {m_r['record']:<14} | {m_r['win_rate_pct']:>6.2f}%   | {m_r['unidades']:>+7.2f} U  | {m_r['roi_pct']:>+5.2f}%"
        )

    # Desglose por Local vs Visitante
    print("\n🏟️ C) Rendimiento por Condición (Local vs Visitante):")
    print(f"{'Lado':<12} | {'Picks':<6} | {'Récord':<14} | {'Win Rate':<10} | {'Unidades':<10} | {'ROI':<8}")
    print("-" * 65)
    desglose_lado = {}
    for s in ["HOME", "AWAY"]:
        sub = df_picks_oficial[df_picks_oficial["lado"] == s]
        m_s = calcular_metricas(sub)
        desglose_lado[s] = m_s
        print(
            f"{s:<12} | {m_s['total_picks']:<6} | {m_s['record']:<14} | {m_s['win_rate_pct']:>6.2f}%   | {m_s['unidades']:>+7.2f} U  | {m_s['roi_pct']:>+5.2f}%"
        )

    # Desglose Números Clave
    print("\n🔑 D) Rendimiento en Números Clave de la NFL:")
    print(f"{'Grupo':<20} | {'Picks':<6} | {'Récord':<14} | {'Win Rate':<10} | {'Unidades':<10} | {'ROI':<8}")
    print("-" * 75)
    desglose_clave = {}
    grupos_clave = {
        "Spread 3.0 / 3.5": df_picks_oficial[df_picks_oficial["abs_spread"].isin([3.0, 3.5])],
        "Spread 7.0 / 7.5": df_picks_oficial[df_picks_oficial["abs_spread"].isin([7.0, 7.5])],
        "Otros Spreads": df_picks_oficial[~df_picks_oficial["abs_spread"].isin([3.0, 3.5, 7.0, 7.5])],
    }
    for k, sub in grupos_clave.items():
        m_k = calcular_metricas(sub)
        desglose_clave[k] = m_k
        print(
            f"{k:<20} | {m_k['total_picks']:<6} | {m_k['record']:<14} | {m_k['win_rate_pct']:>6.2f}%   | {m_k['unidades']:>+7.2f} U  | {m_k['roi_pct']:>+5.2f}%"
        )

    # Guardar reporte JSON
    reporte_final = {
        "version": ensamble.version,
        "n_juegos_evaluados": len(df_test),
        "umbral_oficial": u_oficial,
        "resumen_oficial": m_oficial,
        "desglose_temporada": desglose_temporada,
        "desglose_rol": desglose_rol,
        "desglose_lado": desglose_lado,
        "desglose_clave": desglose_clave,
        "comparativa_umbrales": res_umbrales,
    }

    with open(RUTA_REPORTE_JSON, "w", encoding="utf-8") as f:
        json.dump(reporte_final, f, indent=2, ensure_ascii=False)
    print("\n" + "=" * 80)
    print(f"💾 Reporte completo exportado a: {RUTA_REPORTE_JSON}")
    print("=" * 80)


if __name__ == "__main__":
    ejecutar_backtest_completo()
