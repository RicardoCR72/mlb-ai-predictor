"""Módulo para evaluar y liquidar Player Props de la NBA contra los boxscores oficiales de ESPN."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.constants import NBA_ALIAS_TO_ABBR, ZONA_CDMX

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
    equipo VARCHAR(32) DEFAULT NULL,
    jugador VARCHAR(128) NOT NULL,
    mercado VARCHAR(64) NOT NULL,
    seleccion VARCHAR(64) NOT NULL,
    linea DOUBLE NOT NULL,
    line_modelo DOUBLE DEFAULT NULL,
    is_milestone TINYINT(1) DEFAULT 0,
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
    registrado_en DATETIME DEFAULT NULL,
    timestamp_cuota VARCHAR(64) DEFAULT NULL,
    model_version VARCHAR(64) DEFAULT NULL,
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


def normalizar_equipo_nba(eq: Any) -> str:
    """Normaliza siglas o nombres de franquicias NBA al estándar oficial de 3 letras."""
    if not eq or pd.isna(eq):
        return ""
    eq_str = str(eq).strip().upper()
    return NBA_ALIAS_TO_ABBR.get(eq_str, eq_str)


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
    is_milestone = bool(prop.get("is_milestone", 0) or ("+" in str(prop.get("seleccion", ""))))

    # Si no hay boxscore disponible habiendo concluido el partido -> PUSH por no participación
    if boxscores_evento.empty:
        return {
            "resultado": "PUSH",
            "unidades_ganadas": 0.0,
            "valor_real": 0.0,
            "motivo": "Jugador no participó (DNP / Inactivo)",
        }

    # Candado Defensivo de Equipo: Verificar si el equipo del jugador ya concluyó su partido
    p_team = normalizar_equipo_nba(prop.get("team") or prop.get("equipo") or prop.get("team_abbr") or "")
    candidatos_box = boxscores_evento.copy()

    if "team" in candidatos_box.columns:
        candidatos_box["norm_team"] = candidatos_box["team"].apply(normalizar_equipo_nba)
        equipos_presentes = set(candidatos_box["norm_team"].dropna().unique())

        if p_team:
            # Si el equipo del atleta NO está en los boxscores cargados, el partido aún NO ha finalizado
            if p_team not in equipos_presentes:
                return {
                    "resultado": "PENDIENTE",
                    "unidades_ganadas": None,
                    "valor_real": None,
                    "motivo": f"Esperando finalización del partido de {p_team}",
                }
            # Filtrar candidatos estrictamente al equipo del atleta para evitar falsos positivos
            candidatos_box = candidatos_box[candidatos_box["norm_team"] == p_team]

    # Búsqueda robusta por nombre normalizado (ignora Jr., Jr, acentos, etc.)
    if "norm_name" in candidatos_box.columns:
        nombres_box = candidatos_box["norm_name"].astype(str)
    else:
        nombres_box = candidatos_box["player_name"].apply(normalizar_nombre_atleta)

    filas_jugador = candidatos_box[nombres_box == p_norm]

    if filas_jugador.empty:
        # Intento de matching por apellido principal ÚNICAMENTE dentro del equipo del jugador
        partes = [p for p in p_norm.split() if len(p) > 2]
        if partes:
            apellido = partes[-1]
            candidatos_apellido = candidatos_box[nombres_box.str.contains(apellido, regex=False)]
            if len(candidatos_apellido) == 1:
                filas_jugador = candidatos_apellido
            elif len(candidatos_apellido) > 1:
                # Ambigüedad: más de un jugador en el equipo comparte el apellido (ej. Jalen y Jaylin Williams)
                return {
                    "resultado": "PENDIENTE",
                    "unidades_ganadas": None,
                    "valor_real": None,
                    "motivo": f"Ambigüedad de apellido '{apellido}' en {p_team} (múltiples candidatos)",
                }

    if filas_jugador.empty:
        # El jugador verdaderamente no disputó minutos en el partido de su equipo
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

    # Empate exacto con la línea (ej. 2 triples con línea 2.0)
    if valor_real == linea:
        if is_milestone and pick_tipo == "OVER":
            # Para un milestone (ej. 10+ Puntos con línea 10.0), alcanzar la cuota es GANADA
            return {
                "resultado": "GANADA",
                "unidades_ganadas": round(cuota_dec - 1.0, 3),
                "valor_real": valor_real,
                "motivo": f"Milestone alcanzado ({valor_real:g} >= {linea:g})",
            }
        else:
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

    # Filtrar estrictamente solo picks oficiales calificados (+EV / Top 20)
    # Evita que se inunden 300+ props no calificados o con EV negativo en el historial
    if "es_top20_oficial" in df_preds.columns and df_preds["es_top20_oficial"].any():
        df_preds = df_preds[df_preds["es_top20_oficial"] == True].copy()
    elif len(df_preds) > 20:
        try:
            from nba.predecir_props import seleccionar_top_props_diarios
            df_preds = seleccionar_top_props_diarios(df_preds, limite=20)
        except Exception:
            if "ev_pct" in df_preds.columns:
                df_preds = df_preds[df_preds["ev_pct"] >= 2.0].head(20).copy()
            else:
                df_preds = df_preds.head(20).copy()

    # Deduplicar predicciones por jugador y mercado (permite apuestas diferentes pero nunca el mismo mercado repetido)
    if "ev_pct" in df_preds.columns:
        df_preds = df_preds.sort_values(by="ev_pct", ascending=False)
    df_preds = df_preds.drop_duplicates(subset=["player_name", "market"], keep="first").copy()

    # 2. Cargar y sincronizar Boxscores de Jugadores oficiales con ESPN
    df_box = pd.DataFrame()
    try:
        from nba.servicio_jugadores_boxscores import sincronizar_boxscores_jugadores
        df_box = sincronizar_boxscores_jugadores()
    except Exception as e:
        logger.warning(f"No se pudieron sincronizar boxscores con ESPN ({e}). Usando copia local si existe.")
        if RUTA_PARQUET_JUGADORES.exists():
            try:
                df_box = pd.read_parquet(RUTA_PARQUET_JUGADORES)
            except Exception as e_pq:
                logger.warning(f"Error leyendo copia local de boxscores: {e_pq}")

    if not df_box.empty:
        if "minutos" not in df_box.columns and "min" in df_box.columns:
            df_box["minutos"] = df_box["min"]
        df_box["norm_name"] = df_box["player_name"].apply(normalizar_nombre_atleta)

    # 3. Preparar filas de predicciones pendientes
    filas_nuevas: List[Dict[str, Any]] = []
    ahora_dt = datetime.now(ZONA_CDMX)

    for _, p in df_preds.iterrows():
        f_str = str(p.get("fecha", ahora_dt.strftime("%Y-%m-%d")))[:10]
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
        ev_raw_val = float(p.get("ev_raw", ev_val) or ev_val)
        proj_val = float(p.get("projection", 0.0) or 0.0)
        fair_imp_val = float(p.get("fair_implied_prob", p.get("implied_prob", 0.5)) or 0.5)
        stars_val = str(p.get("stars", "⭐"))
        conf_val = str(p.get("confidence", "MEDIA"))
        p_team_val = str(p.get("team") or p.get("equipo") or "")
        is_mstone = int(p.get("is_milestone", 0) or (1 if "+" in str(p.get("seleccion", "")) else 0))
        line_mod = float(p.get("line_modelo", linea_val) or linea_val)

        fila = {
            "id_juego": id_juego,
            "fecha": f_str,
            "fecha_str": f_str,
            "hora_cdmx": str(p.get("hora", "TBD")),
            "equipo_local": eq_loc,
            "equipo_visitante": eq_vis,
            "partido": f"{eq_vis} @ {eq_loc}",
            "jugador": jugador_nom,
            "equipo": p_team_val,
            "pilar": "Props de Jugadores",
            "mercado": mercado_nom,
            "mercado_display": f"{mercado_nom} (Prop)",
            "seleccion": f"{jugador_nom} · {pick_tipo} {linea_val:g}",
            "linea": linea_val,
            "line_modelo": line_mod,
            "is_milestone": is_mstone,
            "cuota": round(cuota_val, 3),
            "projection": round(proj_val, 1),
            "model_prob": round(prob_val, 4),
            "fair_implied_prob": round(fair_imp_val, 4),
            "ev_raw": round(ev_raw_val, 1),
            "linea_apertura": linea_val,
            "cuota_apertura": round(cuota_val, 3),
            "linea_cierre": None,
            "cuota_cierre": None,
            "clv_pct": None,
            "probabilidad": round(prob_val, 3),
            "edge": round(ev_val / 100.0, 3),
            "ev_pct": round(ev_val, 1),
            "stars": stars_val,
            "confianza": conf_val,
            "valor_real": None,
            "resultado": "PENDIENTE",
            "unidades_ganadas": None,
            "unidades": None,
            "marcador_final": "En juego",
            "motivo": "Registrado para auditoría",
            "registrado_en": str(p.get("registrado_en") or ahora_dt.isoformat()),
            "timestamp_cuota": str(p.get("timestamp_cuota") or ahora_dt.isoformat()),
            "model_version": str(p.get("model_version", "v2.5_bayesian_props")),
            "actualizado_en": ahora_dt,
        }
        filas_nuevas.append(fila)

    if not filas_nuevas:
        return {"ok": False, "mensaje": "No se generaron registros nuevos."}

    df_nuevas = pd.DataFrame(filas_nuevas)

    # 4. Fusionar con histórico persistente local
    df_existente = pd.DataFrame()
    if RUTA_HISTORIAL_PROPS_PARQUET.exists():
        try:
            df_existente = pd.read_parquet(RUTA_HISTORIAL_PROPS_PARQUET)
        except Exception:
            pass

    if not df_existente.empty:
        if "registrado_en" not in df_existente.columns:
            df_existente["registrado_en"] = df_existente["actualizado_en"]
        # Alinear esquemas de columnas
        for col_f in df_nuevas.columns:
            if col_f not in df_existente.columns:
                df_existente[col_f] = None
        for col_f in df_existente.columns:
            if col_f not in df_nuevas.columns:
                df_nuevas[col_f] = None
        df_total = pd.concat([df_existente, df_nuevas[df_existente.columns]], ignore_index=True)
    else:
        df_total = df_nuevas

    # Candado Anti-Sesgo y Regla de Inmutabilidad de Auditoría:
    # Desempate estricto por primer snapshot registrado (registrado_en ASC).
    # La primera línea y cuota registradas son permanentes; descarta snapshots o corridas posteriores.
    df_total["_ts_reg"] = pd.to_datetime(df_total["registrado_en"].fillna(df_total["actualizado_en"]), errors="coerce")
    df_total.sort_values(
        by=["fecha_str", "_ts_reg"],
        ascending=[False, True],
        inplace=True
    )
    df_total.drop_duplicates(subset=["fecha_str", "jugador", "mercado"], keep="first", inplace=True)
    df_total.drop(columns=["_ts_reg"], inplace=True, errors="ignore")

    # 5. Liquidación exclusiva de picks que permanecen en PENDIENTE
    if not df_box.empty:
        filas_actualizadas = []
        for _, row in df_total.iterrows():
            row_dict = row.to_dict()
            estado_actual = str(row_dict.get("resultado", "")).strip().upper()

            # Si el pick YA fue liquidado de forma concluyente, es estrictamente INMUTABLE
            if estado_actual in ("GANADA", "PERDIDA", "PUSH"):
                filas_actualizadas.append(row_dict)
                continue

            # Si está PENDIENTE, intentar liquidar con los boxscores oficiales cargados
            f_str = str(row_dict.get("fecha_str", ""))[:10]
            sub_box = df_box[df_box["fecha"].astype(str).str[:10] == f_str] if "fecha" in df_box.columns else df_box
            if not sub_box.empty:
                pick_tipo = "OVER" if "OVER" in str(row_dict.get("seleccion", "")).upper() else "UNDER"
                p_item = {
                    "player_name": row_dict.get("jugador"),
                    "player_clean": row_dict.get("jugador"),
                    "team": row_dict.get("equipo", ""),
                    "market": row_dict.get("mercado"),
                    "line": float(row_dict.get("linea", 0.0) or 0.0),
                    "pick_type": pick_tipo,
                    "pick_odds_decimal": float(row_dict.get("cuota", 1.91) or 1.91),
                    "is_milestone": int(row_dict.get("is_milestone", 0) or 0),
                    "seleccion": str(row_dict.get("seleccion", "")),
                }
                res = liquidar_prop_nba(p_item, sub_box, partido_finalizado=True)
                # Solo actualizar si el partido ya arrojó un resultado concluyente
                if res.get("resultado") != "PENDIENTE":
                    row_dict["resultado"] = res.get("resultado")
                    row_dict["unidades_ganadas"] = res.get("unidades_ganadas")
                    row_dict["unidades"] = res.get("unidades_ganadas")
                    row_dict["valor_real"] = res.get("valor_real")
                    row_dict["motivo"] = res.get("motivo")
                    row_dict["actualizado_en"] = datetime.now(ZONA_CDMX)
                    if res.get("valor_real") is not None:
                        row_dict["marcador_final"] = f"Real: {res.get('valor_real'):g} (Línea {float(row_dict.get('linea', 0)):g})"
            filas_actualizadas.append(row_dict)
        df_total = pd.DataFrame(filas_actualizadas)

    df_total.sort_values(by=["fecha_str", "ev_pct"], ascending=[False, False], inplace=True)

    df_total.to_parquet(RUTA_HISTORIAL_PROPS_PARQUET, index=False)
    df_total.to_csv(RUTA_HISTORIAL_PROPS_CSV, index=False)
    logger.info(f"💾 Guardados exitosamente {len(df_total)} props en {RUTA_HISTORIAL_PROPS_PARQUET}")

    # 6. Persistencia en MySQL (nba_registro_props) si está configurado
    try:
        from nba.registro import obtener_conexion_mysql
        conexion = conn or obtener_conexion_mysql(timeout=3)
        if conexion:
            cur = conexion.cursor()
            cur.execute(DDL_NBA_PROPS)

            # Migración automática de columnas si la tabla ya existía
            columnas_a_migrar = [
                ("equipo", "VARCHAR(32) DEFAULT NULL"),
                ("line_modelo", "DOUBLE DEFAULT NULL"),
                ("is_milestone", "TINYINT(1) DEFAULT 0"),
                ("registrado_en", "DATETIME DEFAULT NULL"),
                ("timestamp_cuota", "VARCHAR(64) DEFAULT NULL"),
                ("model_version", "VARCHAR(64) DEFAULT NULL"),
            ]
            for col_n, col_t in columnas_a_migrar:
                try:
                    cur.execute(f"ALTER TABLE nba_registro_props ADD COLUMN {col_n} {col_t};")
                    conexion.commit()
                except Exception:
                    pass

            sql_insert = """
            INSERT INTO nba_registro_props (
                id_juego, fecha, hora_cdmx, equipo_local, equipo_visitante, equipo,
                jugador, mercado, seleccion, linea, line_modelo, is_milestone,
                cuota, probabilidad, edge, ev_pct, estrellas, confianza, valor_real,
                resultado, unidades_ganadas, motivo, registrado_en, timestamp_cuota,
                model_version, actualizado_en
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                valor_real = VALUES(valor_real),
                resultado = VALUES(resultado),
                unidades_ganadas = VALUES(unidades_ganadas),
                motivo = VALUES(motivo),
                actualizado_en = VALUES(actualizado_en);
            """
            for _, f in df_total.iterrows():
                reg_dt_str = str(f.get("registrado_en") or "")[:19].replace("T", " ")
                if not reg_dt_str or reg_dt_str == "None":
                    reg_dt_str = ahora_dt.strftime("%Y-%m-%d %H:%M:%S")

                act_dt_str = str(f.get("actualizado_en") or "")[:19].replace("T", " ")
                if not act_dt_str or act_dt_str == "None":
                    act_dt_str = ahora_dt.strftime("%Y-%m-%d %H:%M:%S")

                cur.execute(sql_insert, (
                    str(f.get("id_juego", "")),
                    str(f.get("fecha_str", f.get("fecha", "")))[:10],
                    str(f.get("hora_cdmx", "TBD")),
                    str(f.get("equipo_local", "")),
                    str(f.get("equipo_visitante", "")),
                    str(f.get("equipo", "")),
                    str(f.get("jugador", "")),
                    str(f.get("mercado", "")),
                    str(f.get("seleccion", "")),
                    float(f.get("linea", 0.0) or 0.0),
                    float(f.get("line_modelo", f.get("linea", 0.0)) or f.get("linea", 0.0)),
                    int(f.get("is_milestone", 0) or 0),
                    float(f.get("cuota", 1.91) or 1.91),
                    float(f.get("probabilidad", 0.5) or 0.5),
                    float(f.get("edge", 0.0) or 0.0),
                    float(f.get("ev_pct", 0.0) or 0.0),
                    str(f.get("stars", "⭐")),
                    str(f.get("confianza", "MEDIA")),
                    float(f.get("valor_real")) if pd.notna(f.get("valor_real")) else None,
                    str(f.get("resultado", "PENDIENTE")),
                    float(f.get("unidades_ganadas")) if pd.notna(f.get("unidades_ganadas")) else None,
                    str(f.get("motivo", "")),
                    reg_dt_str,
                    str(f.get("timestamp_cuota", "")),
                    str(f.get("model_version", "v2.5_bayesian_props")),
                    act_dt_str,
                ))
            conexion.commit()
            cur.close()
            if conn is None and conexion.is_connected():
                conexion.close()
            logger.info(f"✅ Sincronizados {len(df_total)} props en MySQL nba_registro_props")
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


def registrar_props_pendientes(df_preds: pd.DataFrame) -> None:
    """Registra predicciones de props como PENDIENTE en el historial persistente de props.
    
    Aplica límite defensivo de máximo 20 picks diarios de mayor confianza para control de banca y auditoría.
    """
    if df_preds is None or df_preds.empty:
        return

    # Asegurar que solo se auditen los Top 20 oficiales de máxima convicción
    if "es_top20_oficial" in df_preds.columns and df_preds["es_top20_oficial"].any():
        df_a_registrar = df_preds[df_preds["es_top20_oficial"] == True].copy()
    elif len(df_preds) > 20:
        try:
            from nba.predecir_props import seleccionar_top_props_diarios
            df_a_registrar = seleccionar_top_props_diarios(df_preds, limite=20)
        except Exception:
            df_a_registrar = df_preds.head(20).copy()
    else:
        df_a_registrar = df_preds.copy()

    RUTA_PROCESSED.mkdir(parents=True, exist_ok=True)
    ahora_dt = datetime.now(ZONA_CDMX)
    filas = []

    for _, p in df_a_registrar.iterrows():
        f_str = str(p.get("fecha", ahora_dt.strftime("%Y-%m-%d")))[:10]
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
        ev_raw_val = float(p.get("ev_raw", ev_val) or ev_val)
        proj_val = float(p.get("projection", 0.0) or 0.0)
        fair_imp_val = float(p.get("fair_implied_prob", p.get("implied_prob", 0.5)) or 0.5)
        stars_val = str(p.get("stars", "⭐"))
        conf_val = str(p.get("confidence", "MEDIA"))
        p_team_val = str(p.get("team") or p.get("equipo") or "")
        is_mstone = int(p.get("is_milestone", 0) or (1 if "+" in str(p.get("seleccion", "")) else 0))
        line_mod = float(p.get("line_modelo", linea_val) or linea_val)

        fila = {
            "id_juego": id_juego,
            "fecha": f_str,
            "fecha_str": f_str,
            "hora_cdmx": str(p.get("hora", "TBD")),
            "equipo_local": eq_loc,
            "equipo_visitante": eq_vis,
            "partido": f"{eq_vis} @ {eq_loc}",
            "jugador": jugador_nom,
            "equipo": p_team_val,
            "pilar": "Props de Jugadores",
            "mercado": mercado_nom,
            "mercado_display": f"{mercado_nom} (Prop)",
            "seleccion": f"{jugador_nom} · {pick_tipo} {linea_val:g}",
            "linea": linea_val,
            "line_modelo": line_mod,
            "is_milestone": is_mstone,
            "cuota": round(cuota_val, 3),
            "projection": round(proj_val, 1),
            "model_prob": round(prob_val, 4),
            "fair_implied_prob": round(fair_imp_val, 4),
            "ev_raw": round(ev_raw_val, 1),
            "linea_apertura": linea_val,
            "cuota_apertura": round(cuota_val, 3),
            "linea_cierre": None,
            "cuota_cierre": None,
            "clv_pct": None,
            "probabilidad": round(prob_val, 3),
            "edge": round(ev_val / 100.0, 3),
            "ev_pct": round(ev_val, 1),
            "stars": stars_val,
            "confianza": conf_val,
            "valor_real": None,
            "resultado": "PENDIENTE",
            "unidades_ganadas": None,
            "unidades": None,
            "marcador_final": "En juego",
            "motivo": "Registrado para auditoría",
            "registrado_en": str(p.get("registrado_en") or ahora_dt.isoformat()),
            "timestamp_cuota": str(p.get("timestamp_cuota") or ahora_dt.isoformat()),
            "model_version": str(p.get("model_version", "v2.5_bayesian_props")),
            "actualizado_en": ahora_dt,
        }
        filas.append(fila)

    if not filas:
        return

    df_nuevas = pd.DataFrame(filas)
    df_existente = pd.DataFrame()
    if RUTA_HISTORIAL_PROPS_PARQUET.exists():
        try:
            df_existente = pd.read_parquet(RUTA_HISTORIAL_PROPS_PARQUET)
        except Exception:
            pass

    if not df_existente.empty:
        if "registrado_en" not in df_existente.columns:
            df_existente["registrado_en"] = df_existente["actualizado_en"]
        # Combinar respetando registros ya concluidos sin duplicar filas
        # Alinear esquemas de columnas y tipos para evitar warnings de concatenación
        cols_nuevas_faltantes = [c for c in df_nuevas.columns if c not in df_existente.columns]
        for c in cols_nuevas_faltantes:
            df_existente[c] = None
        cols_existentes_faltantes = [c for c in df_existente.columns if c not in df_nuevas.columns]
        for c in cols_existentes_faltantes:
            df_nuevas[c] = None

        cols_float = ["linea_apertura", "cuota_apertura", "linea_cierre", "cuota_cierre", "clv_pct", "projection", "model_prob", "fair_implied_prob", "ev_raw"]
        for c in cols_float:
            if c in df_existente.columns:
                df_existente[c] = pd.to_numeric(df_existente[c], errors="coerce")
            if c in df_nuevas.columns:
                df_nuevas[c] = pd.to_numeric(df_nuevas[c], errors="coerce")

        df_total = pd.concat([df_existente, df_nuevas[df_existente.columns]], ignore_index=True)

        # Candado Anti-Sesgo y Regla de Inmutabilidad de Primer Snapshot:
        # Desempate estricto por tiempo de registro matutino (registrado_en ASC).
        # La primera cuota y línea registradas se preservan inmutables.
        df_total["_ts_reg"] = pd.to_datetime(df_total["registrado_en"].fillna(df_total["actualizado_en"]), errors="coerce")
        df_total.sort_values(
            by=["fecha_str", "_ts_reg"],
            ascending=[False, True],
            inplace=True
        )
        df_total.drop_duplicates(subset=["fecha_str", "jugador", "mercado"], keep="first", inplace=True)
        df_total.drop(columns=["_ts_reg"], inplace=True, errors="ignore")
    else:
        df_total = df_nuevas

    df_total.sort_values(by=["fecha_str", "ev_pct"], ascending=[False, False], inplace=True)
    df_total.to_parquet(RUTA_HISTORIAL_PROPS_PARQUET, index=False)
    df_total.to_csv(RUTA_HISTORIAL_PROPS_CSV, index=False)
    logger.info(f"💾 {len(df_nuevas)} props registrados como PENDIENTE en {RUTA_HISTORIAL_PROPS_PARQUET}")


def cargar_historial_props_nba() -> pd.DataFrame:
    """Carga el historial completo de props de NBA desde Parquet o MySQL."""
    # 1. Intentar desde Parquet persistente local
    if RUTA_HISTORIAL_PROPS_PARQUET.exists():
        try:
            df = pd.read_parquet(RUTA_HISTORIAL_PROPS_PARQUET)
            if not df.empty:
                # Si hay registros pendientes de días previos, intentar liquidar en segundo plano
                hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
                hay_pendientes_pasados = any(
                    (str(r.get("resultado")).strip().upper() == "PENDIENTE") and (str(r.get("fecha_str", ""))[:10] < hoy_cdmx)
                    for _, r in df.iterrows()
                )
                if hay_pendientes_pasados:
                    try:
                        sincronizar_y_liquidar_props_nba()
                        df = pd.read_parquet(RUTA_HISTORIAL_PROPS_PARQUET)
                    except Exception as e_liq:
                        logger.warning(f"Error liquidando props pendientes pasados: {e_liq}")
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

