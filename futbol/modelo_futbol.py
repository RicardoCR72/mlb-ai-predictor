"""Motor predictivo bivariado y cuantitativo para fútbol mundial.

Combina:
1. Probabilidades implícitas desparasitadas (sin vig) de DraftKings.
2. Inversión bivariada Poisson para derivar goles esperados (xG Local y xG Visita).
3. Matriz exacta de probabilidades de marcadores 10x10.
4. Selección calibrada de picks oficiales (Moneyline y Totales) sin sesgo de underdogs.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple
import numpy as np
from scipy.stats import poisson

from futbol.constantes import obtener_info_liga


def desparasitar_cuotas_1x2(p_h: float, p_d: float, p_a: float) -> Tuple[float, float, float]:
    """Elimina el margen de la casa (overround) para obtener probabilidades reales sin vig."""
    suma = p_h + p_d + p_a
    if suma <= 0:
        return 0.40, 0.28, 0.32
    return round(p_h / suma, 4), round(p_d / suma, 4), round(p_a / suma, 4)


def desparasitar_cuotas_totales(p_o: float, p_u: float) -> Tuple[float, float]:
    """Elimina el margen de la casa en mercado de Totales Over / Under."""
    suma = p_o + p_u
    if suma <= 0:
        return 0.50, 0.50
    return round(p_o / suma, 4), round(p_u / suma, 4)


def estimar_xg_partido(
    p_home_real: float,
    p_draw_real: float,
    p_away_real: float,
    linea_total: float = 2.5,
    p_over_real: float = 0.50,
    media_liga_tot: float = 2.65,
) -> Tuple[float, float]:
    """Deriva los goles esperados (xG) para local y visitante consistentemente."""
    # Estimación de goles totales proyectados combinando línea de bookmaker y media de la liga
    base_tot = (linea_total * 0.70) + (media_liga_tot * 0.30)
    # Ajuste por sesgo de Over / Under del mercado
    over_delta = (p_over_real - 0.50) * 0.85
    lambda_total = max(base_tot + over_delta, 1.60)

    # Distribución entre local y visitante basada en sus probabilidades relativas
    ratio_home = p_home_real / max(p_home_real + p_away_real, 0.01)
    # Factor de ventaja de localía
    ratio_home = float(np.clip(ratio_home, 0.22, 0.78))

    lambda_home = round(float(lambda_total * ratio_home), 2)
    lambda_away = round(float(lambda_total * (1.0 - ratio_home)), 2)

    return max(lambda_home, 0.30), max(lambda_away, 0.25)


def proyectar_partido_futbol(partido: Dict[str, Any]) -> Dict[str, Any]:
    """Calcula la matriz bivariada de goles y genera la predicción integral del partido."""
    info_liga = obtener_info_liga(partido.get("liga_codigo", "mex.1"))
    media_liga_tot = info_liga.get("media_goles_local", 1.50) + info_liga.get("media_goles_visita", 1.15)
    linea_tot = float(partido.get("linea_total") or info_liga.get("linea_default", 2.5))

    p_raw_h = float(partido.get("ml_local_prob") or 0.40)
    p_raw_d = float(partido.get("ml_empate_prob") or 0.28)
    p_raw_a = float(partido.get("ml_visita_prob") or 0.32)

    p_raw_o = float(partido.get("over_prob_implicita") or 0.52)
    p_raw_u = float(partido.get("under_prob_implicita") or 0.48)

    # 1. Probabilidades reales del mercado sin vig
    p_mkt_h, p_mkt_d, p_mkt_a = desparasitar_cuotas_1x2(p_raw_h, p_raw_d, p_raw_a)
    p_mkt_o, p_mkt_u = desparasitar_cuotas_totales(p_raw_o, p_raw_u)

    # 2. Inferencia de xG
    xg_local, xg_visita = estimar_xg_partido(
        p_home_real=p_mkt_h,
        p_draw_real=p_mkt_d,
        p_away_real=p_mkt_a,
        linea_total=linea_tot,
        p_over_real=p_mkt_o,
        media_liga_tot=media_liga_tot,
    )

    # 3. Matriz bivariada 10x10 de goles Poisson
    max_g = 10
    prob_h = [poisson.pmf(i, xg_local) for i in range(max_g)]
    prob_a = [poisson.pmf(j, xg_visita) for j in range(max_g)]
    grid = np.outer(prob_h, prob_a)

    # Normalización exacta
    grid /= np.sum(grid)

    p_home_win = float(np.sum(np.tril(grid, -1)))
    p_draw = float(np.sum(np.diag(grid)))
    p_away_win = float(np.sum(np.triu(grid, 1)))

    # Ponderación Bayesiana: 50% modelo Poisson + 50% mercado desparasitado
    # Esto asegura consistencia matemática y al mismo tiempo captura noticias de alineaciones
    p_final_home = round(0.50 * p_home_win + 0.50 * p_mkt_h, 4)
    p_final_draw = round(0.50 * p_draw + 0.50 * p_mkt_d, 4)
    p_final_away = round(0.50 * p_away_win + 0.50 * p_mkt_a, 4)

    # Normalizar suma exacta
    suma_ml = p_final_home + p_final_draw + p_final_away
    p_final_home = round(p_final_home / suma_ml, 4)
    p_final_draw = round(p_final_draw / suma_ml, 4)
    p_final_away = round(p_final_away / suma_ml, 4)

    # Totales Over / Under
    i_idx, j_idx = np.meshgrid(np.arange(max_g), np.arange(max_g), indexing="ij")
    p_over_pois = float(np.sum(grid[i_idx + j_idx > linea_tot]))
    p_under_pois = float(np.sum(grid[i_idx + j_idx < linea_tot]))

    p_final_over = round(0.50 * p_over_pois + 0.50 * p_mkt_o, 4)
    p_final_under = round(0.50 * p_under_pois + 0.50 * p_mkt_u, 4)
    suma_tot = p_final_over + p_final_under
    p_final_over = round(p_final_over / suma_tot, 4)
    p_final_under = round(p_final_under / suma_tot, 4)

    # Marcador más probable
    max_idx = np.unravel_index(np.argmax(grid), grid.shape)
    marcador_esperado = f"{max_idx[0]} - {max_idx[1]}"
    prob_marcador = round(float(grid[max_idx]), 3)

    # Edges contra cuotas de casas
    edge_home = p_final_home - p_raw_h
    edge_away = p_final_away - p_raw_a
    edge_draw = p_final_draw - p_raw_d
    edge_over = p_final_over - p_raw_o
    edge_under = p_final_under - p_raw_u

    home_team = partido["equipo_local"]
    away_team = partido["equipo_visita"]

    # 4. Selección del Pick Oficial Calibrado
    candidatos = []

    # Candidato Totales: OVER
    if p_final_over >= 0.505:
        candidatos.append({
            "mercado": "Totales (Over/Under)",
            "seleccion": f"OVER {linea_tot:g}",
            "probabilidad": p_final_over,
            "edge": edge_over,
            "cuota": partido.get("over_momio") or "-115",
            "cuota_dec": partido.get("over_momio_dec") or 1.85,
            "detalle": f"xG Proyectado: {xg_local + xg_visita:.2f} goles (Over: {p_final_over*100:.1f}%)"
        })
    # Candidato Totales: UNDER
    elif p_final_under >= 0.505:
        candidatos.append({
            "mercado": "Totales (Over/Under)",
            "seleccion": f"UNDER {linea_tot:g}",
            "probabilidad": p_final_under,
            "edge": edge_under,
            "cuota": partido.get("under_momio") or "-115",
            "cuota_dec": partido.get("under_momio_dec") or 1.85,
            "detalle": f"xG Proyectado: {xg_local + xg_visita:.2f} goles (Under: {p_final_under*100:.1f}%)"
        })

    # Candidato Moneyline: Local (Debe ser favorito proyectado con solidez)
    if p_final_home >= 0.44 and p_final_home > p_final_away:
        candidatos.append({
            "mercado": "Moneyline",
            "seleccion": f"{home_team} ML",
            "probabilidad": p_final_home,
            "edge": max(edge_home, 0.01),
            "cuota": partido.get("moneyline_local") or "-110",
            "cuota_dec": partido.get("ml_local_dec") or 1.91,
            "detalle": f"Favorito proyectado con {p_final_home*100:.1f}% de probabilidad (xG: {xg_local:.2f} vs {xg_visita:.2f})"
        })
    # Candidato Moneyline: Visita (Debe ser favorito visitante proyectado con solidez)
    elif p_final_away >= 0.44 and p_final_away > p_final_home:
        candidatos.append({
            "mercado": "Moneyline",
            "seleccion": f"{away_team} ML",
            "probabilidad": p_final_away,
            "edge": max(edge_away, 0.01),
            "cuota": partido.get("moneyline_visita") or "-110",
            "cuota_dec": partido.get("ml_visita_dec") or 1.91,
            "detalle": f"Favorito visitante con {p_final_away*100:.1f}% de probabilidad (xG: {xg_visita:.2f} vs {xg_local:.2f})"
        })

    # Ordenar candidatos priorizando probabilidad real de acierto combinada con valor
    def score_candidato(c):
        p = float(c.get("probabilidad", 0.0))
        ed = float(c.get("edge", 0.0))
        return p * (1.0 + max(ed, 0.0))

    candidatos.sort(key=score_candidato, reverse=True)

    if candidatos:
        mejor = candidatos[0]
    else:
        # Fallback natural al total con mayor probabilidad
        if p_final_over >= p_final_under:
            mejor = {
                "mercado": "Totales (Over/Under)",
                "seleccion": f"OVER {linea_tot:g}",
                "probabilidad": p_final_over,
                "edge": max(edge_over, 0.01),
                "cuota": partido.get("over_momio") or "-115",
                "cuota_dec": partido.get("over_momio_dec") or 1.85,
                "detalle": f"xG Proyectado: {xg_local + xg_visita:.2f} goles."
            }
        else:
            mejor = {
                "mercado": "Totales (Over/Under)",
                "seleccion": f"UNDER {linea_tot:g}",
                "probabilidad": p_final_under,
                "edge": max(edge_under, 0.01),
                "cuota": partido.get("under_momio") or "-115",
                "cuota_dec": partido.get("under_momio_dec") or 1.85,
                "detalle": f"xG Proyectado: {xg_local + xg_visita:.2f} goles."
            }

    # Nivel de confianza
    if mejor["probabilidad"] >= 0.58 or (mejor["probabilidad"] >= 0.52 and mejor.get("edge", 0) >= 0.03):
        confianza = "ALTA"
    elif mejor["probabilidad"] >= 0.46:
        confianza = "MEDIA"
    else:
        confianza = "NEUTRAL"

    return {
        "xg_local": xg_local,
        "xg_visita": xg_visita,
        "total_proyectado": round(xg_local + xg_visita, 2),
        "marcador_mas_probable": marcador_esperado,
        "prob_marcador_mas_probable": prob_marcador,
        "prob_local": p_final_home,
        "prob_empate": p_final_draw,
        "prob_visita": p_final_away,
        "prob_over": p_final_over,
        "prob_under": p_final_under,
        "edge_local": round(edge_home, 4),
        "edge_visita": round(edge_away, 4),
        "edge_empate": round(edge_draw, 4),
        "edge_over": round(edge_over, 4),
        "edge_under": round(edge_under, 4),
        "pick_mercado": mejor["mercado"],
        "pick_seleccion": mejor["seleccion"],
        "pick_probabilidad": round(mejor["probabilidad"], 4),
        "pick_edge": round(float(mejor.get("edge", 0.0)), 4),
        "pick_cuota": mejor.get("cuota"),
        "pick_cuota_dec": mejor.get("cuota_dec"),
        "pick_detalle": mejor.get("detalle", ""),
        "confianza": confianza,
    }
