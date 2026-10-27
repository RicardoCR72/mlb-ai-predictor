"""Módulo unificado para liquidar en vivo todos los mercados de la NFL:
- Totales de Partido (Over / Under)
- Moneyline (Ganador Directo)
- Props de Jugadores (Recepciones, Yardas Recepción, Pases, Yardas Terrestres, Anytime TD)

Extrae los marcadores oficiales y boxscores de ESPN en tiempo real y actualiza MySQL.
"""
from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import requests
import pandas as pd

from core.db import get_db_connection
from nfl.proveedor_cuotas import obtener_jornada_nfl_espn
from nfl.registro_moneyline import liquidar_partidos_pendientes_moneyline

logger = logging.getLogger("liquidar_nfl")
ZONA_CDMX = ZoneInfo("America/Mexico_City")

URL_ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"


def normalizar_texto(texto: str) -> str:
    """Normaliza nombres para comparación robusta (sin acentos, minúsculas, sin puntos)."""
    if not texto:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace(".", "").replace("'", "").replace("-", " ").strip()
    return " ".join(s.split())


def calcular_beneficio_momio(momio: Any, resultado: str) -> Optional[float]:
    """Calcula unidades ganadas/perdidas para 1 unidad apostada."""
    if resultado == "PERDIDA":
        return -1.0
    if resultado == "PUSH":
        return 0.0
    if resultado != "GANADA":
        return None

    if momio is None or pd.isna(momio):
        return 0.91  # -110 por defecto

    try:
        m = float(momio)
        if m >= 100:
            return round(m / 100.0, 3)
        if m <= -100:
            return round(100.0 / abs(m), 3)
        if 1.0 < m < 15.0:  # Cuota decimal
            return round(m - 1.0, 3)
        return 0.91
    except Exception:
        return 0.91


def liquidar_totales_nfl(partidos_espn: List[Dict[str, Any]]) -> int:
    """Liquida apuestas de Totales (Over/Under) en nfl_juegos y nfl_predicciones_totales."""
    conn = None
    evaluados = 0
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Mapear partidos de ESPN finalizados por combinación (visita, local)
        finales_espn = {}
        for ev in partidos_espn:
            estado = str(ev.get("estado", "")).upper()
            desc = str(ev.get("descripcion_estado", "")).upper()
            if "FINAL" in estado or "FINAL" in desc:
                v = ev.get("equipo_visita")
                l = ev.get("equipo_local")
                sc_v = ev.get("marcador_visita")
                sc_l = ev.get("marcador_local")
                if v and l and sc_v is not None and sc_l is not None:
                    finales_espn[(v, l)] = {
                        "marcador_visita": int(sc_v),
                        "marcador_local": int(sc_l),
                        "total": int(sc_v) + int(sc_l),
                    }

        if not finales_espn:
            cursor.close()
            return 0

        # Actualizar nfl_juegos con marcadores finales
        for (v, l), datos in finales_espn.items():
            cursor.execute(
                """
                UPDATE nfl_juegos
                SET marcador_visitante = %s, marcador_local = %s, estado = 'finalizado'
                WHERE equipo_visitante = %s AND equipo_local = %s AND temporada = 2026;
                """,
                (datos["marcador_visita"], datos["marcador_local"], v, l),
            )
        conn.commit()

        # Buscar predicciones de totales pendientes
        cursor.execute(
            """
            SELECT p.id_prediccion, p.id_juego, p.linea_total, p.seleccion, p.cuota_pick,
                   j.equipo_visitante, j.equipo_local
            FROM nfl_predicciones_totales p
            JOIN nfl_juegos j ON j.id_juego = p.id_juego
            WHERE p.resultado_pick = 'PENDIENTE';
            """
        )
        pendientes = cursor.fetchall()
        ahora_str = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")

        for p in pendientes:
            par = (p["equipo_visitante"], p["equipo_local"])
            if par in finales_espn:
                tot_real = finales_espn[par]["total"]
                linea = float(p["linea_total"])
                sel = str(p["seleccion"]).upper()

                if tot_real == linea:
                    res = "PUSH"
                elif sel == "OVER":
                    res = "GANADA" if tot_real > linea else "PERDIDA"
                elif sel == "UNDER":
                    res = "GANADA" if tot_real < linea else "PERDIDA"
                else:
                    continue

                u_gan = calcular_beneficio_momio(p.get("cuota_pick"), res)

                cursor.execute(
                    """
                    UPDATE nfl_predicciones_totales
                    SET total_real = %s, resultado_pick = %s, beneficio_unidades = %s, evaluado_en = %s
                    WHERE id_prediccion = %s;
                    """,
                    (tot_real, res, u_gan, ahora_str, p["id_prediccion"]),
                )
                evaluados += 1

        conn.commit()
        cursor.close()
    except Exception as exc:
        logger.error(f"Error liquidando Totales NFL: {exc}")
    finally:
        if conn and conn.is_connected():
            conn.close()

    return evaluados


def obtener_boxscore_espn(id_evento: str) -> Dict[str, Dict[str, float]]:
    """Descarga el boxscore oficial de ESPN para un evento y devuelve estadísticas por jugador."""
    stats_por_jugador = {}
    try:
        resp = requests.get(f"{URL_ESPN_SUMMARY}?event={id_evento}", timeout=10)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        players_sec = data.get("boxscore", {}).get("players", [])

        for team_sec in players_sec:
            for cat in team_sec.get("statistics", []):
                cat_name = cat.get("name", "")
                keys = cat.get("keys", [])
                for athlete_item in cat.get("athletes", []):
                    ath = athlete_item.get("athlete", {})
                    nombre = ath.get("displayName", "")
                    norm_nombre = normalizar_texto(nombre)
                    if not norm_nombre:
                        continue

                    if norm_nombre not in stats_por_jugador:
                        stats_por_jugador[norm_nombre] = {
                            "receptions": 0.0,
                            "receiving_yards": 0.0,
                            "passing_yards": 0.0,
                            "passing_tds": 0.0,
                            "rushing_yards": 0.0,
                            "anytime_td": 0.0,
                        }

                    stats_raw = athlete_item.get("stats", [])
                    stat_map = dict(zip(keys, stats_raw))

                    if cat_name == "receiving":
                        stats_por_jugador[norm_nombre]["receptions"] = float(stat_map.get("receptions", 0))
                        stats_por_jugador[norm_nombre]["receiving_yards"] = float(stat_map.get("receivingYards", 0))
                        rec_td = float(stat_map.get("receivingTouchdowns", 0))
                        stats_por_jugador[norm_nombre]["anytime_td"] += rec_td

                    elif cat_name == "rushing":
                        stats_por_jugador[norm_nombre]["rushing_yards"] = float(stat_map.get("rushingYards", 0))
                        rush_td = float(stat_map.get("rushingTouchdowns", 0))
                        stats_por_jugador[norm_nombre]["anytime_td"] += rush_td

                    elif cat_name == "passing":
                        stats_por_jugador[norm_nombre]["passing_yards"] = float(stat_map.get("passingYards", 0))
                        stats_por_jugador[norm_nombre]["passing_tds"] = float(stat_map.get("passingTouchdowns", 0))
    except Exception as exc:
        logger.warning(f"Error descargando boxscore ESPN {id_evento}: {exc}")

    return stats_por_jugador


def liquidar_props_nfl(partidos_espn: List[Dict[str, Any]]) -> int:
    """Liquida proyecciones de props de jugadores en nfl_proyecciones_props usando estadísticas oficiales de ESPN."""
    conn = None
    evaluados = 0
    try:
        finales_espn = [
            ev for ev in partidos_espn
            if "FINAL" in str(ev.get("estado", "")).upper() or "FINAL" in str(ev.get("descripcion_estado", "")).upper()
        ]

        if not finales_espn:
            return 0

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ahora_str = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")

        for ev in finales_espn:
            id_ev = str(ev.get("id_evento", ""))
            v = ev.get("equipo_visita")
            l = ev.get("equipo_local")
            if not v or not l:
                continue

            # Consultar props pendientes de este juego uniendo dinámicamente nfl_juegos
            cursor.execute(
                """
                SELECT p.id_proyeccion, p.tipo_prop, p.linea, p.seleccion, p.cuota_pick,
                       ju.nombre as nombre_jugador
                FROM nfl_proyecciones_props p
                JOIN nfl_juegos j ON j.id_juego = p.id_juego
                JOIN nfl_jugadores ju ON ju.id_jugador = p.id_jugador
                WHERE j.equipo_visitante = %s AND j.equipo_local = %s AND p.resultado_pick = 'PENDIENTE';
                """,
                (v, l),
            )
            props_pendientes = cursor.fetchall()
            if not props_pendientes:
                continue

            # Obtener boxscore de ESPN
            boxscore = obtener_boxscore_espn(id_ev)
            if not boxscore:
                continue

            for prop in props_pendientes:
                norm_p = normalizar_texto(prop["nombre_jugador"])
                # Buscar coincidencia exacta o por apellido/nombre
                stats_jugador = boxscore.get(norm_p)
                if not stats_jugador:
                    # Intento de matching por subcadena
                    for k_name, k_stats in boxscore.items():
                        if norm_p in k_name or k_name in norm_p:
                            stats_jugador = k_stats
                            break

                if not stats_jugador:
                    # El partido ya finalizó y el jugador no participó (DNP / Inactivo).
                    # Regla oficial de casas de apuestas (DraftKings/FanDuel): VOID / PUSH (devolución 0.0 u).
                    cursor.execute(
                        """
                        UPDATE nfl_proyecciones_props
                        SET valor_real = NULL, resultado_pick = 'PUSH', beneficio_unidades = 0.0, evaluado_en = %s
                        WHERE id_proyeccion = %s;
                        """,
                        (ahora_str, prop["id_proyeccion"]),
                    )
                    evaluados += 1
                    continue

                tipo_prop = str(prop["tipo_prop"])
                if tipo_prop not in stats_jugador:
                    val_real = 0.0
                else:
                    val_real = float(stats_jugador[tipo_prop])
                linea = float(prop["linea"]) if prop["linea"] is not None else 0.5
                sel = str(prop["seleccion"] or "").upper()

                if sel == "ANOTA":
                    res = "GANADA" if val_real >= 1.0 else "PERDIDA"
                elif abs(val_real - linea) < 1e-6:
                    res = "PUSH"
                elif sel == "OVER":
                    res = "GANADA" if val_real > linea else "PERDIDA"
                elif sel == "UNDER":
                    res = "GANADA" if val_real < linea else "PERDIDA"
                else:
                    continue

                u_gan = calcular_beneficio_momio(prop.get("cuota_pick"), res)

                cursor.execute(
                    """
                    UPDATE nfl_proyecciones_props
                    SET valor_real = %s, resultado_pick = %s, beneficio_unidades = %s, evaluado_en = %s
                    WHERE id_proyeccion = %s;
                    """,
                    (val_real, res, u_gan, ahora_str, prop["id_proyeccion"]),
                )
                evaluados += 1

        conn.commit()
        cursor.close()
    except Exception as exc:
        logger.error(f"Error liquidando Props NFL: {exc}")
    finally:
        if conn and conn.is_connected():
            conn.close()

    return evaluados


def liquidar_todo_nfl() -> Dict[str, Any]:
    """Función maestra que liquida Moneyline, Totales y Props concluidos de la NFL."""
    partidos_espn = obtener_jornada_nfl_espn()

    res_ml = liquidar_partidos_pendientes_moneyline()
    eval_ml = res_ml.get("evaluados", 0)

    eval_tot = liquidar_totales_nfl(partidos_espn)
    eval_props = liquidar_props_nfl(partidos_espn)

    total_eval = eval_ml + eval_tot + eval_props

    # Limpiar caché de Streamlit si está en entorno Streamlit
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass

    mensaje = f"Se liquidaron exitosamente: {eval_ml} Moneyline, {eval_tot} Totales y {eval_props} Props." if total_eval > 0 else "No hay nuevos partidos ni props concluidos pendientes por liquidar."

    return {
        "ok": True,
        "total": total_eval,
        "moneyline": eval_ml,
        "totales": eval_tot,
        "props": eval_props,
        "mensaje": mensaje,
    }
