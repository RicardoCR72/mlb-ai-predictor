"""Script de actualización y sincronización de boxscores oficiales de la temporada actual NBA.

1. Extrae todos los partidos finalizados de la temporada 2026-27 desde la API de ESPN (desde el tip-off de octubre hasta hoy).
2. Transforma cada boxscore al esquema estándar de 29 columnas (Posesiones, Four Factors, Tiros, Rebotes, Pérdidas).
3. Integra las nuevas filas a data/nba/raw/partidos_historicos_nba.parquet sin duplicados.
4. Ejecuta el pipeline completo de Feature Engineering (nba/construir_dataset.py).
5. Re-entrena los ensambles predictivos de Spread, Moneyline y Totales con los datos frescos.
6. Actualiza las predicciones de hoy con los nuevos perfiles de tiro y ritmo de la temporada 2026.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX
from nba.proveedor_cuotas import normalizar_equipo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nba_actualizar_boxscores")

RUTA_RAW = RAIZ / "data" / "nba" / "raw"
RUTA_PARQUET_RAW = RUTA_RAW / "partidos_historicos_nba.parquet"
RUTA_CSV_RAW = RUTA_RAW / "partidos_historicos_nba.csv"


def _parse_split(val: Any) -> Tuple[int, int]:
    """Separa strings de formato 'Made-Attempted' (ej. '46-91' -> 46, 91)."""
    try:
        parts = str(val).split("-")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 0, 0


def descargar_eventos_temporada_actual(
    fecha_inicio: str = "2026-10-20",
    fecha_fin: Optional[str] = None
) -> List[Dict[str, str]]:
    """Consulta ESPN Scoreboard día por día para obtener los IDs de todos los juegos finalizados."""
    hoy_cdmx = datetime.now(ZONA_CDMX).date()
    end_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date() if fecha_fin else hoy_cdmx
    cur_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()

    eventos_finalizados: List[Dict[str, str]] = []

    logger.info(f"⏳ Buscando partidos finalizados entre {cur_dt} y {end_dt}...")

    while cur_dt <= end_dt:
        f_str = cur_dt.strftime("%Y%m%d")
        url_sb = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={f_str}"
        req = urllib.request.Request(url_sb, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for ev in data.get("events", []):
                st_name = ev.get("status", {}).get("type", {}).get("name", "")
                if "STATUS_FINAL" in st_name:
                    eventos_finalizados.append({
                        "id": str(ev.get("id")),
                        "fecha": cur_dt.strftime("%Y-%m-%d"),
                        "nombre": str(ev.get("name")),
                    })
        except Exception as err:
            logger.warning(f"Error consultando fecha {f_str} en ESPN: {err}")

        cur_dt += timedelta(days=1)
        time.sleep(0.08)

    logger.info(f"✅ Se encontraron {len(eventos_finalizados)} partidos oficiales finalizados en la temporada 2026-27.")
    return eventos_finalizados


def obtener_boxscore_partido(ev_id: str, fecha_str: str) -> List[Dict[str, Any]]:
    """Descarga y formatea el boxscore completo de un partido en dos filas (Local y Visitante)."""
    url_sum = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={ev_id}"
    req = urllib.request.Request(url_sum, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as err:
        logger.warning(f"No se pudo descargar boxscore para evento {ev_id}: {err}")
        return []

    header = data.get("header", {})
    comp = header.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return []

    rows: List[Dict[str, Any]] = []

    for competitor in competitors:
        t_info = competitor.get("team", {})
        raw_abbr = t_info.get("abbreviation", "")
        abbr = normalizar_equipo(raw_abbr)
        name = t_info.get("displayName", "")
        t_id = int(t_info.get("id", 0))
        score = int(competitor.get("score", 0))
        is_home = (competitor.get("homeAway") == "home")
        wl = "W" if competitor.get("winner") else "L"

        opp = [c for c in competitors if c != competitor][0]
        opp_abbr = normalizar_equipo(opp.get("team", {}).get("abbreviation", ""))
        opp_score = int(opp.get("score", 0))
        matchup = f"{abbr} vs. {opp_abbr}" if is_home else f"{abbr} @ {opp_abbr}"

        # Extraer mapa de estadísticas de equipo
        stat_dict: Dict[str, str] = {}
        for team_box in data.get("boxscore", {}).get("teams", []):
            if normalizar_equipo(team_box.get("team", {}).get("abbreviation", "")) == abbr:
                for s in team_box.get("statistics", []):
                    stat_dict[s.get("name", "")] = s.get("displayValue", "")

        fgm, fga = _parse_split(stat_dict.get("fieldGoalsMade-fieldGoalsAttempted", "0-0"))
        fg3m, fg3a = _parse_split(stat_dict.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "0-0"))
        ftm, fta = _parse_split(stat_dict.get("freeThrowsMade-freeThrowsAttempted", "0-0"))
        oreb = int(stat_dict.get("offensiveRebounds", 0))
        dreb = int(stat_dict.get("defensiveRebounds", 0))
        reb = int(stat_dict.get("totalRebounds", 0))
        ast = int(stat_dict.get("assists", 0))
        stl = int(stat_dict.get("steals", 0))
        blk = int(stat_dict.get("blocks", 0))
        tov = int(stat_dict.get("totalTurnovers", 0))
        pf = int(stat_dict.get("fouls", 0))

        # Determinar minutos jugados (240 reglamentarios, +25 por cada prórroga)
        linescores = competitor.get("linescores", [])
        periodos = len(linescores)
        minutos = 240 + (max(0, periodos - 4) * 25)

        row = {
            "SEASON_ID": "22026",
            "TEAM_ID": t_id,
            "TEAM_ABBREVIATION": abbr,
            "TEAM_NAME": name,
            "GAME_ID": f"002{ev_id}",
            "GAME_DATE": pd.to_datetime(fecha_str),
            "MATCHUP": matchup,
            "WL": wl,
            "MIN": minutos,
            "PTS": score,
            "FGM": fgm,
            "FGA": fga,
            "FG_PCT": round(fgm / fga, 3) if fga > 0 else 0.0,
            "FG3M": fg3m,
            "FG3A": fg3a,
            "FG3_PCT": round(fg3m / fg3a, 3) if fg3a > 0 else 0.0,
            "FTM": ftm,
            "FTA": fta,
            "FT_PCT": round(ftm / fta, 3) if fta > 0 else 0.0,
            "OREB": oreb,
            "DREB": dreb,
            "REB": reb,
            "AST": ast,
            "STL": stl,
            "BLK": blk,
            "TOV": tov,
            "PF": pf,
            "PLUS_MINUS": float(score - opp_score),
            "SEASON": "2026-27"
        }
        rows.append(row)

    return rows


def actualizar_dataset_temporada_actual() -> Dict[str, Any]:
    """Descarga los partidos de 2026-27, los fusiona con el histórico y reentrena los modelos."""
    logger.info("🏀 === INICIANDO ACTUALIZACIÓN DEL DATASET CON LA TEMPORADA ACTUAL NBA (2026-27) ===")

    # 1. Cargar histórico existente
    if not RUTA_PARQUET_RAW.exists():
        raise FileNotFoundError(f"No existe el archivo histórico base en {RUTA_PARQUET_RAW}.")

    df_existente = pd.read_parquet(RUTA_PARQUET_RAW)
    df_existente["GAME_DATE"] = pd.to_datetime(df_existente["GAME_DATE"])
    logger.info(f"Dataset histórico cargado: {len(df_existente):,} registros equipo-partido.")

    # 2. Descargar todos los partidos finalizados de la temporada 2026-27
    eventos = descargar_eventos_temporada_actual(fecha_inicio="2026-10-20")
    if not eventos:
        logger.warning("No se encontraron eventos para descargar.")
        return {"ok": False, "mensaje": "No se encontraron eventos nuevos"}

    # Filtrar solo eventos que falten en el histórico
    ids_existentes = set(df_existente["GAME_ID"].astype(str).unique())
    eventos_nuevos = [e for e in eventos if f"002{e['id']}" not in ids_existentes]

    logger.info(f"Partidos por sincronizar con boxscores completos: {len(eventos_nuevos)} de {len(eventos)}.")

    nuevas_filas: List[Dict[str, Any]] = []
    for idx, ev in enumerate(eventos_nuevos):
        filas_partido = obtener_boxscore_partido(ev["id"], ev["fecha"])
        if filas_partido:
            nuevas_filas.extend(filas_partido)
        if idx > 0 and idx % 20 == 0:
            logger.info(f"   -> Progreso: {idx}/{len(eventos_nuevos)} partidos procesados...")
        time.sleep(0.05)

    logger.info(f"✅ Se obtuvieron {len(nuevas_filas)} nuevas filas equipo-partido de la temporada 2026-27.")

    if nuevas_filas:
        df_nuevas = pd.DataFrame(nuevas_filas)
        df_actualizado = pd.concat([df_existente, df_nuevas], ignore_index=True)
        # Deduplicar con seguridad
        df_actualizado = df_actualizado.drop_duplicates(subset=["GAME_ID", "TEAM_ABBREVIATION"], keep="last")
        df_actualizado = df_actualizado.sort_values(["GAME_DATE", "GAME_ID"]).reset_index(drop=True)

        # Guardar en raw
        df_actualizado.to_parquet(RUTA_PARQUET_RAW, index=False)
        df_actualizado.to_csv(RUTA_CSV_RAW, index=False, encoding="utf-8")
        logger.info(f"💾 Guardado histórico actualizado: {RUTA_PARQUET_RAW} ({len(df_actualizado):,} filas).")
    else:
        logger.info("El dataset histórico ya cuenta con los boxscores más recientes de 2026-27.")
        df_actualizado = df_existente

    # 3. Re-ejecutar pipeline de Feature Engineering
    logger.info("⚙️ Re-ejecutando Feature Engineering completo (Four Factors, Pace, Ratings)...")
    from nba.construir_dataset import procesar_pipeline_completo
    df_procesado = procesar_pipeline_completo()

    # 4. Re-entrenar modelos predictivos
    logger.info("🧠 Re-entrenando modelos predictivos NBA con datos frescos de 2026...")
    from nba.entrenar_spread_ml import entrenar_modelo_spread
    from nba.entrenar_totales import entrenar_modelo_totales
    
    bundle_sp = entrenar_modelo_spread()
    bundle_tot = entrenar_modelo_totales()

    # 5. Generar predicciones actualizadas para hoy
    logger.info("🎯 Generando predicciones actualizadas para la jornada de hoy...")
    from nba.predecir_hoy import predecir_partidos_hoy
    preds_hoy = predecir_partidos_hoy(force_refresh=True)

    resumen = {
        "ok": True,
        "partidos_2026_sincronizados": len(nuevas_filas) // 2 if nuevas_filas else 0,
        "total_partidos_raw": len(df_actualizado) // 2,
        "dataset_procesado_partidos": len(df_procesado),
        "mae_spread_val": bundle_sp.get("metrics_val", {}).get("mae", 0.0),
        "mae_totales_val": bundle_tot.get("metrics_val", {}).get("mae", 0.0),
        "predicciones_generadas_hoy": len(preds_hoy),
    }

    logger.info(f"🏁 Actualización y re-entrenamiento completado con éxito: {resumen}")
    return resumen


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    actualizar_dataset_temporada_actual()
