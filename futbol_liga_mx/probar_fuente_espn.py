"""Inspecciona dos ventanas de ESPN Liga MX sin escribir archivos ni usar claves.

Este endpoint JSON público no tiene contrato formal de estabilidad. El objetivo
es comprobar cobertura y campos antes de convertirlo en proveedor del modelo.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard"
VENTANAS = (
    ("Apertura 2025", "20250701-20250731", "20250712"),
    ("Apertura 2026", "20260920-20261010", "20260927"),
)


def descargar(fechas, opener=urlopen):
    url = BASE + "?" + urlencode({"dates": fechas, "limit": 200})
    request = Request(url, headers={"Accept": "application/json",
                                    "User-Agent": "Mozilla/5.0"})
    with opener(request, timeout=25) as response:
        raw = response.read(3_000_001)
        if len(raw) > 3_000_000:
            raise ValueError("ESPN devolvió más de 3 MB; inspecciona el intervalo.")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise ValueError("No se encontró la lista de eventos de ESPN.")
    return data


def resumen(data, etiqueta):
    events = data["events"]
    print(f"\n{etiqueta}: {len(events)} eventos")
    print("campos raíz:", sorted(data.keys()))
    leagues = data.get("leagues") or []
    if leagues:
        print("liga:", [{"id": x.get("id"), "name": x.get("name")}
                         for x in leagues[:2]])
    statuses = {}
    for event in events:
        status = event.get("status") or {}
        kind = (status.get("type") or {}).get("name", "SIN_ESTADO")
        statuses[kind] = statuses.get(kind, 0) + 1
    print("estados:", statuses)
    for event in events[:2]:
        competition = (event.get("competitions") or [{}])[0]
        teams = [{"lado": c.get("homeAway"),
                  "equipo": (c.get("team") or {}).get("displayName"),
                  "marcador": c.get("score")}
                 for c in competition.get("competitors") or []]
        print("ejemplo:", json.dumps({
            "id": event.get("id"), "fecha": event.get("date"),
            "temporada": event.get("season"), "jornada": event.get("week"),
            "estado": event.get("status"),
            "competicion_campos": sorted(competition.keys()),
            "tipo_competicion": competition.get("type"),
            "ronda": competition.get("round"), "nota": competition.get("note"),
            "equipos": teams,
        }, ensure_ascii=False, default=str))


def main():
    for etiqueta, rango, fecha_segura in VENTANAS:
        try:
            data = descargar(rango)
            # Algunos endpoints ignoran los rangos. Una fecha conocida ayuda
            # a distinguir ese caso de ausencia real de la temporada.
            if not data["events"]:
                print(f"{etiqueta}: rango sin eventos; probando {fecha_segura}.")
                data = descargar(fecha_segura)
            resumen(data, etiqueta)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            code = getattr(exc, "code", "")
            print(f"{etiqueta}: ERROR {type(exc).__name__} {code}. {exc}")


if __name__ == "__main__":
    main()
