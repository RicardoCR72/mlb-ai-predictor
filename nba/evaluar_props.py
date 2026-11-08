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
RUTA_PROCESSED = RAIZ / "data" / "nba" / "processed"
RUTA_PARQUET_JUGADORES = RUTA_PROCESSED / "player_boxscores_2026_27.parquet"
RUTA_CSV_JUGADORES = RUTA_PROCESSED / "player_boxscores_2026_27.csv"
RUTA_PRED_PARQUET = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.parquet"
RUTA_PRED_JSON = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.json"
RUTA_HISTORIAL_PROPS_PARQUET = RUTA_PROCESSED / "historial_props_nba.parquet"
RUTA_HISTORIAL_PROPS_CSV = RUTA_PROCESSED / "historial_props_nba.csv"

DDL_NBA_PROPS = """
CREATE TABLE IF NOT EXISTS nba_registro_props (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id_juego VARCHAR(64) NOT NULL,
    fecha DATE NOT NULL,
    hora_cdmx VARCHAR(16) NOT NULL,
    equipo_local VARCHAR(64) NOT NULL,
    equipo_visitante VARCHAR(64) NOT NULL,
    jugador VARCHAR(128) NOT NULL,
    mercado VARCHAR(64) NOT NULL,
    seleccion VARCHAR(64) NOT NULL,
    linea DOUBLE NOT NULL,
    cuota DOUBLE NOT NULL,
    probabilidad DOUBLE NOT NULL,
    edge DOUBLE NOT NULL,
    ev_pct DOUBLE NOT NULL,
    estrellas VARCHAR(16) NOT NULL,
    confianza VARCHAR(16) NOT NULL,
    valor_real DOUBLE DEFAULT NULL,
    resultado VARCHAR(16) DEFAULT 'PENDIENTE',
    unidades_ganadas DOUBLE DEFAULT NULL,
    motivo VARCHAR(255) DEFAULT NULL,
    actualizado_en DATETIME NOT NULL,
    UNIQUE KEY uq_nba_prop (id_juego, jugador, mercado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

MAPA_MERCADOS_STATS = {
    "Total Points": "pts",
    "Total Rebounds": "reb",
    "Total Assists": "ast",
    "Total Triples": "t3_made",
    "Total PRA": "pra",
    "Total PR": "pr",
    "Total PA": "pa",
}


def normalizar_nombre_atleta(n: str) -> str:
    """Normaliza nombres de jugadores eliminando acentos, sufijos (Jr, III), puntos y caracteres especiales."""
    if not n:
        return ""
    import unicodedata, re
    s = unicodedata.normalize("NFKD", str(n)).encode("ASCII", "ignore").decode("utf-8")
    s = s.lower().strip()
    s = re.sub(r"[\.\'\,\-]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return " ".join(s.split())


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
    * Si el jugador participó (minutos > 0):
      -> La estadística oficial se compara contra la línea.
      -> Si el jugador hizo 0 del prop (ej. 0 triples) habiendo jugado, NO es push:
         - Si era OVER: se declara PERDIDA (-1.0 u)
         - Si era UNDER: se declara GANADA (+cuota u)
      -> Solo es PUSH si la estadística oficial es exactamente igual a la línea (ej. 2 == 2.0).
    """
    if not partido_finalizado:
        return {
            "resultado": "PENDIENTE",
            "unidades_ganadas": None,
            "valor_real": None,
            "motivo": "Partido en juego o programado",
        }

    p_nombre = str(prop.get("player_clean") or prop.get("player_name", "")).strip()
    p_norm = normalizar_nombre_atleta(p_nombre)
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

    # Búsqueda robusta por nombre normalizado (ignora Jr., Jr, acentos, etc.)
    if "norm_name" in boxscores_evento.columns:
        nombres_box = boxscores_evento["norm_name"].astype(str)
    else:
        nombres_box = boxscores_evento["player_name"].apply(normalizar_nombre_atleta)

    filas_jugador = boxscores_evento[nombres_box == p_norm]

    if filas_jugador.empty:
        # Intento de matching por apellido principal
        partes = [p for p in p_norm.split() if len(p) > 2]
        if partes:
            apellido = partes[-1]
            filas_jugador = boxscores_evento[nombres_box.str.contains(apellido, regex=False)]

    if filas_jugador.empty:
        # El jugador verdaderamente no disputó minutos en el partido
        return {
            "resultado": "PUSH",
            "unidades_ganadas": 0.0,
            "valor_real": 0.0,
            "motivo": "Jugador no participó (DNP / Inactivo)",
        }

    registro = filas_jugador.iloc[0]
    minutos = float(registro.get("minutos", registro.get("min", 0.0)) or 0.0)

    # Si disputó 0 minutos (DNP oficial en planilla), es PUSH
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

    # Empate exacto con la línea (ej. 2 triples con línea 2.0) -> PUSH
    if valor_real == linea:
        return {
            "resultado": "PUSH",
            "unidades_ganadas": 0.0,
            "valor_real": valor_real,
            "motivo": f"Empate exacto con la línea ({valor_real:g} == {linea:g})",
        }

    # Evaluación deportiva estándar habiendo jugado minutos
    if pick_tipo == "OVER":
        if valor_real > linea:
            return {
                "resultado": "GANADA",
                "unidades_ganadas": round(cuota_dec - 1.0, 3),
                "valor_real": valor_real,
                "motivo": f"Superó la línea ({valor_real:g} > {linea:g}) con {minutos:g} min",
            }
        else:
            return {
                "resultado": "PERDIDA",
                "unidades_ganadas": -1.0,
                "valor_real": valor_real,
                "motivo": f"No superó la línea ({valor_real:g} < {linea:g}) con {minutos:g} min",
            }
    elif pick_tipo == "UNDER":
        if valor_real < linea:
            return {
                "resultado": "GANADA",
                "unidades_ganadas": round(cuota_dec - 1.0, 3),
                "valor_real": valor_real,
                "motivo": f"Se mantuvo bajo la línea ({valor_real:g} < {linea:g}) con {minutos:g} min",
            }
        else:
            return {
                "resultado": "PERDIDA",
                "unidades_ganadas": -1.0,
                "valor_real": valor_real,
                "motivo": f"Superó la línea ({valor_real:g} > {linea:g}) con {minutos:g} min",
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


def sincronizar_y_liquidar_props_nba(conn=None) -> Dict[str, Any]:
    """Sincroniza boxscores de jugadores y liquida las predicciones de props NBA.
    
    Guarda el histórico unificado en Parquet local y en MySQL (nba_registro_props).
    """
    RUTA_PROCESSED.mkdir(parents=True, exist_ok=True)
    
    # 1. Asegurar predicciones disponibles
    df_preds = pd.DataFrame()
    if RUTA_PRED_PARQUET.exists():
        try:
            df_preds = pd.read_parquet(RUTA_PRED_PARQUET)
        except Exception as e:
            logger.warning(f"Error leyendo parquet de predicciones: {e}")
    if df_preds.empty and RUTA_PRED_JSON.exists():
        try:
            df_preds = pd.read_json(RUTA_PRED_JSON)
        except Exception as e:
            logger.warning(f"Error leyendo JSON de predicciones: {e}")

    if df_preds.empty:
        return {"ok": False, "mensaje": "No hay archivo de predicciones de props de NBA disponible."}

    # Deduplicar predicciones por jugador y mercado (mayor EV%)
    if "ev_pct" in df_preds.columns:
        df_preds = df_preds.sort_values(by="ev_pct", ascending=False)
    df_preds = df_preds.drop_duplicates(subset=["player_name", "market"], keep="first").copy()

    # 2. Cargar Boxscores de Jugadores oficiales
    df_box = pd.DataFrame()
    if RUTA_PARQUET_JUGADORES.exists():
        try:
            df_box = pd.read_parquet(RUTA_PARQUET_JUGADORES)
        except Exception as e:
            logger.warning(f"Error leyendo boxscores de jugadores: {e}")

    if df_box.empty:
        try:
            from nba.servicio_jugadores_boxscores import sincronizar_boxscores_jugadores
            df_box = sincronizar_boxscores_jugadores()
        except Exception as e:
            logger.warning(f"No se pudieron sincronizar boxscores: {e}")

    if not df_box.empty:
        if "minutos" not in df_box.columns and "min" in df_box.columns:
            df_box["minutos"] = df_box["min"]
        df_box["norm_name"] = df_box["player_name"].apply(normalizar_nombre_atleta)

    # 3. Evaluar cada prop
    filas_evaluadas: List[Dict[str, Any]] = []
    ahora_dt = datetime.now(ZONA_CDMX)

    for _, p in df_preds.iterrows():
        f_str = str(p.get("fecha", ahora_dt.strftime("%Y-%m-%d")))[:10]
        sub_box = df_box[df_box["fecha"] == f_str] if not df_box.empty and "fecha" in df_box.columns else df_box
        
        # Determinar si el partido ya finalizó
        partido_fin = not sub_box.empty if not df_box.empty else False
        res = liquidar_prop_nba(p, sub_box, partido_finalizado=partido_fin)

        eq_vis = str(p.get("away_team", "Visita"))
        eq_loc = str(p.get("home_team", "Local"))
        id_juego = f"{eq_vis}_{eq_loc}_{f_str}".replace(" ", "_")
        jugador_nom = str(p.get("player_name", ""))
        mercado_nom = str(p.get("market", ""))
        pick_tipo = str(p.get("pick_type", "OVER")).upper()
        linea_val = float(p.get("line", 0.0) or 0.0)
        cuota_val = float(p.get("pick_odds_decimal", 1.91) or 1.91)
        prob_val = float(p.get("model_prob", 0.5) or 0.5)
        ev_val = float(p.get("ev_pct", 0.0) or 0.0)
        stars_val = str(p.get("stars", "⭐"))
        conf_val = str(p.get("confidence", "MEDIA"))

        val_real = res.get("valor_real")
        marcador_txt = f"Real: {val_real:g} (Línea {linea_val:g})" if val_real is not None else "En juego"

        fila = {
            "id_juego": id_juego,
            "fecha": f_str,
            "fecha_str": f_str,
            "hora_cdmx": str(p.get("hora", "TBD")),
            "equipo_local": eq_loc,
            "equipo_visitante": eq_vis,
            "partido": f"{eq_vis} @ {eq_loc}",
            "jugador": jugador_nom,
            "pilar": "Props de Jugadores",
            "mercado": mercado_nom,
            "mercado_display": f"{mercado_nom} (Prop)",
            "seleccion": f"{jugador_nom} · {pick_tipo} {linea_val:g}",
            "linea": linea_val,
            "cuota": round(cuota_val, 3),
            "probabilidad": round(prob_val, 3),
            "edge": round(ev_val / 100.0, 3),
            "ev_pct": round(ev_val, 1),
            "stars": stars_val,
            "confianza": conf_val,
            "valor_real": val_real,
            "resultado": res.get("resultado", "PENDIENTE"),
            "unidades_ganadas": res.get("unidades_ganadas"),
            "unidades": res.get("unidades_ganadas"),
            "marcador_final": marcador_txt,
            "motivo": res.get("motivo", ""),
            "actualizado_en": ahora_dt,
        }
        filas_evaluadas.append(fila)

    if not filas_evaluadas:
        return {"ok": False, "mensaje": "No se generaron registros evaluados."}

    df_nuevas = pd.DataFrame(filas_evaluadas)

    # 4. Fusionar con histórico persistente local
    df_existente = pd.DataFrame()
    if RUTA_HISTORIAL_PROPS_PARQUET.exists():
        try:
            df_existente = pd.read_parquet(RUTA_HISTORIAL_PROPS_PARQUET)
        except Exception:
            pass

    if not df_existente.empty:
        df_total = pd.concat([df_existente, df_nuevas], ignore_index=True)
    else:
        df_total = df_nuevas

    df_total.drop_duplicates(subset=["fecha_str", "jugador", "mercado"], keep="last", inplace=True)

    # Re-evaluar contra los boxscores oficiales para asegurar que ningún jugador que sí jugó quede en PUSH
    if not df_box.empty:
        filas_actualizadas = []
        for _, row in df_total.iterrows():
            row_dict = row.to_dict()
            f_str = str(row_dict.get("fecha_str", ""))[:10]
            sub_box = df_box[df_box["fecha"] == f_str] if "fecha" in df_box.columns else df_box
            if not sub_box.empty:
                pick_tipo = "OVER" if "OVER" in str(row_dict.get("seleccion", "")) else "UNDER"
                p_item = {
                    "player_name": row_dict.get("jugador"),
                    "market": row_dict.get("mercado"),
                    "line": float(row_dict.get("linea", 0.0) or 0.0),
                    "pick_type": pick_tipo,
                    "pick_odds_decimal": float(row_dict.get("cuota", 1.91) or 1.91),
                }
                res = liquidar_prop_nba(p_item, sub_box, partido_finalizado=True)
                row_dict["resultado"] = res.get("resultado", row_dict.get("resultado"))
                row_dict["unidades_ganadas"] = res.get("unidades_ganadas", row_dict.get("unidades_ganadas"))
                row_dict["unidades"] = res.get("unidades_ganadas", row_dict.get("unidades"))
                row_dict["valor_real"] = res.get("valor_real", row_dict.get("valor_real"))
                row_dict["motivo"] = res.get("motivo", row_dict.get("motivo"))
                if res.get("valor_real") is not None:
                    row_dict["marcador_final"] = f"Real: {res.get('valor_real'):g} (Línea {float(row_dict.get('linea', 0)):g})"
            filas_actualizadas.append(row_dict)
        df_total = pd.DataFrame(filas_actualizadas)

    df_total.sort_values(by=["fecha_str", "ev_pct"], ascending=[False, False], inplace=True)

    df_total.to_parquet(RUTA_HISTORIAL_PROPS_PARQUET, index=False)
    df_total.to_csv(RUTA_HISTORIAL_PROPS_CSV, index=False)
    logger.info(f"💾 Guardados exitosamente {len(df_total)} props en {RUTA_HISTORIAL_PROPS_PARQUET}")

    # 5. Persistencia en MySQL (nba_registro_props) si está configurado
    try:
        from nba.registro import obtener_conexion_mysql
        conexion = conn or obtener_conexion_mysql(timeout=3)
        if conexion:
            cur = conexion.cursor()
            cur.execute(DDL_NBA_PROPS)
            conexion.commit()

            sql_insert = """
            INSERT INTO nba_registro_props (
                id_juego, fecha, hora_cdmx, equipo_local, equipo_visitante,
                jugador, mercado, seleccion, linea, cuota, probabilidad,
                edge, ev_pct, estrellas, confianza, valor_real, resultado,
                unidades_ganadas, motivo, actualizado_en
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cuota = VALUES(cuota),
                probabilidad = VALUES(probabilidad),
                edge = VALUES(edge),
                ev_pct = VALUES(ev_pct),
                estrellas = VALUES(estrellas),
                confianza = VALUES(confianza),
                valor_real = VALUES(valor_real),
                resultado = VALUES(resultado),
                unidades_ganadas = VALUES(unidades_ganadas),
                motivo = VALUES(motivo),
                actualizado_en = VALUES(actualizado_en)
            """
            for f in filas_evaluadas:
                cur.execute(sql_insert, (
                    f["id_juego"], f["fecha"], f["hora_cdmx"], f["equipo_local"], f["equipo_visitante"],
                    f["jugador"], f["mercado"], f["seleccion"], f["linea"], f["cuota"], f["probabilidad"],
                    f["edge"], f["ev_pct"], f["stars"], f["confianza"], f["valor_real"], f["resultado"],
                    f["unidades_ganadas"], f["motivo"], ahora_dt.strftime("%Y-%m-%d %H:%M:%S")
                ))
            conexion.commit()
            cur.close()
            if conn is None and conexion.is_connected():
                conexion.close()
            logger.info(f"✅ Sincronizados {len(filas_evaluadas)} props en MySQL nba_registro_props")
    except Exception as exc:
        logger.warning(f"No se pudo guardar en MySQL (usando Parquet local): {exc}")

    tot_liq = len([f for f in filas_evaluadas if f["resultado"] in ["GANADA", "PERDIDA", "PUSH"]])
    ganadas = len([f for f in filas_evaluadas if f["resultado"] == "GANADA"])
    perdidas = len([f for f in filas_evaluadas if f["resultado"] == "PERDIDA"])
    pushes = len([f for f in filas_evaluadas if f["resultado"] == "PUSH"])

    return {
        "ok": True,
        "total_evaluados": tot_liq,
        "ganadas": ganadas,
        "perdidas": perdidas,
        "pushes": pushes,
        "mensaje": f"Props sincronizados: {ganadas}G - {perdidas}P ({pushes} PUSH de {tot_liq} concluidos)",
    }


def cargar_historial_props_nba() -> pd.DataFrame:
    """Carga el historial completo de props de NBA desde Parquet o MySQL."""
    # 1. Intentar desde Parquet persistente local
    if RUTA_HISTORIAL_PROPS_PARQUET.exists():
        try:
            df = pd.read_parquet(RUTA_HISTORIAL_PROPS_PARQUET)
            if not df.empty:
                return df
        except Exception as e:
            logger.warning(f"Error leyendo historial_props_nba.parquet: {e}")

    # 2. Si no existe o está vacío, liquidar y sincronizar ahora mismo
    try:
        sincronizar_y_liquidar_props_nba()
        if RUTA_HISTORIAL_PROPS_PARQUET.exists():
            return pd.read_parquet(RUTA_HISTORIAL_PROPS_PARQUET)
    except Exception as e:
        logger.warning(f"Error generando historial de props: {e}")

    return pd.DataFrame()

