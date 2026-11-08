"""Servicio de descarga, sincronización y análisis de boxscores individuales de jugadores NBA.

Descarga los boxscores oficiales partido a partido desde ESPN API (temporada 2026-27)
y genera métricas de tendencia: promedio de temporada, desviación estándar, promedio
últimos 5 partidos (L5), minutos jugados y PRA (Puntos + Rebotes + Asistencias).
"""

from __future__ import annotations

import json
import logging
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nba_servicio_jugadores")

RUTA_DATA_NBA = RAIZ / "data" / "nba" / "processed"
RUTA_PARQUET_JUGADORES = RUTA_DATA_NBA / "player_boxscores_2026_27.parquet"
RUTA_CSV_JUGADORES = RUTA_DATA_NBA / "player_boxscores_2026_27.csv"


def _parse_split(val: Any) -> Tuple[int, int]:
    """Separa strings 'Made-Attempted' (ej. '4-9' -> 4, 9)."""
    try:
        parts = str(val).split("-")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 0, 0


def _parse_min(val: Any) -> float:
    """Convierte minutos a float (maneja '34', '34:12', etc.)."""
    try:
        s = str(val).strip()
        if ":" in s:
            parts = s.split(":")
            return round(float(parts[0]) + float(parts[1]) / 60.0, 1)
        return float(s)
    except Exception:
        return 0.0


def descargar_eventos_finalizados(
    fecha_inicio: str = "2026-10-20",
    fecha_fin: Optional[str] = None
) -> List[Dict[str, str]]:
    """Obtiene los IDs y fechas de todos los partidos finalizados en la temporada."""
    hoy_cdmx = datetime.now(ZONA_CDMX).date()
    end_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date() if fecha_fin else hoy_cdmx
    cur_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()

    eventos: List[Dict[str, str]] = []

    while cur_dt <= end_dt:
        f_str = cur_dt.strftime("%Y%m%d")
        url_sb = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={f_str}"
        req = urllib.request.Request(url_sb, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for ev in data.get("events", []):
                st_name = ev.get("status", {}).get("type", {}).get("name", "")
                if "STATUS_FINAL" in st_name:
                    eventos.append({
                        "id": str(ev.get("id")),
                        "fecha": cur_dt.strftime("%Y-%m-%d"),
                        "nombre": str(ev.get("name")),
                    })
        except Exception as err:
            logger.warning(f"Error consultando fecha {f_str} en ESPN: {err}")

        cur_dt += timedelta(days=1)
        time.sleep(0.04)

    return eventos


def obtener_boxscore_jugadores_evento(ev_id: str, fecha_str: str) -> List[Dict[str, Any]]:
    """Descarga el boxscore detallado de jugadores para un evento de ESPN."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={ev_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as err:
        logger.warning(f"No se pudo descargar boxscore para evento {ev_id}: {err}")
        return []

    header = data.get("header", {})
    comp = header.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])
    
    # Identificar local y visitante
    home_team, away_team = "", ""
    for c in competitors:
        t_abbr = c.get("team", {}).get("abbreviation", "")
        if c.get("homeAway") == "home":
            home_team = t_abbr
        else:
            away_team = t_abbr

    filas_jugadores: List[Dict[str, Any]] = []

    for team_box in data.get("boxscore", {}).get("players", []):
        t_abbr = team_box.get("team", {}).get("abbreviation", "")
        t_name = team_box.get("team", {}).get("displayName", "")
        es_local = (t_abbr == home_team)
        oponente = away_team if es_local else home_team

        for stat_sec in team_box.get("statistics", []):
            labels = stat_sec.get("labels", [])
            for a in stat_sec.get("athletes", []):
                if a.get("didNotPlay", False):
                    continue
                
                athlete_info = a.get("athlete", {})
                p_id = str(athlete_info.get("id", ""))
                p_name = athlete_info.get("displayName", "")
                p_pos = athlete_info.get("position", {}).get("abbreviation", "")
                
                raw_stats = dict(zip(labels, a.get("stats", [])))
                
                minutos = _parse_min(raw_stats.get("MIN", 0))
                puntos = int(raw_stats.get("PTS", 0) or 0)
                rebotes = int(raw_stats.get("REB", 0) or 0)
                asistencias = int(raw_stats.get("AST", 0) or 0)
                robos = int(raw_stats.get("STL", 0) or 0)
                bloqueos = int(raw_stats.get("BLK", 0) or 0)
                perdidas = int(raw_stats.get("TO", 0) or 0)
                
                fg_m, fg_a = _parse_split(raw_stats.get("FG", "0-0"))
                t3_m, t3_a = _parse_split(raw_stats.get("3PT", "0-0"))
                ft_m, ft_a = _parse_split(raw_stats.get("FT", "0-0"))
                
                pra = puntos + rebotes + asistencias
                pr = puntos + rebotes
                pa = puntos + asistencias

                filas_jugadores.append({
                    "event_id": ev_id,
                    "fecha": fecha_str,
                    "player_id": p_id,
                    "player_name": p_name,
                    "position": p_pos,
                    "team": t_abbr,
                    "team_name": t_name,
                    "opponent": oponente,
                    "is_home": int(es_local),
                    "min": minutos,
                    "pts": puntos,
                    "reb": rebotes,
                    "ast": asistencias,
                    "stl": robos,
                    "blk": bloqueos,
                    "to": perdidas,
                    "t3_made": t3_m,
                    "t3_att": t3_a,
                    "fg_made": fg_m,
                    "fg_att": fg_a,
                    "ft_made": ft_m,
                    "ft_att": ft_a,
                    "pra": pra,
                    "pr": pr,
                    "pa": pa,
                })

    return filas_jugadores


def sincronizar_boxscores_jugadores(
    max_workers: int = 8,
    forzar_todo: bool = False
) -> pd.DataFrame:
    """Descarga y sincroniza los boxscores de jugadores en Parquet incrementalmente."""
    RUTA_DATA_NBA.mkdir(parents=True, exist_ok=True)
    
    df_existente = pd.DataFrame()
    ids_procesados = set()

    if not forzar_todo and RUTA_PARQUET_JUGADORES.exists():
        try:
            df_existente = pd.read_parquet(RUTA_PARQUET_JUGADORES)
            ids_procesados = set(df_existente["event_id"].unique())
            logger.info(f"📂 Cargados {len(df_existente)} registros previos de jugadores ({len(ids_procesados)} juegos).")
        except Exception as e:
            logger.warning(f"Error leyendo parquet existente: {e}. Se descargará todo.")

    todos_eventos = descargar_eventos_finalizados()
    pendientes = [ev for ev in todos_eventos if ev["id"] not in ids_procesados]
    
    logger.info(f"📊 Total eventos: {len(todos_eventos)} | Ya procesados: {len(ids_procesados)} | Pendientes: {len(pendientes)}")

    if not pendientes and not df_existente.empty:
        logger.info("✅ Boxscores de jugadores ya se encuentran completamente actualizados.")
        return df_existente

    nuevos_registros: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {
            executor.submit(obtener_boxscore_jugadores_evento, ev["id"], ev["fecha"]): ev["id"]
            for ev in pendientes
        }
        for fut in as_completed(futuros):
            ev_id = futuros[fut]
            try:
                filas = fut.result()
                if filas:
                    nuevos_registros.extend(filas)
            except Exception as err:
                logger.error(f"Error procesando boxscore para evento {ev_id}: {err}")

    if nuevos_registros:
        df_nuevos = pd.DataFrame(nuevos_registros)
        if not df_existente.empty:
            df_total = pd.concat([df_existente, df_nuevos], ignore_index=True)
        else:
            df_total = df_nuevos
        
        # Deduplicar por evento y jugador
        df_total.drop_duplicates(subset=["event_id", "player_id"], inplace=True)
        df_total.sort_values(by=["fecha", "player_name"], inplace=True)
        
        df_total.to_parquet(RUTA_PARQUET_JUGADORES, index=False)
        df_total.to_csv(RUTA_CSV_JUGADORES, index=False)
        logger.info(f"💾 Guardados exitosamente {len(df_total)} registros de jugadores en {RUTA_PARQUET_JUGADORES}")
        return df_total
    
    return df_existente


def calcular_perfil_jugador(df_boxscores: pd.DataFrame, min_minutos: float = 10.0) -> pd.DataFrame:
    """Calcula promedios de temporada, desviación estándar y últimos 5 juegos (L5)."""
    if df_boxscores.empty:
        return pd.DataFrame()

    df_activos = df_boxscores[df_boxscores["min"] >= min_minutos].copy()
    df_activos.sort_values(by="fecha", ascending=True, inplace=True)

    perfiles = []

    for (p_name, team), p_df in df_activos.groupby(["player_name", "team"]):
        if len(p_df) < 2:
            continue

        l5 = p_df.tail(5)

        p_info = {
            "player_name": p_name,
            "team": team,
            "position": p_df["position"].iloc[-1],
            "games_played": len(p_df),
            "min_avg": round(p_df["min"].mean(), 1),
            "min_l5": round(l5["min"].mean(), 1),
            
            # Puntos
            "pts_avg": round(p_df["pts"].mean(), 1),
            "pts_std": round(p_df["pts"].std(ddof=1) or 1.0, 1),
            "pts_l5": round(l5["pts"].mean(), 1),
            
            # Rebotes
            "reb_avg": round(p_df["reb"].mean(), 1),
            "reb_std": round(p_df["reb"].std(ddof=1) or 1.0, 1),
            "reb_l5": round(l5["reb"].mean(), 1),
            
            # Asistencias
            "ast_avg": round(p_df["ast"].mean(), 1),
            "ast_std": round(p_df["ast"].std(ddof=1) or 1.0, 1),
            "ast_l5": round(l5["ast"].mean(), 1),
            
            # Triples
            "t3_avg": round(p_df["t3_made"].mean(), 1),
            "t3_std": round(p_df["t3_made"].std(ddof=1) or 0.8, 1),
            "t3_l5": round(l5["t3_made"].mean(), 1),
            
            # Combos
            "pra_avg": round(p_df["pra"].mean(), 1),
            "pra_std": round(p_df["pra"].std(ddof=1) or 4.5, 1),
            "pra_l5": round(l5["pra"].mean(), 1),

            "pr_avg": round(p_df["pr"].mean(), 1),
            "pr_std": round(p_df["pr"].std(ddof=1) or 3.5, 1),
            "pr_l5": round(l5["pr"].mean(), 1),

            "pa_avg": round(p_df["pa"].mean(), 1),
            "pa_std": round(p_df["pa"].std(ddof=1) or 3.5, 1),
            "pa_l5": round(l5["pa"].mean(), 1),
            
            # Robos y Bloqueos
            "stl_avg": round(p_df["stl"].mean(), 1),
            "blk_avg": round(p_df["blk"].mean(), 1),
        }
        perfiles.append(p_info)

    return pd.DataFrame(perfiles)


if __name__ == "__main__":
    t0 = time.time()
    df = sincronizar_boxscores_jugadores()
    perfil = calcular_perfil_jugador(df)
    print(f"✅ Sincronización completada en {time.time() - t0:.1f}s. Jugadores perfilados: {len(perfil)}")
    if not perfil.empty:
        print(perfil.sort_values(by="pts_avg", ascending=False).head(10)[["player_name", "team", "games_played", "min_avg", "pts_avg", "pts_l5", "reb_avg", "ast_avg", "pra_avg"]])

