"""Servicio extractor de líneas y momios de Player Props desde la API pública de Bovada (0 Créditos).

Extrae en tiempo real las líneas de:
* Puntos (Total Points)
* Rebotes (Total Rebounds)
* Asistencias (Total Assists)
* Triples (3-Point Field Goals / Milestones)
* Combos (Puntos + Rebotes + Asistencias - PRA, Puntos + Rebotes, Puntos + Asistencias)

Selecciona la línea principal (la más cercana al equilibrio 50/50 o -110) y calcula
las probabilidades implícitas de la casa.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nba_servicio_bovada")

URL_BOVADA_BASKETBALL = "https://www.bovada.lv/services/sports/event/v2/events/A/description/basketball"
DIR_CACHE = RAIZ / "data" / "nba" / "cache"
RUTA_CACHE_PROPS = DIR_CACHE / "bovada_props_hoy.json"

# Mapeo de siglas Bovada a estándar NBA
MAPA_EQUIPOS_BOVADA = {
    "ATL": "ATL", "BKN": "BKN", "BOS": "BOS", "CHA": "CHA", "CHI": "CHI",
    "CLE": "CLE", "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GS": "GS", "GSW": "GS",
    "HOU": "HOU", "IND": "IND", "LAC": "LAC", "LAL": "LAL", "MEM": "MEM",
    "MIA": "MIA", "MIL": "MIL", "MIN": "MIN", "NO": "NO", "NOP": "NO",
    "NY": "NY", "NYK": "NY", "OKC": "OKC", "ORL": "ORL", "PHI": "PHI",
    "PHX": "PHX", "POR": "POR", "SAC": "SAC", "SA": "SA", "SAS": "SA",
    "TOR": "TOR", "UTA": "UTA", "WAS": "WSH", "WSH": "WSH"
}


def _limpiar_nombre_jugador(nombre: str) -> str:
    """Normaliza nombres de jugadores quitando sufijos como Jr, III, etc."""
    n = nombre.strip()
    n = re.sub(r"\s+(Jr\.?|Sr\.?|II|III|IV)$", "", n, flags=re.IGNORECASE)
    return n.strip()


def _american_a_decimal(american: Any) -> float:
    """Convierte momio americano a cuota decimal."""
    try:
        s = str(american).strip().upper()
        if s == "EVEN":
            return 2.0
        val = float(s)
        if val > 0:
            return round((val / 100.0) + 1.0, 3)
        else:
            return round((100.0 / abs(val)) + 1.0, 3)
    except Exception:
        return 1.909


def descargar_mercados_bovada() -> List[Dict[str, Any]]:
    """Descarga los eventos y mercados de baloncesto desde Bovada con soporte SSL resiliente."""
    import ssl
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    }
    req = urllib.request.Request(URL_BOVADA_BASKETBALL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except Exception as err:
        try:
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data
        except Exception as err2:
            logger.error(f"Error descargando datos de Bovada: {err2}")
            return []


def extraer_props_nba(usar_cache: bool = False, max_horas_cache: float = 4.0) -> pd.DataFrame:
    """Extrae y formatea todos los player props de la NBA disponibles hoy en Bovada."""
    DIR_CACHE.mkdir(parents=True, exist_ok=True)

    if usar_cache and RUTA_CACHE_PROPS.exists():
        try:
            mtime = RUTA_CACHE_PROPS.stat().st_mtime
            edad_horas = (time.time() - mtime) / 3600.0
            hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
            if edad_horas <= max_horas_cache:
                with open(RUTA_CACHE_PROPS, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                df_cache = pd.DataFrame(cached_data)
                if not df_cache.empty:
                    fecha_cache = str(df_cache.get("fecha", pd.Series([""])).iloc[0])[:10]
                    if fecha_cache >= hoy_cdmx:
                        logger.info(f"⚡ Cargados {len(df_cache)} props de Bovada desde caché local ({edad_horas:.1f}h de antigüedad).")
                        return df_cache
        except Exception as e:
            logger.warning(f"Error leyendo caché de props: {e}")

    raw_data = descargar_mercados_bovada()
    if not raw_data:
        if RUTA_CACHE_PROPS.exists():
            logger.warning("No se pudo conectar a Bovada en tiempo real; utilizando caché local de respaldo si existe.")
            with open(RUTA_CACHE_PROPS, "r", encoding="utf-8") as f:
                return pd.DataFrame(json.load(f))
        return pd.DataFrame()

    eventos_nba = []
    for sec in raw_data:
        path = [p.get("description") for p in sec.get("path", [])]
        if path == ["NBA", "Basketball"]:
            eventos_nba.extend(sec.get("events", []))

    logger.info(f"🏀 Encontrados {len(eventos_nba)} eventos NBA en Bovada.")

    props_extraidos: List[Dict[str, Any]] = []

    for ev in eventos_nba:
        game_desc = ev.get("description", "")
        game_id = str(ev.get("id", ""))
        start_time_ms = ev.get("startTime", 0)
        dt_juego = datetime.fromtimestamp(start_time_ms / 1000.0, tz=timezone.utc) if start_time_ms else datetime.now(timezone.utc)
        dt_cdmx = dt_juego.astimezone(ZONA_CDMX)
        fecha_str = dt_cdmx.strftime("%Y-%m-%d")
        hora_str = dt_cdmx.strftime("%H:%M")

        partes_juego = [p.strip() for p in game_desc.split("@")]
        away_name = partes_juego[0] if len(partes_juego) > 0 else ""
        home_name = partes_juego[1] if len(partes_juego) > 1 else ""

        # Extraer spread del partido para control de riesgo por blowout
        game_spread = 0.0
        for dg_s in ev.get("displayGroups", []):
            for mk_s in dg_s.get("markets", []):
                if mk_s.get("description") == "Point Spread":
                    outs_s = mk_s.get("outcomes", [])
                    desc_outs = [o.get("description", "") for o in outs_s]
                    if not any(period in " ".join(desc_outs) for period in ["- 1H", "- 1Q", "- 2Q", "- 3Q", "- 4Q"]):
                        for o_s in outs_s:
                            hd = o_s.get("price", {}).get("handicap")
                            if hd is not None:
                                try:
                                    game_spread = abs(float(hd))
                                    break
                                except Exception:
                                    pass
                    if game_spread > 0:
                        break
            if game_spread > 0:
                break

        for dg in ev.get("displayGroups", []):
            grupo = dg.get("description", "")
            for m in dg.get("markets", []):
                m_desc = m.get("description", "")
                
                # 1. Puntos, Rebotes, Asistencias
                # Formato: "Total Points - Player Name (TEAM)"
                match_std = re.match(r"^Total\s+(Points|Rebounds|Assists)\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)
                
                # 2. Combos
                # Formato: "Total Points, Rebounds and Assists - Player Name (TEAM)"
                match_pra = re.match(r"^Total\s+Points,\s+Rebounds\s+and\s+Assists\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)
                match_pr = re.match(r"^Total\s+Points\s+and\s+Rebounds\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)
                match_pa = re.match(r"^Total\s+Points\s+and\s+Assists\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)

                # 3. Triples (Milestones)
                # Formato: "Total Made Threes Milestones - Player Name (TEAM)"
                match_t3 = re.match(r"^Total\s+Made\s+Threes(?:\s+Milestones)?\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)

                mercado_tipo = None
                p_nombre = None
                t_sigla = None

                if match_std:
                    tipo_raw = match_std.group(1).title()
                    mercado_tipo = f"Total {tipo_raw}"
                    p_nombre = match_std.group(2).strip()
                    t_sigla = match_std.group(3).strip().upper()
                elif match_pra:
                    mercado_tipo = "Total PRA"
                    p_nombre = match_pra.group(1).strip()
                    t_sigla = match_pra.group(2).strip().upper()
                elif match_pr:
                    mercado_tipo = "Total PR"
                    p_nombre = match_pr.group(1).strip()
                    t_sigla = match_pr.group(2).strip().upper()
                elif match_pa:
                    mercado_tipo = "Total PA"
                    p_nombre = match_pa.group(1).strip()
                    t_sigla = match_pa.group(2).strip().upper()
                elif match_t3:
                    mercado_tipo = "Total Triples"
                    p_nombre = match_t3.group(1).strip()
                    t_sigla = match_t3.group(2).strip().upper()

                if not mercado_tipo or not p_nombre:
                    continue

                t_sigla = MAPA_EQUIPOS_BOVADA.get(t_sigla, t_sigla)
                p_limpio = _limpiar_nombre_jugador(p_nombre)

                # Si es triples en milestones:
                if mercado_tipo == "Total Triples":
                    for out in m.get("outcomes", []):
                        out_desc = out.get("description", "")
                        # "To Make 2+ Threes" -> linea = 1.5
                        match_mstone = re.search(r"(\d+)\+", out_desc)
                        if match_mstone:
                            n_threes = int(match_mstone.group(1))
                            linea = float(n_threes) - 0.5
                            pr = out.get("price", {})
                            am_odds = pr.get("american")
                            dec_odds = float(pr.get("decimal") or _american_a_decimal(am_odds))
                            
                            # Solo agregamos las líneas más jugables (0.5, 1.5, 2.5, 3.5, 4.5)
                            if 0.5 <= linea <= 4.5 and 1.30 <= dec_odds <= 3.60:
                                props_extraidos.append({
                                    "bovada_game_id": game_id,
                                    "game": game_desc,
                                    "fecha": fecha_str,
                                    "hora": hora_str,
                                    "away_team": away_name,
                                    "home_team": home_name,
                                    "player_name": p_nombre,
                                    "player_clean": p_limpio,
                                    "team": t_sigla,
                                    "market": mercado_tipo,
                                    "line": linea,
                                    "over_american": am_odds,
                                    "over_decimal": dec_odds,
                                    "under_american": None,
                                    "under_decimal": None,
                                    "implied_prob_over": round(1.0 / dec_odds, 4),
                                    "implied_prob_under": None,
                                    "is_milestone": 1,
                                    "game_spread": game_spread,
                                })
                    continue

                # Mercados estándar de dos vías (Over / Under)
                by_handicap: Dict[float, List[Dict[str, Any]]] = {}
                for o in m.get("outcomes", []):
                    h_val = o.get("price", {}).get("handicap")
                    if h_val is not None:
                        try:
                            h_flt = float(h_val)
                            by_handicap.setdefault(h_flt, []).append(o)
                        except Exception:
                            pass

                if not by_handicap:
                    continue

                # Encontrar la línea más equilibrada (más cercana a cuota 1.909 / -110)
                best_h = None
                best_diff = 9999.0
                for h_flt, outs in by_handicap.items():
                    if len(outs) == 2:
                        diff = sum(abs(float(o.get("price", {}).get("decimal", 1.909)) - 1.909) for o in outs)
                        if diff < best_diff:
                            best_diff = diff
                            best_h = h_flt

                # Si no encontramos par exacto, tomar la primera
                if best_h is None:
                    best_h = list(by_handicap.keys())[0]

                outs_final = by_handicap.get(best_h, [])
                o_over = next((o for o in outs_final if o.get("type") == "O"), None)
                o_under = next((o for o in outs_final if o.get("type") == "U"), None)

                over_dec = float(o_over.get("price", {}).get("decimal") or _american_a_decimal(o_over.get("price", {}).get("american"))) if o_over else None
                under_dec = float(o_under.get("price", {}).get("decimal") or _american_a_decimal(o_under.get("price", {}).get("american"))) if o_under else None

                props_extraidos.append({
                    "bovada_game_id": game_id,
                    "game": game_desc,
                    "fecha": fecha_str,
                    "hora": hora_str,
                    "away_team": away_name,
                    "home_team": home_name,
                    "player_name": p_nombre,
                    "player_clean": p_limpio,
                    "team": t_sigla,
                    "market": mercado_tipo,
                    "line": float(best_h),
                    "over_american": o_over.get("price", {}).get("american") if o_over else None,
                    "over_decimal": over_dec,
                    "under_american": o_under.get("price", {}).get("american") if o_under else None,
                    "under_decimal": under_dec,
                    "implied_prob_over": round(1.0 / over_dec, 4) if over_dec else None,
                    "implied_prob_under": round(1.0 / under_dec, 4) if under_dec else None,
                    "is_milestone": 0,
                    "game_spread": game_spread,
                })

    df_props = pd.DataFrame(props_extraidos)

    if not df_props.empty:
        df_props.drop_duplicates(subset=["game", "player_clean", "market", "line"], inplace=True)
        # Guardar en JSON caché
        with open(RUTA_CACHE_PROPS, "w", encoding="utf-8") as f:
            json.dump(df_props.to_dict(orient="records"), f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Extraídos y guardados {len(df_props)} player props en {RUTA_CACHE_PROPS}")

    return df_props


if __name__ == "__main__":
    df = extraer_props_nba(usar_cache=False)
    print(f"Total props extraídos: {len(df)}")
    if not df.empty:
        print(df.head(10)[["game", "player_clean", "team", "market", "line", "over_american", "under_american"]])
        print("\nDistribución por mercado:\n", df["market"].value_counts())

