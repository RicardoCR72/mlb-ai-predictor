"""Proveedor de partidos, cuotas y marcadores en vivo para la Liga MX vía ESPN (DraftKings).

Ventajas:
- 100% gratuito sin consumo de API-Football ni límites de créditos.
- Trae cuotas reales pre-partido de DraftKings para Moneyline (1X2) y Totales Over/Under.
- Marcadores en vivo y finales actualizados en tiempo real.
"""
from __future__ import annotations

import logging
import re
import sys
import unicodedata
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import requests

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.cache import cached_get_json
from core.constants import ZONA_CDMX
from futbol_liga_mx.proveedor_espn import ALIASES, canonical

logger = logging.getLogger(__name__)

URL_ESPN_LIGAMX = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard"


def american_to_decimal(american: Any) -> Optional[float]:
    """Convierte momio americano (+150, -110, 290) a cuota decimal (2.50, 1.91, 3.90)."""
    if american is None:
        return None
    try:
        val_str = str(american).replace("+", "").strip()
        val = float(val_str)
        if val == 0:
            return None
        if val > 0:
            return round(1.0 + (val / 100.0), 3)
        else:
            return round(1.0 + (100.0 / abs(val)), 3)
    except Exception:
        return None


def american_to_prob(american: Any) -> Optional[float]:
    """Convierte momio americano a probabilidad implícita."""
    dec = american_to_decimal(american)
    if not dec or dec <= 1.0:
        return None
    return round(1.0 / dec, 4)


def normalizar_equipo_ligamx(nombre: str) -> str:
    """Normaliza el nombre del equipo a la denominación canónica de Liga MX."""
    if not nombre:
        return ""
    canon = canonical(nombre)
    return canon if canon else str(nombre).strip()


def obtener_calendario_y_cuotas_ligamx(
    fecha: Optional[str] = None,
    force_refresh: bool = False,
    ttl_minutes: int = 15
) -> List[Dict[str, Any]]:
    """Consulta la cartelera de Liga MX y sus cuotas de DraftKings desde ESPN.
    
    fecha: en formato YYYYMMDD o YYYY-MM-DD. Si es None, consulta la jornada en curso.
    """
    params: Dict[str, Any] = {"limit": 100}
    if fecha:
        params["dates"] = fecha.replace("-", "")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        data, _ = cached_get_json(
            URL_ESPN_LIGAMX,
            params=params,
            headers=headers,
            ttl_minutes=ttl_minutes,
            force_refresh=force_refresh
        )
    except Exception as err:
        logger.warning(f"Error al consultar ESPN Liga MX: {err}")
        return []

    if not data or "events" not in data:
        return []

    partidos = []
    for evento in data.get("events", []):
        try:
            ev_id = str(evento.get("id"))
            fecha_iso = evento.get("date", "")
            
            # Fecha y hora en CDMX
            dt_utc = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
            dt_cdmx = dt_utc.astimezone(ZONA_CDMX)

            comp = evento.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])

            home_comp = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away_comp = next((c for c in competitors if c.get("homeAway") == "away"), {})

            raw_home = home_comp.get("team", {}).get("displayName", "")
            raw_away = away_comp.get("team", {}).get("displayName", "")

            home_name = normalizar_equipo_ligamx(raw_home)
            away_name = normalizar_equipo_ligamx(raw_away)

            if not home_name or not away_name:
                continue

            # Estado del juego
            status_obj = evento.get("status", {}).get("type", {})
            estado = status_obj.get("name", "STATUS_SCHEDULED")
            desc_estado = status_obj.get("description", "")

            score_home = home_comp.get("score")
            score_away = away_comp.get("score")

            # Cuotas de DraftKings
            odds_list = comp.get("odds", [])
            odd = odds_list[0] if (odds_list and isinstance(odds_list[0], dict)) else {}
            provider_dict = odd.get("provider") if isinstance(odd.get("provider"), dict) else {}
            provider_name = provider_dict.get("name", "DraftKings")

            # Moneyline (1X2)
            ml_obj = odd.get("moneyline") if isinstance(odd.get("moneyline"), dict) else {}
            home_odds_obj = ml_obj.get("home") if isinstance(ml_obj.get("home"), dict) else {}
            away_odds_obj = ml_obj.get("away") if isinstance(ml_obj.get("away"), dict) else {}
            ml_home_close = (home_odds_obj.get("close") or home_odds_obj.get("open") or {}).get("odds") if isinstance(home_odds_obj.get("close") or home_odds_obj.get("open"), dict) else None
            ml_away_close = (away_odds_obj.get("close") or away_odds_obj.get("open") or {}).get("odds") if isinstance(away_odds_obj.get("close") or away_odds_obj.get("open"), dict) else None
            
            # Fallback a homeTeamOdds / awayTeamOdds
            if ml_home_close is None and isinstance(odd.get("homeTeamOdds"), dict):
                ml_home_close = odd["homeTeamOdds"].get("moneyLine")
            if ml_away_close is None and isinstance(odd.get("awayTeamOdds"), dict):
                ml_away_close = odd["awayTeamOdds"].get("moneyLine")

            # Empate
            draw_obj = odd.get("draw") if isinstance(odd.get("draw"), dict) else (odd.get("drawOdds") if isinstance(odd.get("drawOdds"), dict) else {})
            ml_draw_close = (draw_obj.get("close") or {}).get("odds") if isinstance(draw_obj.get("close"), dict) else draw_obj.get("moneyLine")

            # Totales (Over / Under)
            total_line = odd.get("overUnder", 2.5)
            tot_obj = odd.get("total") if isinstance(odd.get("total"), dict) else {}
            over_obj = tot_obj.get("over") if isinstance(tot_obj.get("over"), dict) else {}
            under_obj = tot_obj.get("under") if isinstance(tot_obj.get("under"), dict) else {}
            over_odds = (over_obj.get("close") or over_obj.get("open") or {}).get("odds") if isinstance(over_obj.get("close") or over_obj.get("open"), dict) else None
            under_odds = (under_obj.get("close") or under_obj.get("open") or {}).get("odds") if isinstance(under_obj.get("close") or under_obj.get("open"), dict) else None

            partidos.append({
                "id_evento": ev_id,
                "partido": f"{away_name} @ {home_name}",
                "equipo_visita": away_name,
                "equipo_local": home_name,
                "fecha_utc": fecha_iso,
                "fecha_cdmx": dt_cdmx.strftime("%Y-%m-%d"),
                "hora_cdmx": dt_cdmx.strftime("%H:%M"),
                "estado": estado,
                "descripcion_estado": desc_estado,
                "marcador_visita": int(score_away) if score_away is not None and str(score_away).isdigit() else None,
                "marcador_local": int(score_home) if score_home is not None and str(score_home).isdigit() else None,
                # Cuotas
                "provider": provider_name,
                "moneyline_local": ml_home_close,
                "moneyline_empate": ml_draw_close,
                "moneyline_visita": ml_away_close,
                "ml_local_dec": american_to_decimal(ml_home_close),
                "ml_empate_dec": american_to_decimal(ml_draw_close),
                "ml_visita_dec": american_to_decimal(ml_away_close),
                "ml_local_prob": american_to_prob(ml_home_close),
                "ml_empate_prob": american_to_prob(ml_draw_close),
                "ml_visita_prob": american_to_prob(ml_away_close),
                # Totales
                "linea_total": float(total_line) if total_line is not None else 2.5,
                "over_momio": over_odds,
                "under_momio": under_odds,
                "over_momio_dec": american_to_decimal(over_odds),
                "under_momio_dec": american_to_decimal(under_odds),
                "over_prob_implicita": american_to_prob(over_odds),
                "under_prob_implicita": american_to_prob(under_odds),
            })
        except Exception as e:
            logger.error(f"Error procesando partido de Liga MX {evento.get('id')}: {e}")
            continue

    return partidos


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("⚽ Consultando partidos y cuotas Liga MX desde ESPN...")
    juegos = obtener_calendario_y_cuotas_ligamx(force_refresh=True)
    print(f"✅ Partidos encontrados en la cartelera: {len(juegos)}")
    for j in juegos:
        print(f"\n[{j['fecha_cdmx']} {j['hora_cdmx']} CDMX] {j['partido']} ({j['estado']})")
        print(f"   ML: Local={j['moneyline_local']} ({j['ml_local_dec']}) | Empate={j['moneyline_empate']} ({j['ml_empate_dec']}) | Visita={j['moneyline_visita']} ({j['ml_visita_dec']})")
        print(f"   Total {j['linea_total']}: Over={j['over_momio']} ({j['over_momio_dec']}) | Under={j['under_momio']} ({j['under_momio_dec']})")
