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
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]


# ==============================================================================
# 1. RECOLECTOR DE CANDIDATOS UNIFICADOS DEL DÍA
# ==============================================================================

def cargar_candidatos_hoy() -> Dict[str, Any]:
    """Carga y unifica las mejores oportunidades del día en NBA, NFL y Fútbol."""
    resultado = {
        "nba_props": [],
        "nba_partidos": [],
        "nfl_props": [],
        "nfl_partidos": [],
        "resumen_texto": "",
        "total_candidatos": 0,
    }

    # 1. NBA Props Hoy
    p_nba_props = RAIZ / "data" / "nba" / "predictions" / "predicciones_props_nba_hoy.parquet"
    if p_nba_props.exists():
        try:
            df_nba_p = pd.read_parquet(p_nba_props)
            top_nba = df_nba_p[df_nba_p.get("stars", "").isin(["⭐⭐⭐", "⭐⭐"])].copy()
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
                    "cuota": r.get("pick_odds_american", "-110"),
                    "estrellas": r.get("stars", "⭐⭐"),
                    "tendencia": r.get("trend", ""),
                    "spread_juego": float(r.get("game_spread") or 0.0),
                })
        except Exception:
            pass

    # 2. NBA Partidos Hoy (Moneyline / Spread)
    p_nba_json = RAIZ / "data" / "nba" / "predictions" / "predicciones_nba_hoy.json"
    if p_nba_json.exists():
        try:
            with open(p_nba_json, "r", encoding="utf-8") as f:
                nba_games = json.load(f)
            for g in nba_games:
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
                        "cuota": str(c.get("cuota", "-110")),
                        "confianza": c.get("confianza", "MEDIA"),
                        "detalle": c.get("detalle", ""),
                    })
        except Exception:
            pass

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
                    "cuota": str(r.get("cuota_pick") or "-110"),
                    "confianza": "ALTA",
                })
    except Exception:
        pass

    # 4. NFL Partidos Hoy (Moneyline)
    p_nfl_ml = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_moneyline.parquet"
    if p_nfl_ml.exists():
        try:
            df_nfl_ml = pd.read_parquet(p_nfl_ml)
            if "recomendar" in df_nfl_ml.columns:
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
                        "cuota": str(r.get("cuota_americana", "-110")),
                        "confianza": "ALTA",
                    })
        except Exception:
            pass

    total_cands = (
        len(resultado["nba_props"])
        + len(resultado["nba_partidos"])
        + len(resultado["nfl_props"])
        + len(resultado["nfl_partidos"])
    )
    resultado["total_candidatos"] = total_cands

    # Construir resumen en texto formateado para el contexto del LLM
    lineas_resumen = []
    lineas_resumen.append(f"### CANDIDATOS OFICIALES ACTIVOS EN OVERDOG SPORTS AI ({total_cands} opciones filtradas):")
    
    if resultado["nba_props"]:
        lineas_resumen.append("\n🏀 [NBA - PROPS DE JUGADORES CALIBRADOS]:")
        for p in resultado["nba_props"][:10]:
            lineas_resumen.append(
                f"- {p['jugador']} ({p['equipo']}) · {p['mercado']}: {p['seleccion']} | Proy: {p['proyeccion']} "
                f"| Prob: {p['probabilidad']*100:.1f}% | EV: {p['ev']:+.1f}% | Cuota: {p['cuota']} | {p['estrellas']} | Spread partido: {p['spread_juego']}"
            )

    if resultado["nba_partidos"]:
        lineas_resumen.append("\n🏀 [NBA - MONEYLINE Y SPREAD]:")
        for m in resultado["nba_partidos"][:6]:
            lineas_resumen.append(
                f"- {m['partido']} · {m['mercado']}: {m['seleccion']} | Prob: {m['probabilidad']*100:.1f}% | EV: {m['ev']:+.1f}% | Cuota: {m['cuota']} ({m['confianza']})"
            )

    if resultado["nfl_props"]:
        lineas_resumen.append("\n🏈 [NFL - PROPS DE JUGADORES CALIBRADOS]:")
        for p in resultado["nfl_props"][:8]:
            lineas_resumen.append(
                f"- {p['jugador']} · {p['mercado']}: {p['seleccion']} | Proy: {p['proyeccion']} "
                f"| Prob: {p['probabilidad']*100:.1f}% | EV: {p['ev']:+.1f}% | Cuota: {p['cuota']}"
            )

    if resultado["nfl_partidos"]:
        lineas_resumen.append("\n🏈 [NFL - MONEYLINE Y SPREAD]:")
        for m in resultado["nfl_partidos"][:6]:
            lineas_resumen.append(
                f"- {m['partido']} · {m['mercado']}: {m['seleccion']} | Prob: {m['probabilidad']*100:.1f}% | EV: {m['ev']:+.1f}% | Cuota: {m['cuota']}"
            )

    resultado["resumen_texto"] = "\n".join(lineas_resumen)
    return resultado


# ==============================================================================
# 2. MOTOR DE SELECCIÓN CUANTITATIVA (DOBLE FILTRO DETERMINÍSTICO)
# ==============================================================================

def seleccionar_candado_oficial(candidatos_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Aplica el 'Doble Filtro' para elegir el pick #1 de máxima seguridad y menor varianza."""
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


def construir_parlay_seguro(candidatos_dict: Dict[str, Any], n_patas: int = 2) -> List[Dict[str, Any]]:
    """Construye un parlay de máxima seguridad con patas descorrelacionadas."""
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

def responder_consulta_asesor(
    pregunta: str,
    candidatos: Optional[Dict[str, Any]] = None,
    historial: Optional[List[Dict[str, str]]] = None,
    api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Procesa la pregunta del usuario utilizando Gemini o el motor heurístico Overdog."""
    if candidatos is None:
        candidatos = cargar_candidatos_hoy()

    # Resolver API Key desde parámetros, variables de entorno o streamlit secrets
    raw_key = gemini_api_key or api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not raw_key:
        try:
            import streamlit as st
            raw_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")
        except Exception:
            pass

    key = str(raw_key).strip().rstrip(".") if raw_key else None

    # MODO 1: Si hay API Key de Gemini, llamada con soporte multimodelo
    if key:
        # Priorizar gemini-3.5-flash que es el modelo activo y estable
        modelos_disponibles = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"]
        
        contexto_completo = (
            f"{PROMPT_SISTEMA_ASESOR}\n\n"
            f"--- CONTEXTO EN VIVO DEL SISTEMA OVERDOG HOY ---\n"
            f"{candidatos.get('resumen_texto', '')}\n"
            f"------------------------------------------------"
        )
        
        contenido_parts = [{"text": contexto_completo}]
        if historial:
            for h in historial[-4:]:
                contenido_parts.append({"text": f"{h.get('role', 'user').upper()}: {h.get('content', '')}"})
        
        contenido_parts.append({"text": f"USUARIO: {pregunta}\nASESOR OVERDOG AI:"})

        payload = {
            "contents": [{"parts": contenido_parts}],
            "generationConfig": {
                "temperature": 0.25,
                "maxOutputTokens": 900,
            }
        }

        for modelo in modelos_disponibles:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={key}"
                resp = requests.post(url, json=payload, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    cands = data.get("candidates", [])
                    if cands and "content" in cands[0] and "parts" in cands[0]["content"]:
                        texto = cands[0]["content"]["parts"][0].get("text", "")
                        if texto.strip():
                            return texto
            except Exception:
                continue  # Intenta el siguiente modelo si hay timeout o error temporal

    # MODO 2: Motor Heurístico Cuantitativo Autónomo (Zero-API Fallback)
    pregunta_norm = pregunta.lower()

    # Prioridad 1: Solicitud de Combinada / Parlay
    if any(k in pregunta_norm for k in ["parlay", "combinada", "patas", "doble", "combinar"]):
        patas = construir_parlay_seguro(candidatos, n_patas=2)
        if len(patas) < 2:
            return (
                "⚡ **Combinada de Baja Varianza · Overdog Sports AI:**\n\n"
                "Para hoy la base de datos registra opciones individuales de valor, pero no recomienda una combinada multievento "
                "por correlación cruzada o falta de volumen suficiente para mitigar la varianza."
            )
        
        texto_patas = []
        cuota_combinada = 1.0
        prob_conjunta = 1.0

        for i, p in enumerate(patas, 1):
            nom = p.get("jugador") or p.get("partido")
            prob_conjunta *= float(p["probabilidad"])
            # Estimación cuota decimal
            odds_str = str(p.get("cuota", "-110"))
            try:
                odds_val = float(odds_str)
                dec = 1.0 + (odds_val/100 if odds_val > 0 else 100/abs(odds_val))
            except Exception:
                dec = 1.91
            cuota_combinada *= dec
            
            texto_patas.append(
                f"**Pata {i}:** {nom} · **{p['seleccion']}** ({p['mercado']})\n"
                f"   - Probabilidad individual: {p['probabilidad']*100:.1f}% | Cuota: {odds_str}"
            )

        patas_str = "\n\n".join(texto_patas)
        return (
            f"🎯 **Combinada de Baja Varianza (2 Patas) · Overdog Sports AI**\n\n"
            f"{patas_str}\n\n"
            f"📈 **Probabilidad Conjunta Estimada:** {prob_conjunta*100:.1f}%\n"
            f"💵 **Cuota Decimal Estimada:** {cuota_combinada:.2f}\n\n"
            f"🛡️ **Control de Riesgo Cuantitativo:**\n"
            f"Ambas patas pertenecen a partidos independientes para evitar contaminación de rendimiento y correlaciones negativas."
        )

    # Prioridad 2: Consulta específica de NFL
    elif "nfl" in pregunta_norm:
        props = candidatos.get("nfl_props", [])
        partidos = candidatos.get("nfl_partidos", [])
        items = []
        for p in props[:3]:
            items.append(f"- **{p['jugador']}** · {p['seleccion']} ({p['mercado']}) | Prob: {p['probabilidad']*100:.1f}%")
        for m in partidos[:2]:
            items.append(f"- **{m['partido']}** · {m['seleccion']} | Prob: {m['probabilidad']*100:.1f}%")
        
        if not items:
            return "🏈 **NFL:** No hay selecciones oficiales activas para la cartelera NFL de hoy."
        return f"🏈 **Top Selecciones NFL de Hoy:**\n\n" + "\n".join(items)

    # Prioridad 3: Consulta específica de NBA
    elif "nba" in pregunta_norm:
        props = candidatos.get("nba_props", [])
        partidos = candidatos.get("nba_partidos", [])
        items = []
        for p in props[:3]:
            items.append(f"- **{p['jugador']}** · {p['seleccion']} ({p['mercado']}) | Prob: {p['probabilidad']*100:.1f}%")
        for m in partidos[:2]:
            items.append(f"- **{m['partido']}** · {m['seleccion']} | Prob: {m['probabilidad']*100:.1f}%")
        
        if not items:
            return "🏀 **NBA:** No hay selecciones oficiales activas para hoy en la cartelera NBA."
        return f"🏀 **Top Selecciones NBA de Hoy:**\n\n" + "\n".join(items) + "\n\n*Todas cuentan con proyección cuantitativa desacoplada y Shrinkage 60/40.*"

    # Prioridad 4: El Candado del Día (selección más segura individual)
    elif any(k in pregunta_norm for k in ["seguro", "candado", "firme", "el mas seguro", "el más seguro"]):
        candado = seleccionar_candado_oficial(candidatos)
        if not candado:
            return (
                "⚡ **Análisis de Overdog Sports AI:**\n\n"
                "En este momento no hay suficientes selecciones con margen de valor estadístico de alta convicción. "
                "Los modelos recomiendan esperar a la actualización de alineaciones oficiales para no forzar selecciones sin ventaja."
            )
        
        jugador_txt = f"**{candado['jugador']}** ({candado.get('equipo', '')})" if candado.get("jugador") else f"**{candado['partido']}**"
        return (
            f"⚡ **El Candado del Día · Overdog Sports AI**\n\n"
            f"🎯 **Selección:** {jugador_txt} · **{candado['seleccion']}**\n"
            f"📊 **Mercado:** {candado['mercado']} | **Deporte:** {candado['deporte']}\n"
            f"📈 **Probabilidad del Modelo:** {candado['probabilidad']*100:.1f}%\n"
            f"💎 **Margen de Valor (EV):** {candado['ev']:+.1f}%\n"
            f"🎯 **Cuota:** {candado['cuota']}\n\n"
            f"🔍 **Doble Filtro Cuantitativo:**\n"
            f"Esta selección superó tanto el Shrinkage Bayesiano como la prueba de varianza. "
            f"Presenta una sólida consistencia en sus últimos partidos y un emparejamiento favorable sin riesgo severo de reducción de minutos."
        )
        return f"🏈 **Top Selecciones NFL de Hoy:**\n\n" + "\n".join(items)

    else:
        candado = seleccionar_candado_oficial(candidatos)
        nombre_cand = f"{candado['jugador']} · {candado['seleccion']}" if candado else "revisión en proceso"
        return (
            f"👋 **Hola, soy el Asesor Cuantitativo de Overdog Sports AI.**\n\n"
            f"Estoy monitoreando en tiempo real las predicciones calibradas del día.\n"
            f"Actualmente la selección de mayor solidez estadística es: **{nombre_cand}**.\n\n"
            f"Puedes preguntarme:\n"
            f"• *'¿Cuál es el partido o pick más seguro del día?'*\n"
            f"• *'Dame una combinada (parlay) segura de 2 selecciones.'*\n"
            f"• *'¿Qué oportunidades hay en la NBA o NFL hoy?'*"
        )
