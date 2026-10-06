"""Proveedor ESPN para Liga MX — completamente gratuito, sin API key.

Usa el endpoint publico de ESPN para obtener los partidos de la temporada
activa (Apertura/Clausura). Complementa los datos historicos de openfootball.

Limitaciones:
- Admite consultas históricas por fecha; la recuperación valida fase y cobertura.
- El endpoint puede cambiar sin aviso (es no oficial).
- Barre dia a dia el rango de la temporada (usa cache local para evitar
  repetir peticiones ya procesadas).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

from .datos import COLUMNS, audit, complete, regular_counts

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard"
MX = ZoneInfo("America/Mexico_City")

FIXTURE_COLUMNS = ["fecha", "inicio_utc", "local", "visitante", "season", "ronda"]

ALIASES: dict[str, str] = {
    "america": "CF America",
    "club america": "CF America",
    "cf america": "CF America",
    "atlas": "Atlas Guadalajara",
    "atlas fc": "Atlas Guadalajara",
    "atlas guadalajara": "Atlas Guadalajara",
    "atletico san luis": "Atletico San Luis",
    "san luis": "Atletico San Luis",
    "monterrey": "CF Monterrey",
    "cf monterrey": "CF Monterrey",
    "pachuca": "CF Pachuca",
    "cf pachuca": "CF Pachuca",
    "leon": "Club Leon",
    "club leon": "Club Leon",
    "necaxa": "Club Necaxa",
    "club necaxa": "Club Necaxa",
    "tijuana": "Club Tijuana",
    "club tijuana": "Club Tijuana",
    "xolos": "Club Tijuana",
    "cruz azul": "Cruz Azul",
    "guadalajara": "Deportivo Guadalajara",
    "chivas": "Deportivo Guadalajara",
    "deportivo guadalajara": "Deportivo Guadalajara",
    "cd guadalajara": "Deportivo Guadalajara",
    "toluca": "Deportivo Toluca",
    "deportivo toluca": "Deportivo Toluca",
    "cd toluca": "Deportivo Toluca",
    "juarez": "FC Juarez",
    "fc juarez": "FC Juarez",
    "queretaro": "Gallos Blancos",
    "queretaro fc": "Gallos Blancos",
    "gallos blancos": "Gallos Blancos",
    "mazatlan": "Mazatlan FC",
    "mazatlan fc": "Mazatlan FC",
    "puebla": "Puebla FC",
    "puebla fc": "Puebla FC",
    "club puebla": "Puebla FC",
    "pumas": "Pumas UNAM",
    "pumas unam": "Pumas UNAM",
    "unam": "Pumas UNAM",
    "santos": "Santos Laguna",
    "santos laguna": "Santos Laguna",
    "tigres": "UANL Tigres",
    "tigres uanl": "UANL Tigres",
    "uanl tigres": "UANL Tigres",
    "tijuana xoloitzcuintles": "Club Tijuana",
    "atlante": "Atlante",
    "atlante fc": "Atlante",
    "atletico de san luis": "Atletico San Luis",
    "atletico san luis": "Atletico San Luis",
}


def canonical(name: str) -> str | None:
    key = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    key = re.sub(r"[^a-z0-9]+", " ", key).strip()
    if key in ALIASES:
        return ALIASES[key]
    primera = key.split()[0] if key.split() else ""
    if primera in ALIASES:
        return ALIASES[primera]
    return None  # Equipo no reconocido; se omite el partido


def get_scoreboard(fecha: str) -> list:
    url = BASE + "?" + urlencode({"dates": fecha, "limit": 200})
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "LigaMX-Research/3.0"})
    with urlopen(req, timeout=20) as r:
        data = json.loads(r.read(5_000_001))
    return data.get("events", [])


def inferir_jornada(events: list) -> dict[str, int]:
    """Infiere el numero de jornada (Matchday) de cada evento por su fecha.

    ESPN a veces no incluye el numero de semana. Como Liga MX juega jornadas
    concentradas en fines de semana, agrupamos las fechas y asignamos Matchday
    1, 2, 3... en orden cronologico dentro de cada torneo.
    """
    # Mapear event_id -> fecha local
    MX_z = ZoneInfo("America/Mexico_City")
    fechas_por_torneo: dict[str, set] = {}  # torneo -> set de fechas
    id_torneo_fecha: dict[str, tuple] = {}   # event_id -> (torneo, fecha)
    for ev in events:
        date_str = ev.get("date", "")
        eid = ev.get("id")
        if not date_str or not eid:
            continue
        try:
            utc_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            local_date = utc_dt.astimezone(MX_z).date()
        except (ValueError, TypeError):
            continue
        torneo = "Apertura" if local_date.month >= 7 else "Clausura"
        fechas_por_torneo.setdefault(torneo, set()).add(local_date)
        id_torneo_fecha[eid] = (torneo, local_date)

    # Para cada torneo: fecha -> numero de jornada (orden cronologico)
    matchday_map: dict[str, dict] = {}
    for torneo, fechas in fechas_por_torneo.items():
        # Agrupar fechas cercanas (mismo fin de semana = misma jornada)
        # Usamos ventana de 4 dias: si dos fechas difieren <= 4 dias, misma jornada.
        sorted_fechas = sorted(fechas)
        grupos: list[date] = []
        for f in sorted_fechas:
            if not grupos or (f - grupos[-1]).days > 4:
                grupos.append(f)
        # Asignar matchday por la fecha representativa del grupo
        fecha_a_md: dict[date, int] = {}
        for fecha in sorted_fechas:
            # Encontrar el grupo mas cercano
            grupo_idx = min(range(len(grupos)), key=lambda i: abs((fecha - grupos[i]).days))
            fecha_a_md[fecha] = grupo_idx + 1
        matchday_map[torneo] = fecha_a_md

    # Resultado: event_id -> numero de jornada
    resultado: dict[str, int] = {}
    for eid, (torneo, fecha) in id_torneo_fecha.items():
        md = matchday_map.get(torneo, {}).get(fecha)
        if md is not None:
            resultado[eid] = md
    return resultado


def parse_events(events: list, cutoff: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    results = []
    upcoming = []
    unknown_teams: set[str] = set()

    # Precalcular jornadas inferidas para todos los eventos
    # Las fechas no demuestran el número de jornada; usar únicamente el dato explícito.

    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue
        date_str = ev.get("date", "")
        if not date_str:
            continue
        try:
            utc_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            local_dt = utc_dt.astimezone(MX)
            local_date = local_dt.date()
        except (ValueError, TypeError):
            continue

        season_info = ev.get("season") or {}
        slug = season_info.get('slug', '')
        if slug and slug not in ('torneo-apertura', 'torneo-clausura'):
            continue  # Liguilla/play-in no entran al modelo de fase regular.
        season_year = local_date.year if local_date.month >= 7 else local_date.year - 1
        season_str = f"{season_year}-{str((season_year + 1) % 100).zfill(2)}"
        torneo = "Apertura" if local_date.month >= 7 else "Clausura"
        # Usar numero de semana de ESPN; si no lo incluye, usar jornada inferida por fecha
        week = ev.get("week")
        if isinstance(week, dict): week = week.get("number")
        if not isinstance(week, int) or not 1 <= week <= 17: week = None
        ronda = f"{torneo}, Matchday {week}" if week else f"{torneo}, fase regular"

        home_name = away_name = None
        home_score = away_score = 0
        for competitor in competitors:
            team_name = (competitor.get("team") or {}).get("displayName", "")
            canon = canonical(team_name)
            if canon is None:
                unknown_teams.add(team_name)
                continue
            side = competitor.get("homeAway")
            try:
                score = int(competitor.get("score") or 0)
            except (ValueError, TypeError):
                score = 0
            if side == "home":
                home_name, home_score = canon, score
            elif side == "away":
                away_name, away_score = canon, score

        if not home_name or not away_name or home_name == away_name:
            continue

        status = (ev.get("status", {}).get("type", {}) or {}).get("name", "")
        utc_iso = utc_dt.astimezone(timezone.utc).isoformat()

        if status in ("STATUS_FULL_TIME", "STATUS_FINAL") and local_date <= cutoff:
            results.append({
                "season": season_str, "fecha": local_date.isoformat(),
                "local": home_name, "visitante": away_name,
                "goles_local": home_score, "goles_visitante": away_score,
                "ronda": ronda, "source_file": "ESPN /scoreboard",
            })
        elif status in ("STATUS_SCHEDULED", "STATUS_TBD") and local_date >= cutoff:
            upcoming.append({
                "fecha": local_date.isoformat(), "inicio_utc": utc_iso,
                "local": home_name, "visitante": away_name,
                "season": season_str, "ronda": ronda,
            })

    if unknown_teams:
        print(f"  AVISO: equipos ESPN sin alias ({len(unknown_teams)}): {sorted(unknown_teams)}")
        print("  Agrega un alias en futbol_liga_mx/proveedor_espn.py::ALIASES si los necesitas.")

    past = pd.DataFrame(results, columns=COLUMNS) if results else pd.DataFrame(columns=COLUMNS)
    future = pd.DataFrame(upcoming, columns=FIXTURE_COLUMNS) if upcoming else pd.DataFrame(columns=FIXTURE_COLUMNS)
    return past, future


def load_cache(cache_dir: Path) -> dict:
    cache_file = cache_dir / "espn_events.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_cache(cache_dir: Path, cache: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "espn_events.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def cache_is_final(entry, day, cutoff):
    events = entry if isinstance(entry, list) else (entry or {}).get('events', [])
    return bool(events) and day < cutoff - timedelta(days=2) and all(
        (ev.get('status', {}).get('type', {}) or {}).get('name')
        in {'STATUS_FULL_TIME', 'STATUS_FINAL', 'STATUS_CANCELED'} for ev in events)


def run(
    partidos: str = "futbol_liga_mx/data/partidos.csv",
    proximos: str = "futbol_liga_mx/data/proximos.csv",
    cutoff: date | None = None,
    season_start: date | None = None,
    season_end: date | None = None,
    workers: int = 1,
    include_today: bool = False,
    strict: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descarga partidos ESPN de la temporada activa y actualiza los CSVs."""
    cutoff = cutoff or (datetime.now(MX).date() - timedelta(days=0 if include_today else 1))
    hoy = datetime.now(MX).date()

    if season_start is None:
        if hoy.month >= 7:
            season_start = date(hoy.year, 7, 1)
            season_end = season_end or date(hoy.year, 12, 31)
        else:
            season_start = date(hoy.year, 1, 1)
            season_end = season_end or date(hoy.year, 6, 30)
    if season_end is None:
        season_end = date(hoy.year, 12, 31)

    scan_end = min(season_end, hoy + timedelta(days=60))

    path = Path(partidos)
    if not path.exists():
        raise ValueError(f"Primero ejecuta futbol_liga_mx.datos: falta {path}")
    existing = pd.read_csv(path)

    cache_dir = Path(proximos).parent / "cache"
    cache = load_cache(cache_dir)

    all_events: dict[str, dict] = {}
    failed_days = []
    curr = season_start
    total_dias = (scan_end - season_start).days + 1
    print(f"Escaneando {total_dias} dias de ESPN ({season_start} a {scan_end})...")

    if not 1 <= workers <= 4: raise ValueError('workers debe estar entre 1 y 4.')
    days = [season_start+timedelta(days=i) for i in range(max(0,total_dias))]
    def fetch_day(day):
        key=day.strftime('%Y%m%d')
        entry=cache.get(key)
        if cache_is_final(entry,day,cutoff):
            return key,entry if isinstance(entry,list) else entry['events'],False,False
        try:return key,get_scoreboard(key),True,False
        except Exception as exc:
            print(f"  {key}: error ({type(exc).__name__}); se conservan resultados existentes")
            return key,[],False,True
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fecha_key,events_day,fetched,failed in pool.map(fetch_day,days):
            if fetched:cache[fecha_key]=events_day
            if failed:failed_days.append(fecha_key)
            for ev in events_day:
                eid=ev.get('id')
                if eid:all_events[eid]=ev

    save_cache(cache_dir, cache)
    if strict and failed_days:
        raise RuntimeError(f"ESPN no respondió en {len(failed_days)} fechas. Se conservó el historial anterior; vuelve a intentar.")
    print(f"Eventos unicos encontrados: {len(all_events)}")

    if not all_events:
        print("ESPN no devolvio eventos. Verifica la temporada activa.")
        return existing, pd.DataFrame(columns=FIXTURE_COLUMNS)

    past_new, future = parse_events(list(all_events.values()), cutoff)
    from .cobertura_actual import scan_report
    scanned = past_new[past_new.fecha.between(season_start.isoformat(),cutoff.isoformat())]
    report = scan_report(list(all_events.values()), scanned, season_start, cutoff, failed_days,allow_current_day=include_today)
    # Solo el escaneo completo desde el inicio del torneo reemplaza la evidencia.
    if season_start == date(2026,7,1) and scan_end >= cutoff:
        path.with_name('cobertura_actual.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f"  Resultados terminados: {len(past_new)}")
    print(f"  Proximos partidos: {len(future)}")

    if not past_new.empty:
        from .inferencia import normalize_teams
        merged = normalize_teams(pd.concat([existing[COLUMNS], past_new[COLUMNS]], ignore_index=True))
        merged = merged.drop_duplicates(['fecha', 'local', 'visitante'], keep='last')
        merged = audit(merged)
        path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(path, index=False)
        print(f"partidos.csv actualizado: {len(merged)} filas totales")
        existing = merged

    future_sorted = future.sort_values(["inicio_utc", "local"]).drop_duplicates(
        subset=["fecha", "local", "visitante"]
    )
    next_path = Path(proximos)
    next_path.parent.mkdir(parents=True, exist_ok=True)
    future_sorted.to_csv(next_path, index=False)
    print(f"proximos.csv: {len(future_sorted)} partidos proximos guardados")

    return existing, future_sorted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Proveedor ESPN Liga MX (sin API key)")
    parser.add_argument("--partidos", default="futbol_liga_mx/data/partidos.csv")
    parser.add_argument("--proximos", default="futbol_liga_mx/data/proximos.csv")
    parser.add_argument("--corte", type=date.fromisoformat, help="Ultimo dia finalizado (AAAA-MM-DD)")
    parser.add_argument("--desde", type=date.fromisoformat, help="Inicio del escaneo (AAAA-MM-DD)")
    parser.add_argument("--hasta", type=date.fromisoformat, help="Fin del escaneo (AAAA-MM-DD)")
    parser.add_argument("--workers", type=int, choices=range(1,5), default=1)
    args = parser.parse_args()
    run(partidos=args.partidos, proximos=args.proximos, cutoff=args.corte,
        season_start=args.desde, season_end=args.hasta, workers=args.workers)

