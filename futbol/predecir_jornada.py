"""Pipeline principal de predicción y liquidación para fútbol mundial (8 ligas).

Funcionalidades:
1. Inferencia automática para partidos de Liga MX, Premier League, LaLiga, Serie A, etc.
2. Congelación estricta de momios y picks una vez comenzado el encuentro.
3. Liquidación automática de partidos concluidos.
4. Persistencia en JSON, Parquet y Base de Datos MySQL.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import sys
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX
from core.db import get_db_connection
from futbol.constantes import CODIGOS_LIGAS, obtener_info_liga
from futbol.modelo_futbol import proyectar_partido_futbol
from futbol.proveedor_cuotas import obtener_jornada_completa_futbol

logger = logging.getLogger("futbol_predecir")

RAIZ = Path(__file__).resolve().parents[1]
RUTA_DATA = RAIZ / "data" / "futbol"
RUTA_PREDICCIONES_JSON = RUTA_DATA / "predicciones_futbol_mundial.json"
RUTA_PREDICCIONES_PARQUET = RUTA_DATA / "predicciones_futbol_mundial.parquet"
RUTA_HISTORIAL_CSV = RUTA_DATA / "historial_picks_futbol.csv"


def asegurar_tabla_futbol_mysql():
    """Crea la tabla en MySQL si no existe para registrar el historial de fútbol mundial."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS futbol_predicciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_evento VARCHAR(64) NOT NULL UNIQUE,
                liga_codigo VARCHAR(16) NOT NULL,
                liga_nombre VARCHAR(64) NOT NULL,
                partido VARCHAR(128) NOT NULL,
                equipo_local VARCHAR(64) NOT NULL,
                equipo_visita VARCHAR(64) NOT NULL,
                fecha_cdmx DATE NOT NULL,
                hora_cdmx VARCHAR(16) NOT NULL,
                estado VARCHAR(32) NOT NULL,
                marcador_local INT DEFAULT NULL,
                marcador_visita INT DEFAULT NULL,
                provider VARCHAR(32) DEFAULT 'DraftKings',
                linea_total DECIMAL(4,2) DEFAULT NULL,
                ml_local VARCHAR(16) DEFAULT NULL,
                ml_empate VARCHAR(16) DEFAULT NULL,
                ml_visita VARCHAR(16) DEFAULT NULL,
                prob_local DECIMAL(5,4) NOT NULL,
                prob_empate DECIMAL(5,4) NOT NULL,
                prob_visita DECIMAL(5,4) NOT NULL,
                prob_over DECIMAL(5,4) NOT NULL,
                prob_under DECIMAL(5,4) NOT NULL,
                pick_mercado VARCHAR(32) NOT NULL,
                pick_seleccion VARCHAR(64) NOT NULL,
                pick_cuota VARCHAR(16) DEFAULT NULL,
                pick_cuota_dec DECIMAL(6,3) DEFAULT NULL,
                pick_probabilidad DECIMAL(5,4) NOT NULL,
                pick_edge DECIMAL(5,4) DEFAULT 0.0,
                confianza VARCHAR(16) NOT NULL,
                resultado_pick VARCHAR(16) DEFAULT 'PENDIENTE',
                beneficio_unidades DECIMAL(6,2) DEFAULT NULL,
                timestamp DATETIME NOT NULL,
                INDEX idx_fecha (fecha_cdmx),
                INDEX idx_liga (liga_codigo),
                INDEX idx_estado (estado)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"No se pudo asegurar la tabla futbol_predicciones en MySQL: {exc}")


def cargar_historial_futbol() -> pd.DataFrame:
    """Carga el historial auditado de picks de fútbol desde MySQL o archivos locales."""
    try:
        from futbol.registro import cargar_historial_futbol as _cargar_hist
        df = _cargar_hist()
        if not df.empty:
            return df
    except Exception:
        pass

    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM futbol_predicciones ORDER BY fecha_cdmx DESC, id DESC", conn)
        conn.close()
        if not df.empty:
            df["fecha"] = pd.to_datetime(df["fecha_cdmx"]).dt.date
            df["probabilidad"] = df["pick_probabilidad"] * 100
            df["resultado"] = df["resultado_pick"]
            return df
    except Exception:
        pass

    if RUTA_PREDICCIONES_PARQUET.exists():
        try:
            df = pd.read_parquet(RUTA_PREDICCIONES_PARQUET)
            if not df.empty:
                df["fecha"] = pd.to_datetime(df["fecha_cdmx"]).dt.date
                df["probabilidad"] = df["pick_probabilidad"] * 100
                df["resultado"] = df.get("resultado_pick", "PENDIENTE")
                return df
        except Exception:
            pass

    if RUTA_PREDICCIONES_JSON.exists():
        try:
            with open(RUTA_PREDICCIONES_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            df = pd.DataFrame(data)
            if not df.empty:
                df["fecha"] = pd.to_datetime(df["fecha_cdmx"]).dt.date
                df["probabilidad"] = df["pick_probabilidad"] * 100
                df["resultado"] = df.get("resultado_pick", "PENDIENTE")
                return df
        except Exception:
            pass

    return pd.DataFrame()


def es_partido_en_curso(estado: str) -> bool:
    """Determina si un encuentro está disputándose en este momento."""
    st = str(estado).upper()
    return any(x in st for x in ["PROGRESS", "LIVE", "FIRST_HALF", "SECOND_HALF", "HALFTIME", "EXTRA_TIME", "SHOOTOUT", "PENALTIES"])


def es_partido_finalizado(estado: str) -> bool:
    """Determina si un encuentro concluyó oficialmente (incluyendo tiempo regular, extra o penales)."""
    st = str(estado).upper()
    return any(x in st for x in ["FINAL", "FULL_TIME", "POST", "END", "FINISHED", "FT"]) and not es_partido_en_curso(estado)


def es_partido_iniciado_o_final(estado: str) -> bool:
    """Determina si el partido ya inició o ya concluyó para congelar cuotas y picks."""
    return es_partido_en_curso(estado) or es_partido_finalizado(estado)


def liquidar_seleccion_futbol(
    mercado: str,
    seleccion: str,
    linea: float,
    cuota_dec: float,
    marcador_local: Optional[int],
    marcador_visita: Optional[int],
    equipo_local: str,
    equipo_visita: str,
) -> Tuple[str, float]:
    """Evalúa el resultado de una apuesta finalizada y calcula unidades ganadas/perdidas."""
    if marcador_local is None or marcador_visita is None:
        return "PENDIENTE", 0.0

    sel_clean = seleccion.replace("LEAN:", "").strip()
    sel_upper = sel_clean.upper()
    tot_goles = marcador_local + marcador_visita
    ambos_marcaron = (marcador_local > 0 and marcador_visita > 0)

    # 1. Ambos Anotan (BTTS)
    if "AMBOS ANOTAN" in sel_upper or "BTTS" in sel_upper:
        if "SÍ" in sel_upper or "SI" in sel_upper or "YES" in sel_upper:
            return ("GANADA", round(cuota_dec - 1.0, 2)) if ambos_marcaron else ("PERDIDA", -1.0)
        elif "NO" in sel_upper:
            return ("GANADA", round(cuota_dec - 1.0, 2)) if not ambos_marcaron else ("PERDIDA", -1.0)

    # 2. Doble Oportunidad
    if "DOBLE OPORTUNIDAD" in sel_upper or "1X" in sel_upper or "X2" in sel_upper or "12" in sel_upper:
        if "1X" in sel_upper or "LOCAL O EMPATE" in sel_upper:
            return ("GANADA", round(cuota_dec - 1.0, 2)) if marcador_local >= marcador_visita else ("PERDIDA", -1.0)
        elif "X2" in sel_upper or "EMPATE O VISITA" in sel_upper:
            return ("GANADA", round(cuota_dec - 1.0, 2)) if marcador_visita >= marcador_local else ("PERDIDA", -1.0)
        elif "12" in sel_upper:
            return ("GANADA", round(cuota_dec - 1.0, 2)) if marcador_local != marcador_visita else ("PERDIDA", -1.0)

    # 3. Empate No Acción (Draw No Bet / DNB)
    if "DNB" in sel_upper or "EMPATE NO ACCIÓN" in sel_upper or "DRAW NO BET" in sel_upper:
        if marcador_local == marcador_visita:
            return "PUSH", 0.0
        if equipo_local.upper() in sel_upper or sel_upper.startswith("1"):
            return ("GANADA", round(cuota_dec - 1.0, 2)) if marcador_local > marcador_visita else ("PERDIDA", -1.0)
        if equipo_visita.upper() in sel_upper or sel_upper.startswith("2"):
            return ("GANADA", round(cuota_dec - 1.0, 2)) if marcador_visita > marcador_local else ("PERDIDA", -1.0)

    # 4. Totales Over / Under
    if "OVER" in sel_upper:
        if tot_goles > linea:
            return "GANADA", round(cuota_dec - 1.0, 2)
        elif tot_goles < linea:
            return "PERDIDA", -1.0
        else:
            return "PUSH", 0.0

    if "UNDER" in sel_upper:
        if tot_goles < linea:
            return "GANADA", round(cuota_dec - 1.0, 2)
        elif tot_goles > linea:
            return "PERDIDA", -1.0
        else:
            return "PUSH", 0.0

    # 5. Moneyline (1X2)
    if "EMPATE" in sel_upper:
        if marcador_local == marcador_visita:
            return "GANADA", round(cuota_dec - 1.0, 2)
        return "PERDIDA", -1.0

    # Victoria Local
    if equipo_local.upper() in sel_upper or sel_upper.startswith("1"):
        if marcador_local > marcador_visita:
            return "GANADA", round(cuota_dec - 1.0, 2)
        return "PERDIDA", -1.0

    # Victoria Visitante
    if equipo_visita.upper() in sel_upper or sel_upper.startswith("2"):
        if marcador_visita > marcador_local:
            return "GANADA", round(cuota_dec - 1.0, 2)
        return "PERDIDA", -1.0

    return "PENDIENTE", 0.0


def predecir_futbol_mundial(
    ligas: Optional[List[str]] = None,
    force_refresh: bool = False,
    dias_adelante: int = 3,
) -> List[Dict[str, Any]]:
    """Ejecuta el pipeline completo de fútbol para todas las ligas configuradas."""
    RUTA_DATA.mkdir(parents=True, exist_ok=True)
    asegurar_tabla_futbol_mysql()

    # Cargar historial previo para preservar picks congelados en partidos iniciados
    predicciones_previas: Dict[str, Dict[str, Any]] = {}
    if RUTA_PREDICCIONES_JSON.exists():
        try:
            with open(RUTA_PREDICCIONES_JSON, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
            for p in prev_data:
                if p.get("id_evento"):
                    predicciones_previas[str(p["id_evento"])] = p
        except Exception:
            pass

    juegos = obtener_jornada_completa_futbol(
        ligas=ligas,
        dias_adelante=dias_adelante,
        force_refresh=force_refresh,
    )

    if not juegos:
        return list(predicciones_previas.values())

    predicciones = []

    for j in juegos:
        id_ev = str(j.get("id_evento", "")).strip()
        prev = predicciones_previas.get(id_ev)

        estado_juego = str(j.get("estado", "")).upper()
        ya_comenzo = es_partido_iniciado_o_final(estado_juego)

        # Si el partido ya inició o finalizó, CONSERVAR PICK CONGELADO pre-partido
        if prev and ya_comenzo and prev.get("pick_seleccion"):
            prev_act = dict(prev)
            prev_act["estado"] = j.get("estado", prev.get("estado"))
            prev_act["descripcion_estado"] = j.get("descripcion_estado", prev.get("descripcion_estado"))
            if j.get("marcador_local") is not None:
                prev_act["marcador_local"] = j["marcador_local"]
            if j.get("marcador_visita") is not None:
                prev_act["marcador_visita"] = j["marcador_visita"]

            # Si ya terminó, evaluar resultado respetando filtro de disciplina
            if es_partido_finalizado(prev_act.get("estado", "")):
                if prev_act.get("confianza") == "NEUTRAL" or float(prev_act.get("pick_edge", 0.0)) < 0.045:
                    prev_act["confianza"] = "NEUTRAL"
                    prev_act["resultado_pick"] = "DESCARTADO"
                    prev_act["beneficio_unidades"] = 0.0
                elif prev_act.get("resultado_pick") not in ["GANADA", "PERDIDA", "PUSH"]:
                    res, u_gan = liquidar_seleccion_futbol(
                        mercado=prev_act.get("pick_mercado", ""),
                        seleccion=prev_act.get("pick_seleccion", ""),
                        linea=float(prev_act.get("linea_total", 2.5)),
                        cuota_dec=float(prev_act.get("pick_cuota_dec", 1.85)),
                        marcador_local=prev_act.get("marcador_local"),
                        marcador_visita=prev_act.get("marcador_visita"),
                        equipo_local=prev_act.get("equipo_local", ""),
                        equipo_visita=prev_act.get("equipo_visita", ""),
                    )
                    if res != "PENDIENTE":
                        prev_act["resultado_pick"] = res
                        prev_act["beneficio_unidades"] = u_gan
                        prev_act["evaluado_en"] = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")

            predicciones.append(prev_act)
            continue

        # Inferencia con modelo cuantitativo bivariado
        proj = proyectar_partido_futbol(j)

        pred = {
            "id_evento": j["id_evento"],
            "liga_codigo": j["liga_codigo"],
            "liga_nombre": j["liga_nombre"],
            "liga_bandera": j["liga_bandera"],
            "liga_pais": j["liga_pais"],
            "partido": j["partido"],
            "equipo_local": j["equipo_local"],
            "equipo_visita": j["equipo_visita"],
            "abbr_local": j.get("abbr_local"),
            "abbr_visita": j.get("abbr_visita"),
            "logo_local": j.get("logo_local"),
            "logo_visita": j.get("logo_visita"),
            "fecha_cdmx": j["fecha_cdmx"],
            "hora_cdmx": j["hora_cdmx"],
            "estado": j["estado"],
            "descripcion_estado": j.get("descripcion_estado", ""),
            "marcador_local": j.get("marcador_local"),
            "marcador_visita": j.get("marcador_visita"),
            "provider": j.get("provider", "DraftKings"),
            # Cuotas de mercado
            "linea_total": j.get("linea_total", 2.5),
            "over_momio": j.get("over_momio"),
            "under_momio": j.get("under_momio"),
            "over_momio_dec": j.get("over_momio_dec"),
            "under_momio_dec": j.get("under_momio_dec"),
            "moneyline_local": j.get("moneyline_local"),
            "moneyline_empate": j.get("moneyline_empate"),
            "moneyline_visita": j.get("moneyline_visita"),
            "ml_local_dec": j.get("ml_local_dec"),
            "ml_empate_dec": j.get("ml_empate_dec"),
            "ml_visita_dec": j.get("ml_visita_dec"),
            # Proyecciones del Modelo
            "xg_local": proj["xg_local"],
            "xg_visita": proj["xg_visita"],
            "total_proyectado": proj["total_proyectado"],
            "marcador_mas_probable": proj["marcador_mas_probable"],
            "prob_marcador_mas_probable": proj["prob_marcador_mas_probable"],
            "prob_local": proj["prob_local"],
            "prob_empate": proj["prob_empate"],
            "prob_visita": proj["prob_visita"],
            "prob_over": proj["prob_over"],
            "prob_under": proj["prob_under"],
            "prob_btts_si": proj.get("prob_btts_si", 0.52),
            "prob_btts_no": proj.get("prob_btts_no", 0.48),
            "prob_1x": proj.get("prob_1x", 0.70),
            "prob_x2": proj.get("prob_x2", 0.60),
            "prob_dnb_local": proj.get("prob_dnb_local", 0.55),
            "prob_dnb_visita": proj.get("prob_dnb_visita", 0.45),
            "edge_local": proj["edge_local"],
            "edge_visita": proj["edge_visita"],
            "edge_empate": proj["edge_empate"],
            "edge_over": proj["edge_over"],
            "edge_under": proj["edge_under"],
            # Pick Oficial
            "pick_mercado": proj["pick_mercado"],
            "pick_seleccion": proj["pick_seleccion"],
            "pick_probabilidad": proj["pick_probabilidad"],
            "pick_edge": proj["pick_edge"],
            "pick_ev": proj.get("pick_ev", 0.0),
            "pick_cuota": proj["pick_cuota"],
            "pick_cuota_dec": proj["pick_cuota_dec"],
            "pick_detalle": proj["pick_detalle"],
            "confianza": proj["confianza"],
            "resultado_pick": "PENDIENTE",
            "beneficio_unidades": None,
            "timestamp": datetime.now(ZONA_CDMX).isoformat(),
        }
        predicciones.append(pred)

    # Guardar en JSON y Parquet
    with open(RUTA_PREDICCIONES_JSON, "w", encoding="utf-8") as f:
        json.dump(predicciones, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 Guardadas {len(predicciones)} predicciones en {RUTA_PREDICCIONES_JSON}")

    try:
        pd.DataFrame(predicciones).to_parquet(RUTA_PREDICCIONES_PARQUET, index=False)
    except Exception:
        pass

    # Sincronización en Base de Datos MySQL
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            for p in predicciones:
                cur.execute("""
                INSERT INTO futbol_predicciones (
                    id_evento, liga_codigo, liga_nombre, partido, equipo_local, equipo_visita,
                    fecha_cdmx, hora_cdmx, estado, marcador_local, marcador_visita, provider,
                    linea_total, ml_local, ml_empate, ml_visita,
                    prob_local, prob_empate, prob_visita, prob_over, prob_under,
                    pick_mercado, pick_seleccion, pick_cuota, pick_cuota_dec, pick_probabilidad, pick_edge,
                    confianza, resultado_pick, beneficio_unidades, timestamp
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    estado = VALUES(estado),
                    marcador_local = VALUES(marcador_local),
                    marcador_visita = VALUES(marcador_visita),
                    confianza = VALUES(confianza),
                    pick_mercado = VALUES(pick_mercado),
                    pick_seleccion = VALUES(pick_seleccion),
                    pick_edge = VALUES(pick_edge),
                    resultado_pick = VALUES(resultado_pick),
                    beneficio_unidades = VALUES(beneficio_unidades);
                """, (
                    p["id_evento"], p["liga_codigo"], p["liga_nombre"], p["partido"], p["equipo_local"], p["equipo_visita"],
                    p["fecha_cdmx"], p["hora_cdmx"], p["estado"], p["marcador_local"], p["marcador_visita"], p["provider"],
                    p["linea_total"], p["moneyline_local"], p["moneyline_empate"], p["moneyline_visita"],
                    p["prob_local"], p["prob_empate"], p["prob_visita"], p["prob_over"], p["prob_under"],
                    p["pick_mercado"], p["pick_seleccion"], p["pick_cuota"], p["pick_cuota_dec"], p["pick_probabilidad"], p["pick_edge"],
                    p["confianza"], p["resultado_pick"], p["beneficio_unidades"], p["timestamp"]
                ))
            conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"Error sincronizando predicciones de fútbol en MySQL: {exc}")

    return predicciones


def liquidar_partidos_pendientes_futbol() -> Dict[str, Any]:
    """Revisa partidos concluidos y actualiza marcadores finales y liquidaciones auditadas."""
    try:
        from futbol.registro import liquidar_partidos_pendientes_futbol as _liq_reg
        res = _liq_reg()
        evaluados = res.get("resueltas", res.get("evaluados", res.get("total_evaluados", 0)))
        if evaluados > 0 or res.get("total_pendientes", 0) > 0:
            return {
                "total_partidos": res.get("total_pendientes", 0) + evaluados,
                "resueltas": evaluados,
                "evaluados": evaluados,
                "total_evaluados": evaluados,
                "ganadas": res.get("ganadas", 0),
                "perdidas": res.get("perdidas", 0),
                "pushes": res.get("pushes", 0),
                "unidades_netas": res.get("unidades_netas", 0.0),
                "mensaje": res.get("mensaje", f"Se liquidaron {evaluados} partidos."),
            }
    except Exception as exc:
        logger.warning(f"Error en liquidar_partidos_pendientes_futbol (registro): {exc}")

    preds = predecir_futbol_mundial(force_refresh=True)
    resueltas = sum(1 for p in preds if p.get("resultado_pick") in ["GANADA", "PERDIDA", "PUSH"])
    ganadas = sum(1 for p in preds if p.get("resultado_pick") == "GANADA")
    perdidas = sum(1 for p in preds if p.get("resultado_pick") == "PERDIDA")
    pushes = sum(1 for p in preds if p.get("resultado_pick") == "PUSH")
    unidades = sum(float(p.get("beneficio_unidades") or 0.0) for p in preds)

    return {
        "total_partidos": len(preds),
        "resueltas": resueltas,
        "evaluados": resueltas,
        "total_evaluados": resueltas,
        "ganadas": ganadas,
        "perdidas": perdidas,
        "pushes": pushes,
        "unidades_netas": round(unidades, 2),
        "mensaje": f"Se liquidaron {resueltas} partidos: {ganadas} Ganadas, {perdidas} Perdidas, {pushes} Push ({unidades:+.2f} u)."
    }


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("⚽ Ejecutando predicciones de Fútbol Mundial...")
    preds = predecir_futbol_mundial(force_refresh=True, dias_adelante=2)
    print(f"Total partidos procesados: {len(preds)}")
    for p in preds[:10]:
        print(f"[{p['liga_bandera']} {p['liga_nombre']}] {p['partido']} | {p['fecha_cdmx']} {p['hora_cdmx']}")
        print(f"   🎯 PICK: {p['pick_mercado']} -> {p['pick_seleccion']} ({p['pick_cuota']}) [Prob: {p['pick_probabilidad']*100:.1f}%] [{p['confianza']}]")
