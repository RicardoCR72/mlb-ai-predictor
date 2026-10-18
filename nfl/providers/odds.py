"""Responsabilidad extraída del flujo CLI NFL."""
import requests
API_BASE = 'https://api.the-odds-api.com/v4'

def api_get(ruta: str, api_key: str, **parametros):
    params = {"apiKey": api_key, **parametros}
    try:
        respuesta = requests.get(f"{API_BASE}{ruta}", params=params, timeout=30)
    except requests.RequestException:
        raise RuntimeError("No se pudo conectar a The Odds API.") from None
    if respuesta.status_code != 200:
        raise RuntimeError(f"The Odds API respondio HTTP {respuesta.status_code}.")
    cuota = {
        "usados": respuesta.headers.get("x-requests-used"),
        "restantes": respuesta.headers.get("x-requests-remaining"),
        "costo": respuesta.headers.get("x-requests-last"),
    }
    return respuesta.json(), cuota
