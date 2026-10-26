"""Constantes y configuración de ligas de fútbol mundial."""
from __future__ import annotations

from typing import Any, Dict

LIGAS_DISPONIBLES: Dict[str, Dict[str, Any]] = {
    "eng.1": {
        "codigo": "eng.1",
        "nombre": "Premier League",
        "pais": "Inglaterra",
        "bandera": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "logo_id": "premier_league",
        "color": "#38003c",
        "color_acento": "#00ff85",
        "media_goles_local": 1.68,
        "media_goles_visita": 1.34,
        "linea_default": 2.5,
        "rho_dixon_coles": -0.110,
        "media_btts_pct": 0.54,
    },
    "esp.1": {
        "codigo": "esp.1",
        "nombre": "LaLiga",
        "pais": "España",
        "bandera": "🇪🇸",
        "logo_id": "laliga",
        "color": "#111827",
        "color_acento": "#ff4b44",
        "media_goles_local": 1.45,
        "media_goles_visita": 1.10,
        "linea_default": 2.5,
        "rho_dixon_coles": -0.125,
        "media_btts_pct": 0.49,
    },
    "mex.1": {
        "codigo": "mex.1",
        "nombre": "Liga MX",
        "pais": "México",
        "bandera": "🇲🇽",
        "logo_id": "ligamx",
        "color": "#06140d",
        "color_acento": "#00e676",
        "media_goles_local": 1.48,
        "media_goles_visita": 1.15,
        "linea_default": 2.5,
        "rho_dixon_coles": -0.120,
        "media_btts_pct": 0.52,
    },
    "ita.1": {
        "codigo": "ita.1",
        "nombre": "Serie A",
        "pais": "Italia",
        "bandera": "🇮🇹",
        "logo_id": "serie_a",
        "color": "#002d62",
        "color_acento": "#008fd7",
        "media_goles_local": 1.44,
        "media_goles_visita": 1.16,
        "linea_default": 2.5,
        "rho_dixon_coles": -0.125,
        "media_btts_pct": 0.50,
    },
    "ger.1": {
        "codigo": "ger.1",
        "nombre": "Bundesliga",
        "pais": "Alemania",
        "bandera": "🇩🇪",
        "logo_id": "bundesliga",
        "color": "#d20515",
        "color_acento": "#ffffff",
        "media_goles_local": 1.74,
        "media_goles_visita": 1.38,
        "linea_default": 3.0,
        "rho_dixon_coles": -0.095,
        "media_btts_pct": 0.58,
    },
    "fra.1": {
        "codigo": "fra.1",
        "nombre": "Ligue 1",
        "pais": "Francia",
        "bandera": "🇫🇷",
        "logo_id": "ligue_1",
        "color": "#091c3e",
        "color_acento": "#dae025",
        "media_goles_local": 1.50,
        "media_goles_visita": 1.18,
        "linea_default": 2.5,
        "rho_dixon_coles": -0.115,
        "media_btts_pct": 0.51,
    },
    "ned.1": {
        "codigo": "ned.1",
        "nombre": "Eredivisie",
        "pais": "Países Bajos",
        "bandera": "🇳🇱",
        "logo_id": "eredivisie",
        "color": "#172340",
        "color_acento": "#00a3e0",
        "media_goles_local": 1.76,
        "media_goles_visita": 1.36,
        "linea_default": 3.0,
        "rho_dixon_coles": -0.095,
        "media_btts_pct": 0.59,
    },
    "usa.1": {
        "codigo": "usa.1",
        "nombre": "MLS",
        "pais": "Estados Unidos",
        "bandera": "🇺🇸",
        "logo_id": "mls",
        "color": "#0b2240",
        "color_acento": "#e03a3e",
        "media_goles_local": 1.62,
        "media_goles_visita": 1.25,
        "linea_default": 2.5,
        "rho_dixon_coles": -0.105,
        "media_btts_pct": 0.56,
    },
}

CODIGOS_LIGAS = list(LIGAS_DISPONIBLES.keys())


def obtener_info_liga(codigo_o_nombre: str) -> Dict[str, Any]:
    """Retorna los metadatos de una liga por código o por nombre."""
    if not codigo_o_nombre:
        return LIGAS_DISPONIBLES["mex.1"]
    
    val = str(codigo_o_nombre).strip().lower()
    if val in LIGAS_DISPONIBLES:
        return LIGAS_DISPONIBLES[val]
    
    for liga in LIGAS_DISPONIBLES.values():
        if val == liga["nombre"].lower() or val in liga["nombre"].lower():
            return liga
        
    return {
        "codigo": val,
        "nombre": codigo_o_nombre,
        "pais": "Internacional",
        "bandera": "⚽",
        "color": "#06140d",
        "color_acento": "#00e676",
        "media_goles_local": 1.50,
        "media_goles_visita": 1.20,
        "linea_default": 2.5,
    }


_MEDIAS_GOLES_CACHE: Dict[str, tuple[float, float]] = {}


def obtener_medias_goles_liga(liga_codigo: str, defaults: tuple[float, float] = (1.50, 1.15)) -> tuple[float, float]:
    """Estima la media de goles local y visitante desde el histórico de partidos finalizados en la BD.

    Aplica regularización bayesiana empírica para estabilizar ligas con muestras incipientes hacia el prior de liga.
    """
    if liga_codigo in _MEDIAS_GOLES_CACHE:
        return _MEDIAS_GOLES_CACHE[liga_codigo]

    try:
        from core.infrastructure.database import query_df
        sql = """
            SELECT AVG(marcador_local) AS media_loc, AVG(marcador_visita) AS media_vis, COUNT(*) AS n
            FROM futbol_predicciones
            WHERE liga_codigo = %s AND marcador_local IS NOT NULL AND marcador_visita IS NOT NULL
        """
        df = query_df(sql, (liga_codigo,))
        if not df.empty and df.iloc[0]['n'] is not None and df.iloc[0]['n'] >= 10:
            obs_loc = float(df.iloc[0]['media_loc'])
            obs_vis = float(df.iloc[0]['media_vis'])
            n = int(df.iloc[0]['n'])
            peso_obs = min(0.85, n / (n + 25.0))
            m_loc = peso_obs * obs_loc + (1.0 - peso_obs) * defaults[0]
            m_vis = peso_obs * obs_vis + (1.0 - peso_obs) * defaults[1]
            res = (round(m_loc, 3), round(m_vis, 3))
            _MEDIAS_GOLES_CACHE[liga_codigo] = res
            return res
    except Exception:
        pass

    _MEDIAS_GOLES_CACHE[liga_codigo] = defaults
    return defaults
