"""Servicio extractor de líneas y momios de Player Props NBA en tiempo real.

Soporta arquitectura dual resiliente:
1. Bovada API pública (0 créditos).
2. The Odds API (DraftKings, FanDuel, Bovada, BetMGM) como respaldo institucional oficial.
3. Caché diario con expiración automática para evitar arrastrar líneas de días anteriores.

Extrae en tiempo real las líneas de:
* Puntos (Total Points)
* Rebotes (Total Rebounds)
* Asistencias (Total Assists)
* Triples (Total Triples / Milestones)
* Combos (PRA, PR, PA)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import NBA_ALIAS_TO_ABBR, ZONA_CDMX

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nba_servicio_bovada")

URL_BOVADA_BASKETBALL = "https://www.bovada.lv/services/sports/event/v2/events/A/description/basketball"
DIR_CACHE = RAIZ / "data" / "nba" / "cache"
RUTA_CACHE_PROPS = DIR_CACHE / "bovada_props_hoy.json"
RUTA_PARQUET_JUGADORES = RAIZ / "data" / "nba" / "processed" / "player_boxscores_2026_27.parquet"

# Estado de la última extracción para diagnóstico de UI
ESTADO_EXTRACCION: Dict[str, Any] = {
    "origen": "desconocido",
    "bloqueo_firewall": False,
    "creditos_consumidos": 0,
    "error": None,
}

# Mapeo de siglas Bovada a estándar NBA
MAPA_EQUIPOS_BOVADA = {
    "ATL": "ATL", "BKN": "BKN", "BOS": "BOS", "CHA": "CHA", "CHI": "CHI",
    "CLE": "CLE", "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GS": "GSW", "GSW": "GSW",
    "HOU": "HOU", "IND": "IND", "LAC": "LAC", "LAL": "LAL", "MEM": "MEM",
    "MIA": "MIA", "MIL": "MIL", "MIN": "MIN", "NO": "NOP", "NOP": "NOP",
    "NY": "NYK", "NYK": "NYK", "OKC": "OKC", "ORL": "ORL", "PHI": "PHI",
    "PHX": "PHX", "POR": "POR", "SAC": "SAC", "SA": "SAS", "SAS": "SAS",
    "TOR": "TOR", "UTA": "UTA", "WAS": "WAS", "WSH": "WAS"
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


def _obtener_odds_api_key() -> Optional[str]:
    """Obtiene la clave de The Odds API desde variables de entorno o secrets.toml."""
    k = os.getenv("THE_ODDS_API_KEY") or os.getenv("ODDS_API_KEY")
    if k:
        return k
    secrets_p = RAIZ / ".streamlit" / "secrets.toml"
    if secrets_p.exists():
        try:
            import toml
            sec = toml.load(secrets_p)
            return sec.get("odds_api_key") or sec.get("THE_ODDS_API_KEY")
        except Exception:
            pass
    return None


def _obtener_mapa_jugador_equipo() -> Dict[str, str]:
    """Construye un diccionario rápido de jugador -> equipo oficial desde los boxscores más recientes."""
    if RUTA_PARQUET_JUGADORES.exists():
        try:
            df_b = pd.read_parquet(RUTA_PARQUET_JUGADORES)
            if not df_b.empty and "player_name" in df_b.columns and "team" in df_b.columns:
                return df_b.sort_values("fecha").groupby("player_name").last()["team"].to_dict()
        except Exception:
            pass
    return {}


def consultar_saldo_odds_api() -> Optional[int]:
    """Consulta los créditos restantes en The Odds API de forma gratuita (0 créditos)."""
    api_key = _obtener_odds_api_key()
    if not api_key:
        return None
    try:
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/basketball_nba/events?apiKey={api_key}",
            timeout=6,
        )
        rem = r.headers.get("x-requests-remaining")
        if rem is not None:
            return int(rem)
    except Exception:
        pass
    return None


def descargar_mercados_bovada() -> List[Dict[str, Any]]:
    """Descarga los eventos y mercados de baloncesto desde Bovada con soporte curl_cffi y detección de firewall."""
    global ESTADO_EXTRACCION
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    }

    # Intento 1: curl_cffi con impersonación de Chrome y SSL permisivo
    try:
        from curl_cffi import requests as cffi_requests
        r = cffi_requests.get(
            URL_BOVADA_BASKETBALL,
            headers=headers,
            impersonate="chrome120",
            verify=False,
            timeout=10,
        )
        if "fortiguard" in r.text.lower() or "access blocked" in r.text.lower():
            ESTADO_EXTRACCION["bloqueo_firewall"] = True
            logger.warning("🛡️ Red local con filtro FortiGuard/Firewall detectada: bloqueando bovada.lv.")
            return []
        if r.status_code == 200:
            data = r.json()
            ESTADO_EXTRACCION["bloqueo_firewall"] = False
            return data
    except Exception as e_cffi:
        logger.debug(f"curl_cffi intente Bovada: {e_cffi}")

    # Intento 2: urllib estándar con contexto SSL no verificado
    import ssl
    req = urllib.request.Request(URL_BOVADA_BASKETBALL, headers=headers)
    try:
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            if "fortiguard" in raw.lower() or "access blocked" in raw.lower():
                ESTADO_EXTRACCION["bloqueo_firewall"] = True
                return []
            data = json.loads(raw)
            ESTADO_EXTRACCION["bloqueo_firewall"] = False
            return data
    except Exception as err2:
        err_str = str(err2).lower()
        if "certificate" in err_str or "403" in err_str or "fortiguard" in err_str:
            ESTADO_EXTRACCION["bloqueo_firewall"] = True
        logger.warning(f"Bovada no disponible directamente ({err2}).")
        return []


def extraer_props_the_odds_api() -> List[Dict[str, Any]]:
    """Extrae player props en vivo desde The Odds API (DraftKings, FanDuel, Bovada) para los partidos de hoy."""
    api_key = _obtener_odds_api_key()
    if not api_key:
        logger.warning("No se encontró clave de The Odds API configurada.")
        return []

    hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
    mapa_jugador_eq = _obtener_mapa_jugador_equipo()

    try:
        events_url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/events?apiKey={api_key}"
        r_ev = requests.get(events_url, timeout=10)
        if r_ev.status_code != 200:
            logger.warning(f"The Odds API error al listar eventos: {r_ev.status_code}")
            return []

        events = r_ev.json()
        logger.info(f"🏀 The Odds API: {len(events)} partidos de NBA encontrados.")

        props_extraidos: List[Dict[str, Any]] = []
        market_map = {
            "player_points": "Total Points",
            "player_rebounds": "Total Rebounds",
            "player_assists": "Total Assists",
            "player_threes": "Total Triples",
        }

        for ev in events:
            ev_id = ev.get("id")
            away = ev.get("away_team", "")
            home = ev.get("home_team", "")
            commence_iso = ev.get("commence_time", "")
            if not commence_iso:
                continue

            dt_utc = datetime.fromisoformat(commence_iso.replace("Z", "+00:00"))
            dt_cdmx = dt_utc.astimezone(ZONA_CDMX)
            fecha_str = dt_cdmx.strftime("%Y-%m-%d")
            hora_str = dt_cdmx.strftime("%H:%M")

            # Solo partidos de hoy en horario CDMX
            if fecha_str < hoy_cdmx:
                continue

            game_desc = f"{away} @ {home}"
            odds_url = (
                f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{ev_id}/odds"
                f"?apiKey={api_key}&regions=us&markets=player_points,player_rebounds,player_assists,player_threes&oddsFormat=decimal"
            )
            ro = requests.get(odds_url, timeout=10)
            if ro.status_code != 200:
                continue

            odds_data = ro.json()
            bms = odds_data.get("bookmakers", [])
            if not bms:
                continue

            # Priorizar DraftKings > FanDuel > Bovada > BetMGM
            bm = None
            for target in ["DraftKings", "FanDuel", "Bovada", "BetMGM"]:
                for b in bms:
                    if b.get("title") == target:
                        bm = b
                        break
                if bm:
                    break
            if not bm:
                bm = bms[0]

            for m in bm.get("markets", []):
                m_key = m.get("key")
                m_name = market_map.get(m_key)
                if not m_name:
                    continue

                by_player: Dict[Tuple[str, float], Dict[str, float]] = {}
                for out in m.get("outcomes", []):
                    p_name = out.get("description", "").strip()
                    point = out.get("point")
                    side = str(out.get("name", "")).lower()
                    price = out.get("price")
                    if not p_name or point is None or not price:
                        continue
                    k = (p_name, float(point))
                    by_player.setdefault(k, {})[side] = float(price)

                for (p_name, point), sides in by_player.items():
                    ov_dec = sides.get("over")
                    un_dec = sides.get("under")
                    if not ov_dec and not un_dec:
                        continue

                    p_limpio = _limpiar_nombre_jugador(p_name)
                    t_sigla = mapa_jugador_eq.get(p_name) or mapa_jugador_eq.get(p_limpio)
                    if not t_sigla:
                        t_sigla = NBA_ALIAS_TO_ABBR.get(home.upper(), "TBD")

                    props_extraidos.append({
                        "bovada_game_id": ev_id,
                        "game": game_desc,
                        "fecha": fecha_str,
                        "hora": hora_str,
                        "away_team": away,
                        "home_team": home,
                        "player_name": p_name,
                        "player_clean": p_limpio,
                        "team": t_sigla,
                        "market": m_name,
                        "line": float(point),
                        "over_american": None,
                        "over_decimal": ov_dec,
                        "under_american": None,
                        "under_decimal": un_dec,
                        "implied_prob_over": round(1.0 / ov_dec, 4) if ov_dec else None,
                        "implied_prob_under": round(1.0 / un_dec, 4) if un_dec else None,
                        "is_milestone": 0,
                        "game_spread": 0.0,
                        "timestamp_cuota": datetime.now(timezone.utc).isoformat(),
                    })

        logger.info(f"✅ The Odds API: {len(props_extraidos)} props extraídos para la cartelera de hoy.")
        return props_extraidos

    except Exception as e_toa:
        logger.warning(f"Error consultando The Odds API: {e_toa}")
        return []


def extraer_props_nba(
    usar_cache: bool = False,
    max_horas_cache: float = 4.0,
    permitir_odds_api: bool = True,
) -> pd.DataFrame:
    """Extrae y formatea todos los player props de la NBA disponibles hoy.
    
    1. Revisa caché si es del mismo día y no ha expirado (0 créditos).
    2. Intenta Bovada pública directa con curl_cffi (0 créditos).
    3. Si Bovada falla por bloqueo de red/firewall y permitir_odds_api=True, consulta The Odds API.
    4. Garantiza que NUNCA se utilicen líneas de días anteriores.
    """
    global ESTADO_EXTRACCION
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")

    # 1. Verificar si hay caché válido de HOY
    if usar_cache and RUTA_CACHE_PROPS.exists():
        try:
            mtime = RUTA_CACHE_PROPS.stat().st_mtime
            edad_horas = (time.time() - mtime) / 3600.0
            if edad_horas <= max_horas_cache:
                with open(RUTA_CACHE_PROPS, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                df_cache = pd.DataFrame(cached_data)
                if not df_cache.empty:
                    fecha_cache = str(df_cache.get("fecha", pd.Series([""])).iloc[0])[:10]
                    if fecha_cache >= hoy_cdmx:
                        logger.info(f"⚡ Cargados {len(df_cache)} props desde caché local de hoy ({edad_horas:.1f}h de antigüedad - 0 créditos).")
                        ESTADO_EXTRACCION["origen"] = "Caché Local de Hoy (0 Créditos)"
                        return df_cache
                    else:
                        logger.info(f"Caché en disco es del {fecha_cache}; se renovará para la jornada de hoy ({hoy_cdmx}).")
        except Exception as e:
            logger.warning(f"Error leyendo caché de props: {e}")

    # 2. Intentar Bovada directa (0 créditos)
    raw_data = descargar_mercados_bovada()
    eventos_nba = []
    if raw_data:
        for sec in raw_data:
            path = [p.get("description") for p in sec.get("path", [])]
            if path == ["NBA", "Basketball"]:
                eventos_nba.extend(sec.get("events", []))

    props_extraidos: List[Dict[str, Any]] = []

    if eventos_nba:
        logger.info(f"🏀 Encontrados {len(eventos_nba)} eventos NBA en Bovada.")
        for ev in eventos_nba:
            game_desc = ev.get("description", "")
            game_id = str(ev.get("id", ""))
            start_time_ms = ev.get("startTime", 0)
            dt_juego = datetime.fromtimestamp(start_time_ms / 1000.0, tz=timezone.utc) if start_time_ms else datetime.now(timezone.utc)
            dt_cdmx = dt_juego.astimezone(ZONA_CDMX)
            fecha_str = dt_cdmx.strftime("%Y-%m-%d")
            hora_str = dt_cdmx.strftime("%H:%M")

            if fecha_str < hoy_cdmx:
                continue

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
                for m in dg.get("markets", []):
                    m_desc = m.get("description", "")
                    
                    match_std = re.match(r"^Total\s+(Points|Rebounds|Assists)\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)
                    match_pra = re.match(r"^Total\s+Points,\s+Rebounds\s+and\s+Assists\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)
                    match_pr = re.match(r"^Total\s+Points\s+and\s+Rebounds\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)
                    match_pa = re.match(r"^Total\s+Points\s+and\s+Assists\s*-\s*(.+?)\s*\(([A-Z]{2,3})\)$", m_desc, re.IGNORECASE)
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

                    if mercado_tipo == "Total Triples":
                        for out in m.get("outcomes", []):
                            out_desc = out.get("description", "")
                            match_mstone = re.search(r"(\d+)\+", out_desc)
                            if match_mstone:
                                n_threes = int(match_mstone.group(1))
                                linea = float(n_threes) - 0.5
                                pr = out.get("price", {})
                                am_odds = pr.get("american")
                                dec_odds = float(pr.get("decimal") or _american_a_decimal(am_odds))
                                
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
                                        "timestamp_cuota": datetime.now(timezone.utc).isoformat(),
                                    })
                        continue

                    # Mercados estándar Over / Under
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

                    best_h = None
                    best_diff = 9999.0
                    for h_flt, outs in by_handicap.items():
                        if len(outs) == 2:
                            diff = sum(abs(float(o.get("price", {}).get("decimal", 1.909)) - 1.909) for o in outs)
                            if diff < best_diff:
                                best_diff = diff
                                best_h = h_flt

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
                        "timestamp_cuota": datetime.now(timezone.utc).isoformat(),
                    })

    # 3. Evaluar resultado de Bovada directa
    if props_extraidos:
        ESTADO_EXTRACCION["origen"] = "Bovada Directo (0 Créditos)"
        ESTADO_EXTRACCION["creditos_consumidos"] = 0
    else:
        # Si Bovada no arrojó props para hoy (bloqueado por firewall o mercado aún cerrado)
        if permitir_odds_api:
            logger.info("📡 Consultando The Odds API como proveedor de respaldo...")
            props_extraidos = extraer_props_the_odds_api()
            if props_extraidos:
                ESTADO_EXTRACCION["origen"] = "The Odds API (Respaldo)"
        else:
            logger.info("ℹ️ permitir_odds_api=False: Se omite The Odds API para proteger créditos.")

    df_props = pd.DataFrame(props_extraidos)

    if not df_props.empty:
        df_props.drop_duplicates(subset=["game", "player_clean", "market", "line"], inplace=True)
        with open(RUTA_CACHE_PROPS, "w", encoding="utf-8") as f:
            json.dump(df_props.to_dict(orient="records"), f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Guardados {len(df_props)} props actualizados en {RUTA_CACHE_PROPS}")
    else:
        # 4. Si fallaron ambos, verificar si el caché existente es de HOY
        if RUTA_CACHE_PROPS.exists():
            try:
                with open(RUTA_CACHE_PROPS, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                df_cache = pd.DataFrame(cached_data)
                if not df_cache.empty:
                    fecha_cache = str(df_cache.get("fecha", pd.Series([""])).iloc[0])[:10]
                    if fecha_cache >= hoy_cdmx:
                        logger.info("Utilizando caché local disponible de hoy (0 créditos).")
                        ESTADO_EXTRACCION["origen"] = "Caché Local de Hoy (0 Créditos)"
                        return df_cache
                    else:
                        logger.warning(f"El caché existente es del {fecha_cache} y los partidos ya concluyeron. No se utilizarán líneas caducas.")
            except Exception:
                pass

    return df_props


if __name__ == "__main__":
    df = extraer_props_nba(usar_cache=False)
    print(f"Total props extraídos: {len(df)}")
    if not df.empty:
        print(df.head(10)[["game", "player_clean", "team", "market", "line", "over_decimal", "under_decimal"]])
        print("\nDistribución por mercado:\n", df["market"].value_counts())
