"""Sistema de caché local en disco con TTL (Time To Live) para llamadas HTTP de cuotas."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional
import requests

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"


def _get_cache_path(url: str, params: Optional[dict[str, Any]] = None) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_key = f"{url}?{json.dumps(params or {}, sort_keys=True)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key_hash}.json"


def cached_get_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    ttl_minutes: int = 20,
    force_refresh: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Realiza una petición GET o retorna el resultado cacheado si no ha expirado el TTL.
    
    Ahorra créditos valiosos de The Odds API evitando consultas duplicadas dentro de la ventana de tiempo.
    """
    cache_file = _get_cache_path(url, params)
    now = time.time()

    # Verificar si existe caché válido
    if not force_refresh and cache_file.exists():
        try:
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            timestamp = cached_data.get("_timestamp", 0)
            if now - timestamp < (ttl_minutes * 60):
                return cached_data.get("data"), cached_data.get("headers", {})
        except Exception:
            pass  # Si el archivo está corrupto, hacer la petición de red

    # Petición de red real
    response = requests.get(url, params=params, headers=headers or {}, timeout=35)
    response.raise_for_status()
    data = response.json()
    resp_headers = dict(response.headers)

    # Guardar en caché
    try:
        payload = {
            "_timestamp": now,
            "data": data,
            "headers": {
                "x-requests-remaining": resp_headers.get("x-requests-remaining"),
                "x-requests-used": resp_headers.get("x-requests-used"),
                "x-requests-last": resp_headers.get("x-requests-last"),
            }
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as err:
        print(f"⚠️ No se pudo guardar caché: {err}")

    return data, resp_headers
