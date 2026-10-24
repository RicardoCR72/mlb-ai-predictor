"""Módulo unificado de Fútbol Mundial para el Oráculo AI.

Cubre las 8 principales ligas del mundo con cuotas en tiempo real de DraftKings y
modelado bivariado calibrado:
- 🇲🇽 Liga MX
- 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
- 🇪🇸 LaLiga
- 🇮🇹 Serie A
- 🇩🇪 Bundesliga
- 🇫🇷 Ligue 1
- 🇳🇱 Eredivisie
- 🇺🇸 MLS
"""
from futbol.constantes import LIGAS_DISPONIBLES, CODIGOS_LIGAS, obtener_info_liga

__all__ = ["LIGAS_DISPONIBLES", "CODIGOS_LIGAS", "obtener_info_liga"]
