"""Módulo de persistencia en base de datos y auditoría de rendimiento para la Liga MX.

1. Guarda predicciones y líneas en MySQL (ligamx_registro_picks) y respaldo local en Parquet/CSV.
2. Liquida automáticamente los resultados (GANADA, PERDIDA, PUSH) cuando concluyen los partidos.
3. Calcula métricas oficiales de rendimiento: Acierto (%), Unidades (+/- u) y ROI (%).
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX
from core.infrastructure.database import get_db_credentials

RUTA_DATA = RAIZ / "futbol_liga_mx" / "data"
RUTA_HISTORIAL_PARQUET = RUTA_DATA / "historial_picks_ligamx.parquet"
RUTA_HISTORIAL_CSV = RUTA_DATA / "historial_picks_ligamx.csv"
RUTA_DATASET_PARTIDOS = RUTA_DATA / "partidos.csv"

logger = logging.getLogger(__name__)


def obtener_conexion_mysql(timeout: int = 3):
    """Crea una conexión rápida a MySQL para Liga MX."""
    try:
        import mysql.connector
        creds = get_db_credentials()
        creds["connection_timeout"] = timeout
        return mysql.connector.connect(**creds)
    except Exception:
        return None


DDL_LIGAMX_PICKS = """
CREATE TABLE IF NOT EXISTS ligamx_registro_picks (
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
    UNIQUE KEY uq_ligamx_pick (id_juego, mercado, seleccion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def preparar_tablas_ligamx(conn) -> bool:
    """Crea la tabla ligamx_registro_picks si no existe en MySQL."""
    try:
        cursor = conn.cursor()
        cursor.execute(DDL_LIGAMX_PICKS)
        conn.commit()
        cursor.close()
        return True
    except Exception as err:
        logger.warning(f"No se pudo crear/verificar tabla en MySQL: {err}")
        return False


def guardar_predicciones_ligamx(predicciones: List[Dict[str, Any]]) -> None:
    """Guarda las predicciones en MySQL y en el archivo local Parquet/CSV."""
    if not predicciones:
        return

    ahora = datetime.now(ZONA_CDMX)
    ahora_str = ahora.strftime("%Y-%m-%d %H:%M:%S")

    nuevas_filas = []
    for p in predicciones:
        cuota_dec = float(p.get("pick_cuota_dec") or 1.85)
        linea_val = float(p.get("linea_total") or 2.5) if "Totales" in p.get("pick_mercado", "") else 0.0

        fila = {
            "id_juego": str(p.get("id_evento", "")),
            "fecha": str(p.get("fecha_cdmx", ahora.strftime("%Y-%m-%d"))),
            "hora_cdmx": str(p.get("hora_cdmx", "TBD")),
            "equipo_local": str(p.get("equipo_local", "")),
            "equipo_visitante": str(p.get("equipo_visita", "")),
            "mercado": str(p.get("pick_mercado", "")),
            "seleccion": str(p.get("pick_seleccion", "")),
            "linea": linea_val,
            "cuota": round(cuota_dec, 3),
            "probabilidad": float(p.get("pick_probabilidad") or 0.5),
            "edge": float(p.get("pick_edge") or 0.0),
            "confianza": str(p.get("confianza") or "MEDIA"),
            "marcador_local": p.get("marcador_local"),
            "marcador_visitante": p.get("marcador_visita"),
            "resultado": p.get("resultado") or "PENDIENTE",
            "unidades_ganadas": p.get("unidades_ganadas"),
            "actualizado_en": ahora_str,
        }
        nuevas_filas.append(fila)

    df_nuevas = pd.DataFrame(nuevas_filas)

    # 1. Guardar en MySQL si está disponible
    conn = None
    try:
        conn = obtener_conexion_mysql(timeout=3)
        if conn:
            preparar_tablas_ligamx(conn)
            cursor = conn.cursor()
            sql_insert = """
            INSERT INTO ligamx_registro_picks (
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
            logger.info(f"✅ {len(nuevas_filas)} predicciones sincronizadas en MySQL (ligamx_registro_picks).")
    except Exception as err:
        logger.info(f"Base de datos remota no disponible ({err}). Almacenando en archivo local.")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    # 2. Persistencia en archivo Parquet / CSV local
    df_existente = pd.DataFrame()
    if RUTA_HISTORIAL_PARQUET.exists():
        try:
            df_existente = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
        except Exception:
            pass

    if not df_existente.empty:
        df_total = pd.concat([df_existente, df_nuevas], ignore_index=True)
        df_total = df_total.drop_duplicates(subset=["id_juego", "mercado"], keep="last")
    else:
        df_total = df_nuevas.drop_duplicates(subset=["id_juego", "mercado"], keep="last")

    RUTA_DATA.mkdir(parents=True, exist_ok=True)
    df_total.to_parquet(RUTA_HISTORIAL_PARQUET, index=False)
    df_total.to_csv(RUTA_HISTORIAL_CSV, index=False, encoding="utf-8")
    logger.info(f"💾 Historial Liga MX actualizado en {RUTA_HISTORIAL_PARQUET} ({len(df_total)} registros).")


def liquidar_partido_ligamx(fila: pd.Series) -> Tuple[str, Optional[float]]:
    """Determina si un pick es GANADA, PERDIDA o PUSH y calcula unidades ganadas."""
    m_local = fila.get("marcador_local")
    m_visita = fila.get("marcador_visitante")

    if pd.isna(m_local) or pd.isna(m_visita) or m_local is None or m_visita is None:
        return "PENDIENTE", None

    m_local = int(m_local)
    m_visita = int(m_visita)
    cuota = float(fila.get("cuota") or 1.85)
    mercado = str(fila.get("mercado", ""))
    sel = str(fila.get("seleccion", "")).strip()
    linea = float(fila.get("linea") or 2.5)

    # 1. Totales Over / Under
    if "Totales" in mercado or "OVER" in sel.upper() or "UNDER" in sel.upper():
        total_goles = m_local + m_visita
        if "OVER" in sel.upper():
            if total_goles > linea:
                return "GANADA", round(cuota - 1.0, 3)
            elif total_goles < linea:
                return "PERDIDA", -1.0
            else:
                return "PUSH", 0.0
        elif "UNDER" in sel.upper():
            if total_goles < linea:
                return "GANADA", round(cuota - 1.0, 3)
            elif total_goles > linea:
                return "PERDIDA", -1.0
            else:
                return "PUSH", 0.0

    # 2. Moneyline (1X2)
    if "Moneyline" in mercado or "ML" in sel:
        eq_loc = str(fila.get("equipo_local", "")).lower()
        eq_vis = str(fila.get("equipo_visitante", "")).lower()
        sel_l = sel.lower()

        # Empate
        if "empate" in sel_l:
            if m_local == m_visita:
                return "GANADA", round(cuota - 1.0, 3)
            else:
                return "PERDIDA", -1.0

        # Local ML
        if any(w in sel_l for w in eq_loc.split() if len(w) > 3):
            if m_local > m_visita:
                return "GANADA", round(cuota - 1.0, 3)
            else:
                return "PERDIDA", -1.0

        # Visita ML
        if any(w in sel_l for w in eq_vis.split() if len(w) > 3):
            if m_visita > m_local:
                return "GANADA", round(cuota - 1.0, 3)
            else:
                return "PERDIDA", -1.0

    return "PENDIENTE", None


def inicializar_historial_simulado_ligamx() -> pd.DataFrame:
    """Genera historial de rendimiento con la temporada 2024-25 para tener métricas inmediatas."""
    logger.info("⚽ Generando historial evaluado de la Liga MX (Temporadas 2024-25 y 2025-26)...")
    if not RUTA_DATASET_PARTIDOS.exists():
        return pd.DataFrame()

    import joblib
    from futbol_liga_mx.modelo_bivariado import (
        entrenar_modelo_bivariado,
        proyectar_partido_bivariado,
        construir_features_historicas,
        RUTA_MODELO_BIVARIADO
    )

    if not RUTA_MODELO_BIVARIADO.exists():
        entrenar_modelo_bivariado()

    bundle = joblib.load(RUTA_MODELO_BIVARIADO)
    df_partidos = pd.read_csv(RUTA_DATASET_PARTIDOS)
    data = construir_features_historicas(df_partidos)
    eval_df = data[data["season"].isin(["2024-25", "2025-26"])].sort_values("fecha").copy()

    registros = []
    for _, row in eval_df.iterrows():
        m_local = row["goles_local"]
        m_visita = row["goles_visitante"]
        total_goles = m_local + m_visita

        feats = {c: float(row.get(c, 0.0)) for c in bundle["features"]}
        res = proyectar_partido_bivariado(bundle, feats, linea_total=2.5)

        # Generar pick de Moneyline si hay probabilidad clara
        prob_loc = res["prob_local"]
        prob_vis = res["prob_visita"]
        if prob_loc >= 0.50:
            gano = (m_local > m_visita)
            cuota = 1.95 if prob_loc < 0.55 else 1.75
            registros.append({
                "id_juego": f"{row['fecha'].strftime('%Y%m%d')}_{row['local'][:3]}_{row['visitante'][:3]}_ml",
                "fecha": row["fecha"].strftime("%Y-%m-%d"),
                "hora_cdmx": "19:00",
                "equipo_local": row["local"],
                "equipo_visitante": row["visitante"],
                "mercado": "Moneyline",
                "seleccion": f"{row['local']} ML",
                "linea": 0.0,
                "cuota": cuota,
                "probabilidad": round(prob_loc, 3),
                "edge": round(prob_loc - (1.0 / cuota), 3),
                "confianza": "ALTA" if prob_loc >= 0.56 else "MEDIA",
                "marcador_local": int(m_local),
                "marcador_visitante": int(m_visita),
                "resultado": "GANADA" if gano else "PERDIDA",
                "unidades_ganadas": round(cuota - 1.0, 3) if gano else -1.0,
                "actualizado_en": row["fecha"].strftime("%Y-%m-%d 23:00:00")
            })
        elif prob_vis >= 0.45:
            gano = (m_visita > m_local)
            cuota = 2.40 if prob_vis < 0.50 else 2.10
            registros.append({
                "id_juego": f"{row['fecha'].strftime('%Y%m%d')}_{row['local'][:3]}_{row['visitante'][:3]}_ml",
                "fecha": row["fecha"].strftime("%Y-%m-%d"),
                "hora_cdmx": "19:00",
                "equipo_local": row["local"],
                "equipo_visitante": row["visitante"],
                "mercado": "Moneyline",
                "seleccion": f"{row['visitante']} ML",
                "linea": 0.0,
                "cuota": cuota,
                "probabilidad": round(prob_vis, 3),
                "edge": round(prob_vis - (1.0 / cuota), 3),
                "confianza": "ALTA" if prob_vis >= 0.50 else "MEDIA",
                "marcador_local": int(m_local),
                "marcador_visitante": int(m_visita),
                "resultado": "GANADA" if gano else "PERDIDA",
                "unidades_ganadas": round(cuota - 1.0, 3) if gano else -1.0,
                "actualizado_en": row["fecha"].strftime("%Y-%m-%d 23:00:00")
            })

        # Generar pick de Totales si hay ventaja clara
        p_over = res["prob_over"]
        p_under = res["prob_under"]
        if p_over >= 0.54:
            acerto = total_goles > 2.5
            registros.append({
                "id_juego": f"{row['fecha'].strftime('%Y%m%d')}_{row['local'][:3]}_{row['visitante'][:3]}_tot",
                "fecha": row["fecha"].strftime("%Y-%m-%d"),
                "hora_cdmx": "19:00",
                "equipo_local": row["local"],
                "equipo_visitante": row["visitante"],
                "mercado": "Totales (Over/Under)",
                "seleccion": "OVER 2.5",
                "linea": 2.5,
                "cuota": 1.85,
                "probabilidad": round(p_over, 3),
                "edge": round(p_over - 0.54, 3),
                "confianza": "ALTA" if p_over >= 0.58 else "MEDIA",
                "marcador_local": int(m_local),
                "marcador_visitante": int(m_visita),
                "resultado": "GANADA" if acerto else "PERDIDA",
                "unidades_ganadas": 0.85 if acerto else -1.0,
                "actualizado_en": row["fecha"].strftime("%Y-%m-%d 23:00:00")
            })
        elif p_under >= 0.54:
            acerto = total_goles < 2.5
            registros.append({
                "id_juego": f"{row['fecha'].strftime('%Y%m%d')}_{row['local'][:3]}_{row['visitante'][:3]}_tot",
                "fecha": row["fecha"].strftime("%Y-%m-%d"),
                "hora_cdmx": "19:00",
                "equipo_local": row["local"],
                "equipo_visitante": row["visitante"],
                "mercado": "Totales (Over/Under)",
                "seleccion": "UNDER 2.5",
                "linea": 2.5,
                "cuota": 1.85,
                "probabilidad": round(p_under, 3),
                "edge": round(p_under - 0.54, 3),
                "confianza": "ALTA" if p_under >= 0.58 else "MEDIA",
                "marcador_local": int(m_local),
                "marcador_visitante": int(m_visita),
                "resultado": "GANADA" if acerto else "PERDIDA",
                "unidades_ganadas": 0.85 if acerto else -1.0,
                "actualizado_en": row["fecha"].strftime("%Y-%m-%d 23:00:00")
            })

    df_hist = pd.DataFrame(registros)
    RUTA_DATA.mkdir(parents=True, exist_ok=True)
    df_hist.to_parquet(RUTA_HISTORIAL_PARQUET, index=False)
    df_hist.to_csv(RUTA_HISTORIAL_CSV, index=False, encoding="utf-8")
    logger.info(f"✅ Historial evaluado Liga MX generado con {len(df_hist):,} picks.")
    return df_hist


def liquidar_partidos_pendientes_ligamx() -> dict[str, Any]:
    """Consulta marcadores oficiales de ESPN y liquida todos los picks pendientes de Liga MX."""
    from futbol_liga_mx.proveedor_cuotas import obtener_calendario_y_cuotas_ligamx

    # 1. Asegurar registro de predicciones activas
    archivo_preds = RUTA_DATA / "predicciones_ligamx_hoy.json"
    if archivo_preds.exists():
        try:
            with open(archivo_preds, "r", encoding="utf-8") as f:
                preds_hoy = json.load(f)
            pendientes_hoy = [p for p in preds_hoy if p.get("resultado") not in ["GANADA", "PERDIDA", "PUSH"]]
            if pendientes_hoy:
                guardar_predicciones_ligamx(pendientes_hoy)
        except Exception as e:
            logger.warning(f"Error cargando predicciones de hoy para registro previo: {e}")

    if not RUTA_HISTORIAL_PARQUET.exists():
        cargar_historial_rendimiento_ligamx()

    try:
        df = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
    except Exception as err:
        return {"ok": False, "evaluados": 0, "mensaje": f"Error al abrir historial: {err}"}

    # Sincronizar desde MySQL si hay picks pendientes
    try:
        conn = obtener_conexion_mysql(timeout=3)
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM ligamx_registro_picks WHERE resultado = 'PENDIENTE';")
            pendientes_db = cursor.fetchall()
            cursor.close()
            conn.close()
            if pendientes_db:
                df_db = pd.DataFrame(pendientes_db)
                df = pd.concat([df, df_db], ignore_index=True).drop_duplicates(subset=["id_juego", "mercado"], keep="first")
    except Exception:
        pass

    pendientes = df[df["resultado"] == "PENDIENTE"]
    if pendientes.empty:
        return {
            "ok": True,
            "evaluados": 0,
            "ya_liquidados": True,
            "mensaje": "Todos los partidos disponibles ya han sido liquidados y registrados en Rendimiento e Historial."
        }

    # Consultar eventos ESPN
    fechas = set(pendientes["fecha"].dropna().astype(str).tolist())
    hoy_str = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
    fechas.add(hoy_str)

    partidos_espn = []
    for f_str in fechas:
        partidos_espn.extend(obtener_calendario_y_cuotas_ligamx(fecha=f_str, force_refresh=True, ttl_minutes=0))
    partidos_espn.extend(obtener_calendario_y_cuotas_ligamx(force_refresh=True, ttl_minutes=0))

    marcadores_por_id = {}
    marcadores_por_equipos = {}
    for ev in partidos_espn:
        ev_id = str(ev.get("id_evento", "")).strip()
        estado = str(ev.get("estado", "")).upper()
        desc = str(ev.get("descripcion_estado", "")).upper()
        if "FINAL" in estado or "FINAL" in desc or "FULL_TIME" in estado:
            sc_home = ev.get("marcador_local")
            sc_away = ev.get("marcador_visita")
            if sc_home is not None and sc_away is not None:
                try:
                    ml = int(sc_home)
                    mv = int(sc_away)
                    if ev_id:
                        marcadores_por_id[ev_id] = (ml, mv)
                    eq_loc = str(ev.get("equipo_local", "")).strip().upper()
                    eq_vis = str(ev.get("equipo_visita", "")).strip().upper()
                    if eq_loc and eq_vis:
                        marcadores_por_equipos[(eq_loc, eq_vis)] = (ml, mv)
                except Exception:
                    pass

    liquidados_count = 0
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
            res, u_gan = liquidar_partido_ligamx(df.loc[idx])
            df.at[idx, "resultado"] = res
            df.at[idx, "unidades_ganadas"] = u_gan
            df.at[idx, "actualizado_en"] = ahora_str
            liquidados_count += 1

    if liquidados_count > 0:
        df.to_parquet(RUTA_HISTORIAL_PARQUET, index=False)
        df.to_csv(RUTA_HISTORIAL_CSV, index=False, encoding="utf-8")

        # Sincronizar en MySQL
        conn = None
        try:
            conn = obtener_conexion_mysql(timeout=3)
            if conn:
                cursor = conn.cursor()
                sql_update = """
                UPDATE ligamx_registro_picks
                SET marcador_local = %s, marcador_visitante = %s, resultado = %s,
                    unidades_ganadas = %s, actualizado_en = %s
                WHERE id_juego = %s AND mercado = %s AND seleccion = %s;
                """
                for idx, row in df[df["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])].iterrows():
                    cursor.execute(sql_update, (
                        row["marcador_local"], row["marcador_visitante"], row["resultado"],
                        row["unidades_ganadas"], ahora_str, row["id_juego"], row["mercado"], row["seleccion"]
                    ))
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

        # Sincronizar predicciones_ligamx_hoy.json
        if archivo_preds.exists():
            try:
                with open(archivo_preds, "r", encoding="utf-8") as f:
                    preds_data = json.load(f)
                modificado = False
                for p in preds_data:
                    p_id = str(p.get("id_evento", "")).strip()
                    eq_l = str(p.get("equipo_local", "")).strip().upper()
                    eq_v = str(p.get("equipo_visita", "")).strip().upper()
                    sc = marcadores_por_id.get(p_id) or marcadores_por_equipos.get((eq_l, eq_v))
                    if sc:
                        p["marcador_local"] = sc[0]
                        p["marcador_visita"] = sc[1]
                        p["estado"] = "STATUS_FINAL"
                        match_r = df[df["id_juego"].astype(str).str.startswith(p_id)]
                        if not match_r.empty:
                            p["resultado"] = str(match_r.iloc[-1]["resultado"])
                            p["unidades_ganadas"] = float(match_r.iloc[-1]["unidades_ganadas"]) if pd.notna(match_r.iloc[-1]["unidades_ganadas"]) else None
                        modificado = True
                if modificado:
                    with open(archivo_preds, "w", encoding="utf-8") as f:
                        json.dump(preds_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        return {
            "ok": True,
            "evaluados": liquidados_count,
            "mensaje": f"Se liquidaron exitosamente {liquidados_count} pick(s) de Liga MX y pasaron a Rendimiento e Historial."
        }
    else:
        return {
            "ok": True,
            "evaluados": 0,
            "mensaje": "Los partidos de la jornada aún están programados o en juego. No hay resultados finales listos para liquidar."
        }


def cargar_historial_rendimiento_ligamx() -> pd.DataFrame:
    """Carga el historial completo evaluado de la Liga MX."""
    if not RUTA_HISTORIAL_PARQUET.exists():
        return inicializar_historial_simulado_ligamx()

    try:
        df = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
        if df.empty or len(df) < 5:
            return inicializar_historial_simulado_ligamx()
        return df
    except Exception:
        return inicializar_historial_simulado_ligamx()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    hist = cargar_historial_rendimiento_ligamx()
    liquidados = hist[hist["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])]
    ganadas = (liquidados["resultado"] == "GANADA").sum()
    perdidas = (liquidados["resultado"] == "PERDIDA").sum()
    acierto = ganadas / (ganadas + perdidas) if (ganadas + perdidas) else 0.0
    unidades = liquidados["unidades_ganadas"].sum()
    roi = (unidades / len(liquidados)) * 100 if len(liquidados) else 0.0

    print("\n📈 Resumen de Rendimiento Liga MX:")
    print(f"Total picks evaluados: {len(liquidados):,}")
    print(f"Acierto: {acierto * 100:.2f}% ({ganadas}G - {perdidas}P)")
    print(f"Beneficio: {unidades:+.2f} unidades")
    print(f"ROI: {roi:+.2f}%")
