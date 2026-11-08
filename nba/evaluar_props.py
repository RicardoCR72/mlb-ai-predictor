"""Módulo para evaluar y liquidar Player Props de la NBA contra los boxscores oficiales de ESPN."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.constants import ZONA_CDMX

logger = logging.getLogger("nba_evaluar_props")

RAIZ = Path(__file__).resolve().parents[1]
RUTA_PARQUET_JUGADORES = RAIZ / "data" / "nba" / "processed" / "player_boxscores_2026_27.parquet"
RUTA_CSV_JUGADORES = RAIZ / "data" / "nba" / "processed" / "player_boxscores_2026_27.csv"
RUTA_PRED_PARQUET = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.parquet"
RUTA_PRED_JSON = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.json"

MAPA_MERCADOS_STATS = {
    "Total Points": "pts",
    "Total Rebounds": "reb",
    "Total Assists": "ast",
    "Total Triples": "t3_made",
    "Total PRA": "pra",
    "Total PR": "pr",
    "Total PA": "pa",
}


def liquidar_prop_nba(
    prop: Dict[str, Any] | pd.Series,
    boxscores_evento: pd.DataFrame,
    partido_finalizado: bool = True,
) -> Dict[str, Any]:
    """Evalúa un prop individual contra el boxscore de jugadores del partido.
    
    Regla de Oro en Apuestas Deportivas (Sportsbook Void / Push Rule):
    * Si el partido ha finalizado y el jugador NO participó (DNP, inactivo, 0 minutos o no figura en el boxscore):
      -> Resultado: 'PUSH' (Devolución)
      -> Unidades ganadas: 0.0
      -> Motivo: 'Jugador no participó (DNP / Inactivo)'
    * Si el jugador jugó (minutos > 0):
      -> Se compara la estadística oficial contra la línea para determinar GANADA, PERDIDA o PUSH.
    """
    if not partido_finalizado:
        return {
            "resultado": "PENDIENTE",
            "unidades_ganadas": None,
            "valor_real": None,
            "motivo": "Partido en juego o programado",
        }

    p_clean = str(prop.get("player_clean") or prop.get("player_name", "")).strip().lower()
    mercado = str(prop.get("market", ""))
    linea = float(prop.get("line") or 0.0)
    pick_tipo = str(prop.get("pick_type", "OVER")).upper()
    cuota_dec = float(prop.get("pick_odds_decimal") or 1.91)

    # Si no hay boxscore disponible habiendo concluido el partido -> PUSH por no participación
    if boxscores_evento.empty:
        return {
            "resultado": "PUSH",
            "unidades_ganadas": 0.0,
            "valor_real": 0.0,
            "motivo": "Jugador no participó (DNP / Inactivo)",
        }

    nombres_box = boxscores_evento["player_name"].astype(str).str.strip().str.lower()
    filas_jugador = boxscores_evento[nombres_box == p_clean]

    if filas_jugador.empty:
        # Intento de matching por apellido
        partes = p_clean.split()
        if len(partes) > 1:
            apellido = partes[-1]
            filas_jugador = boxscores_evento[nombres_box.str.endswith(apellido)]

    if filas_jugador.empty:
        # El jugador no disputó minutos en el partido
        return {
            "resultado": "PUSH",
            "unidades_ganadas": 0.0,
            "valor_real": 0.0,
            "motivo": "Jugador no participó (DNP / Inactivo)",
        }

    registro = filas_jugador.iloc[0]
    minutos = float(registro.get("minutos", 0.0) or 0.0)

    # Si jugó 0 minutos, es DNP / Push
    if minutos <= 0.0:
        return {
            "resultado": "PUSH",
            "unidades_ganadas": 0.0,
            "valor_real": 0.0,
            "motivo": "Jugador no participó (0 minutos jugados)",
        }

    col_stat = MAPA_MERCADOS_STATS.get(mercado)
    if not col_stat or col_stat not in registro:
        return {
            "resultado": "PENDIENTE",
            "unidades_ganadas": None,
            "valor_real": None,
            "motivo": f"Mercado {mercado} no mapeado en estadísticas",
        }

    valor_real = float(registro[col_stat])

    if valor_real == linea:
        return {
            "resultado": "PUSH",
            "unidades_ganadas": 0.0,
            "valor_real": valor_real,
            "motivo": f"Empate exacto con la línea ({valor_real} == {linea})",
        }

    if pick_tipo == "OVER":
        if valor_real > linea:
            return {
                "resultado": "GANADA",
                "unidades_ganadas": round(cuota_dec - 1.0, 3),
                "valor_real": valor_real,
                "motivo": f"Superó la línea ({valor_real} > {linea})",
            }
        else:
            return {
                "resultado": "PERDIDA",
                "unidades_ganadas": -1.0,
                "valor_real": valor_real,
                "motivo": f"No superó la línea ({valor_real} < {linea})",
            }
    elif pick_tipo == "UNDER":
        if valor_real < linea:
            return {
                "resultado": "GANADA",
                "unidades_ganadas": round(cuota_dec - 1.0, 3),
                "valor_real": valor_real,
                "motivo": f"Se mantuvo bajo la línea ({valor_real} < {linea})",
            }
        else:
            return {
                "resultado": "PERDIDA",
                "unidades_ganadas": -1.0,
                "valor_real": valor_real,
                "motivo": f"Superó la línea ({valor_real} > {linea})",
            }

    return {
        "resultado": "PENDIENTE",
        "unidades_ganadas": None,
        "valor_real": valor_real,
        "motivo": "Tipo de pick no reconocido",
    }


def registrar_devolucion_nba_dnp(
    prop: Dict[str, Any],
    id_juego: str,
    conn=None,
) -> bool:
    """Registra una devolución oficial (PUSH) en oracle_devoluciones si el jugador fue DNP."""
    from core.devoluciones import save_refund
    p_name = prop.get("player_name", "")
    mercado = prop.get("market", "")
    try:
        from core.db import get_db_connection
        conexion = conn or get_db_connection()
        save_refund(
            conexion,
            sport="NBA",
            game_id=id_juego,
            player_id=p_name,
            market=mercado,
            reason="Jugador no participó (DNP / Inactivo)",
            source="ESPN Official Boxscore",
            evidence={
                "player": p_name,
                "market": mercado,
                "line": prop.get("line"),
                "minutes": 0.0,
                "status": "DNP",
            },
        )
        if conn is None and conexion.is_connected():
            conexion.close()
        return True
    except Exception as exc:
        logger.warning(f"No se pudo registrar devolución en MySQL: {exc}")
        return False

