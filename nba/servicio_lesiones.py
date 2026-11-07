"""Servicio de Reporte de Lesiones e Impacto Cuantitativo NBA (OVERDOG AI).

Consulta la API oficial en tiempo real de ESPN para la NBA:
1. Extrae el reporte médico completo de todos los equipos.
2. Cuantifica el impacto real en el Spread (Margen) y Totales (Over/Under)
   según el valor sobre reemplazo (VORP/Net Rating) del jugador lesionado.
3. Aplica ponderación bayesiana según el estado: OUT (100%), DOUBTFUL (75%),
   QUESTIONABLE (45%), PROBABLE (10%).
4. Genera alertas de 'Injury Lock' para proteger al usuario contra líneas trampa.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.constants import ZONA_CDMX
from nba.proveedor_cuotas import normalizar_equipo

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[1]
RUTA_CACHE_LESIONES = RAIZ / "data" / "nba" / "cache" / "reporte_lesiones_nba.json"
RUTA_CACHE_LESIONES.parent.mkdir(parents=True, exist_ok=True)

URL_ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

# Mapeo cuantitativo de impacto de jugadores estrella y titulares clave de la NBA
# Valores calibrados en puntos contra el Spread y puntos en Puntos Totales
IMPACTO_JUGADORES: Dict[str, Dict[str, float]] = {
    # Tier 1: Mega-Estrellas / Candidatos MVP (Impacto 5.0 - 6.5 pts)
    "Nikola Jokic": {"spread": 6.5, "total": 6.0, "tier": 1},
    "Luka Doncic": {"spread": 6.2, "total": 6.5, "tier": 1},
    "Giannis Antetokounmpo": {"spread": 6.0, "total": 5.5, "tier": 1},
    "Shai Gilgeous-Alexander": {"spread": 5.8, "total": 5.0, "tier": 1},
    "Joel Embiid": {"spread": 5.5, "total": 5.0, "tier": 1},
    "Jayson Tatum": {"spread": 5.2, "total": 4.8, "tier": 1},
    "Stephen Curry": {"spread": 5.5, "total": 6.0, "tier": 1},
    "Steph Curry": {"spread": 5.5, "total": 6.0, "tier": 1},
    "Anthony Davis": {"spread": 5.0, "total": 4.5, "tier": 1},
    "Kevin Durant": {"spread": 5.0, "total": 4.8, "tier": 1},
    "LeBron James": {"spread": 4.8, "total": 4.5, "tier": 1},
    "Victor Wembanyama": {"spread": 5.0, "total": 4.0, "tier": 1},

    # Tier 2: All-Stars / Motores Ofensivos Principales (Impacto 3.0 - 4.5 pts)
    "Tyrese Haliburton": {"spread": 4.5, "total": 5.5, "tier": 2},
    "Paolo Banchero": {"spread": 4.2, "total": 4.5, "tier": 2},
    "Donovan Mitchell": {"spread": 4.2, "total": 4.2, "tier": 2},
    "Devin Booker": {"spread": 4.0, "total": 4.2, "tier": 2},
    "Jalen Brunson": {"spread": 4.2, "total": 4.5, "tier": 2},
    "Anthony Edwards": {"spread": 4.2, "total": 4.0, "tier": 2},
    "De'Aaron Fox": {"spread": 3.8, "total": 4.0, "tier": 2},
    "Trae Young": {"spread": 4.0, "total": 5.0, "tier": 2},
    "Ja Morant": {"spread": 4.0, "total": 4.2, "tier": 2},
    "Jimmy Butler": {"spread": 3.8, "total": 3.5, "tier": 2},
    "Jimmy Butler III": {"spread": 3.8, "total": 3.5, "tier": 2},
    "Bam Adebayo": {"spread": 3.5, "total": 3.0, "tier": 2},
    "Kyrie Irving": {"spread": 3.8, "total": 4.0, "tier": 2},
    "Jaylen Brown": {"spread": 3.5, "total": 3.5, "tier": 2},
    "Kawhi Leonard": {"spread": 4.0, "total": 3.5, "tier": 2},
    "Zion Williamson": {"spread": 3.8, "total": 4.0, "tier": 2},
    "Domantas Sabonis": {"spread": 3.8, "total": 4.0, "tier": 2},
    "Damian Lillard": {"spread": 3.8, "total": 4.5, "tier": 2},
    "LaMelo Ball": {"spread": 3.6, "total": 4.2, "tier": 2},
    "Karl-Anthony Towns": {"spread": 3.8, "total": 4.0, "tier": 2},
    "Cade Cunningham": {"spread": 3.6, "total": 4.0, "tier": 2},
    "Chet Holmgren": {"spread": 3.5, "total": 3.2, "tier": 2},
    "Jalen Williams": {"spread": 3.2, "total": 3.0, "tier": 2},
    "Tyrese Maxey": {"spread": 3.6, "total": 4.0, "tier": 2},
    "Alperen Sengun": {"spread": 3.4, "total": 3.5, "tier": 2},
    "Scottie Barnes": {"spread": 3.2, "total": 3.2, "tier": 2},
    "Darius Garland": {"spread": 3.0, "total": 3.5, "tier": 2},
    "Pascal Siakam": {"spread": 3.2, "total": 3.0, "tier": 2},
    "Paul George": {"spread": 3.2, "total": 3.2, "tier": 2},
    "Jamal Murray": {"spread": 3.2, "total": 3.5, "tier": 2},
    "Desmond Bane": {"spread": 3.0, "total": 3.2, "tier": 2},
    "Jaren Jackson Jr.": {"spread": 3.2, "total": 2.8, "tier": 2},

    # Tier 3: Titulares de Alto Impacto / Especialistas / Anclas Defensivas (1.5 - 2.8 pts)
    "Jarrett Allen": {"spread": 2.5, "total": 2.2, "tier": 3},
    "Evan Mobley": {"spread": 2.8, "total": 2.2, "tier": 3},
    "Jalen Suggs": {"spread": 2.2, "total": 2.0, "tier": 3},
    "Draymond Green": {"spread": 2.6, "total": 2.0, "tier": 3},
    "Derrick White": {"spread": 2.5, "total": 2.5, "tier": 3},
    "Jrue Holiday": {"spread": 2.5, "total": 2.2, "tier": 3},
    "Kristaps Porzingis": {"spread": 2.8, "total": 2.8, "tier": 3},
    "OG Anunoby": {"spread": 2.5, "total": 2.0, "tier": 3},
    "Mikal Bridges": {"spread": 2.4, "total": 2.5, "tier": 3},
    "Jalen Johnson": {"spread": 2.6, "total": 2.6, "tier": 3},
    "Franz Wagner": {"spread": 2.8, "total": 2.8, "tier": 3},
    "CJ McCollum": {"spread": 2.4, "total": 2.8, "tier": 3},
    "Michael Porter Jr.": {"spread": 2.3, "total": 2.6, "tier": 3},
    "Myles Turner": {"spread": 2.4, "total": 2.2, "tier": 3},
    "Coby White": {"spread": 2.2, "total": 2.6, "tier": 3},
    "Fred VanVleet": {"spread": 2.3, "total": 2.5, "tier": 3},
    "Jerami Grant": {"spread": 2.2, "total": 2.4, "tier": 3},
    "Tyler Herro": {"spread": 2.5, "total": 2.8, "tier": 3},
    "Dejounte Murray": {"spread": 2.6, "total": 2.8, "tier": 3},
    "Brandon Ingram": {"spread": 2.8, "total": 2.8, "tier": 3},
    "Austin Reaves": {"spread": 2.0, "total": 2.2, "tier": 3},
    "Bradley Beal": {"spread": 2.3, "total": 2.6, "tier": 3},
    "Rudy Gobert": {"spread": 2.5, "total": 1.8, "tier": 3},
    "Josh Hart": {"spread": 1.8, "total": 1.5, "tier": 3},
    "DeMar DeRozan": {"spread": 2.6, "total": 2.6, "tier": 3},
    "Steven Adams": {"spread": 1.5, "total": 1.2, "tier": 3},
    "Clint Capela": {"spread": 1.6, "total": 1.4, "tier": 3},
    "Shaedon Sharpe": {"spread": 2.0, "total": 2.2, "tier": 3},
}

PESO_ESTADO_LESION = {
    "OUT": 1.0,
    "RULED OUT": 1.0,
    "DOUBTFUL": 0.75,
    "QUESTIONABLE": 0.45,
    "DAY-TO-DAY": 0.45,
    "PROBABLE": 0.10,
}


def _normalizar_estado_medico(status_raw: str, comentario: str = "") -> str:
    """Clasifica el estado médico preciso analizando tanto la etiqueta como el comentario del reporte."""
    txt = (str(status_raw) + " " + str(comentario)).lower()
    if "ruled out" in txt or "is out" in txt or "won't play" in txt or "will miss" in txt:
        return "OUT"
    if "doubtful" in txt:
        return "DOUBTFUL"
    if "probable" in txt:
        return "PROBABLE"
    if "questionable" in txt:
        return "QUESTIONABLE"
    if "out" in str(status_raw).lower():
        return "OUT"
    return "DAY-TO-DAY"


def obtener_reporte_lesiones_nba(force_refresh: bool = False, max_age_minutes: int = 20) -> Dict[str, List[Dict[str, Any]]]:
    """Descarga y cachea el reporte oficial de lesiones de la NBA desde la API de ESPN."""
    ahora = datetime.now(ZONA_CDMX)

    # 1. Intentar cargar desde caché si es reciente
    if not force_refresh and RUTA_CACHE_LESIONES.exists():
        try:
            with open(RUTA_CACHE_LESIONES, "r", encoding="utf-8") as f:
                cached = json.load(f)
            guardado_en = datetime.fromisoformat(cached.get("guardado_en", "2000-01-01T00:00:00"))
            if (ahora - guardado_en).total_seconds() < max_age_minutes * 60:
                return cached.get("equipos", {})
        except Exception as e_cache:
            logger.warning(f"Error leyendo caché de lesiones NBA: {e_cache}")

    # 2. Consultar API ESPN
    try:
        req = urllib.request.Request(
            URL_ESPN_INJURIES,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        equipos_lesiones: Dict[str, List[Dict[str, Any]]] = {}

        for item in data.get("injuries", []):
            raw_team = item.get("displayName", "")
            abbr_team = normalizar_equipo(raw_team)
            if not abbr_team:
                continue

            lista_equipo = []
            for inj in item.get("injuries", []):
                ath = inj.get("athlete", {})
                p_name = ath.get("displayName", "").strip()
                if not p_name:
                    continue

                pos = ath.get("position", {}).get("abbreviation", "N/D")
                st_raw = inj.get("status", "Day-To-Day")
                comment = inj.get("shortComment", "") or inj.get("longComment", "")
                st_norm = _normalizar_estado_medico(st_raw, comment)
                inj_type = inj.get("details", {}).get("type", "Lesión")

                # Consultar impacto cuantificado
                metricas = IMPACTO_JUGADORES.get(p_name)
                if metricas:
                    imp_spread = metricas["spread"]
                    imp_total = metricas["total"]
                    tier = metricas["tier"]
                else:
                    # Titulares y jugadores de rol no listados expresamente
                    imp_spread = 0.8
                    imp_total = 0.9
                    tier = 4

                lista_equipo.append({
                    "jugador": p_name,
                    "posicion": pos,
                    "estado_raw": st_raw,
                    "estado": st_norm,
                    "tipo_lesion": inj_type,
                    "comentario": comment,
                    "impacto_spread": imp_spread,
                    "impacto_total": imp_total,
                    "tier": tier,
                    "es_estrella": tier in [1, 2],
                })

            equipos_lesiones[abbr_team] = lista_equipo

        # Guardar en caché
        with open(RUTA_CACHE_LESIONES, "w", encoding="utf-8") as f:
            json.dump({
                "guardado_en": ahora.isoformat(),
                "total_equipos": len(equipos_lesiones),
                "equipos": equipos_lesiones
            }, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Reporte de lesiones NBA actualizado: {len(equipos_lesiones)} franquicias con novedades.")
        return equipos_lesiones

    except Exception as err:
        logger.warning(f"Error consultando ESPN Injuries NBA: {err}. Intentando fallback en caché.")
        if RUTA_CACHE_LESIONES.exists():
            try:
                with open(RUTA_CACHE_LESIONES, "r", encoding="utf-8") as f:
                    return json.load(f).get("equipos", {})
            except Exception:
                pass
        return {}


def calcular_impacto_lesiones_partido(
    equipo_visita: str,
    equipo_local: str,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """Calcula el impacto neto en puntos de las lesiones para el enfrentamiento (Spread y Totales).

    Retorna:
    - pen_spread_visita: Puntos perdidos por el equipo visitante.
    - pen_spread_local: Puntos perdidos por el equipo local.
    - ajuste_neto_spread: Impacto neto favorable al local (+ favorece local, - favorece visita).
    - ajuste_total_puntos: Reducción esperada en el Total de puntos (Over/Under).
    - alertas: Alertas críticas sobre estrellas confirmadas OUT o en duda.
    - candado_lesion: Booleano que indica si una estrella clave está en duda e invalida el pick.
    """
    reporte = obtener_reporte_lesiones_nba(force_refresh=force_refresh)

    abbr_vis = normalizar_equipo(equipo_visita)
    abbr_loc = normalizar_equipo(equipo_local)

    lesiones_vis = reporte.get(abbr_vis, [])
    lesiones_loc = reporte.get(abbr_loc, [])

    pen_spread_vis = 0.0
    pen_total_vis = 0.0
    pen_spread_loc = 0.0
    pen_total_loc = 0.0

    alertas: List[str] = []
    hay_candado = False

    # Procesar equipo visitante
    for p in lesiones_vis:
        peso = PESO_ESTADO_LESION.get(p["estado"], 0.45)
        impacto_sp = p["impacto_spread"] * peso
        impacto_tot = p["impacto_total"] * peso
        pen_spread_vis += impacto_sp
        pen_total_vis += impacto_tot

        if p["es_estrella"]:
            if p["estado"] == "OUT":
                alertas.append(f"🚨 {p['jugador']} ({abbr_vis}) CONFIRMADO OUT (-{p['impacto_spread']:.1f} pts)")
            elif p["estado"] in ["QUESTIONABLE", "DAY-TO-DAY", "DOUBTFUL"]:
                alertas.append(f"⚠️ {p['jugador']} ({abbr_vis}) EN DUDA ({p['estado']})")
                if p["tier"] == 1:
                    hay_candado = True

    # Procesar equipo local
    for p in lesiones_loc:
        peso = PESO_ESTADO_LESION.get(p["estado"], 0.45)
        impacto_sp = p["impacto_spread"] * peso
        impacto_tot = p["impacto_total"] * peso
        pen_spread_loc += impacto_sp
        pen_total_loc += impacto_tot

        if p["es_estrella"]:
            if p["estado"] == "OUT":
                alertas.append(f"🚨 {p['jugador']} ({abbr_loc}) CONFIRMADO OUT (-{p['impacto_spread']:.1f} pts)")
            elif p["estado"] in ["QUESTIONABLE", "DAY-TO-DAY", "DOUBTFUL"]:
                alertas.append(f"⚠️ {p['jugador']} ({abbr_loc}) EN DUDA ({p['estado']})")
                if p["tier"] == 1:
                    hay_candado = True

    # El ajuste de spread favorable al local es: (penalizacion visita - penalizacion local)
    # Si la visita está más disminuida, pen_spread_vis > pen_spread_loc => ajuste_neto_spread > 0 (Local más favorito)
    ajuste_neto_spread = round(pen_spread_vis - pen_spread_loc, 2)

    # Las bajas ofensivas restan puntos al total proyectado
    ajuste_total_puntos = round(-(pen_total_vis + pen_total_loc), 2)

    return {
        "abbr_visita": abbr_vis,
        "abbr_local": abbr_loc,
        "lesiones_visita": lesiones_vis,
        "lesiones_local": lesiones_loc,
        "penalizacion_spread_visita": round(pen_spread_vis, 2),
        "penalizacion_spread_local": round(pen_spread_loc, 2),
        "ajuste_neto_spread": ajuste_neto_spread,
        "ajuste_total_puntos": ajuste_total_puntos,
        "alertas": alertas,
        "candado_lesion": hay_candado,
    }
