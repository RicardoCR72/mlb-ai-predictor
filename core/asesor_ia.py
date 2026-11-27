"""Módulo del Asesor Inteligente Overdog AI (Segundo Filtro Cuantitativo y Contextual).

Este módulo actúa como el analista jefe supervisor:
1. Extrae los candidatos pre-seleccionados por los modelos matemáticos (+EV, calibrados).
2. Aplica el 'Doble Filtro' contextual (riesgo de blowout, lesiones, correlación en combinadas).
3. Responde interactivamente a consultas del usuario ("¿Cuál es el más seguro?", "¿Qué parlay armar?").
4. Funciona tanto con la API de Gemini (modo conversacional profundo) como con el motor
   heurístico cuantitativo autónomo de Overdog (modo offline sin clave API).
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from core.constants import ZONA_CDMX
from core.filtro_top5 import (
    MERCADOS_PROPS_NBA_EXCLUIDOS_TOP5,
    TOP_N_PICKS,
    etiqueta_top,
    filtrar_top5_picks_dict,
)

RAIZ = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def _formatear_cuota(cuota_am: Any, cuota_dec: Any = None) -> str:
    """Normaliza la cuota para visualización; evita imprimir 'None' o 'nan'."""
    if cuota_am is not None and not (isinstance(cuota_am, float) and math.isnan(cuota_am)):
        s = str(cuota_am).strip()
        if s and s.lower() not in ("none", "nan", "nat"):
            return s
    try:
        d = float(cuota_dec)
        if math.isfinite(d) and d > 1.0:
            if abs(d - 2.0) < 1e-3:
                return "EVEN"
            if d > 2.0:
                return f"+{int(round((d - 1.0) * 100.0))}"
            return f"{int(round(-100.0 / (d - 1.0)))}"
    except (TypeError, ValueError):
        pass
    return "N/D"


# ==============================================================================
# 1. RECOLECTOR DE CANDIDATOS UNIFICADOS DEL DÍA
# ==============================================================================

def cargar_candidatos_hoy(fecha_objetivo: Optional[str] = None) -> Dict[str, Any]:
    """Carga y unifica las mejores oportunidades del día en NBA y NFL filtradas por fecha."""
    hoy_cdmx = str(fecha_objetivo or datetime.now(ZONA_CDMX).strftime("%Y-%m-%d"))[:10]
    resultado: Dict[str, Any] = {
        "nba_props": [],
        "nba_partidos": [],
        "nfl_props": [],
        "nfl_partidos": [],
        "resumen_texto": "",
        "total_candidatos": 0,
        "fecha_referencia": hoy_cdmx,
        "advertencias": [],
    }

    # 1. NBA Props Hoy (filtrado por fecha del día y probabilidad >= 52%)
    p_nba_props = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.parquet"
    if p_nba_props.exists():
        try:
            df_nba_p = pd.read_parquet(p_nba_props)
            if not df_nba_p.empty and "fecha" in df_nba_p.columns:
                fechas_str = df_nba_p["fecha"].astype(str).str[:10]
                df_hoy = df_nba_p[fechas_str == hoy_cdmx].copy()
                if df_hoy.empty:
                    ultima = fechas_str.dropna().max()
                    resultado["advertencias"].append(
                        f"NBA Props desactualizados: archivo con fecha máxima {ultima} (esperado {hoy_cdmx})."
                    )
                df_nba_p = df_hoy
            if not df_nba_p.empty and "stars" in df_nba_p.columns:
                top_nba = df_nba_p[df_nba_p["stars"].astype(str).str.strip() != "⚪"].copy()
                if "market" in top_nba.columns:
                    top_nba = top_nba[~top_nba["market"].astype(str).isin(MERCADOS_PROPS_NBA_EXCLUIDOS_TOP5)]
                if "model_prob" in top_nba.columns:
                    probs = pd.to_numeric(top_nba["model_prob"], errors="coerce").fillna(0.0)
                    top_nba = top_nba[probs >= 0.54]
                if "ev_pct" in top_nba.columns:
                    evs = pd.to_numeric(top_nba["ev_pct"], errors="coerce").fillna(0.0)
                    top_nba = top_nba[evs >= 2.0]
                for _, r in top_nba.iterrows():
                    resultado["nba_props"].append({
                        "deporte": "NBA",
                        "tipo": "PROP",
                        "jugador": r.get("player_name"),
                        "partido": r.get("game"),
                        "equipo": r.get("team"),
                        "mercado": r.get("market"),
                        "seleccion": f"{r.get('pick_type')} {r.get('line')}",
                        "linea": float(r.get("line") or 0.0),
                        "proyeccion": float(r.get("projection") or 0.0),
                        "probabilidad": float(r.get("model_prob") or 0.5),
                        "ev": float(r.get("ev_pct") or 0.0),
                        "cuota": _formatear_cuota(r.get("pick_odds_american"), r.get("pick_odds_decimal")),
                        "confianza": "ALTA" if float(r.get("model_prob") or 0.0) >= 0.57 else "MEDIA",
                        "tendencia": r.get("trend", ""),
                        "spread_juego": float(r.get("game_spread") or 0.0),
                    })
                resultado["nba_props"] = filtrar_top5_picks_dict(
                    resultado["nba_props"],
                    get_conf=lambda x: x.get("confianza"),
                    get_prob=lambda x: x.get("probabilidad"),
                    get_ev=lambda x: x.get("ev"),
                    get_id_unico=lambda x: x.get("jugador"),
                    limite=TOP_N_PICKS,
                    min_prob=0.54,
                    min_ev_pct=1.99,
                    confianzas_validas=("ALTA", "MEDIA"),
                )
        except Exception as err:
            logger.warning(f"Error leyendo NBA Props parquet: {err}")

    # 2. NBA Partidos Hoy (Moneyline / Spread, filtrado por fecha)
    p_nba_json = RAIZ / "data" / "nba" / "predictions" / "predicciones_nba_hoy.json"
    if p_nba_json.exists():
        try:
            with open(p_nba_json, "r", encoding="utf-8") as f:
                nba_games = json.load(f)
            fechas_json = [str(g.get("fecha_cdmx") or g.get("fecha") or "")[:10] for g in nba_games if isinstance(g, dict)]
            tiene_fechas = any(fechas_json)
            nba_games_hoy = [
                g for g in nba_games
                if not tiene_fechas or str(g.get("fecha_cdmx") or g.get("fecha") or "")[:10] == hoy_cdmx
            ]
            if tiene_fechas and nba_games and not nba_games_hoy:
                ultima_j = max(f for f in fechas_json if f)
                resultado["advertencias"].append(
                    f"NBA Partidos desactualizados: archivo con fecha máxima {ultima_j} (esperado {hoy_cdmx})."
                )
            for g in nba_games_hoy:
                cands = g.get("candidatos", [])
                for c in cands:
                    resultado["nba_partidos"].append({
                        "deporte": "NBA",
                        "tipo": "PARTIDO",
                        "partido": f"{g.get('equipo_visita')} @ {g.get('equipo_local')}",
                        "mercado": c.get("mercado"),
                        "seleccion": c.get("seleccion"),
                        "probabilidad": float(c.get("probabilidad") or 0.5),
                        "ev": float(c.get("ev") or 0.0) * 100.0,
                        "cuota": _formatear_cuota(c.get("cuota"), c.get("cuota_dec")),
                        "confianza": c.get("confianza", "MEDIA"),
                        "detalle": c.get("detalle", ""),
                    })
        except Exception as err:
            logger.warning(f"Error leyendo NBA Partidos json: {err}")

    # 3. NFL Props Hoy
    try:
        from nfl.persistence.props import obtener_conexion
        conn = obtener_conexion()
        if conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT p.*, jug.player_name 
                FROM nfl_proyecciones_props p
                LEFT JOIN nfl_jugadores jug ON p.id_jugador = jug.player_id
                WHERE p.estado_pick = 'CANDIDATO'
            """)
            rows = cur.fetchall()
            for r in rows:
                resultado["nfl_props"].append({
                    "deporte": "NFL",
                    "tipo": "PROP",
                    "jugador": r.get("player_name") or r.get("id_jugador"),
                    "partido": r.get("id_juego"),
                    "mercado": r.get("tipo_prop"),
                    "seleccion": f"{r.get('seleccion')} {r.get('linea')}",
                    "linea": float(r.get("linea") or 0.0),
                    "proyeccion": float(r.get("proyeccion") or 0.0),
                    "probabilidad": float(r.get("probabilidad_pick") or 0.5),
                    "ev": float(r.get("ev_estimado") or 0.0) * 100.0,
                    "cuota": _formatear_cuota(r.get("cuota_pick")),
                    "confianza": "ALTA",
                })
    except Exception as err:
        logger.debug(f"NFL Props MySQL no disponible (se usará fallback CSV): {err}")

    # Fallback NFL Props desde CSV si la base de datos está vacía
    if not resultado["nfl_props"]:
        dir_nfl_pred = RAIZ / "data" / "nfl" / "predictions"
        archivos_props_csv = sorted(dir_nfl_pred.glob("nfl_props_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
        for f_csv in archivos_props_csv:
            try:
                df_p = pd.read_csv(f_csv)
                if "estado_pick" in df_p.columns and "player_name" in df_p.columns:
                    cands_nfl = df_p[df_p["estado_pick"] == "CANDIDATO"]
                    for _, r in cands_nfl.iterrows():
                        resultado["nfl_props"].append({
                            "deporte": "NFL",
                            "tipo": "PROP",
                            "jugador": r.get("player_name"),
                            "partido": f"{r.get('team', '')} vs {r.get('opponent_team', '')}",
                            "mercado": r.get("tipo_prop"),
                            "seleccion": f"{r.get('seleccion', 'OVER')} {r.get('linea', 0.0)}",
                            "linea": float(r.get("linea") or 0.0),
                            "proyeccion": float(r.get("proyeccion") or 0.0),
                            "probabilidad": float(r.get("probabilidad_pick") or 0.55),
                            "ev": float(r.get("ev_estimado") or 0.0) * 100.0,
                            "cuota": _formatear_cuota(r.get("cuota_pick")),
                            "confianza": "ALTA",
                        })
                    if resultado["nfl_props"]:
                        break
            except Exception as err:
                logger.warning(f"Error leyendo NFL Props CSV {f_csv.name}: {err}")

    # 4. NFL Partidos Hoy (Moneyline y Spread)
    p_nfl_ml = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_moneyline.parquet"
    if p_nfl_ml.exists():
        try:
            df_nfl_ml = pd.read_parquet(p_nfl_ml)
            # Soporte para ambas estructuras (antigua con away_team y actual con partido)
            if "confianza" in df_nfl_ml.columns and "partido" in df_nfl_ml.columns:
                recs_ml = df_nfl_ml[(df_nfl_ml["confianza"] == "ALTA") | (df_nfl_ml.get("edge", 0) > 0.04)]
                for _, r in recs_ml.head(6).iterrows():
                    resultado["nfl_partidos"].append({
                        "deporte": "NFL",
                        "tipo": "PARTIDO",
                        "partido": r.get("partido"),
                        "mercado": "Moneyline",
                        "seleccion": r.get("seleccion"),
                        "probabilidad": float(r.get("probabilidad_pick") or 0.6),
                        "ev": float(r.get("ev_estimado") or 0.0) * 100.0,
                        "cuota": _formatear_cuota(r.get("cuota_pick")),
                        "confianza": str(r.get("confianza", "ALTA")),
                    })
            elif "recomendar" in df_nfl_ml.columns:
                recs = df_nfl_ml[df_nfl_ml["recomendar"] == True]
                for _, r in recs.iterrows():
                    resultado["nfl_partidos"].append({
                        "deporte": "NFL",
                        "tipo": "PARTIDO",
                        "partido": f"{r.get('away_team')} @ {r.get('home_team')}",
                        "mercado": "Moneyline",
                        "seleccion": f"{r.get('pick')} ML",
                        "probabilidad": float(r.get("prob_ganar") or 0.6),
                        "ev": float(r.get("ev") or 0.0) * 100.0,
                        "cuota": _formatear_cuota(r.get("cuota_americana")),
                        "confianza": "ALTA",
                    })
        except Exception as err:
            logger.warning(f"Error leyendo NFL Moneyline parquet: {err}")

    # 5. NFL Spreads Calibrados
    p_nfl_spread = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_spread.parquet"
    if p_nfl_spread.exists():
        try:
            df_nfl_sp = pd.read_parquet(p_nfl_spread)
            if "recomendar" in df_nfl_sp.columns:
                recs_sp = df_nfl_sp[df_nfl_sp["recomendar"] == True]
                for _, r in recs_sp.iterrows():
                    resultado["nfl_partidos"].append({
                        "deporte": "NFL",
                        "tipo": "PARTIDO",
                        "partido": f"{r.get('away_team')} @ {r.get('home_team')}",
                        "mercado": f"Spread ({r.get('linea_pick', '')})",
                        "seleccion": f"{r.get('pick')} {r.get('linea_pick', '')}",
                        "probabilidad": float(r.get("prob_seleccion") or 0.54),
                        "ev": float(r.get("ev_esperado_pct") or 0.0),
                        "cuota": "-110",
                        "confianza": "ALTA",
                    })
        except Exception as err:
            logger.warning(f"Error leyendo NFL Spread parquet: {err}")

    # Aplicar filtro Top 5 más confiables con +EV en NBA Partidos, NFL Props y NFL Partidos
    resultado["nba_partidos"] = filtrar_top5_picks_dict(
        resultado["nba_partidos"],
        get_conf=lambda x: x.get("confianza"),
        get_prob=lambda x: x.get("probabilidad"),
        get_ev=lambda x: x.get("ev"),
        get_id_unico=lambda x: x.get("partido"),
        limite=TOP_N_PICKS,
        min_prob=0.53,
        min_ev=0.0,
        confianzas_validas=("ALTA", "MEDIA"),
    )
    resultado["nfl_props"] = filtrar_top5_picks_dict(
        resultado["nfl_props"],
        get_conf=lambda x: x.get("confianza"),
        get_prob=lambda x: x.get("probabilidad"),
        get_ev=lambda x: x.get("ev"),
        get_id_unico=lambda x: x.get("jugador"),
        limite=TOP_N_PICKS,
        min_prob=0.53,
        min_ev=0.0,
        confianzas_validas=("ALTA", "MEDIA"),
    )
    resultado["nfl_partidos"] = filtrar_top5_picks_dict(
        resultado["nfl_partidos"],
        get_conf=lambda x: x.get("confianza"),
        get_prob=lambda x: x.get("probabilidad"),
        get_ev=lambda x: x.get("ev"),
        get_id_unico=lambda x: f"{x.get('partido')}_{x.get('mercado')}",
        limite=TOP_N_PICKS,
        min_prob=0.53,
        min_ev=0.0,
        confianzas_validas=("ALTA", "MEDIA"),
    )

    total_cands = (
        len(resultado["nba_props"])
        + len(resultado["nba_partidos"])
        + len(resultado["nfl_props"])
        + len(resultado["nfl_partidos"])
    )
    resultado["total_candidatos"] = total_cands

    # Construir resumen en texto formateado para el contexto del LLM (solo Top 5 por categoría)
    lineas_resumen = []
    lineas_resumen.append(f"### TOP SELECCIONES DE ALTA CONFIANZA EN OVERDOG SPORTS AI ({total_cands} opciones filtradas):")

    if resultado["nba_props"]:
        lineas_resumen.append("\n🏀 [NBA - TOP 5 PROPS DE JUGADORES CALIBRADOS]:")
        for idx, p in enumerate(resultado["nba_props"][:TOP_N_PICKS]):
            lineas_resumen.append(
                f"- {etiqueta_top(idx + 1)} {p['jugador']} ({p['equipo']}) · {p['mercado']}: {p['seleccion']} | Proy: {p['proyeccion']} "
                f"| Prob: {p['probabilidad']*100:.1f}% | EV: {p['ev']:+.1f}% | Cuota: {p['cuota']} | Spread partido: {p['spread_juego']}"
            )

    if resultado["nba_partidos"]:
        lineas_resumen.append("\n🏀 [NBA - TOP 5 MONEYLINE Y SPREAD]:")
        for idx, m in enumerate(resultado["nba_partidos"][:TOP_N_PICKS]):
            lineas_resumen.append(
                f"- {etiqueta_top(idx + 1)} {m['partido']} · {m['mercado']}: {m['seleccion']} | Prob: {m['probabilidad']*100:.1f}% | EV: {m['ev']:+.1f}% | Cuota: {m['cuota']} ({m['confianza']})"
            )

    if resultado["nfl_props"]:
        lineas_resumen.append("\n🏈 [NFL - TOP 5 PROPS DE JUGADORES CALIBRADOS]:")
        for idx, p in enumerate(resultado["nfl_props"][:TOP_N_PICKS]):
            lineas_resumen.append(
                f"- {etiqueta_top(idx + 1)} {p['jugador']} · {p['mercado']}: {p['seleccion']} | Proy: {p['proyeccion']} "
                f"| Prob: {p['probabilidad']*100:.1f}% | EV: {p['ev']:+.1f}% | Cuota: {p['cuota']}"
            )

    if resultado["nfl_partidos"]:
        lineas_resumen.append("\n🏈 [NFL - TOP 5 MONEYLINE Y SPREAD]:")
        for idx, m in enumerate(resultado["nfl_partidos"][:TOP_N_PICKS]):
            lineas_resumen.append(
                f"- {etiqueta_top(idx + 1)} {m['partido']} · {m['mercado']}: {m['seleccion']} | Prob: {m['probabilidad']*100:.1f}% | EV: {m['ev']:+.1f}% | Cuota: {m['cuota']}"
            )

    resultado["resumen_texto"] = "\n".join(lineas_resumen)
    return resultado


# ==============================================================================
# 2. MOTOR DE SELECCIÓN CUANTITATIVA (DOBLE FILTRO DETERMINÍSTICO)
# ==============================================================================

def seleccionar_candado_oficial(candidatos_dict: Dict[str, Any], deporte: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Aplica el 'Doble Filtro' para elegir el pick #1 de máxima seguridad y menor varianza."""
    if deporte == "NFL":
        todos = candidatos_dict.get("nfl_props", []) + candidatos_dict.get("nfl_partidos", [])
    elif deporte == "NBA":
        todos = candidatos_dict.get("nba_props", []) + candidatos_dict.get("nba_partidos", [])
    else:
        todos = (
            candidatos_dict.get("nba_props", [])
            + candidatos_dict.get("nfl_props", [])
            + candidatos_dict.get("nba_partidos", [])
            + candidatos_dict.get("nfl_partidos", [])
        )
    if not todos:
        return None

    def _score_seguridad(c: Dict[str, Any]) -> float:
        score = 0.0
        prob = float(c.get("probabilidad") or 0.5)
        ev = float(c.get("ev") or 0.0)
        
        # 1. Base por probabilidad matemática pura (mayor probabilidad = menor varianza)
        score += prob * 100.0  # Ej. 58% -> 58 pts
        
        # 2. Bonificación por EV positivo equilibrado
        score += min(ev, 10.0) * 1.5
        
        # 3. Bonificación por Top Picks oficiales
        if c.get("estrellas") == "⭐⭐⭐":
            score += 25.0
        elif c.get("estrellas") == "⭐⭐":
            score += 10.0
            
        # 4. Bonificación por mercado estable (Rebotes y Yardas terrestres son los más consistentes)
        m = str(c.get("mercado", "")).lower()
        if "rebound" in m or "rebote" in m:
            score += 8.0
        elif "rushing" in m or "carrera" in m:
            score += 6.0
        elif "assist" in m or "asistencia" in m:
            score -= 5.0  # Penalización por volatilidad de tiro ajeno
            
        # 5. Penalización por riesgo de paliza/blowout en la NBA (spread >= 9.5)
        spread = float(c.get("spread_juego") or 0.0)
        if spread >= 10.0 and "OVER" in str(c.get("seleccion", "")).upper():
            score -= 12.0

        return score

    candidatos_ordenados = sorted(todos, key=_score_seguridad, reverse=True)
    return candidatos_ordenados[0] if candidatos_ordenados else None


def construir_parlay_seguro(candidatos_dict: Dict[str, Any], n_patas: int = 2, deporte: Optional[str] = None) -> List[Dict[str, Any]]:
    """Construye un parlay de máxima seguridad con patas descorrelacionadas."""
    if deporte == "NFL":
        todos = candidatos_dict.get("nfl_props", []) + candidatos_dict.get("nfl_partidos", [])
    elif deporte == "NBA":
        todos = candidatos_dict.get("nba_props", []) + candidatos_dict.get("nba_partidos", [])
    else:
        todos = (
            candidatos_dict.get("nba_props", [])
            + candidatos_dict.get("nba_partidos", [])
            + candidatos_dict.get("nfl_props", [])
            + candidatos_dict.get("nfl_partidos", [])
        )
    if len(todos) < n_patas:
        return todos

    # Filtrar solo picks con probabilidad >= 53.5%
    alta_prob = [c for c in todos if float(c.get("probabilidad") or 0.0) >= 0.535]
    if len(alta_prob) < n_patas:
        alta_prob = todos

    # Ordenar por probabilidad descendente
    alta_prob_sort = sorted(alta_prob, key=lambda x: float(x.get("probabilidad") or 0.0), reverse=True)

    patas_elegidas = []
    juegos_usados = set()
    jugadores_usados = set()

    for cand in alta_prob_sort:
        partido = cand.get("partido") or cand.get("equipo")
        jugador = cand.get("jugador")

        # Regla 1: Máximo 1 selección por partido (evita correlación negativa o colapso conjunto)
        if partido and partido in juegos_usados:
            continue
        # Regla 2: Máximo 1 selección por jugador
        if jugador and jugador in jugadores_usados:
            continue

        patas_elegidas.append(cand)
        if partido:
            juegos_usados.add(partido)
        if jugador:
            jugadores_usados.add(jugador)

        if len(patas_elegidas) >= n_patas:
            break

    return patas_elegidas


# ==============================================================================
# 3. INTERFAZ DE CONSULTA INTELIGENTE (LLM O HEURÍSTICO)
# ==============================================================================

PROMPT_SISTEMA_ASESOR = """Eres el ASESOR CUANTITATIVO JEFE de "OVERDOG SPORTS AI".
Tu misión es actuar como el segundo filtro analítico y supervisor crítico de las selecciones deportivas del día.

REGLAS INSTITUCIONALES OBLIGATORIAS:
1. ENFOQUE Y VOCABULARIO:
   - Mantén un tono periodístico, analítico y cuantitativo (ciencia de datos y valor esperado +EV).
   - Vocabulario PROHIBIDO: apuesta, apostar, parlay (usa 'combinada'), momio (usa 'cuota'), dinero, lock, fija.
   - Vocabulario OFICIAL: 'proyección', 'pronóstico', 'tendencia', 'probabilidad', 'margen de valor', 'combinada de baja varianza', 'candado estadístico'.

2. REGLA DE ORO DE VERACIDAD (TOLERANCIA CERO A ALUCINACIONES):
   - SOLO puedes recomendar selecciones que figuren explícitamente en el bloque de CANDIDATOS ACTIVOS provisto en el contexto.
   - NUNCA inventes jugadores, líneas o partidos que no estén en la lista. Si te preguntan por un partido que no tiene candidato, dilo con honestidad: "Nuestros modelos matemáticos no encontraron margen de valor suficiente en ese encuentro".

3. CRITERIO DE SELECCIÓN PARA "EL MÁS SEGURO" (EL CANDADO):
   - Debe ser la opción con mayor probabilidad empírica (>= 55%), EV positivo comprobado y menor riesgo de factores externos (ej. evitar Overs en partidos con riesgo de paliza o minutos limitados).

4. ESTRUCTURA DE RESPUESTA:
   - Directa, concisa y elegante.
   - Explica el POR QUÉ matemático (Línea vs Proyección calibrada) y el POR QUÉ cualitativo (defensa rival, rol consolidado).
"""

def obtener_gemini_api_key() -> Optional[str]:
    """Obtiene la clave de API de Gemini desde variables de entorno, Streamlit secrets o archivo local secrets.toml."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key:
        return key.strip().rstrip(".")
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")
            if key:
                return str(key).strip().rstrip(".")
    except Exception as err:
        logger.debug(f"No se pudo leer st.secrets: {err}")
    
    # Lectura directa de .streamlit/secrets.toml
    try:
        sec_path = RAIZ / ".streamlit" / "secrets.toml"
        if sec_path.exists():
            for line in sec_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY") or line.startswith("gemini_api_key"):
                    partes = line.split("=", 1)
                    if len(partes) == 2:
                        val = partes[1].strip().strip('"').strip("'").rstrip(".")
                        if val:
                            return val
    except Exception as err:
        logger.warning(f"Error leyendo secrets.toml local: {err}")
    return None


def _construir_respuesta_determinista(pregunta: str, candidatos: Dict[str, Any]) -> Tuple[str, bool]:
    """Evalúa intención/deporte de forma determinista y retorna (texto_respuesta, hay_candidatos)."""
    pregunta_norm = pregunta.lower().strip()
    pregunta_limpia = pregunta_norm.replace("doble filtro", "")

    deporte_filtro = None
    if "nfl" in pregunta_norm and "nba" not in pregunta_norm:
        deporte_filtro = "NFL"
    elif "nba" in pregunta_norm and "nfl" not in pregunta_norm:
        deporte_filtro = "NBA"

    es_combinada = any(k in pregunta_limpia for k in ["parlay", "combinada", "patas", "combinar", "combinadas", "parleys"])
    es_candado = any(k in pregunta_limpia for k in ["mas seguro", "más seguro", "candado", "el mas seguro", "el más seguro", "firme", "seguro del dia", "seguro del día"])
    es_consulta_nfl = ("nfl" in pregunta_norm) and not es_candado and not es_combinada
    es_consulta_nba = ("nba" in pregunta_norm) and not es_candado and not es_combinada

    advs = [a for a in candidatos.get("advertencias", []) if not deporte_filtro or deporte_filtro in a]
    nota_adv = ("\n\n⚠️ *Aviso de frescura:* " + " ".join(advs)) if advs else ""

    # Prioridad 1: Solicitud de Combinada / Parlay (2 o más patas)
    if es_combinada:
        patas = construir_parlay_seguro(candidatos, n_patas=2, deporte=deporte_filtro)
        if len(patas) < 2:
            dep_msg = f" en {deporte_filtro}" if deporte_filtro else ""
            return (
                f"⚡ **Combinada de Baja Varianza · Overdog Sports AI:**\n\n"
                f"Para hoy la base de datos no registra al menos 2 selecciones independientes calificadas{dep_msg} "
                f"para armar una combinada de baja varianza.{nota_adv}",
                False,
            )

        texto_patas = []
        cuota_combinada = 1.0
        prob_conjunta = 1.0
        for i, p in enumerate(patas, 1):
            nom = p.get("jugador") or p.get("partido")
            prob_conjunta *= float(p["probabilidad"])
            odds_str = _formatear_cuota(p.get("cuota"))
            try:
                odds_val = float(odds_str)
                dec = 1.0 + (odds_val / 100 if odds_val > 0 else 100 / abs(odds_val))
            except Exception:
                dec = 1.91
            cuota_combinada *= dec
            texto_patas.append(
                f"**Pata {i}:** {nom} · **{p['seleccion']}** ({p['mercado']} · {p.get('deporte', '')})\n"
                f"   - Probabilidad individual: {p['probabilidad']*100:.1f}% | Cuota: {odds_str}"
            )

        patas_str = "\n\n".join(texto_patas)
        deporte_tag = f" ({deporte_filtro})" if deporte_filtro else ""
        return (
            f"🎯 **Combinada de Baja Varianza (2 Patas){deporte_tag} · Overdog Sports AI**\n\n"
            f"{patas_str}\n\n"
            f"📈 **Probabilidad Conjunta Estimada:** {prob_conjunta*100:.1f}%\n"
            f"💵 **Cuota Decimal Estimada:** {cuota_combinada:.2f}\n\n"
            f"🛡️ **Control de Riesgo Cuantitativo:**\n"
            f"Ambas patas pertenecen a selecciones independientes para evitar contaminación de rendimiento y correlaciones negativas.",
            True,
        )

    # Prioridad 2: Consulta del Candado / Más Seguro Individual
    if es_candado or any(k in pregunta_norm for k in ["seguro", "candado", "firme"]):
        candado = seleccionar_candado_oficial(candidatos, deporte=deporte_filtro)
        if not candado:
            dep_msg = f" para {deporte_filtro}" if deporte_filtro else ""
            return (
                f"⚡ **Análisis de Overdog Sports AI:**\n\n"
                f"En este momento no hay selecciones vigentes con margen de valor estadístico de alta convicción{dep_msg}. "
                f"Los modelos recomiendan esperar a la actualización oficial de cartelera y líneas.{nota_adv}",
                False,
            )

        jugador_txt = f"**{candado['jugador']}** ({candado.get('equipo', '')})" if candado.get("jugador") else f"**{candado['partido']}**"
        cuota_txt = _formatear_cuota(candado.get("cuota"))
        return (
            f"⚡ **El Candado del Día · Overdog Sports AI**\n\n"
            f"🎯 **Selección:** {jugador_txt} · **{candado['seleccion']}**\n"
            f"📊 **Mercado:** {candado['mercado']} | **Deporte:** {candado['deporte']}\n"
            f"📈 **Probabilidad del Modelo:** {candado['probabilidad']*100:.1f}%\n"
            f"💎 **Margen de Valor (EV):** {candado['ev']:+.1f}%\n"
            f"🎯 **Cuota:** {cuota_txt}\n\n"
            f"🔍 **Doble Filtro Cuantitativo:**\n"
            f"Esta selección superó tanto el Shrinkage Bayesiano como la prueba de varianza. "
            f"Presenta una sólida consistencia en sus últimos partidos y un emparejamiento favorable sin riesgo severo de reducción de minutos.",
            True,
        )

    # Prioridad 3: Consulta general de NFL
    if es_consulta_nfl or "nfl" in pregunta_norm:
        props = candidatos.get("nfl_props", [])
        partidos = candidatos.get("nfl_partidos", [])
        items = []
        for p in props[:4]:
            items.append(f"- **{p['jugador']}** · {p['seleccion']} ({p['mercado']}) | Prob: {p['probabilidad']*100:.1f}% | EV: {p.get('ev', 0):+.1f}% | Cuota: {_formatear_cuota(p.get('cuota'))}")
        for m in partidos[:3]:
            items.append(f"- **{m['partido']}** · {m['seleccion']} | Prob: {m['probabilidad']*100:.1f}% | EV: {m.get('ev', 0):+.1f}% | Cuota: {_formatear_cuota(m.get('cuota'))}")

        if not items:
            return f"🏈 **NFL:** No hay selecciones oficiales activas para la cartelera NFL de hoy.{nota_adv}", False
        return "🏈 **Top Selecciones NFL de Hoy:**\n\n" + "\n".join(items) + "\n\n*Todas filtradas con el protocolo de 9 candados defensivos y Shrinkage Bayesiano.*", True

    # Prioridad 4: Consulta general de NBA
    if es_consulta_nba or "nba" in pregunta_norm:
        props = candidatos.get("nba_props", [])
        partidos = candidatos.get("nba_partidos", [])
        items = []
        for p in props[:4]:
            items.append(f"- **{p['jugador']}** ({p.get('equipo', '')}) · {p['seleccion']} ({p['mercado']}) | Proy: {p.get('proyeccion', '')} | Prob: {p['probabilidad']*100:.1f}% | EV: {p.get('ev', 0):+.1f}% | Cuota: {_formatear_cuota(p.get('cuota'))}")
        for m in partidos[:3]:
            items.append(f"- **{m['partido']}** · {m['seleccion']} | Prob: {m['probabilidad']*100:.1f}% | EV: {m.get('ev', 0):+.1f}% | Cuota: {_formatear_cuota(m.get('cuota'))}")

        if not items:
            return f"🏀 **NBA:** No hay selecciones oficiales activas para hoy en la cartelera NBA.{nota_adv}", False
        return "🏀 **Top Selecciones NBA de Hoy:**\n\n" + "\n".join(items) + "\n\n*Todas cuentan con proyección cuantitativa desacoplada y Shrinkage 60/40.*", True

    # General / bienvenida / consulta libre
    candado = seleccionar_candado_oficial(candidatos)
    if not candado:
        return (
            f"👋 **Hola, soy el Asesor Cuantitativo de Overdog Sports AI.**\n\n"
            f"No hay selecciones vigentes calificadas para la fecha actual ({candidatos.get('fecha_referencia', '')}).{nota_adv}",
            False,
        )
    nombre_cand = f"{candado.get('jugador') or candado.get('partido')} · {candado['seleccion']} ({candado['deporte']})"
    return (
        f"👋 **Hola, soy el Asesor Cuantitativo de Overdog Sports AI.**\n\n"
        f"Estoy monitoreando las predicciones calibradas vigentes.\n"
        f"Actualmente la selección de mayor solidez estadística es: **{nombre_cand}** (Prob: {candado['probabilidad']*100:.1f}%, Cuota: {_formatear_cuota(candado.get('cuota'))}).\n\n"
        f"Puedes preguntarme:\n"
        f"• *'¿Cuál es el partido o pick más seguro del día?'*\n"
        f"• *'Dame una combinada (parlay) segura de 2 selecciones.'*\n"
        f"• *'¿Qué oportunidades hay en la NBA o NFL hoy?'*",
        True,
    )


def responder_consulta_asesor(
    pregunta: str,
    candidatos: Optional[Dict[str, Any]] = None,
    historial: Optional[List[Dict[str, str]]] = None,
    api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Procesa la pregunta del usuario con selección determinista y redacción opcional vía Gemini."""
    if candidatos is None:
        candidatos = cargar_candidatos_hoy()

    # 1. Selección determinista estricta (evita cambio de deporte o alucinaciones del LLM)
    texto_determinista, hay_candidatos = _construir_respuesta_determinista(pregunta, candidatos)
    if not hay_candidatos:
        return texto_determinista

    # Resolver API Key (si se pasa "" explícitamente, desactiva Gemini para modo offline determinista)
    if gemini_api_key == "" or api_key == "":
        key = None
    else:
        raw_key = gemini_api_key or api_key or obtener_gemini_api_key()
        key = str(raw_key).strip().rstrip(".") if raw_key else None

    # MODO 1: Si hay API Key de Gemini, el LLM redacta únicamente sobre la selección ya validada
    if key:
        modelos_disponibles = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]
        contexto_completo = (
            f"{PROMPT_SISTEMA_ASESOR}\n\n"
            f"REGLA ESTRICTA ADICIONAL:\n"
            f"- Debes basar tu respuesta EXCLUSIVAMENTE en la SELECCIÓN VALIDADA POR EL MOTOR CUANTITATIVO abajo.\n"
            f"- Prohibido cambiar de deporte, sustituir jugadores/partidos o inventar líneas.\n\n"
            f"--- SELECCIÓN VALIDADA POR EL MOTOR CUANTITATIVO ({candidatos.get('fecha_referencia', '')}) ---\n"
            f"{texto_determinista}\n"
            f"----------------------------------------------------------------"
        )

        contenido_parts = [{"text": contexto_completo}]
        if historial:
            for h in historial[-4:]:
                contenido_parts.append({"text": f"{h.get('role', 'user').upper()}: {h.get('content', '')}"})

        contenido_parts.append({"text": f"USUARIO: {pregunta}\nASESOR OVERDOG AI:"})

        payload = {
            "contents": [{"parts": contenido_parts}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 900,
            }
        }
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

        for modelo in modelos_disponibles:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
                resp = requests.post(url, json=payload, headers=headers, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    cands = data.get("candidates", [])
                    if cands and "content" in cands[0] and "parts" in cands[0]["content"]:
                        texto = cands[0]["content"]["parts"][0].get("text", "")
                        if texto.strip():
                            return texto
                else:
                    logger.warning(f"Gemini ({modelo}) respondió status {resp.status_code}")
            except Exception as err:
                logger.warning(f"Fallo consultando Gemini ({modelo}): {err}")
                continue

    return texto_determinista
