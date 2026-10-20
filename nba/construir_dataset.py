"""Construcción y Feature Engineering del dataset analítico de la NBA.

Transforma los boxscores crudos en un dataset a nivel de partido con:
- Posesiones y Pace normalizado a 48 minutos.
- Ratings ofensivos, defensivos y netos (ORtg, DRtg, NetRtg).
- Four Factors de Dean Oliver (eFG%, TOV%, ORB%, FT Rate).
- Medias rodantes (L5, L10, L20) con .shift(1) para evitar Data Leakage.
- Días de descanso, banderas Back-to-Back (B2B) y fatiga de calendario.
- Diferenciales entre local y visitante (Matchup Features).
- Targets: Margen de victoria (Spread), Ganador directo (Moneyline) y Puntos totales (Over/Under).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

RUTA_RAW = RAIZ / "data" / "nba" / "raw" / "partidos_historicos_nba.parquet"
RUTA_PROCESSED = RAIZ / "data" / "nba" / "processed"
RUTA_PROCESSED.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def resolver_local_visitante(df: pd.DataFrame) -> pd.DataFrame:
    """Identifica con 100% de precisión al equipo local y visitante según MATCHUP."""
    def obtener_local(matchup: str) -> str:
        if " vs. " in matchup:
            return matchup.split(" vs. ")[0].strip()
        elif " @ " in matchup:
            return matchup.split(" @ ")[1].strip()
        return ""

    df = df.copy()
    home_teams = df["MATCHUP"].apply(obtener_local)
    df["IS_HOME"] = (df["TEAM_ABBREVIATION"] == home_teams).astype(int)
    return df


def calcular_metricas_avanzadas_equipo(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula posesiones, pace, four factors y ratings por equipo-partido."""
    df = df.copy()
    
    # Minutos jugados normalizados por equipo (normalmente 240 en 48 min de 5 jugadores)
    minutos = df["MIN"].replace(0, 240)
    
    # 1. Posesiones estimadas (Fórmula estándar de Dean Oliver)
    # Poss = FGA - OREB + TOV + (0.44 * FTA)
    df["POSS"] = df["FGA"] - df["OREB"] + df["TOV"] + (0.44 * df["FTA"])
    df["POSS"] = df["POSS"].clip(lower=60, upper=140)

    # 2. Pace (Posesiones proyectadas a 48 minutos)
    df["PACE"] = (df["POSS"] * 48.0) / (minutos / 5.0)

    # 3. Four Factors
    # eFG% = (FGM + 0.5 * FG3M) / FGA
    df["EFG_PCT"] = np.where(df["FGA"] > 0, (df["FGM"] + 0.5 * df["FG3M"]) / df["FGA"], 0.0)
    
    # TS% = PTS / (2 * (FGA + 0.44 * FTA))
    true_shot_denom = 2 * (df["FGA"] + 0.44 * df["FTA"])
    df["TS_PCT"] = np.where(true_shot_denom > 0, df["PTS"] / true_shot_denom, 0.0)
    
    # TOV% = TOV / Poss
    df["TOV_PCT"] = np.where(df["POSS"] > 0, df["TOV"] / df["POSS"], 0.0)
    
    # FT Rate = FTM / FGA
    df["FT_RATE"] = np.where(df["FGA"] > 0, df["FTM"] / df["FGA"], 0.0)

    # Win flag
    df["WIN"] = (df["WL"] == "W").astype(int)

    return df


def fusionar_datos_rival(df: pd.DataFrame) -> pd.DataFrame:
    """Cruza cada fila de equipo con su rival en el mismo GAME_ID para obtener métricas defensivas."""
    cols_rival = ["GAME_ID", "TEAM_ABBREVIATION", "PTS", "POSS", "DREB", "OREB", "EFG_PCT"]
    df_rival = df[cols_rival].copy()
    df_rival.columns = [
        "GAME_ID", "OPP_ABBREVIATION", "OPP_PTS", "OPP_POSS", "OPP_DREB", "OPP_OREB", "OPP_EFG_PCT"
    ]

    # Merge donde el rival es el otro equipo en el mismo partido
    merged = pd.merge(df, df_rival, on="GAME_ID")
    merged = merged[merged["TEAM_ABBREVIATION"] != merged["OPP_ABBREVIATION"]].copy()

    # Offensive y Defensive Rating (Puntos anotados y permitidos por cada 100 posesiones)
    merged["ORTG"] = np.where(merged["POSS"] > 0, 100.0 * (merged["PTS"] / merged["POSS"]), 100.0)
    merged["DRTG"] = np.where(merged["OPP_POSS"] > 0, 100.0 * (merged["OPP_PTS"] / merged["OPP_POSS"]), 100.0)
    merged["NET_RTG"] = merged["ORTG"] - merged["DRTG"]

    # Offensive Rebounding Percentage (ORB%)
    reb_denom = merged["OREB"] + merged["OPP_DREB"]
    merged["ORB_PCT"] = np.where(reb_denom > 0, merged["OREB"] / reb_denom, 0.0)

    return merged


def calcular_descanso_y_fatiga(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula días de descanso, back-to-back y 3-en-4 para cada equipo a lo largo del tiempo."""
    df = df.sort_values(["TEAM_ABBREVIATION", "GAME_DATE"]).reset_index(drop=True)
    
    # Diferencia de días con el partido anterior del mismo equipo
    diff_dias = df.groupby("TEAM_ABBREVIATION")["GAME_DATE"].diff().dt.days
    
    # Imputar 3 días de descanso (promedio de liga) para el primer partido de temporada
    df["REST_DAYS"] = diff_dias.fillna(3).clip(lower=0, upper=7).astype(float)
    df["IS_B2B"] = (df["REST_DAYS"] == 1).astype(int)
    
    # 3 partidos en 4 noches
    diff_2_juegos = df.groupby("TEAM_ABBREVIATION")["GAME_DATE"].diff(2).dt.days
    df["IS_3_IN_4"] = (diff_2_juegos <= 4).fillna(False).astype(int)

    return df


def calcular_medias_rodantes(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula promedios rodantes L5, L10 y L20 usando estrictamente .shift(1) para evitar Data Leakage."""
    df = df.sort_values(["TEAM_ABBREVIATION", "GAME_DATE"]).reset_index(drop=True)

    metricas_rodantes = [
        "PTS", "OPP_PTS", "PACE", "ORTG", "DRTG", "NET_RTG",
        "EFG_PCT", "TOV_PCT", "ORB_PCT", "FT_RATE", "WIN"
    ]

    grouped = df.groupby("TEAM_ABBREVIATION", group_keys=False)

    for ventana in [5, 10, 20]:
        pref = f"L{ventana}"
        # .shift(1) asegura que el partido de hoy NO esté incluido en la media
        rodante = grouped[metricas_rodantes].apply(
            lambda x: x.shift(1).rolling(window=ventana, min_periods=2).mean()
        )
        for col in metricas_rodantes:
            df[f"{col}_{pref}"] = rodante[col]

    return df


def construir_dataset_partidos(df_teams: pd.DataFrame) -> pd.DataFrame:
    """Transforma los datos por equipo a filas únicas por partido con features diferenciales."""
    local = df_teams[df_teams["IS_HOME"] == 1].copy()
    visita = df_teams[df_teams["IS_HOME"] == 0].copy()

    # Prefijar columnas para local y visitante
    cols_meta = ["GAME_ID", "GAME_DATE", "SEASON"]
    cols_targets_local = ["PTS", "WIN"]
    cols_targets_visita = ["PTS"]

    cols_features = [
        "REST_DAYS", "IS_B2B", "IS_3_IN_4",
        # L5
        "PTS_L5", "OPP_PTS_L5", "PACE_L5", "ORTG_L5", "DRTG_L5", "NET_RTG_L5",
        "EFG_PCT_L5", "TOV_PCT_L5", "ORB_PCT_L5", "FT_RATE_L5", "WIN_L5",
        # L10
        "PTS_L10", "OPP_PTS_L10", "PACE_L10", "ORTG_L10", "DRTG_L10", "NET_RTG_L10",
        "EFG_PCT_L10", "TOV_PCT_L10", "ORB_PCT_L10", "FT_RATE_L10", "WIN_L10",
        # L20
        "PTS_L20", "OPP_PTS_L20", "PACE_L20", "ORTG_L20", "DRTG_L20", "NET_RTG_L20",
        "EFG_PCT_L20", "TOV_PCT_L20", "ORB_PCT_L20", "FT_RATE_L20", "WIN_L20",
    ]

    local_sub = local[cols_meta + ["TEAM_ABBREVIATION"] + cols_targets_local + cols_features].copy()
    local_sub.rename(columns={"TEAM_ABBREVIATION": "HOME_TEAM", "PTS": "HOME_PTS", "WIN": "HOME_WIN"}, inplace=True)
    for c in cols_features:
        local_sub.rename(columns={c: f"HOME_{c}"}, inplace=True)

    visita_sub = visita[["GAME_ID", "TEAM_ABBREVIATION"] + cols_targets_visita + cols_features].copy()
    visita_sub.rename(columns={"TEAM_ABBREVIATION": "AWAY_TEAM", "PTS": "AWAY_PTS"}, inplace=True)
    for c in cols_features:
        visita_sub.rename(columns={c: f"AWAY_{c}"}, inplace=True)

    partidos = pd.merge(local_sub, visita_sub, on="GAME_ID")

    # Targets finales
    partidos["TOTAL_PTS"] = partidos["HOME_PTS"] + partidos["AWAY_PTS"]
    partidos["MARGIN_HOME"] = partidos["HOME_PTS"] - partidos["AWAY_PTS"]

    # Features diferenciales del enfrentamiento (Matchup Differentials)
    partidos["DIFF_NET_RTG_L5"] = partidos["HOME_NET_RTG_L5"] - partidos["AWAY_NET_RTG_L5"]
    partidos["DIFF_NET_RTG_L10"] = partidos["HOME_NET_RTG_L10"] - partidos["AWAY_NET_RTG_L10"]
    partidos["DIFF_NET_RTG_L20"] = partidos["HOME_NET_RTG_L20"] - partidos["AWAY_NET_RTG_L20"]

    partidos["DIFF_ORTG_L10"] = partidos["HOME_ORTG_L10"] - partidos["AWAY_ORTG_L10"]
    partidos["DIFF_DRTG_L10"] = partidos["HOME_DRTG_L10"] - partidos["AWAY_DRTG_L10"]
    partidos["DIFF_EFG_L10"] = partidos["HOME_EFG_PCT_L10"] - partidos["AWAY_EFG_PCT_L10"]
    partidos["DIFF_WIN_L10"] = partidos["HOME_WIN_L10"] - partidos["AWAY_WIN_L10"]
    partidos["DIFF_REST"] = partidos["HOME_REST_DAYS"] - partidos["AWAY_REST_DAYS"]

    # Proyección combinada de Pace y Puntos esperados
    partidos["PACE_PROYECTADO_L10"] = (partidos["HOME_PACE_L10"] + partidos["AWAY_PACE_L10"]) / 2.0
    partidos["OFF_VS_DEF_HOME"] = partidos["HOME_ORTG_L10"] - partidos["AWAY_DRTG_L10"]
    partidos["OFF_VS_DEF_AWAY"] = partidos["AWAY_ORTG_L10"] - partidos["HOME_DRTG_L10"]

    # Eliminar primeros partidos de cada temporada que aún no tengan al menos 2 partidos previos
    partidos = partidos.dropna(subset=["HOME_PTS_L5", "AWAY_PTS_L5", "DIFF_NET_RTG_L10"]).reset_index(drop=True)

    return partidos


def procesar_pipeline_completo() -> pd.DataFrame:
    """Ejecuta el pipeline de Feature Engineering de extremo a extremo."""
    logger.info("🏀 Iniciando pipeline de Feature Engineering NBA...")
    
    if not RUTA_RAW.exists():
        raise FileNotFoundError(f"No se encontró el archivo {RUTA_RAW}. Ejecuta antes nba/descargar_datos.py.")

    df_raw = pd.read_parquet(RUTA_RAW)
    # Filtrar solo juegos oficiales (Regular Season '002', Playoffs '004', Play-In '005')
    df_raw = df_raw[df_raw["GAME_ID"].str[:3].isin(["002", "004", "005"])].copy()
    logger.info(f"Partidos oficiales a procesar: {df_raw['GAME_ID'].nunique():,} ({len(df_raw):,} filas equipo-partido)")

    df_home = resolver_local_visitante(df_raw)
    df_metrics = calcular_metricas_avanzadas_equipo(df_home)
    df_opp = fusionar_datos_rival(df_metrics)
    df_rest = calcular_descanso_y_fatiga(df_opp)
    df_rolling = calcular_medias_rodantes(df_rest)
    dataset = construir_dataset_partidos(df_rolling)

    logger.info(f"✅ Dataset final construido con {len(dataset):,} partidos y {len(dataset.columns)} columnas.")

    # Guardar en data/nba/processed/
    out_parquet = RUTA_PROCESSED / "dataset_partidos_nba.parquet"
    out_csv = RUTA_PROCESSED / "dataset_partidos_nba.csv"
    
    dataset.to_parquet(out_parquet, index=False)
    dataset.to_csv(out_csv, index=False, encoding="utf-8")
    
    logger.info(f"💾 Guardado: {out_parquet}")
    logger.info(f"💾 Guardado: {out_csv}")

    return dataset


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    df = procesar_pipeline_completo()

    print("\n📊 Primeras filas del dataset procesado:")
    print(df[["GAME_DATE", "HOME_TEAM", "AWAY_TEAM", "HOME_PTS", "AWAY_PTS", "MARGIN_HOME", "TOTAL_PTS", "DIFF_NET_RTG_L10", "PACE_PROYECTADO_L10"]].head(5))

    print("\n🔍 Correlaciones más fuertes con el Margen de Victoria (MARGIN_HOME):")
    corrs_margin = df.select_dtypes(include=[np.number]).corr()["MARGIN_HOME"].sort_values(ascending=False)
    print(pd.concat([corrs_margin.head(6), corrs_margin.tail(5)]))

    print("\n🔍 Correlaciones más fuertes con los Puntos Totales (TOTAL_PTS):")
    corrs_total = df.select_dtypes(include=[np.number]).corr()["TOTAL_PTS"].sort_values(ascending=False)
    print(pd.concat([corrs_total.head(6), corrs_total.tail(5)]))
