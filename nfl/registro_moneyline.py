"""Módulo de persistencia, liquidación y auditoría de picks Moneyline NFL.

Gestiona:
1. Creación de tabla MySQL `nfl_predicciones_moneyline`.
2. Sincronización de predicciones activas e historial.
3. Liquidación automática de partidos terminados (GANADA / PERDIDA / PUSH).
4. Métricas históricas de rendimiento (Win Rate, Unidades, ROI).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import pandas as pd

from core.db import get_db_connection

logger = logging.getLogger("nfl_registro_moneyline")
ZONA_CDMX = ZoneInfo("America/Mexico_City")

RAIZ = Path(__file__).resolve().parents[1]
RUTA_CSV_HISTORIAL = RAIZ / "data" / "nfl" / "predictions" / "historial_moneyline_nfl.csv"


DDL_TABLA_MONEYLINE_NFL = """
CREATE TABLE IF NOT EXISTS nfl_predicciones_moneyline (
    id_prediccion INT AUTO_INCREMENT PRIMARY KEY,
    id_juego VARCHAR(64) NOT NULL,
    partido VARCHAR(64) NOT NULL,
    equipo_local VARCHAR(16) NOT NULL,
    equipo_visita VARCHAR(16) NOT NULL,
    fecha_cdmx VARCHAR(16) NOT NULL,
    hora_cdmx VARCHAR(16) NOT NULL,
    modelo_version VARCHAR(64) NOT NULL,
    ml_local VARCHAR(16),
    ml_visita VARCHAR(16),
    ml_local_dec DECIMAL(6,3),
    ml_visita_dec DECIMAL(6,3),
    spread_line DECIMAL(5,2),
    prob_local DECIMAL(6,4),
    prob_visita DECIMAL(6,4),
    edge_local DECIMAL(6,4),
    edge_visita DECIMAL(6,4),
    seleccion VARCHAR(32) NOT NULL,
    cuota_pick VARCHAR(16) NOT NULL,
    cuota_dec DECIMAL(6,3) NOT NULL,
    probabilidad_pick DECIMAL(6,4) NOT NULL,
    edge DECIMAL(6,4) NOT NULL,
    ev_estimado DECIMAL(6,2) NOT NULL,
    confianza VARCHAR(16) NOT NULL,
    estado_juego VARCHAR(32) DEFAULT 'STATUS_SCHEDULED',
    marcador_local INT DEFAULT NULL,
    marcador_visita INT DEFAULT NULL,
    resultado_pick VARCHAR(32) DEFAULT 'PENDIENTE',
    beneficio_unidades DECIMAL(6,3) DEFAULT NULL,
    ganador_real VARCHAR(16) DEFAULT NULL,
    generado_en DATETIME,
    actualizado_en DATETIME,
    evaluado_en DATETIME,
    UNIQUE KEY uq_juego_modelo (id_juego, modelo_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def asegurar_tabla_moneyline():
    """Crea la tabla en MySQL si aún no existe."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(DDL_TABLA_MONEYLINE_NFL)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        logger.warning(f"No se pudo asegurar la tabla nfl_predicciones_moneyline: {exc}")


def calcular_beneficio(cuota_dec: float, resultado: str) -> float:
    """Calcula unidades ganadas/perdidas sobre 1 unidad arriesgada."""
    if resultado == "GANADA":
        return round(float(cuota_dec) - 1.0, 3)
    elif resultado == "PERDIDA":
        return -1.0
    return 0.0


def liquidar_partido_moneyline(
    seleccion: str,
    equipo_local: str,
    equipo_visita: str,
    marcador_local: Optional[int],
    marcador_visita: Optional[int],
    cuota_dec: float,
) -> tuple[str, Optional[float], Optional[str]]:
    """Evalúa el ganador del encuentro y el resultado de la apuesta Moneyline."""
    if marcador_local is None or marcador_visita is None:
        return "PENDIENTE", None, None

    if marcador_local > marcador_visita:
        ganador = equipo_local
    elif marcador_visita > marcador_local:
        ganador = equipo_visita
    else:
        ganador = "EMPATE"

    # Seleccion es típicamente "{equipo} ML"
    equipo_elegido = seleccion.replace(" ML", "").strip()

    if ganador == "EMPATE":
        # Empate en temporada regular tras overtime = Push
        resultado = "PUSH"
        unidades = 0.0
    elif equipo_elegido == ganador:
        resultado = "GANADA"
        unidades = round(cuota_dec - 1.0, 3)
    else:
        resultado = "PERDIDA"
        unidades = -1.0

    return resultado, unidades, ganador


def guardar_predicciones_moneyline_mysql(predicciones: List[Dict[str, Any]]):
    """Guarda o actualiza las predicciones de Moneyline en MySQL."""
    if not predicciones:
        return

    asegurar_tabla_moneyline()

    ahora = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")
    sql = """
    INSERT INTO nfl_predicciones_moneyline (
        id_juego, partido, equipo_local, equipo_visita, fecha_cdmx, hora_cdmx,
        modelo_version, ml_local, ml_visita, ml_local_dec, ml_visita_dec, spread_line,
        prob_local, prob_visita, edge_local, edge_visita,
        seleccion, cuota_pick, cuota_dec, probabilidad_pick, edge, ev_estimado, confianza,
        estado_juego, marcador_local, marcador_visita, resultado_pick, beneficio_unidades,
        ganador_real, generado_en, actualizado_en
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s
    ) ON DUPLICATE KEY UPDATE
        partido = VALUES(partido),
        estado_juego = VALUES(estado_juego),
        marcador_local = VALUES(marcador_local),
        marcador_visita = VALUES(marcador_visita),
        resultado_pick = IF(resultado_pick IN ('GANADA', 'PERDIDA', 'PUSH'), resultado_pick, VALUES(resultado_pick)),
        beneficio_unidades = IF(beneficio_unidades IS NOT NULL, beneficio_unidades, VALUES(beneficio_unidades)),
        ganador_real = IF(ganador_real IS NOT NULL, ganador_real, VALUES(ganador_real)),
        actualizado_en = VALUES(actualizado_en)
    """

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        valores = []
        for p in predicciones:
            valores.append((
                str(p.get("id_evento", "")),
                p.get("partido", ""),
                p.get("equipo_local", ""),
                p.get("equipo_visita", ""),
                p.get("fecha_cdmx", ""),
                p.get("hora_cdmx", ""),
                p.get("modelo_version", "nfl_moneyline_calibrado_v1"),
                p.get("ml_local"),
                p.get("ml_visita"),
                p.get("ml_local_dec"),
                p.get("ml_visita_dec"),
                p.get("spread_line"),
                p.get("prob_local"),
                p.get("prob_visita"),
                p.get("edge_local"),
                p.get("edge_visita"),
                p.get("pick_seleccion", ""),
                p.get("pick_cuota", ""),
                p.get("pick_cuota_dec", 1.91),
                p.get("pick_probabilidad", 0.5),
                p.get("pick_edge", 0.0),
                p.get("ev_estimado", 0.0),
                p.get("confianza", "NEUTRAL"),
                p.get("estado", "STATUS_SCHEDULED"),
                p.get("marcador_local"),
                p.get("marcador_visita"),
                p.get("resultado_pick", "PENDIENTE"),
                p.get("beneficio_unidades"),
                p.get("ganador_real"),
                ahora,
                ahora,
            ))
        cursor.executemany(sql, valores)
        conn.commit()
        cursor.close()
    except Exception as exc:
        logger.warning(f"Error guardando en MySQL nfl_predicciones_moneyline: {exc}")
    finally:
        if conn and conn.is_connected():
            conn.close()


def liquidar_partidos_pendientes_moneyline() -> Dict[str, Any]:
    """Consulta ESPN para obtener marcadores de partidos concluidos y liquidar los picks pendientes."""
    import json
    from nfl.proveedor_cuotas import obtener_jornada_nfl_espn

    RUTA_JSON = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_moneyline.json"
    if not RUTA_JSON.exists():
        return {"evaluados": 0, "mensaje": "No hay archivo de predicciones de Moneyline para evaluar."}

    try:
        with open(RUTA_JSON, "r", encoding="utf-8") as f:
            predicciones = json.load(f)
    except Exception as exc:
        return {"evaluados": 0, "mensaje": f"Error leyendo archivo de predicciones: {exc}"}

    partidos_espn = obtener_jornada_nfl_espn()
    dict_espn = {str(p["id_evento"]): p for p in partidos_espn}

    evaluados = 0
    ahora_str = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")

    for p in predicciones:
        id_ev = str(p.get("id_evento", ""))
        live = dict_espn.get(id_ev)
        if live:
            p["estado"] = live.get("estado", p.get("estado"))
            p["descripcion_estado"] = live.get("descripcion_estado", p.get("descripcion_estado"))
            if live.get("marcador_local") is not None:
                p["marcador_local"] = live["marcador_local"]
            if live.get("marcador_visita") is not None:
                p["marcador_visita"] = live["marcador_visita"]

        # Si ya terminó y estaba pendiente, liquidar
        if ("FINAL" in str(p.get("estado", "")).upper()) and p.get("resultado_pick") not in ["GANADA", "PERDIDA", "PUSH"]:
            res, u_gan, ganador = liquidar_partido_moneyline(
                seleccion=p.get("pick_seleccion", ""),
                equipo_local=p.get("equipo_local", ""),
                equipo_visita=p.get("equipo_visita", ""),
                marcador_local=p.get("marcador_local"),
                marcador_visita=p.get("marcador_visita"),
                cuota_dec=p.get("pick_cuota_dec", 1.91),
            )
            if res != "PENDIENTE":
                p["resultado_pick"] = res
                p["beneficio_unidades"] = u_gan
                p["ganador_real"] = ganador
                p["evaluado_en"] = ahora_str
                evaluados += 1

    # Guardar en JSON
    with open(RUTA_JSON, "w", encoding="utf-8") as f:
        json.dump(predicciones, f, indent=2, ensure_ascii=False)

    # Actualizar en MySQL
    guardar_predicciones_moneyline_mysql(predicciones)

    return {
        "evaluados": evaluados,
        "mensaje": f"Se liquidaron {evaluados} partidos concluidos con éxito." if evaluados > 0 else "No hubo nuevos partidos concluidos por liquidar.",
    }


def cargar_historial_moneyline_mysql() -> pd.DataFrame:
    """Carga todo el historial liquidado de Moneyline desde MySQL o CSV."""
    asegurar_tabla_moneyline()
    consulta = """
    SELECT
        id_prediccion, id_juego, partido, equipo_local, equipo_visita,
        fecha_cdmx, hora_cdmx, modelo_version,
        ml_local, ml_visita, spread_line, prob_local, prob_visita,
        seleccion, cuota_pick, cuota_dec, probabilidad_pick, edge, ev_estimado, confianza,
        estado_juego, marcador_local, marcador_visita, resultado_pick, beneficio_unidades,
        ganador_real, generado_en, actualizado_en, evaluado_en
    FROM nfl_predicciones_moneyline
    ORDER BY fecha_cdmx DESC, id_prediccion DESC
    """
    conn = None
    try:
        conn = get_db_connection()
        df = pd.read_sql(consulta, conn)
        return df
    except Exception as exc:
        logger.warning(f"Error consultando historial MySQL: {exc}")
        return pd.DataFrame()
    finally:
        if conn and conn.is_connected():
            conn.close()
