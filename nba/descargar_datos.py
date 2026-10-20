"""Descarga de datos históricos de partidos de la NBA mediante nba_api.

Guarda los boxscores de cada equipo por partido para las temporadas deseadas en data/nba/raw/.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from nba_api.stats.endpoints import leaguegamefinder

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

RUTA_RAW = RAIZ / "data" / "nba" / "raw"
RUTA_RAW.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Temporadas históricas recomendadas para entrenamiento
TEMPORADAS_DEFECTO = [
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
]


def descargar_temporada(temporada: str) -> pd.DataFrame:
    """Descarga todos los partidos de una temporada específica de la NBA (league_id='00')."""
    logger.info(f"⏳ Descargando temporada NBA {temporada}...")
    try:
        # League_id '00' corresponde a la NBA (excluyendo G-League '20' y WNBA '10')
        finder = leaguegamefinder.LeagueGameFinder(
            season_nullable=temporada,
            league_id_nullable="00"
        )
        df = finder.get_data_frames()[0]
        logger.info(f"   -> {len(df)} registros obtenidos para {temporada}.")
        return df
    except Exception as err:
        logger.error(f"❌ Error al descargar temporada {temporada}: {err}")
        return pd.DataFrame()


def descargar_datos_historicos(
    temporadas: Optional[List[str]] = None,
    guardar_csv: bool = True,
    guardar_parquet: bool = True
) -> pd.DataFrame:
    """Descarga partidos de múltiples temporadas y los consolida en data/nba/raw/."""
    temporadas = temporadas or TEMPORADAS_DEFECTO
    dfs = []

    for temp in temporadas:
        df_temp = descargar_temporada(temp)
        if not df_temp.empty:
            df_temp["SEASON"] = temp
            dfs.append(df_temp)
        time.sleep(0.8)  # Pequeña pausa para respetar el rate limit de stats.nba.com

    if not dfs:
        logger.error("No se descargaron datos de ninguna temporada.")
        return pd.DataFrame()

    df_total = pd.concat(dfs, ignore_index=True)
    
    # Formatear columnas básicas
    df_total["GAME_DATE"] = pd.to_datetime(df_total["GAME_DATE"])
    df_total = df_total.sort_values(["GAME_DATE", "GAME_ID"]).reset_index(drop=True)

    # Rutas de guardado
    archivo_parquet = RUTA_RAW / "partidos_historicos_nba.parquet"
    archivo_csv = RUTA_RAW / "partidos_historicos_nba.csv"

    if guardar_parquet:
        df_total.to_parquet(archivo_parquet, index=False)
        logger.info(f"💾 Guardado Parquet: {archivo_parquet} ({len(df_total)} filas)")

    if guardar_csv:
        df_total.to_csv(archivo_csv, index=False, encoding="utf-8")
        logger.info(f"💾 Guardado CSV: {archivo_csv}")

    return df_total


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("🏀 Iniciando descarga de datos históricos de la NBA...")
    df = descargar_datos_historicos()
    if not df.empty:
        print("\n✅ Resumen de descarga:")
        print(f"Total registros (equipo-partido): {len(df):,}")
        print(f"Total partidos únicos: {df['GAME_ID'].nunique():,}")
        print("\nRegistros por temporada:")
        print(df.groupby("SEASON")["GAME_ID"].nunique().to_string())
    else:
        print("❌ No se pudieron descargar los datos.")
