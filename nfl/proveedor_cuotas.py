"""Proveedor en tiempo real de cuotas y resultados oficiales de la NFL.

Extrae directamente de la API Scoreboard de ESPN las cuotas oficiales de DraftKings:
- Moneyline (Ganador Directo) Local y Visitante
- Hándicap (Spread)
- Totales (Over/Under)
- Marcadores en vivo y estados oficiales de juego
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import requests

logger = logging.getLogger("nfl_proveedor_cuotas")
ZONA_CDMX = ZoneInfo("America/Mexico_City")

URL_ESPN_NFL_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

MAPEO_EQUIPOS_ESPN = {
    "LAR": "LA",
    "WSH": "WAS",
}


def american_to_decimal(cuota_str: Any) -> Optional[float]:
    """Convierte momio americano (+145, -175) a formato decimal europeo."""
    if cuota_str is None:
        return None
    try:
        val = str(cuota_str).strip().replace("+", "")
        num = float(val)
        if num == 0:
            return None
        if num > 0:
            return round(1.0 + (num / 100.0), 3)
        return round(1.0 + (100.0 / abs(num)), 3)
    except (ValueError, TypeError):
        return None


def obtener_jornada_nfl_espn(dates: Optional[str] = None) -> List[Dict[str, Any]]:
    """Consulta la cartelera oficial y cuotas de DraftKings para la NFL vía ESPN Scoreboard."""
    params: Dict[str, Any] = {}
    if dates:
        params["dates"] = dates

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    try:
        resp = requests.get(URL_ESPN_NFL_SCOREBOARD, params=params, headers=headers, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"ESPN NFL retornó HTTP {resp.status_code}")
            return []
        data = resp.json()
    except Exception as exc:
        logger.error(f"Error consultando ESPN NFL: {exc}")
        return []

    eventos = data.get("events", [])
    partidos = []

    for ev in eventos:
        id_evento = str(ev.get("id", ""))
        fecha_utc_str = ev.get("date", "")
        estado_obj = ev.get("status", {}).get("type", {})
        estado_nombre = estado_obj.get("name", "STATUS_SCHEDULED")
        descripcion_estado = estado_obj.get("detail", estado_obj.get("description", ""))

        # Fecha y hora en CDMX
        fecha_cdmx, hora_cdmx = "", ""
        if fecha_utc_str:
            try:
                dt_utc = datetime.fromisoformat(fecha_utc_str.replace("Z", "+00:00"))
                dt_cdmx = dt_utc.astimezone(ZONA_CDMX)
                fecha_cdmx = dt_cdmx.strftime("%Y-%m-%d")
                hora_cdmx = dt_cdmx.strftime("%H:%M")
            except Exception:
                fecha_cdmx = fecha_utc_str[:10]

        competitions = ev.get("competitions", [])
        if not competitions:
            continue
        comp = competitions[0]
        competitors = comp.get("competitors", [])

        home_comp = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away_comp = next((c for c in competitors if c.get("homeAway") == "away"), {})

        home_raw = home_comp.get("team", {}).get("abbreviation", "")
        away_raw = away_comp.get("team", {}).get("abbreviation", "")

        home_team = MAPEO_EQUIPOS_ESPN.get(home_raw, home_raw)
        away_team = MAPEO_EQUIPOS_ESPN.get(away_raw, away_raw)

        # Marcadores
        marcador_home = None
        marcador_away = None
        try:
            if home_comp.get("score") is not None:
                marcador_home = int(home_comp["score"])
            if away_comp.get("score") is not None:
                marcador_away = int(away_comp["score"])
        except (ValueError, TypeError):
            pass

        # Cuotas DraftKings
        odds_list = comp.get("odds", [])
        dk_odd = None
        for o in odds_list:
            if not isinstance(o, dict):
                continue
            prov_name = str(o.get("provider", {}).get("name", "")).lower()
            if "draftkings" in prov_name:
                dk_odd = o
                break
        if not dk_odd and odds_list and isinstance(odds_list[0], dict):
            dk_odd = odds_list[0]

        ml_home = None
        ml_away = None
        spread_val = None
        spread_home_odds = None
        spread_away_odds = None
        linea_tot = None
        over_momio = None
        under_momio = None

        if dk_odd:
            # 1. Moneyline
            ml_obj = dk_odd.get("moneyline", {})
            if isinstance(ml_obj, dict):
                ml_home = ml_obj.get("home", {}).get("close", {}).get("odds") or ml_obj.get("home", {}).get("open", {}).get("odds")
                ml_away = ml_obj.get("away", {}).get("close", {}).get("odds") or ml_obj.get("away", {}).get("open", {}).get("odds")

            # Fallback a homeTeamOdds / awayTeamOdds
            if ml_home is None and isinstance(dk_odd.get("homeTeamOdds"), dict):
                ml_home = dk_odd["homeTeamOdds"].get("moneyLine")
            if ml_away is None and isinstance(dk_odd.get("awayTeamOdds"), dict):
                ml_away = dk_odd["awayTeamOdds"].get("moneyLine")

            # 2. Spread (Hándicap)
            spread_val = dk_odd.get("spread")
            spread_obj = dk_odd.get("pointSpread", {})
            if isinstance(spread_obj, dict):
                spread_home_odds = spread_obj.get("home", {}).get("close", {}).get("odds")
                spread_away_odds = spread_obj.get("away", {}).get("close", {}).get("odds")

            # 3. Totales (Over/Under)
            linea_tot = dk_odd.get("overUnder")
            tot_obj = dk_odd.get("total", {})
            if isinstance(tot_obj, dict):
                over_momio = tot_obj.get("over", {}).get("close", {}).get("odds") or tot_obj.get("over", {}).get("open", {}).get("odds")
                under_momio = tot_obj.get("under", {}).get("close", {}).get("odds") or tot_obj.get("under", {}).get("open", {}).get("odds")

        # Formatear momios a strings con signo
        def formatear_momio(m):
            if m is None:
                return None
            m_str = str(m).strip()
            try:
                val = float(m_str.replace("+", ""))
                return f"+{int(val)}" if val > 0 else f"{int(val)}"
            except Exception:
                return m_str

        ml_home = formatear_momio(ml_home)
        ml_away = formatear_momio(ml_away)
        over_momio = formatear_momio(over_momio)
        under_momio = formatear_momio(under_momio)

        partidos.append({
            "id_evento": id_evento,
            "partido": f"{away_team} @ {home_team}",
            "equipo_local": home_team,
            "equipo_visita": away_team,
            "fecha_cdmx": fecha_cdmx,
            "hora_cdmx": hora_cdmx,
            "estado": estado_nombre,
            "descripcion_estado": descripcion_estado,
            "marcador_local": marcador_home,
            "marcador_visita": marcador_away,
            "provider": dk_odd.get("provider", {}).get("name", "DraftKings") if dk_odd else "DraftKings",
            "spread_line": float(spread_val) if spread_val is not None else None,
            "spread_home_odds": spread_home_odds,
            "spread_away_odds": spread_away_odds,
            "moneyline_local": ml_home,
            "moneyline_visita": ml_away,
            "ml_local_dec": american_to_decimal(ml_home),
            "ml_visita_dec": american_to_decimal(ml_away),
            "linea_total": float(linea_tot) if linea_tot is not None else None,
            "over_momio": over_momio,
            "under_momio": under_momio,
            "over_momio_dec": american_to_decimal(over_momio),
            "under_momio_dec": american_to_decimal(under_momio),
        })

    return partidos


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    partidos = obtener_jornada_nfl_espn()
    print(f"\n🏈 Partidos de NFL encontrados en ESPN ({len(partidos)}):")
    for p in partidos:
        print(f"[{p['fecha_cdmx']} {p['hora_cdmx']}] {p['partido']} ({p['estado']})")
        print(f"   ML: {p['equipo_local']} ({p['moneyline_local']}) vs {p['equipo_visita']} ({p['moneyline_visita']}) | Spread: {p['spread_line']}")
        print(f"   O/U: {p['linea_total']} (Over: {p['over_momio']}, Under: {p['under_momio']})")
