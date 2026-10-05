"""Un resumen diario de resultados y cuota para el Telegram del proyecto.

Solo /sports de The Odds API: consultar el saldo no gasta créditos.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX as MX, ZONA_MX as MAZATLAN
from core.db import get_db_connection


def get_json(url, *, headers=None, opener=urlopen):
    request = Request(url, headers=headers or {})
    with opener(request, timeout=30) as response:
        return json.load(response), response.headers


def saldo_odds(api_key, getter=get_json):
    if not api_key:
        return "No disponible: configura ODDS_API_KEY."
    url = "https://api.the-odds-api.com/v4/sports/?" + urlencode({"apiKey": api_key})
    _, headers = getter(url)
    used = headers.get("x-requests-used")
    remaining = headers.get("x-requests-remaining")
    if used is None or remaining is None:
        return "No disponible: la API no envió las cabeceras de cuota."
    return f"{used} usados · {remaining} restantes este mes"


def liga_mx_resultados(fecha, api_key, getter=get_json):
    """Solo marcadores de ayer: API-Football, ajena a los 500 créditos."""
    if not api_key:
        raise ValueError("Falta API_FOOTBALL_KEY.")
    base = "https://v3.football.api-sports.io/"
    headers = {"x-apisports-key": api_key}

    def fetch(endpoint, params):
        data, _ = getter(base + endpoint + "?" + urlencode(params), headers=headers)
        if data.get("errors") or not isinstance(data.get("response"), list):
            raise ValueError("API-Football no devolvió resultados válidos.")
        return data["response"]

    leagues = fetch("leagues", {"name": "Liga MX", "country": "Mexico"})
    ids = [row["league"]["id"] for row in leagues
           if row.get("league", {}).get("name") == "Liga MX"
           and row.get("country", {}).get("name") == "Mexico"]
    if len(ids) != 1:
        raise ValueError("No se pudo identificar Liga MX en API-Football.")
    season = fecha.year if fecha.month >= 7 else fecha.year - 1
    # Un juego nocturno de México puede pertenecer al día UTC siguiente.
    fechas_utc = [fecha, fecha + timedelta(days=1)]
    partidos = {}
    for day in fechas_utc:
        rows = fetch("fixtures", {
            "league": ids[0], "season": season, "date": day.isoformat(),
        })
        for row in rows:
            fixture = row.get("fixture", {})
            if fixture.get("status", {}).get("short") not in {"FT", "AET", "PEN"}:
                continue
            stamp = fixture.get("date", "")
            kickoff = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if kickoff.astimezone(MX).date() != fecha:
                continue
            home = row.get("teams", {}).get("home", {}).get("name")
            away = row.get("teams", {}).get("away", {}).get("name")
            goals = row.get("goals") or {}
            if home and away and all(isinstance(goals.get(team), int) for team in ("home", "away")):
                partidos[fixture["id"]] = f"{away} {goals['away']}–{goals['home']} {home}"
    return list(partidos.values())


def db_connection():
    return get_db_connection()


def resultados_db(connection, table, fecha):
    if table not in {"juegos", "nfl_juegos"}:
        raise ValueError("Tabla no permitida.")
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"SELECT equipo_visitante, marcador_visitante, marcador_local, equipo_local "
            f"FROM {table} WHERE DATE(fecha) = %s "
            "AND LOWER(estado) = 'finalizado' "
            "AND marcador_local IS NOT NULL AND marcador_visitante IS NOT NULL "
            "ORDER BY fecha, id_juego",
            (fecha.isoformat(),),
        )
        return [f"{away} {a}–{h} {home}" for away, a, h, home in cursor.fetchall()]
    finally:
        cursor.close()


def resultados_nfl_publicos(fecha):
    """Respaldo sin The Odds API si la tabla aún no recibió marcadores."""
    import nflreadpy as nfl

    season = fecha.year if fecha.month >= 3 else fecha.year - 1
    schedules = nfl.load_schedules([season]).to_pandas()
    if schedules.empty:
        return []
    dates = schedules["gameday"].astype(str).str[:10]
    games = schedules[(dates == fecha.isoformat())
                      & schedules["home_score"].notna()
                      & schedules["away_score"].notna()]
    return [f"{row.away_team} {int(row.away_score)}–{int(row.home_score)} {row.home_team}"
            for row in games.itertuples(index=False)]


def section(title, rows):
    if rows is None:
        return f"{title}: no se pudo consultar."
    if not rows:
        return f"{title}: sin partidos finalizados ayer."
    return f"{title}: {len(rows)} finalizados\n" + "\n".join(f"• {row}" for row in rows)


def build_report(mlb, nfl, soccer, quota, yesterday):
    return "\n\n".join([
        f"📊 Resultados del {yesterday:%d/%m/%Y}",
        section("⚾ MLB", mlb),
        section("🏈 NFL", nfl),
        section("⚽ Liga MX", soccer),
        f"💳 The Odds API: {quota}",
    ])


def send_telegram(message, token, chat_id):
    if not token or not chat_id:
        raise ValueError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
    # Telegram acepta hasta 4096 caracteres; preservar saldo y encabezados.
    if len(message) > 3900:
        message = message[:3800] + "\n… (mensaje abreviado)"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=25) as response:
            answer = json.load(response)
    except (HTTPError, URLError) as error:
        code = getattr(error, "code", "red")
        raise RuntimeError(f"Telegram no recibió el informe (HTTP {code}).") from None
    if answer.get("ok") is not True:
        raise RuntimeError("Telegram rechazó el mensaje.")


def main():
    yesterday = datetime.now(MX).date() - timedelta(days=1)
    mlb_yesterday = datetime.now(MAZATLAN).date() - timedelta(days=1)
    mlb = nfl = soccer = None
    try:
        conn = db_connection()
        try:
            mlb = resultados_db(conn, "juegos", mlb_yesterday)
        except Exception as error:
            print("MLB sin datos:", type(error).__name__)
        try:
            nfl = resultados_db(conn, "nfl_juegos", yesterday)
        except Exception as error:
            print("NFL sin datos:", type(error).__name__)
        conn.close()
    except Exception as error:
        print("Base de datos no disponible:", type(error).__name__)

    if not nfl:
        try:
            nfl = resultados_nfl_publicos(yesterday)
        except Exception as error:
            print("Calendario NFL no disponible:", type(error).__name__)

    try:
        soccer = liga_mx_resultados(yesterday, os.environ.get("API_FOOTBALL_KEY"))
    except Exception as error:
        print("Liga MX sin datos:", type(error).__name__)

    try:
        quota = saldo_odds(os.environ.get("ODDS_API_KEY") or os.environ.get("THE_ODDS_API_KEY"))
    except Exception as error:
        print("Saldo no disponible:", type(error).__name__)
        quota = "no disponible (error al consultar la API)"

    message = build_report(mlb, nfl, soccer, quota, yesterday)
    send_telegram(message, os.environ.get("TELEGRAM_BOT_TOKEN"),
                  os.environ.get("TELEGRAM_CHAT_ID"))
    print("Resumen enviado a Telegram. Cuota:", quota)


if __name__ == "__main__":
    main()
