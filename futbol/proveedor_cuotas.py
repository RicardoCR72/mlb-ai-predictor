"""Proveedor multilíga en tiempo real de partidos, cuotas y marcadores vía ESPN (DraftKings).

Soporta las 8 principales ligas del fútbol mundial:
- 🇲🇽 Liga MX (mex.1)
- 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League (eng.1)
- 🇪🇸 LaLiga (esp.1)
- 🇮🇹 Serie A (ita.1)
- 🇩🇪 Bundesliga (ger.1)
- 🇫🇷 Ligue 1 (fra.1)
- 🇳🇱 Eredivisie (ned.1)
- 🇺🇸 MLS (usa.1)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import requests

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.cache import cached_get_json
from core.constants import ZONA_CDMX
from futbol.constantes import LIGAS_DISPONIBLES, CODIGOS_LIGAS, obtener_info_liga

logger = logging.getLogger(__name__)

URL_ESPN_SOCCER_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def american_to_decimal(american: Any) -> Optional[float]:
    """Convierte momio americano (+150, -110, 290) a cuota decimal europea (2.50, 1.91, 3.90)."""
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
    """Calcula la probabilidad implícita pura desde momio americano."""
    dec = american_to_decimal(american)
    if not dec or dec <= 1.0:
        return None
    return round(1.0 / dec, 4)


def normalizar_momio_str(momio: Any) -> Optional[str]:
    """Asegura formato legible con signo para cuotas americanas (+140, -120)."""
    if momio is None:
        return None
    m_str = str(momio).strip()
    try:
        val = float(m_str.replace("+", ""))
        return f"+{int(val)}" if val > 0 else f"{int(val)}"
    except Exception:
        return m_str


def obtener_partidos_liga_espn(
    liga_code: str = "mex.1",
    fecha: Optional[str] = None,
    force_refresh: bool = False,
    ttl_minutes: int = 15,
) -> List[Dict[str, Any]]:
    """Consulta los partidos y cuotas oficiales de DraftKings para una liga específica desde ESPN."""
    info_liga = obtener_info_liga(liga_code)
    codigo = info_liga["codigo"]

    url = f"{URL_ESPN_SOCCER_BASE}/{codigo}/scoreboard"
    params: Dict[str, Any] = {"limit": 100}
    if fecha:
        params["dates"] = fecha.replace("-", "")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    try:
        data, _ = cached_get_json(
            url,
            params=params,
            headers=headers,
            ttl_minutes=ttl_minutes,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        logger.warning(f"Error consultando ESPN para {info_liga['nombre']} ({codigo}): {exc}")
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json() if resp.status_code == 200 else {}
        except Exception:
            return []

    if not data or "events" not in data:
        return []

    partidos: List[Dict[str, Any]] = []

    for evento in data.get("events", []):
        try:
            ev_id = str(evento.get("id", ""))
            fecha_iso = evento.get("date", "")

            # Conversión de fecha y hora a Zona Horaria CDMX
            fecha_cdmx, hora_cdmx = "", ""
            if fecha_iso:
                try:
                    dt_utc = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
                    dt_cdmx = dt_utc.astimezone(ZONA_CDMX)
                    fecha_cdmx = dt_cdmx.strftime("%Y-%m-%d")
                    hora_cdmx = dt_cdmx.strftime("%H:%M")
                except Exception:
                    fecha_cdmx = fecha_iso[:10]

            competitions = evento.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            competitors = comp.get("competitors", [])

            home_comp = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away_comp = next((c for c in competitors if c.get("homeAway") == "away"), {})

            team_home_obj = home_comp.get("team", {})
            team_away_obj = away_comp.get("team", {})

            home_name = team_home_obj.get("displayName") or team_home_obj.get("name") or ""
            away_name = team_away_obj.get("displayName") or team_away_obj.get("name") or ""

            if not home_name or not away_name:
                continue

            home_abbr = team_home_obj.get("abbreviation") or home_name[:3].upper()
            away_abbr = team_away_obj.get("abbreviation") or away_name[:3].upper()
            home_logo = team_home_obj.get("logo")
            away_logo = team_away_obj.get("logo")

            # Estado del juego
            status_obj = evento.get("status", {}).get("type", {})
            estado = status_obj.get("name", "STATUS_SCHEDULED")
            desc_estado = status_obj.get("shortDetail") or status_obj.get("description") or ""

            score_home = home_comp.get("score")
            score_away = away_comp.get("score")

            marcador_home = int(score_home) if score_home is not None and str(score_home).isdigit() else None
            marcador_away = int(score_away) if score_away is not None and str(score_away).isdigit() else None

            # Extracción segura de cuotas DraftKings
            odds_list = comp.get("odds", [])
            odd = odds_list[0] if (odds_list and isinstance(odds_list[0], dict)) else {}
            provider_dict = odd.get("provider") if isinstance(odd.get("provider"), dict) else {}
            provider_name = provider_dict.get("name", "DraftKings")

            # 1. Moneyline (1X2)
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

            # 2. Totales (Over / Under)
            total_line = odd.get("overUnder") or info_liga.get("linea_default", 2.5)
            tot_obj = odd.get("total") if isinstance(odd.get("total"), dict) else {}
            over_obj = tot_obj.get("over") if isinstance(tot_obj.get("over"), dict) else {}
            under_obj = tot_obj.get("under") if isinstance(tot_obj.get("under"), dict) else {}

            over_odds = (over_obj.get("close") or over_obj.get("open") or {}).get("odds") if isinstance(over_obj.get("close") or over_obj.get("open"), dict) else None
            under_odds = (under_obj.get("close") or under_obj.get("open") or {}).get("odds") if isinstance(under_obj.get("close") or under_obj.get("open"), dict) else None

            # 3. Ambos Anotan (BTTS) si está disponible en la respuesta del proveedor
            btts_obj = odd.get("bothTeamsToScore") or odd.get("btts") or odd.get("bothTeamsScore") or {}
            btts_yes = None
            btts_no = None
            if isinstance(btts_obj, dict):
                btts_yes = (btts_obj.get("yes") or btts_obj.get("close") or {}).get("odds") if isinstance(btts_obj.get("yes") or btts_obj.get("close"), dict) else btts_obj.get("yes")
                btts_no = (btts_obj.get("no") or {}).get("odds") if isinstance(btts_obj.get("no"), dict) else btts_obj.get("no")

            partidos.append({
                "id_evento": ev_id,
                "liga_codigo": codigo,
                "liga_nombre": info_liga["nombre"],
                "liga_bandera": info_liga["bandera"],
                "liga_pais": info_liga["pais"],
                "partido": f"{away_name} @ {home_name}",
                "equipo_local": home_name,
                "equipo_visita": away_name,
                "abbr_local": home_abbr,
                "abbr_visita": away_abbr,
                "logo_local": home_logo,
                "logo_visita": away_logo,
                "fecha_cdmx": fecha_cdmx,
                "hora_cdmx": hora_cdmx,
                "estado": estado,
                "descripcion_estado": desc_estado,
                "marcador_local": marcador_home,
                "marcador_visita": marcador_away,
                # Cuotas Oficiales
                "provider": provider_name,
                "moneyline_local": normalizar_momio_str(ml_home_close),
                "moneyline_empate": normalizar_momio_str(ml_draw_close),
                "moneyline_visita": normalizar_momio_str(ml_away_close),
                "ml_local_dec": american_to_decimal(ml_home_close),
                "ml_empate_dec": american_to_decimal(ml_draw_close),
                "ml_visita_dec": american_to_decimal(ml_away_close),
                "ml_local_prob": american_to_prob(ml_home_close),
                "ml_empate_prob": american_to_prob(ml_draw_close),
                "ml_visita_prob": american_to_prob(ml_away_close),
                # Totales Over / Under
                "linea_total": float(total_line) if total_line is not None else 2.5,
                "over_momio": normalizar_momio_str(over_odds),
                "under_momio": normalizar_momio_str(under_odds),
                "over_momio_dec": american_to_decimal(over_odds),
                "under_momio_dec": american_to_decimal(under_odds),
                "over_prob_implicita": american_to_prob(over_odds),
                "under_prob_implicita": american_to_prob(under_odds),
                # Ambos Anotan (BTTS) del proveedor
                "btts_si_momio": normalizar_momio_str(btts_yes),
                "btts_no_momio": normalizar_momio_str(btts_no),
                "btts_si_momio_dec": american_to_decimal(btts_yes),
                "btts_no_momio_dec": american_to_decimal(btts_no),
            })
        except Exception as exc:
            logger.error(f"Error procesando partido {evento.get('id')} de {liga_code}: {exc}")
            continue

    return partidos


def obtener_jornada_completa_futbol(
    ligas: Optional[List[str]] = None,
    dias_adelante: int = 3,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """Consulta la cartelera y cuotas de todas las ligas configuradas para la ventana de días solicitada."""
    ligas_a_consultar = ligas if ligas else CODIGOS_LIGAS
    hoy = datetime.now(ZONA_CDMX).date()
    fechas = [(hoy + timedelta(days=i)).strftime("%Y%m%d") for i in range(dias_adelante + 1)]

    juegos_por_id: Dict[str, Dict[str, Any]] = {}

    for liga_cod in ligas_a_consultar:
        # 1. Consulta cartelera activa del día
        partidos_dia = obtener_partidos_liga_espn(liga_code=liga_cod, force_refresh=force_refresh)
        for p in partidos_dia:
            juegos_por_id[p["id_evento"]] = p

        # 2. Fechas subsiguientes de la ventana
        for f_str in fechas:
            partidos_sub = obtener_partidos_liga_espn(liga_code=liga_cod, fecha=f_str, force_refresh=force_refresh)
            for p in partidos_sub:
                if p["id_evento"] not in juegos_por_id:
                    juegos_por_id[p["id_evento"]] = p

    lista = list(juegos_por_id.values())
    lista.sort(key=lambda x: (x.get("fecha_cdmx", ""), x.get("hora_cdmx", "")))
    return lista
