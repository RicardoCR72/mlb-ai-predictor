"""Módulo de persistencia en base de datos y auditoría de rendimiento para la NBA.

1. Guarda predicciones y líneas en MySQL (nba_registro_picks) y respaldo local en Parquet/CSV.
2. Liquida automáticamente los resultados (GANADA, PERDIDA, PUSH) cuando concluyen los partidos.
3. Calcula métricas oficiales de rendimiento: Acierto (%), Unidades (+/- u) y ROI (%).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX

RUTA_PROCESSED = RAIZ / "data" / "nba" / "processed"
RUTA_HISTORIAL_PARQUET = RUTA_PROCESSED / "historial_picks_nba.parquet"
RUTA_HISTORIAL_CSV = RUTA_PROCESSED / "historial_picks_nba.csv"
RUTA_DATASET_PARTIDOS = RUTA_PROCESSED / "dataset_partidos_nba.parquet"

logger = logging.getLogger(__name__)


def obtener_conexion_mysql(timeout: int = 2):
    """Crea una conexión rápida a MySQL con timeout corto para no congelar la app si está offline."""
    try:
        from core.infrastructure.database import get_db_credentials
        import mysql.connector
        creds = get_db_credentials()
        creds["connection_timeout"] = timeout
        conn = mysql.connector.connect(**creds)
        return conn
    except Exception:
        return None

DDL_NBA_PICKS = """
CREATE TABLE IF NOT EXISTS nba_registro_picks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id_juego VARCHAR(64) NOT NULL,
    fecha DATE NOT NULL,
    hora_cdmx VARCHAR(16) NOT NULL,
    equipo_local VARCHAR(64) NOT NULL,
    equipo_visitante VARCHAR(64) NOT NULL,
    mercado VARCHAR(32) NOT NULL,
    seleccion VARCHAR(64) NOT NULL,
    linea DOUBLE DEFAULT NULL,
    cuota DOUBLE NOT NULL,
    probabilidad DOUBLE NOT NULL,
    edge DOUBLE NOT NULL,
    confianza VARCHAR(16) NOT NULL,
    marcador_local INT DEFAULT NULL,
    marcador_visitante INT DEFAULT NULL,
    resultado VARCHAR(16) DEFAULT 'PENDIENTE',
    unidades_ganadas DOUBLE DEFAULT NULL,
    actualizado_en DATETIME NOT NULL,
    UNIQUE KEY uq_nba_pick (id_juego, mercado, seleccion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def preparar_tablas_nba(conn) -> bool:
    """Crea la tabla nba_registro_picks si no existe en MySQL."""
    try:
        cursor = conn.cursor()
        cursor.execute(DDL_NBA_PICKS)
        conn.commit()
        cursor.close()
        return True
    except Exception as err:
        logger.warning(f"No se pudo crear/verificar tabla en MySQL: {err}")
        return False


def guardar_predicciones_nba(predicciones: List[Dict[str, Any]]) -> None:
    """Guarda las predicciones del día en MySQL y en el archivo local de historial para todos los mercados."""
    if not predicciones:
        return

    ahora = datetime.now(ZONA_CDMX)
    ahora_str = ahora.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Preparar filas con formato uniforme para todos los mercados disponibles
    nuevas_filas = []
    for p in predicciones:
        id_ev = str(p.get("id_evento") or p.get("id_juego") or "").strip()
        fecha_cdmx = str(p.get("fecha_cdmx", ahora.strftime("%Y-%m-%d")))
        hora_cdmx = str(p.get("hora_cdmx", "TBD"))
        eq_loc = str(p.get("equipo_local", ""))
        eq_vis = str(p.get("equipo_visita") or p.get("equipo_visitante", ""))
        m_loc = p.get("marcador_local")
        m_vis = p.get("marcador_visita") if p.get("marcador_visita") is not None else p.get("marcador_visitante")

        # Si el objeto p ya es un pick atómico individual preformateado
        if "prob_local_win" not in p and p.get("pick_mercado"):
            cuota_dec = float(p.get("ml_local_dec") or 1.91)
            if "UNDER" in p.get("pick_seleccion", "") or "OVER" in p.get("pick_seleccion", ""):
                cuota_dec = 1.909
            elif p.get("abbr_visita") in p.get("pick_seleccion", ""):
                cuota_dec = float(p.get("ml_visita_dec") or 1.91)
            linea_val = p.get("linea_total") if "Totales" in p.get("pick_mercado", "") else p.get("linea_spread")
            if linea_val is None:
                import re
                m_l = re.search(r'([+-]?\d+(?:\.\d+)?)', p.get("pick_seleccion", ""))
                linea_val = float(m_l.group(1)) if m_l else 0.0

            fila_unica = {
                "id_juego": id_ev,
                "fecha": fecha_cdmx,
                "hora_cdmx": hora_cdmx,
                "equipo_local": eq_loc,
                "equipo_visitante": eq_vis,
                "mercado": str(p.get("pick_mercado", "")),
                "seleccion": str(p.get("pick_seleccion", "")),
                "linea": float(linea_val or 0.0),
                "cuota": round(cuota_dec, 3),
                "probabilidad": float(p.get("pick_probabilidad") or 0.5),
                "edge": float(p.get("pick_edge") or 0.0),
                "confianza": str(p.get("confianza") or "MEDIA"),
                "marcador_local": m_loc,
                "marcador_visitante": m_vis,
                "resultado": p.get("resultado") or "PENDIENTE",
                "unidades_ganadas": p.get("unidades_ganadas"),
                "actualizado_en": ahora_str,
            }
            if m_loc is not None and m_vis is not None and fila_unica["resultado"] == "PENDIENTE":
                r_res, r_u = liquidar_partido(pd.Series(fila_unica))
                fila_unica["resultado"] = r_res
                fila_unica["unidades_ganadas"] = r_u
            nuevas_filas.append(fila_unica)
            continue

        # Generar las 3 dimensiones de mercado (Moneyline, Spread y Totales)
        # 1. Moneyline
        p_loc = float(p.get("prob_local_win") or 0.5)
        p_vis = float(p.get("prob_visita_win") or 0.5)
        cuota_ml = float(p.get("ml_local_dec") or 1.91) if p_loc >= p_vis else float(p.get("ml_visita_dec") or 1.91)
        sel_ml = f"{eq_loc} ML" if p_loc >= p_vis else f"{eq_vis} ML"
        pr_ml = p_loc if p_loc >= p_vis else p_vis
        edge_ml = pr_ml - (1.0 / cuota_ml if cuota_ml > 0 else 0.5)
        f_ml = {
            "id_juego": f"{id_ev}_ml",
            "fecha": fecha_cdmx,
            "hora_cdmx": hora_cdmx,
            "equipo_local": eq_loc,
            "equipo_visitante": eq_vis,
            "mercado": "Moneyline",
            "seleccion": sel_ml,
            "linea": 0.0,
            "cuota": round(cuota_ml, 3),
            "probabilidad": round(pr_ml, 3),
            "edge": round(edge_ml, 3),
            "confianza": "ALTA" if pr_ml >= 0.60 else "MEDIA",
            "marcador_local": m_loc,
            "marcador_visitante": m_vis,
            "resultado": "PENDIENTE",
            "unidades_ganadas": None,
            "actualizado_en": ahora_str,
        }
        if m_loc is not None and m_vis is not None:
            r_res, r_u = liquidar_partido(pd.Series(f_ml))
            f_ml["resultado"] = r_res
            f_ml["unidades_ganadas"] = r_u
        nuevas_filas.append(f_ml)

        # 2. Spread (solo para juegos de hoy en adelante con línea válida; en juegos pasados solo existían ML y Totales)
        sp_val = float(p.get("linea_spread") or 0.0)
        hoy_str = ahora_cdmx.strftime("%Y-%m-%d")
        if fecha_cdmx >= hoy_str and sp_val != 0.0:
            p_cov_h = float(p.get("prob_cover_home") or 0.5)
            p_cov_v = float(p.get("prob_cover_away") or 0.5)
            sel_sp = f"{eq_loc} {sp_val:+0.1f}" if p_cov_h >= p_cov_v else f"{eq_vis} {-sp_val:+0.1f}"
            pr_sp = p_cov_h if p_cov_h >= p_cov_v else p_cov_v
            f_sp = {
                "id_juego": f"{id_ev}_spread",
                "fecha": fecha_cdmx,
                "hora_cdmx": hora_cdmx,
                "equipo_local": eq_loc,
                "equipo_visitante": eq_vis,
                "mercado": "Spread",
                "seleccion": sel_sp,
                "linea": sp_val,
                "cuota": 1.909,
                "probabilidad": round(pr_sp, 3),
                "edge": round(pr_sp - 0.5238, 3),
                "confianza": "ALTA" if pr_sp >= 0.56 else "MEDIA",
                "marcador_local": m_loc,
                "marcador_visitante": m_vis,
                "resultado": "PENDIENTE",
                "unidades_ganadas": None,
                "actualizado_en": ahora_str,
            }
            if m_loc is not None and m_vis is not None:
                r_res, r_u = liquidar_partido(pd.Series(f_sp))
                f_sp["resultado"] = r_res
                f_sp["unidades_ganadas"] = r_u
            nuevas_filas.append(f_sp)

        # 3. Totales
        tot_linea = float(p.get("linea_total") or 228.0)
        p_over = float(p.get("prob_over") or 0.5)
        p_under = float(p.get("prob_under") or 0.5)
        es_over = p_over > p_under
        pr_tot = p_over if es_over else p_under
        tipo_tot = "OVER" if es_over else "UNDER"
        sel_tot = f"{tipo_tot} {tot_linea}"
        f_tot = {
            "id_juego": f"{id_ev}_tot",
            "fecha": fecha_cdmx,
            "hora_cdmx": hora_cdmx,
            "equipo_local": eq_loc,
            "equipo_visitante": eq_vis,
            "mercado": f"Totales ({tipo_tot})",
            "seleccion": sel_tot,
            "linea": tot_linea,
            "cuota": 1.909,
            "probabilidad": round(pr_tot, 3),
            "edge": round(abs(float(p.get("edge_puntos_total") or 0.0)) / 10.0, 3),
            "confianza": "ALTA" if abs(float(p.get("edge_puntos_total") or 0.0)) >= 4.0 else "MEDIA",
            "marcador_local": m_loc,
            "marcador_visitante": m_vis,
            "resultado": "PENDIENTE",
            "unidades_ganadas": None,
            "actualizado_en": ahora_str,
        }
        if m_loc is not None and m_vis is not None:
            r_res, r_u = liquidar_partido(pd.Series(f_tot))
            f_tot["resultado"] = r_res
            f_tot["unidades_ganadas"] = r_u
        nuevas_filas.append(f_tot)

    df_nuevas = pd.DataFrame(nuevas_filas)

    # 2. Persistencia en Base de Datos MySQL si está disponible
    conn = None
    try:
        conn = obtener_conexion_mysql(timeout=2)
        if conn:
            preparar_tablas_nba(conn)
            cursor = conn.cursor()
            sql_insert = """
            INSERT INTO nba_registro_picks (
                id_juego, fecha, hora_cdmx, equipo_local, equipo_visitante,
                mercado, seleccion, linea, cuota, probabilidad, edge,
                confianza, marcador_local, marcador_visitante, resultado,
                unidades_ganadas, actualizado_en
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cuota = VALUES(cuota),
                probabilidad = VALUES(probabilidad),
                edge = VALUES(edge),
                confianza = VALUES(confianza),
                marcador_local = COALESCE(VALUES(marcador_local), marcador_local),
                marcador_visitante = COALESCE(VALUES(marcador_visitante), marcador_visitante),
                resultado = CASE WHEN resultado IN ('GANADA', 'PERDIDA', 'PUSH') THEN resultado ELSE VALUES(resultado) END,
                unidades_ganadas = COALESCE(VALUES(unidades_ganadas), unidades_ganadas),
                actualizado_en = VALUES(actualizado_en);
            """
            for f in nuevas_filas:
                cursor.execute(sql_insert, (
                    f["id_juego"], f["fecha"], f["hora_cdmx"], f["equipo_local"], f["equipo_visitante"],
                    f["mercado"], f["seleccion"], f["linea"], f["cuota"], f["probabilidad"], f["edge"],
                    f["confianza"], f["marcador_local"], f["marcador_visitante"], f["resultado"],
                    f["unidades_ganadas"], f["actualizado_en"]
                ))
            conn.commit()
            cursor.close()
            logger.info(f"✅ {len(nuevas_filas)} predicciones sincronizadas en MySQL (nba_registro_picks).")
    except Exception as err:
        logger.info(f"Base de datos remota no disponible en este momento ({err}). Guardando en almacenamiento local.")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    # 3. Persistencia en almacenamiento local (Parquet / CSV)
    df_existente = pd.DataFrame()
    if RUTA_HISTORIAL_PARQUET.exists():
        try:
            df_existente = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
        except Exception:
            pass

    if not df_existente.empty:
        # Partidos ya liquidados (bloqueados permanentemente para no sobreescribir auditorías ganadas/perdidas)
        liquidados_prev = df_existente[df_existente["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])]
        ids_liquidados = set(liquidados_prev["id_juego"].astype(str)) if not liquidados_prev.empty else set()

        # Mapeo de (base_id, tipo_mercado) existentes en el historial para evitar duplicar picks
        base_mercados_existentes = set()
        for _, r_ex in df_existente.iterrows():
            b_id = str(r_ex["id_juego"]).split("_")[0]
            tm = "Totales" if "Totales" in str(r_ex["mercado"]) else str(r_ex["mercado"])
            base_mercados_existentes.add((b_id, tm))

        def es_duplicado(r):
            if str(r["id_juego"]) in ids_liquidados:
                return True
            b_id = str(r["id_juego"]).split("_")[0]
            tm = "Totales" if "Totales" in str(r["mercado"]) else str(r["mercado"])
            return (b_id, tm) in base_mercados_existentes

        df_nuevas_filtradas = df_nuevas[~df_nuevas.apply(es_duplicado, axis=1)]

        if not df_nuevas_filtradas.empty:
            df_total = pd.concat([df_existente, df_nuevas_filtradas], ignore_index=True)
            df_total = df_total.drop_duplicates(subset=["id_juego"], keep="last")
        else:
            df_total = df_existente
    else:
        df_total = df_nuevas.drop_duplicates(subset=["id_juego"], keep="first")

    df_total.to_parquet(RUTA_HISTORIAL_PARQUET, index=False)
    df_total.to_csv(RUTA_HISTORIAL_CSV, index=False, encoding="utf-8")
    logger.info(f"💾 Historial actualizado en {RUTA_HISTORIAL_PARQUET} ({len(df_total)} registros).")


def liquidar_partido(fila: pd.Series) -> Tuple[str, Optional[float]]:
    """Determina si un pick es GANADA, PERDIDA o PUSH y calcula el beneficio en unidades."""
    m_local = fila.get("marcador_local")
    m_visita = fila.get("marcador_visitante")

    if pd.isna(m_local) or pd.isna(m_visita) or m_local is None or m_visita is None:
        return "PENDIENTE", None

    m_local = int(m_local)
    m_visita = int(m_visita)
    cuota = float(fila.get("cuota") or 1.91)
    mercado = str(fila.get("mercado", ""))
    sel = str(fila.get("seleccion", "")).strip()
    linea = float(fila.get("linea") or 0.0)

    # 1. Totales Over / Under (asegurando límite de palabra para no confundir con thUNDER)
    import re
    es_over = bool(re.search(r'\bOVER\b', sel, re.IGNORECASE))
    es_under = bool(re.search(r'\bUNDER\b', sel, re.IGNORECASE))
    if "Totales" in mercado or es_over or es_under:
        total_puntos = m_local + m_visita
        if es_over:
            if total_puntos > linea:
                return "GANADA", round(cuota - 1.0, 3)
            elif total_puntos < linea:
                return "PERDIDA", -1.0
            else:
                return "PUSH", 0.0
        elif es_under:
            if total_puntos < linea:
                return "GANADA", round(cuota - 1.0, 3)
            elif total_puntos > linea:
                return "PERDIDA", -1.0
            else:
                return "PUSH", 0.0

    # 2. Moneyline
    if "Moneyline" in mercado or "ML" in sel:
        eq_local = str(fila.get("equipo_local", "")).lower()
        eq_vis = str(fila.get("equipo_visitante", "")).lower()
        sel_l = sel.lower()
        if any(part in sel_l for part in eq_local.split()):
            if m_local > m_visita:
                return "GANADA", round(cuota - 1.0, 3)
            elif m_local < m_visita:
                return "PERDIDA", -1.0
            else:
                return "PUSH", 0.0
        elif any(part in sel_l for part in eq_vis.split()):
            if m_visita > m_local:
                return "GANADA", round(cuota - 1.0, 3)
            elif m_visita < m_local:
                return "PERDIDA", -1.0
            else:
                return "PUSH", 0.0

    # 3. Spread / Hándicap
    if "Spread" in mercado or "+" in sel or "-" in sel:
        import re
        eq_local = str(fila.get("equipo_local", "")).lower()
        eq_vis = str(fila.get("equipo_visitante", "")).lower()
        sel_l = sel.lower()
        
        match_spread = re.search(r'([+-]\d+(?:\.\d+)?)', sel)
        if match_spread:
            handicap = float(match_spread.group(1))
            if any(part in sel_l for part in eq_local.split()):
                diff = (m_local + handicap) - m_visita
            else:
                diff = (m_visita + handicap) - m_local
        else:
            margen = m_local - m_visita
            if any(part in sel_l for part in eq_local.split()):
                diff = margen + linea
            else:
                diff = -margen + linea

        if diff > 0:
            return "GANADA", round(cuota - 1.0, 3)
        elif diff < 0:
            return "PERDIDA", -1.0
        else:
            return "PUSH", 0.0

    return "PENDIENTE", None


def inicializar_historial_simulado() -> pd.DataFrame:
    """Carga únicamente el historial verídico de la temporada actual desde MySQL o local."""
    return cargar_historial_rendimiento()


def liquidar_partidos_pendientes_nba() -> dict[str, Any]:
    """Consulta ESPN Scoreboard y liquida todos los picks pendientes de la NBA.
    Actualiza el archivo Parquet/CSV, la base de datos MySQL y el archivo JSON de predicciones
    para que queden auditados y pasen a Rendimiento e Historial.
    """
    from nba.proveedor_cuotas import obtener_calendario_y_cuotas_nba

    # 1. Asegurar que las predicciones pendientes de hoy se registren
    archivo_preds = RAIZ / "data" / "nba" / "predictions" / "predicciones_nba_hoy.json"
    if archivo_preds.exists():
        try:
            with open(archivo_preds, "r", encoding="utf-8") as f:
                preds_hoy = json.load(f)
            pendientes_hoy = [
                p for p in preds_hoy
                if p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]
            ]
            if pendientes_hoy:
                guardar_predicciones_nba(pendientes_hoy)
        except Exception as err_preds:
            logger.warning(f"Error cargando predicciones de hoy para registro previo: {err_preds}")

    if not RUTA_HISTORIAL_PARQUET.exists():
        cargar_historial_rendimiento()

    try:
        df = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
    except Exception as err:
        return {"ok": False, "evaluados": 0, "mensaje": f"Error al abrir historial: {err}"}

    # Sincronizar desde MySQL si hay picks pendientes que falten en el archivo local
    try:
        conn = obtener_conexion_mysql(timeout=3)
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM nba_registro_picks WHERE resultado = 'PENDIENTE';")
            pendientes_db = cursor.fetchall()
            cursor.close()
            conn.close()
            if pendientes_db:
                df_db = pd.DataFrame(pendientes_db)
                if "fecha" in df_db.columns:
                    df_db["fecha"] = df_db["fecha"].astype(str)
                if "fecha" in df.columns:
                    df["fecha"] = df["fecha"].astype(str)
                df = pd.concat([df, df_db], ignore_index=True).drop_duplicates(subset=["id_juego"], keep="last")
    except Exception:
        pass

    # 2. Consultar marcadores de ESPN para hoy y las últimas fechas (al menos los últimos 5 días)
    hoy_dt = datetime.now(ZONA_CDMX)
    fechas = {(hoy_dt - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(5)}
    pendientes = df[df["resultado"] == "PENDIENTE"]
    if not pendientes.empty:
        fechas.update(pendientes["fecha"].dropna().astype(str).tolist())

    partidos_espn = []
    for f_str in sorted(fechas):
        partidos_espn.extend(obtener_calendario_y_cuotas_nba(fecha=f_str, force_refresh=True, ttl_minutes=0))
    # Consulta por defecto sin fecha
    partidos_espn.extend(obtener_calendario_y_cuotas_nba(force_refresh=True, ttl_minutes=0))

    marcadores_por_id = {}
    marcadores_por_equipos = {}
    partidos_finales_map = {}
    for ev in partidos_espn:
        ev_id = str(ev.get("id_evento", "")).strip()
        estado = str(ev.get("estado", "")).upper()
        desc = str(ev.get("descripcion_estado", "")).upper()
        if "FINAL" in estado or "FINAL" in desc:
            sc_home = ev.get("marcador_local")
            sc_away = ev.get("marcador_visita")
            if sc_home is not None and sc_away is not None:
                try:
                    ml = int(sc_home)
                    mv = int(sc_away)
                    if ev_id:
                        marcadores_por_id[ev_id] = (ml, mv)
                        partidos_finales_map[ev_id] = ev
                    eq_loc = str(ev.get("equipo_local", "")).strip().upper()
                    eq_vis = str(ev.get("equipo_visita", "")).strip().upper()
                    ab_loc = str(ev.get("abbr_local", "")).strip().upper()
                    ab_vis = str(ev.get("abbr_visita", "")).strip().upper()
                    if eq_loc and eq_vis:
                        marcadores_por_equipos[(eq_loc, eq_vis)] = (ml, mv)
                    if ab_loc and ab_vis:
                        marcadores_por_equipos[(ab_loc, ab_vis)] = (ml, mv)
                except (ValueError, TypeError):
                    pass

    # Backfill automático de partidos finalizados de ESPN que falten en el historial
    ids_existentes = set(df["id_juego"].astype(str).apply(lambda x: x.split("_")[0]))
    partidos_faltantes = [ev for ev_id, ev in partidos_finales_map.items() if ev_id not in ids_existentes]
    if partidos_faltantes:
        try:
            from nba.predecir_hoy import generar_predicciones_nba_hoy, cargar_perfiles_recientes_equipos
            import joblib
            b_sp = joblib.load(RAIZ / "modelos_nba" / "modelo_spread_ml.joblib")
            b_tot = joblib.load(RAIZ / "modelos_nba" / "modelo_totales.joblib")
            perfs = cargar_perfiles_recientes_equipos()
            nuevas_preds = generar_predicciones_nba_hoy(partidos_faltantes, perfs, b_sp, b_tot)
            guardar_predicciones_nba(nuevas_preds)
            df = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
        except Exception as e_gen:
            logger.warning(f"Error generando predicciones para partidos faltantes: {e_gen}")

    liquidados_count = 0
    liquidados_indices = []
    ahora_str = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")

    for idx, row in df[df["resultado"] == "PENDIENTE"].iterrows():
        ev_id = str(row["id_juego"]).split("_")[0].strip()
        eq_loc = str(row.get("equipo_local", "")).strip().upper()
        eq_vis = str(row.get("equipo_visitante", "")).strip().upper()

        sc = marcadores_por_id.get(ev_id)
        if not sc and (eq_loc, eq_vis) in marcadores_por_equipos:
            sc = marcadores_por_equipos[(eq_loc, eq_vis)]

        if sc:
            m_loc, m_vis = sc
            df.at[idx, "marcador_local"] = m_loc
            df.at[idx, "marcador_visitante"] = m_vis
            res, u_gan = liquidar_partido(df.loc[idx])
            df.at[idx, "resultado"] = res
            df.at[idx, "unidades_ganadas"] = u_gan
            df.at[idx, "actualizado_en"] = ahora_str
            liquidados_count += 1
            liquidados_indices.append(idx)

    if liquidados_count > 0:
        df = df.drop_duplicates(subset=["id_juego"], keep="last")
        if "fecha" in df.columns:
            df["fecha"] = df["fecha"].astype(str)
        df.to_parquet(RUTA_HISTORIAL_PARQUET, index=False)
        df.to_csv(RUTA_HISTORIAL_CSV, index=False, encoding="utf-8")

        # Sincronizar en MySQL solo los registros recién liquidados
        conn = None
        try:
            conn = obtener_conexion_mysql(timeout=2)
            if conn and liquidados_indices:
                cursor = conn.cursor()
                sql_update = """
                UPDATE nba_registro_picks
                SET marcador_local = %s, marcador_visitante = %s, resultado = %s,
                    unidades_ganadas = %s, actualizado_en = %s
                WHERE id_juego = %s AND mercado = %s AND seleccion = %s;
                """
                params_list = [
                    (
                        df.at[i, "marcador_local"], df.at[i, "marcador_visitante"], df.at[i, "resultado"],
                        df.at[i, "unidades_ganadas"], ahora_str, df.at[i, "id_juego"], df.at[i, "mercado"], df.at[i, "seleccion"]
                    )
                    for i in liquidados_indices
                ]
                cursor.executemany(sql_update, params_list)
                conn.commit()
                cursor.close()
        except Exception as e:
            logger.warning(f"Error sincronizando liquidación en MySQL: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        # 3. Sincronizar predicciones_nba_hoy.json para reflejar el estado liquidado y marcadores finales
        if archivo_preds.exists():
            try:
                with open(archivo_preds, "r", encoding="utf-8") as f:
                    preds_data = json.load(f)
                modificado = False
                for p in preds_data:
                    p_id = str(p.get("id_evento", "")).strip()
                    p_eq_loc = str(p.get("equipo_local", "")).strip().upper()
                    p_eq_vis = str(p.get("equipo_visita", "")).strip().upper()

                    sc = marcadores_por_id.get(p_id)
                    if not sc and (p_eq_loc, p_eq_vis) in marcadores_por_equipos:
                        sc = marcadores_por_equipos[(p_eq_loc, p_eq_vis)]

                    if sc:
                        m_loc, m_vis = sc
                        p["marcador_local"] = m_loc
                        p["marcador_visita"] = m_vis
                        p["estado"] = "STATUS_FINAL"

                        match_rows = df[(df["id_juego"].astype(str).str.startswith(p_id)) & (df["resultado"].isin(["GANADA", "PERDIDA", "PUSH"]))]
                        if not match_rows.empty:
                            p["resultado"] = str(match_rows.iloc[-1]["resultado"])
                            u_val = match_rows.iloc[-1]["unidades_ganadas"]
                            p["unidades_ganadas"] = float(u_val) if pd.notna(u_val) else None
                        modificado = True
                if modificado:
                    with open(archivo_preds, "w", encoding="utf-8") as f:
                        json.dump(preds_data, f, indent=2, ensure_ascii=False)
                    pd.DataFrame(preds_data).to_parquet(archivo_preds.with_suffix(".parquet"), index=False)
            except Exception as e_json:
                logger.warning(f"Error actualizando predicciones_nba_hoy.json: {e_json}")

        return {
            "ok": True,
            "evaluados": liquidados_count,
            "mensaje": f"Se liquidaron exitosamente {liquidados_count} pick(s) y pasaron a Rendimiento e Historial."
        }
    else:
        return {
            "ok": True,
            "evaluados": 0,
            "mensaje": "Los partidos de hoy aún están programados o en juego. No hay resultados finales listos para liquidar."
        }


def cargar_historial_rendimiento() -> pd.DataFrame:
    """Carga el historial verídico de picks evaluados de la NBA (solo temporada actual)."""
    # 1. Intentar cargar desde MySQL (fuente en vivo y verídica de la temporada actual)
    try:
        conn = obtener_conexion_mysql(timeout=3)
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM nba_registro_picks ORDER BY fecha DESC, id DESC;")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            if rows:
                df = pd.DataFrame(rows)
                if "fecha" in df.columns:
                    df["fecha"] = df["fecha"].astype(str)
                RUTA_PROCESSED.mkdir(parents=True, exist_ok=True)
                df.to_parquet(RUTA_HISTORIAL_PARQUET, index=False)
                df.to_csv(RUTA_HISTORIAL_CSV, index=False, encoding="utf-8")
                return df
    except Exception as err:
        logger.warning(f"No se pudo consultar MySQL para historial NBA: {err}")

    # 2. Si MySQL no está disponible, intentar desde Parquet local
    if RUTA_HISTORIAL_PARQUET.exists():
        try:
            df = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
            if not df.empty:
                return df
        except Exception as err:
            logger.warning(f"Error cargando parquet de historial NBA: {err}")

    return pd.DataFrame()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    hist = cargar_historial_rendimiento()
    liquidados = hist[hist["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])]
    ganadas = (liquidados["resultado"] == "GANADA").sum()
    perdidas = (liquidados["resultado"] == "PERDIDA").sum()
    acierto = ganadas / (ganadas + perdidas) if (ganadas + perdidas) else 0.0
    unidades = liquidados["unidades_ganadas"].sum()
    roi = (unidades / len(liquidados)) * 100 if len(liquidados) else 0.0

    print("\n📈 Resumen de Rendimiento NBA:")
    print(f"Total picks evaluados: {len(liquidados):,}")
    print(f"Acierto: {acierto * 100:.2f}% ({ganadas}G - {perdidas}P)")
    print(f"Beneficio: {unidades:+.2f} unidades")
    print(f"ROI: {roi:+.2f}%")
