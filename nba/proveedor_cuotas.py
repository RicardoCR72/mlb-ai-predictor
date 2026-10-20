"""Proveedor de cuotas y calendario de la NBA vía API pública de ESPN (DraftKings).

Ventajas:
- 100% gratuito, sin límites de peticiones ni consumo de créditos de The Odds API.
- Cuotas completas de Moneyline, Spread (Hándicap) y Totales (Over/Under).
- Incluye líneas de apertura (open) y de cierre (close) para detectar movimientos de mercado.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo
import requests

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.cache import cached_get_json
from core.constants import NBA_ALIAS_TO_ABBR, NBA_TEAMS, ZONA_CDMX, ZONA_MX

logger = logging.getLogger(__name__)

URL_ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"


def american_to_decimal(american: Any) -> Optional[float]:
    """Convierte momio americano (+150, -110) a cuota decimal (2.50, 1.91)."""
    if american is None:
        return None
    try:
        val = float(str(american).replace("+", "").strip())
        if val == 0:
            return None
        if val > 0:
            return round(1.0 + (val / 100.0), 3)
        else:
            return round(1.0 + (100.0 / abs(val)), 3)
    except Exception:
        return None


def american_to_prob(american: Any) -> Optional[float]:
    """Convierte momio americano a probabilidad implícita (0.0 a 1.0)."""
    dec = american_to_decimal(american)
    if not dec or dec <= 1.0:
        return None
    return round(1.0 / dec, 4)


def normalizar_equipo(nombre_o_abbr: str) -> str:
    """Normaliza alias de ESPN o casas de apuestas a la abreviatura estándar de 3 letras."""
    if not nombre_o_abbr:
        return ""
    limpio = str(nombre_o_abbr).strip().upper()
    return NBA_ALIAS_TO_ABBR.get(limpio, limpio)


def obtener_calendario_y_cuotas_nba(
    fecha: Optional[str] = None,
    force_refresh: bool = False,
    ttl_minutes: int = 15
) -> list[dict[str, Any]]:
    """Consulta los partidos y cuotas de la NBA para una fecha específica (YYYYMMDD o hoy).
    
    Usa caché con TTL de 15 minutos para no saturar y mantener respuesta instantánea.
    """
    params: dict[str, Any] = {}
    if fecha:
        params["dates"] = fecha.replace("-", "")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        data, _ = cached_get_json(
            URL_ESPN_SCOREBOARD,
            params=params,
            headers=headers,
            ttl_minutes=ttl_minutes,
            force_refresh=force_refresh
        )
    except Exception as err:
        logger.warning(f"Error al consultar ESPN NBA scoreboard: {err}")
        return []

    if not data or "events" not in data:
        return []

    partidos = []
    for evento in data.get("events", []):
        try:
            ev_id = str(evento.get("id"))
            nombre = evento.get("name", "")
            fecha_iso = evento.get("date", "")
            
            # Formatear fecha y hora a zona CDMX y Mazatlán
            dt_utc = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
            dt_cdmx = dt_utc.astimezone(ZONA_CDMX)
            
            competencia = evento.get("competitions", [{}])[0]
            competitors = competencia.get("competitors", [])
            
            home_data = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away_data = next((c for c in competitors if c.get("homeAway") == "away"), {})
            
            home_abbr = normalizar_equipo(home_data.get("team", {}).get("abbreviation", ""))
            away_abbr = normalizar_equipo(away_data.get("team", {}).get("abbreviation", ""))
            
            home_name = NBA_TEAMS.get(home_abbr, home_data.get("team", {}).get("displayName", home_abbr))
            away_name = NBA_TEAMS.get(away_abbr, away_data.get("team", {}).get("displayName", away_abbr))

            # Estado del juego
            status_type = evento.get("status", {}).get("type", {})
            estado_juego = status_type.get("name", "STATUS_SCHEDULED")  # STATUS_SCHEDULED, STATUS_IN_PROGRESS, STATUS_FINAL
            descripcion_estado = status_type.get("description", "")
            
            score_home = home_data.get("score")
            score_away = away_data.get("score")
            
            # Cuotas
            odds_list = competencia.get("odds", [])
            odd = odds_list[0] if odds_list else {}
            provider_name = odd.get("provider", {}).get("displayName", "DraftKings")
            
            # 1. Totales (Over / Under)
            total_line = odd.get("overUnder")
            total_obj = odd.get("total", {})
            over_odds = total_obj.get("over", {}).get("close", {}).get("odds", "-110")
            under_odds = total_obj.get("under", {}).get("close", {}).get("odds", "-110")
            over_line_open = total_obj.get("over", {}).get("open", {}).get("line")
            
            # 2. Point Spread (Hándicap)
            spread_details = odd.get("details", "")  # Ej: "BOS -1.5"
            spread_line = odd.get("spread")
            spread_obj = odd.get("pointSpread", {})
            home_spread_close = spread_obj.get("home", {}).get("close", {})
            away_spread_close = spread_obj.get("away", {}).get("close", {})
            
            # 3. Moneyline
            ml_obj = odd.get("moneyline", {})
            ml_home_close = ml_obj.get("home", {}).get("close", {}).get("odds")
            ml_away_close = ml_obj.get("away", {}).get("close", {}).get("odds")
            ml_home_open = ml_obj.get("home", {}).get("open", {}).get("odds")
            ml_away_open = ml_obj.get("away", {}).get("open", {}).get("odds")

            partidos.append({
                "id_evento": ev_id,
                "partido": f"{away_name} @ {home_name}",
                "equipo_visita": away_name,
                "equipo_local": home_name,
                "abbr_visita": away_abbr,
                "abbr_local": home_abbr,
                "fecha_utc": fecha_iso,
                "fecha_cdmx": dt_cdmx.strftime("%Y-%m-%d"),
                "hora_cdmx": dt_cdmx.strftime("%H:%M"),
                "estado": estado_juego,
                "descripcion_estado": descripcion_estado,
                "marcador_visita": int(score_away) if score_away and score_away.isdigit() else None,
                "marcador_local": int(score_home) if score_home and score_home.isdigit() else None,
                # Mercados
                "provider": provider_name,
                "spread_detalles": spread_details,
                "spread_linea": spread_line,
                "spread_local_linea": home_spread_close.get("line"),
                "spread_local_momio": home_spread_close.get("odds"),
                "spread_visita_linea": away_spread_close.get("line"),
                "spread_visita_momio": away_spread_close.get("odds"),
                "total_linea": float(total_line) if total_line is not None else None,
                "total_open": float(str(over_line_open).replace("o", "").replace("u", "")) if over_line_open else None,
                "over_momio": over_odds,
                "under_momio": under_odds,
                "over_prob_implicita": american_to_prob(over_odds),
                "under_prob_implicita": american_to_prob(under_odds),
                "moneyline_local": ml_home_close,
                "moneyline_visita": ml_away_close,
                "moneyline_local_dec": american_to_decimal(ml_home_close),
                "moneyline_visita_dec": american_to_decimal(ml_away_close),
                "moneyline_local_prob": american_to_prob(ml_home_close),
                "moneyline_visita_prob": american_to_prob(ml_away_close),
                "moneyline_local_open": ml_home_open,
                "moneyline_visita_open": ml_away_open,
            })
        except Exception as e:
            logger.error(f"Error procesando evento NBA {evento.get('id')}: {e}")
            continue

    return partidos


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("🏀 Consultando partidos y cuotas NBA desde ESPN (DraftKings)...")
    juegos = obtener_calendario_y_cuotas_nba(force_refresh=True)
    print(f"✅ Partidos encontrados: {len(juegos)}")
    for j in juegos:
        print(f"\n[{j['hora_cdmx']} CDMX] {j['partido']}")
        print(f"   Spread: {j['spread_detalles']} | Total O/U: {j['total_linea']} (Open: {j['total_open']})")
        print(f"   Moneyline: Local {j['moneyline_local']} ({j['moneyline_local_dec']}) vs Visita {j['moneyline_visita']} ({j['moneyline_visita_dec']})")
