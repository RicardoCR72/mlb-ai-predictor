"""Módulo de persistencia, auditoría y análisis de rendimiento para Fútbol Mundial.

1. Guarda predicciones y líneas en MySQL (futbol_registro_picks) y respaldo local en Parquet/CSV.
2. Liquida automáticamente los resultados (GANADA, PERDIDA, PUSH) consultando marcadores finales.
3. Calcula métricas oficiales de rendimiento: Acierto (%), Unidades (+/- u) y ROI (%).
4. Renderiza la interfaz ejecutiva de Rendimiento e Historial con filtros, gráficas y tarjetas.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX
from core.infrastructure.database import get_db_credentials
from futbol.constantes import CODIGOS_LIGAS, obtener_info_liga
from futbol.proveedor_cuotas import obtener_partidos_liga_espn
from futbol.modelo_futbol import proyectar_partido_futbol

logger = logging.getLogger(__name__)

RUTA_DATA = RAIZ / "data" / "futbol"
RUTA_HISTORIAL_PARQUET = RUTA_DATA / "historial_picks_futbol.parquet"
RUTA_HISTORIAL_CSV = RUTA_DATA / "historial_picks_futbol.csv"
RUTA_PREDICCIONES_JSON = RUTA_DATA / "predicciones_futbol_mundial.json"

DDL_FUTBOL_PICKS = """
CREATE TABLE IF NOT EXISTS futbol_registro_picks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id_juego VARCHAR(64) NOT NULL,
    fecha DATE NOT NULL,
    hora_cdmx VARCHAR(16) NOT NULL,
    liga_codigo VARCHAR(16) NOT NULL DEFAULT 'mex.1',
    liga_nombre VARCHAR(64) NOT NULL DEFAULT 'Liga MX',
    liga_bandera VARCHAR(16) NOT NULL DEFAULT '⚽',
    equipo_local VARCHAR(64) NOT NULL,
    equipo_visitante VARCHAR(64) NOT NULL,
    mercado VARCHAR(32) NOT NULL,
    seleccion VARCHAR(64) NOT NULL,
    linea DOUBLE DEFAULT 2.5,
    cuota DOUBLE NOT NULL,
    probabilidad DOUBLE NOT NULL,
    edge DOUBLE NOT NULL,
    confianza VARCHAR(16) NOT NULL,
    marcador_local INT DEFAULT NULL,
    marcador_visitante INT DEFAULT NULL,
    resultado VARCHAR(16) DEFAULT 'PENDIENTE',
    unidades_ganadas DOUBLE DEFAULT NULL,
    actualizado_en DATETIME NOT NULL,
    UNIQUE KEY uq_futbol_pick (id_juego, mercado, seleccion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def obtener_conexion_mysql(timeout: int = 2):
    """Crea una conexión rápida a MySQL con timeout corto para no congelar la app si está offline."""
    try:
        import mysql.connector
        creds = get_db_credentials()
        creds["connection_timeout"] = timeout
        return mysql.connector.connect(**creds)
    except Exception:
        return None


def preparar_tablas_futbol(conn) -> bool:
    """Crea la tabla futbol_registro_picks si no existe en MySQL."""
    try:
        cursor = conn.cursor()
        cursor.execute(DDL_FUTBOL_PICKS)
        conn.commit()
        cursor.close()
        return True
    except Exception as err:
        logger.warning(f"No se pudo crear/verificar tabla en MySQL: {err}")
        return False


def _normalizar_df_historial(df: pd.DataFrame) -> pd.DataFrame:
    """Asegura consistencia de columnas en DataFrames de auditoría de fútbol."""
    if df.empty:
        return df
    df = df.copy()
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    if "partido" not in df.columns:
        if "equipo_local" in df.columns and "equipo_visitante" in df.columns:
            df["partido"] = df["equipo_visitante"].astype(str) + " @ " + df["equipo_local"].astype(str)
        elif "equipo_local" in df.columns and "equipo_visita" in df.columns:
            df["partido"] = df["equipo_visita"].astype(str) + " @ " + df["equipo_local"].astype(str)
        else:
            df["partido"] = "Partido"
    if "beneficio_unidades" not in df.columns:
        if "unidades_ganadas" in df.columns:
            df["beneficio_unidades"] = pd.to_numeric(df["unidades_ganadas"], errors="coerce").fillna(0.0)
        elif "unidades" in df.columns:
            df["beneficio_unidades"] = pd.to_numeric(df["unidades"], errors="coerce").fillna(0.0)
        else:
            df["beneficio_unidades"] = 0.0
    if "unidades_ganadas" not in df.columns:
        df["unidades_ganadas"] = df["beneficio_unidades"]
    if "unidades" not in df.columns:
        df["unidades"] = df["beneficio_unidades"]
    if "pick_mercado" not in df.columns and "mercado" in df.columns:
        df["pick_mercado"] = df["mercado"]
    if "mercado" not in df.columns and "pick_mercado" in df.columns:
        df["mercado"] = df["pick_mercado"]
    if "pick_seleccion" not in df.columns and "seleccion" in df.columns:
        df["pick_seleccion"] = df["seleccion"]
    if "seleccion" not in df.columns and "pick_seleccion" in df.columns:
        df["seleccion"] = df["pick_seleccion"]
    if "pick_cuota" not in df.columns and "cuota" in df.columns:
        df["pick_cuota"] = df["cuota"]
    if "cuota" not in df.columns and "pick_cuota" in df.columns:
        df["cuota"] = df["pick_cuota"]
    if "pick_probabilidad" not in df.columns and "probabilidad" in df.columns:
        df["pick_probabilidad"] = df["probabilidad"]
    return df


def cargar_historial_futbol() -> pd.DataFrame:
    """Carga el historial de picks auditados de fútbol desde MySQL o archivos locales."""
    # 1. Intentar desde MySQL si está disponible
    conn = obtener_conexion_mysql(timeout=2)
    if conn:
        try:
            df = pd.read_sql("SELECT * FROM futbol_registro_picks ORDER BY fecha DESC, id DESC", conn)
            conn.close()
            if not df.empty and len(df) >= 20:
                return _normalizar_df_historial(df)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    # 2. Intentar desde Parquet local
    if RUTA_HISTORIAL_PARQUET.exists():
        try:
            df = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
            if not df.empty:
                return _normalizar_df_historial(df)
        except Exception:
            pass

    # 3. Intentar desde CSV local
    if RUTA_HISTORIAL_CSV.exists():
        try:
            df = pd.read_csv(RUTA_HISTORIAL_CSV)
            if not df.empty:
                return _normalizar_df_historial(df)
        except Exception:
            pass

    # 4. Semilla de respaldo desde futbol_liga_mx si existe
    ruta_lmx = RAIZ / "futbol_liga_mx" / "data" / "historial_picks_ligamx.csv"
    if ruta_lmx.exists():
        try:
            df_lmx = pd.read_csv(ruta_lmx)
            if not df_lmx.empty:
                df_lmx["liga_codigo"] = "mex.1"
                df_lmx["liga_nombre"] = "Liga MX"
                df_lmx["liga_bandera"] = "🇲🇽"
                guardar_picks_en_historial(df_lmx.to_dict(orient="records"))
                return _normalizar_df_historial(df_lmx)
        except Exception:
            pass

    return pd.DataFrame()


def guardar_picks_en_historial(nuevos: List[Dict[str, Any]]) -> None:
    """Inserta o actualiza picks auditados en el almacenamiento local y MySQL."""
    if not nuevos:
        return

    RUTA_DATA.mkdir(parents=True, exist_ok=True)
    df_nuevos = pd.DataFrame(nuevos)

    # Cargar existente para fusionar
    df_actual = pd.DataFrame()
    if RUTA_HISTORIAL_PARQUET.exists():
        try:
            df_actual = pd.read_parquet(RUTA_HISTORIAL_PARQUET)
        except Exception:
            pass
    elif RUTA_HISTORIAL_CSV.exists():
        try:
            df_actual = pd.read_csv(RUTA_HISTORIAL_CSV)
        except Exception:
            pass

    if not df_actual.empty:
        df_total = pd.concat([df_actual, df_nuevos], ignore_index=True)
    else:
        df_total = df_nuevos

    # Deduplicar por id_juego, mercado y selección
    cols_dedup = [c for c in ["id_juego", "mercado", "seleccion"] if c in df_total.columns]
    if cols_dedup:
        df_total = df_total.drop_duplicates(subset=cols_dedup, keep="last")

    # Guardar en local
    try:
        df_total.to_parquet(RUTA_HISTORIAL_PARQUET, index=False)
        df_total.to_csv(RUTA_HISTORIAL_CSV, index=False, encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Error guardando historial local de fútbol: {exc}")

    # Guardar en MySQL si está disponible
    conn = obtener_conexion_mysql(timeout=2)
    if conn:
        try:
            preparar_tablas_futbol(conn)
            cursor = conn.cursor()
            sql_insert = """
            INSERT INTO futbol_registro_picks (
                id_juego, fecha, hora_cdmx, liga_codigo, liga_nombre, liga_bandera,
                equipo_local, equipo_visitante, mercado, seleccion, linea, cuota,
                probabilidad, edge, confianza, marcador_local, marcador_visitante,
                resultado, unidades_ganadas, actualizado_en
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                marcador_local = VALUES(marcador_local),
                marcador_visitante = VALUES(marcador_visitante),
                resultado = VALUES(resultado),
                unidades_ganadas = VALUES(unidades_ganadas),
                actualizado_en = VALUES(actualizado_en);
            """
            for row in nuevos:
                cursor.execute(sql_insert, (
                    str(row.get("id_juego", "")),
                    str(row.get("fecha", "")),
                    str(row.get("hora_cdmx", "12:00")),
                    str(row.get("liga_codigo", "mex.1")),
                    str(row.get("liga_nombre", "Fútbol")),
                    str(row.get("liga_bandera", "⚽")),
                    str(row.get("equipo_local", "")),
                    str(row.get("equipo_visitante", "")),
                    str(row.get("mercado", "")),
                    str(row.get("seleccion", "")),
                    float(row.get("linea", 2.5)),
                    float(row.get("cuota", 1.85)),
                    float(row.get("probabilidad", 0.5)),
                    float(row.get("edge", 0.0)),
                    str(row.get("confianza", "MEDIA")),
                    row.get("marcador_local"),
                    row.get("marcador_visitante"),
                    str(row.get("resultado", "PENDIENTE")),
                    row.get("unidades_ganadas"),
                    datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")
                ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as exc:
            logger.warning(f"Error sincronizando historial de fútbol en MySQL: {exc}")


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

    # 3. Totales Over / Under
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

    # 4. Moneyline (1X2)
    if "EMPATE" in sel_upper or "(X)" in sel_upper:
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


def liquidar_partidos_pendientes_futbol() -> Dict[str, Any]:
    """Consulta marcadores en ESPN para partidos concluidos, liquida picks y actualiza el historial."""
    # 1. Cargar predicciones activas
    predicciones = []
    if RUTA_PREDICCIONES_JSON.exists():
        try:
            with open(RUTA_PREDICCIONES_JSON, "r", encoding="utf-8") as f:
                predicciones = json.load(f)
        except Exception:
            pass

    hoy = datetime.now(ZONA_CDMX).date()
    fechas_a_revisar = [(hoy - timedelta(days=d)).strftime("%Y%m%d") for d in [0, 1, 2]]

    nuevos_liquidados = []
    total_evaluados = 0
    total_ganadas = 0
    total_perdidas = 0
    total_pushes = 0
    unidades_netas = 0.0

    # Consultar marcadores oficiales recientes en ESPN
    partidos_recientes_espn = {}
    for f_str in fechas_a_revisar:
        for cod_liga in CODIGOS_LIGAS:
            try:
                juegos_espn = obtener_partidos_liga_espn(cod_liga, fecha=f_str, force_refresh=True)
                for j in juegos_espn:
                    ev_id = str(j.get("id_evento", "")).strip()
                    if ev_id and j.get("marcador_local") is not None and j.get("marcador_visita") is not None:
                        partidos_recientes_espn[ev_id] = j
            except Exception:
                pass

    # Evaluar partidos pendientes en la cartelera activa
    modificados = False
    for p in predicciones:
        ev_id = str(p.get("id_evento", "")).strip()
        juego_final = partidos_recientes_espn.get(ev_id)
        if juego_final and p.get("resultado_pick") not in ["GANADA", "PERDIDA", "PUSH"]:
            ml = juego_final["marcador_local"]
            mv = juego_final["marcador_visita"]
            p["marcador_local"] = ml
            p["marcador_visita"] = mv
            p["estado"] = juego_final.get("estado", "STATUS_FULL_TIME")

            pick_m = p.get("pick_mercado", "Totales (Over/Under)")
            pick_s = p.get("pick_seleccion", "")
            linea_t = float(p.get("linea_total", 2.5))
            cuota_d = float(p.get("pick_cuota_dec", 1.85))

            res, u_gan = liquidar_seleccion_futbol(
                mercado=pick_m,
                seleccion=pick_s,
                linea=linea_t,
                cuota_dec=cuota_d,
                marcador_local=ml,
                marcador_visita=mv,
                equipo_local=p.get("equipo_local", ""),
                equipo_visita=p.get("equipo_visita", ""),
            )

            if res in ["GANADA", "PERDIDA", "PUSH"]:
                p["resultado_pick"] = res
                p["beneficio_unidades"] = u_gan
                modificados = True
                total_evaluados += 1
                if res == "GANADA":
                    total_ganadas += 1
                elif res == "PERDIDA":
                    total_perdidas += 1
                else:
                    total_pushes += 1
                unidades_netas += u_gan

                # Preparar para el historial permanente
                nuevos_liquidados.append({
                    "id_juego": f"{ev_id}_{pick_m[:3]}",
                    "fecha": p.get("fecha_cdmx", hoy.strftime("%Y-%m-%d")),
                    "hora_cdmx": p.get("hora_cdmx", "12:00"),
                    "liga_codigo": p.get("liga_codigo", "mex.1"),
                    "liga_nombre": p.get("liga_nombre", "Fútbol"),
                    "liga_bandera": p.get("liga_bandera", "⚽"),
                    "equipo_local": p.get("equipo_local", ""),
                    "equipo_visitante": p.get("equipo_visita", ""),
                    "mercado": pick_m,
                    "seleccion": pick_s,
                    "linea": linea_t,
                    "cuota": round(cuota_d, 2),
                    "probabilidad": round(float(p.get("pick_probabilidad", 0.5)), 3),
                    "edge": round(float(p.get("pick_edge", 0.0)), 3),
                    "confianza": p.get("confianza", "MEDIA"),
                    "marcador_local": int(ml),
                    "marcador_visitante": int(mv),
                    "resultado": res,
                    "unidades_ganadas": u_gan,
                    "actualizado_en": datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")
                })

    if modificados:
        try:
            with open(RUTA_PREDICCIONES_JSON, "w", encoding="utf-8") as f:
                json.dump(predicciones, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    if nuevos_liquidados:
        guardar_picks_en_historial(nuevos_liquidados)

    return {
        "evaluados": total_evaluados,
        "ganadas": total_ganadas,
        "perdidas": total_perdidas,
        "pushes": total_pushes,
        "unidades_netas": round(unidades_netas, 2),
        "mensaje": f"Se liquidaron {total_evaluados} partidos: {total_ganadas} Ganadas, {total_perdidas} Perdidas, {total_pushes} Push ({unidades_netas:+.2f} u)."
    }


def render_historial_futbol(mercado_activo: str):
    """Renderiza la auditoría ejecutiva y rendimiento histórico de selecciones de fútbol mundial."""
    st.markdown(
        """<div style="background: linear-gradient(145deg, #091f14, #05140b); border: 1px solid #00e676; border-radius: 14px; padding: 1.25rem; margin-bottom: 1.25rem;">
<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
<div>
<div style="font-size: 1.15rem; font-weight: 900; color: #ffffff;">⚽ Auditoría Oficial y Rendimiento Histórico · Fútbol Mundial</div>
<div style="color: #8ba797; font-size: 0.85rem; margin-top: 0.2rem;">Registro inmutable de picks recomendados, marcadores verificados en ESPN y liquidaciones transparentes a 1 unidad plana.</div>
</div>
<div>
<span style="background: #00e676; color: #05140b; font-weight: 900; font-size: 0.75rem; padding: 0.35rem 0.75rem; border-radius: 999px;">AUDITORÍA ACTIVA</span>
</div>
</div>
</div>""",
        unsafe_allow_html=True,
    )

    df_hist = cargar_historial_futbol()
    if df_hist.empty:
        st.info("Aún no hay historial de partidos liquidados en el registro de fútbol mundial.")
        return

    # Limpiar y filtrar exclusivamente partidos liquidados (GANADA, PERDIDA, PUSH)
    f_liq = df_hist[df_hist["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])].copy()
    if f_liq.empty:
        st.info("No hay picks concluidos en el registro. Pulsa '🏁 Liquidar Partidos' para auditar los encuentros finalizados.")
        return

    # ==========================================
    # FILTROS DESPLEGABLES DE AUDITORÍA
    # ==========================================
    with st.expander("⚙️ Filtros de Rendimiento y Auditoría", expanded=True):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)

        # 1. Filtro de Liga
        with col_f1:
            nombres_ligas = {
                "todas": "🌍 Todas las Ligas",
                "mex.1": "🇲🇽 Liga MX",
                "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
                "esp.1": "🇪🇸 LaLiga",
                "ita.1": "🇮🇹 Serie A",
                "ger.1": "🇩🇪 Bundesliga",
                "fra.1": "🇫🇷 Ligue 1",
                "ned.1": "🇳🇱 Eredivisie",
                "usa.1": "🇺🇸 MLS",
            }
            ligas_presentes = ["todas"] + [c for c in CODIGOS_LIGAS if c in f_liq["liga_codigo"].values]
            etiquetas_ligas = [f"{nombres_ligas.get(c, c)} ({len(f_liq) if c == 'todas' else (f_liq['liga_codigo'] == c).sum()})" for c in ligas_presentes]
            sel_liga_idx = st.selectbox(
                "Filtrar por Liga:",
                range(len(ligas_presentes)),
                format_func=lambda i: etiquetas_ligas[i],
                key="hist_sel_liga",
            )
            sel_liga = ligas_presentes[sel_liga_idx]

        # 2. Filtro de Mercado
        with col_f2:
            mercados_unicos = ["Todos los mercados"] + sorted(f_liq["mercado"].dropna().unique().tolist())
            idx_def_mercado = 0
            for idx_m, m_op in enumerate(mercados_unicos):
                if mercado_activo and mercado_activo[:7].lower() in m_op.lower():
                    idx_def_mercado = idx_m
                    break
            sel_mercado = st.selectbox("Mercado analizado:", mercados_unicos, index=idx_def_mercado, key="hist_sel_mercado")

        # 3. Filtro de Confianza
        with col_f3:
            sel_conf = st.selectbox(
                "Nivel de Confianza:",
                ["Todas las selecciones", "Solo ALTA confianza", "Solo MEDIA confianza"],
                key="hist_sel_conf",
            )

        # 4. Filtro de Resultado
        with col_f4:
            sel_resultado = st.selectbox(
                "Resultado:",
                ["Todos los resultados", "Solo Ganadas", "Solo Perdidas", "Solo Pushes"],
                key="hist_sel_res",
            )

        # Fila de buscador por texto
        busqueda_equipo = st.text_input(
            "Buscar equipo de Fútbol:",
            placeholder="🔍 Ej: Real Madrid, Barcelona, Arsenal, América, Chivas, Chelsea...",
            key="hist_busqueda_equipo",
        ).strip().lower()

    # Aplicación de filtros
    if sel_liga != "todas":
        f_liq = f_liq[f_liq["liga_codigo"] == sel_liga]

    if sel_mercado != "Todos los mercados":
        f_liq = f_liq[f_liq["mercado"] == sel_mercado]

    if sel_conf == "Solo ALTA confianza":
        f_liq = f_liq[f_liq["confianza"] == "ALTA"]
    elif sel_conf == "Solo MEDIA confianza":
        f_liq = f_liq[f_liq["confianza"] == "MEDIA"]

    if sel_resultado == "Solo Ganadas":
        f_liq = f_liq[f_liq["resultado"] == "GANADA"]
    elif sel_resultado == "Solo Perdidas":
        f_liq = f_liq[f_liq["resultado"] == "PERDIDA"]
    elif sel_resultado == "Solo Pushes":
        f_liq = f_liq[f_liq["resultado"] == "PUSH"]

    if busqueda_equipo:
        f_liq = f_liq[
            f_liq["equipo_local"].astype(str).str.lower().str.contains(busqueda_equipo, na=False) |
            f_liq["equipo_visitante"].astype(str).str.lower().str.contains(busqueda_equipo, na=False)
        ]

    if f_liq.empty:
        st.warning("⚠️ No se encontraron picks ni partidos liquidados para la combinación de filtros seleccionada.")
        return

    # ==========================================
    # MÉTRICAS EJECUTIVAS HOMOLOGADAS
    # ==========================================
    n_eval = len(f_liq)
    ganadas = int((f_liq["resultado"] == "GANADA").sum())
    perdidas = int((f_liq["resultado"] == "PERDIDA").sum())
    pushes = int((f_liq["resultado"] == "PUSH").sum())
    decididas = ganadas + perdidas
    acierto_pct = (ganadas / decididas * 100.0) if decididas else 0.0
    beneficio_u = float(pd.to_numeric(f_liq["unidades_ganadas"], errors="coerce").fillna(0.0).sum())
    roi_pct = (beneficio_u / max(n_eval, 1)) * 100.0

    rmcols = st.columns(4)
    rmcols[0].metric("Picks Evaluados", f"{n_eval:,}")
    rmcols[1].metric("Tasa de Acierto", f"{acierto_pct:.1f}%", f"{ganadas}G - {perdidas}P" + (f" ({pushes} Push)" if pushes else ""))
    rmcols[2].metric("Beneficio Acumulado", f"{beneficio_u:+.2f} u")
    rmcols[3].metric("ROI Estimado", f"{roi_pct:+.2f}%")

    st.markdown("<div style='margin-bottom: 1rem;'></div>", unsafe_allow_html=True)

    # ==========================================
    # GRÁFICA DE EVOLUCIÓN ACUMULADA
    # ==========================================
    if len(f_liq) > 1 and f_liq["fecha"].nunique() > 1:
        st.subheader("📈 Evolución de Unidades en el Tiempo (1 u plana)")
        f_liq_chart = f_liq.copy()
        f_liq_chart["fecha_dt"] = pd.to_datetime(f_liq_chart["fecha"])
        evolucion = f_liq_chart.sort_values("fecha_dt").copy()
        evolucion["Unidades Acumuladas"] = pd.to_numeric(evolucion["unidades_ganadas"], errors="coerce").fillna(0.0).cumsum()

        chart_data = evolucion.set_index("fecha_dt")["Unidades Acumuladas"]
        st.line_chart(chart_data, use_container_width=True)

    # ==========================================
    # DESGLOSE POR MERCADO Y LIGA
    # ==========================================
    with st.expander("📊 Desglose Detallado por Mercado y Liga"):
        col_des1, col_des2 = st.columns(2)
        with col_des1:
            st.markdown("**Rendimiento por Mercado:**")
            agrupado_mercado = []
            for m, g in f_liq.groupby("mercado"):
                g_dec = g[g["resultado"].isin(["GANADA", "PERDIDA"])]
                g_gan = (g["resultado"] == "GANADA").sum()
                g_per = (g["resultado"] == "PERDIDA").sum()
                g_acierto = (g_gan / len(g_dec) * 100.0) if len(g_dec) else 0.0
                g_u = pd.to_numeric(g["unidades_ganadas"], errors="coerce").fillna(0.0).sum()
                g_roi = (g_u / len(g) * 100.0) if len(g) else 0.0
                agrupado_mercado.append({
                    "Mercado": m,
                    "Picks": len(g),
                    "Ganadas": int(g_gan),
                    "Perdidas": int(g_per),
                    "Acierto (%)": round(g_acierto, 1),
                    "Unidades": round(g_u, 2),
                    "ROI (%)": round(g_roi, 1),
                })
            st.dataframe(pd.DataFrame(agrupado_mercado), hide_index=True, use_container_width=True)

        with col_des2:
            st.markdown("**Rendimiento por Liga:**")
            agrupado_liga = []
            for l, g in f_liq.groupby("liga_nombre"):
                g_dec = g[g["resultado"].isin(["GANADA", "PERDIDA"])]
                g_gan = (g["resultado"] == "GANADA").sum()
                g_per = (g["resultado"] == "PERDIDA").sum()
                g_acierto = (g_gan / len(g_dec) * 100.0) if len(g_dec) else 0.0
                g_u = pd.to_numeric(g["unidades_ganadas"], errors="coerce").fillna(0.0).sum()
                g_roi = (g_u / len(g) * 100.0) if len(g) else 0.0
                agrupado_liga.append({
                    "Liga": l,
                    "Picks": len(g),
                    "Ganadas": int(g_gan),
                    "Perdidas": int(g_per),
                    "Acierto (%)": round(g_acierto, 1),
                    "Unidades": round(g_u, 2),
                    "ROI (%)": round(g_roi, 1),
                })
            st.dataframe(pd.DataFrame(agrupado_liga), hide_index=True, use_container_width=True)

    # ==========================================
    # TARJETAS DE PARTIDOS LIQUIDADOS
    # ==========================================
    st.write("")
    partidos_grupos = []
    for (f_val, ev_val, el_val), g_df in f_liq.sort_values(["fecha", "hora_cdmx"], ascending=[False, False]).groupby(
        ["fecha", "equipo_visitante", "equipo_local"], sort=False
    ):
        h_cdmx = g_df["hora_cdmx"].iloc[0] if "hora_cdmx" in g_df.columns else "12:00"
        mv = g_df["marcador_visitante"].iloc[0] if "marcador_visitante" in g_df.columns else None
        ml = g_df["marcador_local"].iloc[0] if "marcador_local" in g_df.columns else None
        l_nom = g_df["liga_nombre"].iloc[0] if "liga_nombre" in g_df.columns else "Fútbol"
        l_band = g_df["liga_bandera"].iloc[0] if "liga_bandera" in g_df.columns else "⚽"

        partidos_grupos.append({
            "fecha": f_val,
            "hora_cdmx": h_cdmx,
            "liga_nombre": l_nom,
            "liga_bandera": l_band,
            "equipo_visitante": ev_val,
            "equipo_local": el_val,
            "marcador_visitante": mv,
            "marcador_local": ml,
            "picks": g_df.to_dict(orient="records"),
            "unidades_totales": float(pd.to_numeric(g_df["unidades_ganadas"], errors="coerce").fillna(0.0).sum()),
        })

    total_partidos = len(partidos_grupos)
    max_tarjetas = 20
    st.subheader(f"⚽ Partidos Liquidados ({total_partidos} partidos · {n_eval} picks)")

    partidos_a_mostrar = partidos_grupos[:max_tarjetas]

    for p_partido in partidos_a_mostrar:
        mv = p_partido["marcador_visitante"]
        ml = p_partido["marcador_local"]
        mv_str = str(int(mv)) if pd.notna(mv) else "-"
        ml_str = str(int(ml)) if pd.notna(ml) else "-"
        u_partido = p_partido["unidades_totales"]
        color_bal = "#00e676" if u_partido > 0 else ("#ff4b44" if u_partido < 0 else "#8ba797")

        with st.container(border=True):
            card_hist_top = (
                f'<div class="card-top" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.65rem;">'
                f'<div>'
                f'<span class="badge-time" style="background: #092416; color: #00e676; border: 1px solid #00e676; font-weight: 800; padding: 0.2rem 0.55rem; border-radius: 6px; font-size: 0.75rem;">🏁 FINAL</span>'
                f'<span style="margin-left: 0.6rem; color: #8ba797; font-size: 0.82rem;">{p_partido["liga_bandera"]} {p_partido["liga_nombre"]} · 📅 {p_partido["fecha"]} · ⏰ {p_partido["hora_cdmx"]} CDMX</span>'
                f'</div>'
                f'<div>'
                f'<span style="font-size: 0.78rem; color: #8ba797; font-weight: 700; margin-right: 0.4rem;">BALANCE PARTIDO:</span>'
                f'<span style="font-weight: 900; font-size: 1rem; color: {color_bal};">{u_partido:+.2f} u</span>'
                f'</div>'
                f'</div>'
            )

            teams_hist = (
                f'<div class="teams-row" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; background: #0c1c14; padding: 0.65rem 1rem; border-radius: 10px; border: 1px solid #143524;">'
                f'<div>'
                f'<div class="team-name" style="font-size: 1.1rem; font-weight: 800; color: #ffffff;">{p_partido["equipo_visitante"]} <span style="color: #00e676; margin-left: 0.4rem; font-size: 1.35rem; font-weight: 900;">{mv_str}</span></div>'
                f'<div class="team-sub" style="font-size: 0.75rem; color: #8ba797;">Visitante</div>'
                f'</div>'
                f'<div style="font-size: 0.9rem; color: #00e676; font-weight: 900; letter-spacing: 0.08em; background: #06180e; border: 1px solid #00e676; padding: 0.2rem 0.6rem; border-radius: 6px;">FULL TIME</div>'
                f'<div style="text-align: right;">'
                f'<div class="team-name" style="font-size: 1.1rem; font-weight: 800; color: #ffffff;"><span style="color: #00e676; margin-right: 0.4rem; font-size: 1.35rem; font-weight: 900;">{ml_str}</span> {p_partido["equipo_local"]}</div>'
                f'<div class="team-sub" style="font-size: 0.75rem; color: #8ba797;">Local</div>'
                f'</div>'
                f'</div>'
            )

            st.markdown(card_hist_top + teams_hist, unsafe_allow_html=True)

            for p in p_partido["picks"]:
                resultado_pick = p.get("resultado")
                u_gan = p.get("unidades_ganadas")
                color_res = "#00e676" if resultado_pick == "GANADA" else ("#ff4b44" if resultado_pick == "PERDIDA" else "#ffd600")
                val_u_box = f"+{u_gan:.2f}" if (u_gan is not None and u_gan > 0) else ("-1.00" if resultado_pick == "PERDIDA" else f"{u_gan:.2f}" if u_gan is not None else "0.00")

                linea_info = f" · Línea: <b>{p.get('linea')}</b>" if (pd.notna(p.get("linea")) and float(p.get("linea", 0.0)) > 0) else ""

                pick_hist_box = (
                    f'<div class="pick-box" style="margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center; background: #091a12; border: 1px solid #143524; padding: 0.65rem 0.9rem; border-radius: 8px;">'
                    f'<div>'
                    f'<div class="pick-title" style="font-size: 0.76rem; color: #8ba797; font-weight: 700;">Recomendación ({p.get("mercado")}) · Confianza {p.get("confianza", "MEDIA")}</div>'
                    f'<div class="pick-sel" style="font-size: 1.05rem; font-weight: 900; color: #ffffff;">{p.get("seleccion")}</div>'
                    f'<div style="font-size: 0.8rem; color: #8ba797; margin-top: 0.2rem;">'
                    f'Cuota: <b>{p.get("cuota", 1.85):.2f}</b> · Prob. Modelo: <b>{float(p.get("probabilidad", 0.5))*100:.1f}%</b>{linea_info}'
                    f'</div>'
                    f'</div>'
                    f'<div style="text-align: right;">'
                    f'<div style="font-size: 0.72rem; color: #8ba797; font-weight: 700;">RESULTADO AUDITADO</div>'
                    f'<div style="font-size: 1.15rem; font-weight: 900; color: {color_res};">{resultado_pick} ({val_u_box} u)</div>'
                    f'</div>'
                    f'</div>'
                )
                st.markdown(pick_hist_box, unsafe_allow_html=True)

    if total_partidos > max_tarjetas:
        st.info(f"ℹ️ Mostrando las tarjetas de los {max_tarjetas} partidos más recientes de {total_partidos}. Utiliza los filtros superiores para aislar cualquier fecha o equipo específico.")

    # ==========================================
    # REGISTRO COMPLETO DE AUDITORÍA
    # ==========================================
    st.write("")
    st.subheader(f"📋 Registro Completo de Auditoría ({len(f_liq)} picks)")

    df_tabla = f_liq.sort_values(["fecha", "hora_cdmx"], ascending=[False, False]).copy()
    df_tabla["Partido"] = df_tabla["equipo_visitante"] + " @ " + df_tabla["equipo_local"]
    df_tabla["Marcador Final"] = df_tabla.apply(
        lambda r: f"{int(r['marcador_visitante'])} - {int(r['marcador_local'])}"
        if pd.notna(r.get("marcador_visitante")) and pd.notna(r.get("marcador_local"))
        else "N/D",
        axis=1
    )
    df_tabla["Cuota"] = df_tabla["cuota"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    df_tabla["Probabilidad"] = df_tabla["probabilidad"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
    df_tabla["Unidades Netas"] = df_tabla["unidades_ganadas"].apply(
        lambda x: f"+{x:.2f} u" if (pd.notna(x) and x > 0) else (f"{x:.2f} u" if pd.notna(x) else "0.00 u")
    )

    columnas_mostrar = [
        "fecha", "hora_cdmx", "liga_nombre", "Partido", "Marcador Final",
        "mercado", "seleccion", "Cuota", "Probabilidad", "confianza", "resultado", "Unidades Netas"
    ]
    renombres = {
        "fecha": "Fecha",
        "hora_cdmx": "Hora CDMX",
        "liga_nombre": "Liga",
        "mercado": "Mercado",
        "seleccion": "Selección",
        "confianza": "Confianza",
        "resultado": "Resultado",
    }
    cols_validas = [c for c in columnas_mostrar if c in df_tabla.columns]
    st.dataframe(
        df_tabla[cols_validas].rename(columns=renombres),
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "📥 Descargar Historial Completo (CSV)",
        df_tabla[cols_validas].rename(columns=renombres).to_csv(index=False),
        "futbol_auditoria_rendimiento.csv",
        "text/csv",
        key="btn_descarga_futbol_csv"
    )
