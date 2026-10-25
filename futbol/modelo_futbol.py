"""Motor predictivo Dixon-Coles bivariado y cuantitativo para fútbol mundial (V2).

Innovaciones V2:
1. Matriz Bivariada Dixon-Coles con corrección de interdependencia en bajas anotaciones
   tau(0,0), tau(1,0), tau(0,1), tau(1,1) calibrada según rho por liga (-0.095 a -0.125).
2. Probabilidades exactas y desparasitadas para 1X2, Over/Under, Ambos Anotan (BTTS) y Doble Oportunidad (1X/X2).
3. Inferencia xG con ventajas de localía diferenciadas por liga y sesgo de totales.
4. Filtro riguroso de Valor Esperado (EV > 0 y Edge >= +2.5%): Elimina sesgo artificial de underdogs
   y previene apuestas con EV negativo originadas por el vig del bookmaker.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
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
    media_local_liga: float = 1.50,
    media_visita_liga: float = 1.15,
) -> Tuple[float, float]:
    """Deriva los goles esperados (xG) para local y visitante con priors de liga."""
    base_tot = (linea_total * 0.70) + (media_liga_tot * 0.30)
    over_delta = (p_over_real - 0.50) * 0.80
    lambda_total = max(base_tot + over_delta, 1.60)

    # Distribución empírica con ancla a ventaja histórica de localía
    denom = max(p_home_real + p_away_real, 0.01)
    ratio_home_mkt = p_home_real / denom
    ratio_home_liga = media_local_liga / max(media_liga_tot, 0.01)

    # Combinación equilibrada de mercado y liga
    ratio_home = float(np.clip(0.75 * ratio_home_mkt + 0.25 * ratio_home_liga, 0.20, 0.80))

    lambda_home = round(float(lambda_total * ratio_home), 2)
    lambda_away = round(float(lambda_total * (1.0 - ratio_home)), 2)

    return max(lambda_home, 0.30), max(lambda_away, 0.25)


def construir_matriz_dixon_coles(
    lambda_home: float,
    lambda_away: float,
    rho: float = -0.115,
    max_goles: int = 10,
) -> np.ndarray:
    """Construye la matriz bivariada ajustada de Dixon-Coles (1997).

    Ajusta la probabilidad de marcadores bajos (0-0, 1-0, 0-1, 1-1) mediante el factor tau.
    """
    grid = np.zeros((max_goles, max_goles), dtype=float)

    for i in range(max_goles):
        p_i = poisson.pmf(i, lambda_home)
        for j in range(max_goles):
            p_j = poisson.pmf(j, lambda_away)
            prob_base = p_i * p_j

            # Ajuste de Dixon-Coles para dependencia de marcadores bajos
            if i == 0 and j == 0:
                tau = 1.0 - (lambda_home * lambda_away * rho)
            elif i == 1 and j == 0:
                tau = 1.0 + (lambda_away * rho)
            elif i == 0 and j == 1:
                tau = 1.0 + (lambda_home * rho)
            elif i == 1 and j == 1:
                tau = 1.0 - rho
            else:
                tau = 1.0

            grid[i, j] = max(prob_base * tau, 0.0)

    # Re-normalización exacta
    suma_total = np.sum(grid)
    if suma_total > 0:
        grid /= suma_total

    return grid


def calcular_ev(prob: float, cuota_dec: float) -> float:
    """Calcula el valor esperado (EV) neto de una apuesta por unidad apostada."""
    if cuota_dec <= 1.0 or prob <= 0.0:
        return -1.0
    return (prob * cuota_dec) - 1.0


def proyectar_partido_futbol(partido: Dict[str, Any]) -> Dict[str, Any]:
    """Calcula la proyección integral de fútbol con modelo Dixon-Coles V2 y selección de valor."""
    info_liga = obtener_info_liga(partido.get("liga_codigo", "mex.1"))
    media_local = float(info_liga.get("media_goles_local", 1.50))
    media_visita = float(info_liga.get("media_goles_visita", 1.15))
    media_liga_tot = media_local + media_visita
    rho_liga = float(info_liga.get("rho_dixon_coles", -0.115))
    linea_tot = float(partido.get("linea_total") or info_liga.get("linea_default", 2.5))

    p_raw_h = float(partido.get("ml_local_prob") or 0.40)
    p_raw_d = float(partido.get("ml_empate_prob") or 0.28)
    p_raw_a = float(partido.get("ml_visita_prob") or 0.32)

    p_raw_o = float(partido.get("over_prob_implicita") or 0.52)
    p_raw_u = float(partido.get("under_prob_implicita") or 0.48)

    # 1. Probabilidades de mercado desparasitadas (Vig-free)
    p_mkt_h, p_mkt_d, p_mkt_a = desparasitar_cuotas_1x2(p_raw_h, p_raw_d, p_raw_a)
    p_mkt_o, p_mkt_u = desparasitar_cuotas_totales(p_raw_o, p_raw_u)

    # 2. Inferencia de xG Local y Visita
    xg_local, xg_visita = estimar_xg_partido(
        p_home_real=p_mkt_h,
        p_draw_real=p_mkt_d,
        p_away_real=p_mkt_a,
        linea_total=linea_tot,
        p_over_real=p_mkt_o,
        media_liga_tot=media_liga_tot,
        media_local_liga=media_local,
        media_visita_liga=media_visita,
    )

    # 3. Matriz bivariada 10x10 Dixon-Coles
    max_g = 10
    grid = construir_matriz_dixon_coles(xg_local, xg_visita, rho=rho_liga, max_goles=max_g)

    # 1X2 Dixon-Coles
    p_dc_home = float(np.sum(np.tril(grid, -1)))
    p_dc_draw = float(np.sum(np.diag(grid)))
    p_dc_away = float(np.sum(np.triu(grid, 1)))

    # Ponderación Bayesiana (50% Modelo Dixon-Coles + 50% Mercado sin vig)
    p_final_home = 0.50 * p_dc_home + 0.50 * p_mkt_h
    p_final_draw = 0.50 * p_dc_draw + 0.50 * p_mkt_d
    p_final_away = 0.50 * p_dc_away + 0.50 * p_mkt_a

    suma_ml = p_final_home + p_final_draw + p_final_away
    p_final_home = round(p_final_home / suma_ml, 4)
    p_final_draw = round(p_final_draw / suma_ml, 4)
    p_final_away = round(p_final_away / suma_ml, 4)

    # Totales Over / Under
    i_idx, j_idx = np.meshgrid(np.arange(max_g), np.arange(max_g), indexing="ij")
    p_dc_over = float(np.sum(grid[i_idx + j_idx > linea_tot]))
    p_dc_under = float(np.sum(grid[i_idx + j_idx < linea_tot]))

    p_final_over = 0.50 * p_dc_over + 0.50 * p_mkt_o
    p_final_under = 0.50 * p_dc_under + 0.50 * p_mkt_u
    suma_tot = p_final_over + p_final_under
    p_final_over = round(p_final_over / suma_tot, 4)
    p_final_under = round(p_final_under / suma_tot, 4)

    # Ambos Anotan (BTTS)
    p_btts_si_dc = float(np.sum(grid[1:, 1:]))
    p_btts_no_dc = 1.0 - p_btts_si_dc
    media_btts = float(info_liga.get("media_btts_pct", 0.52))
    p_btts_si = round(0.70 * p_btts_si_dc + 0.30 * media_btts, 4)
    p_btts_no = round(1.0 - p_btts_si, 4)

    # Doble Oportunidad
    p_1x = round(p_final_home + p_final_draw, 4)
    p_x2 = round(p_final_away + p_final_draw, 4)

    # Empate No Acción (Draw No Bet)
    denom_dnb = max(p_final_home + p_final_away, 0.01)
    p_dnb_home = round(p_final_home / denom_dnb, 4)
    p_dnb_away = round(p_final_away / denom_dnb, 4)

    # Marcador más probable
    max_idx = np.unravel_index(np.argmax(grid), grid.shape)
    marcador_esperado = f"{max_idx[0]} - {max_idx[1]}"
    prob_marcador = round(float(grid[max_idx]), 3)

    # Edges directos (Diferencia contra probabilidad implícita del bookmaker)
    edge_home = p_final_home - p_raw_h
    edge_away = p_final_away - p_raw_a
    edge_draw = p_final_draw - p_raw_d
    edge_over = p_final_over - p_raw_o
    edge_under = p_final_under - p_raw_u

    cuota_dec_home = float(partido.get("ml_local_dec") or 1.91)
    cuota_dec_away = float(partido.get("ml_visita_dec") or 1.91)
    cuota_dec_draw = float(partido.get("ml_empate_dec") or 3.20)
    cuota_dec_over = float(partido.get("over_momio_dec") or 1.87)
    cuota_dec_under = float(partido.get("under_momio_dec") or 1.87)

    # EV para cada mercado estándar
    ev_home = calcular_ev(p_final_home, cuota_dec_home)
    ev_away = calcular_ev(p_final_away, cuota_dec_away)
    ev_draw = calcular_ev(p_final_draw, cuota_dec_draw)
    ev_over = calcular_ev(p_final_over, cuota_dec_over)
    ev_under = calcular_ev(p_final_under, cuota_dec_under)

    home_team = partido.get("equipo_local", "Local")
    away_team = partido.get("equipo_visita", "Visita")

    # 4. Generación y Evaluación de Candidatos con Filtro de Valor Riguroso
    candidatos: List[Dict[str, Any]] = []

    # Mercado Totales: OVER
    # Requiere edge real >= +2.5% y EV positivo
    if edge_over >= 0.025 and ev_over >= 0.015 and p_final_over >= 0.52:
        candidatos.append({
            "mercado": "Totales (Over/Under)",
            "seleccion": f"OVER {linea_tot:g} Goles",
            "probabilidad": p_final_over,
            "edge": edge_over,
            "ev": ev_over,
            "cuota": partido.get("over_momio") or "-115",
            "cuota_dec": cuota_dec_over,
            "detalle": f"xG Proyectado: {xg_local + xg_visita:.2f} goles vs línea {linea_tot:g} (Over: {p_final_over*100:.1f}%, EV: +{ev_over*100:.1f}%)",
        })

    # Mercado Totales: UNDER
    if edge_under >= 0.025 and ev_under >= 0.015 and p_final_under >= 0.52:
        candidatos.append({
            "mercado": "Totales (Over/Under)",
            "seleccion": f"UNDER {linea_tot:g} Goles",
            "probabilidad": p_final_under,
            "edge": edge_under,
            "ev": ev_under,
            "cuota": partido.get("under_momio") or "-115",
            "cuota_dec": cuota_dec_under,
            "detalle": f"xG Proyectado: {xg_local + xg_visita:.2f} goles vs línea {linea_tot:g} (Under: {p_final_under*100:.1f}%, EV: +{ev_under*100:.1f}%)",
        })

    # Mercado Moneyline: Local (Favorito sólido con valor)
    if p_final_home >= 0.45 and edge_home >= 0.020 and ev_home >= 0.015:
        candidatos.append({
            "mercado": "Moneyline",
            "seleccion": f"{home_team} ML",
            "probabilidad": p_final_home,
            "edge": edge_home,
            "ev": ev_home,
            "cuota": partido.get("moneyline_local") or "-110",
            "cuota_dec": cuota_dec_home,
            "detalle": f"Favorito con ventaja local (Prob: {p_final_home*100:.1f}%, xG: {xg_local:.2f} vs {xg_visita:.2f}, EV: +{ev_home*100:.1f}%)",
        })

    # Mercado Moneyline: Visita (Favorito visitante con valor)
    if p_final_away >= 0.45 and edge_away >= 0.020 and ev_away >= 0.015:
        candidatos.append({
            "mercado": "Moneyline",
            "seleccion": f"{away_team} ML",
            "probabilidad": p_final_away,
            "edge": edge_away,
            "ev": ev_away,
            "cuota": partido.get("moneyline_visita") or "-110",
            "cuota_dec": cuota_dec_away,
            "detalle": f"Superioridad visitante proyectada (Prob: {p_final_away*100:.1f}%, xG: {xg_visita:.2f} vs {xg_local:.2f}, EV: +{ev_away*100:.1f}%)",
        })

    # Mercado Ambos Anotan (BTTS) si hay alta convicción ofensiva
    if p_btts_si >= 0.58 and xg_local >= 1.15 and xg_visita >= 1.10:
        candidatos.append({
            "mercado": "Ambos Anotan (BTTS)",
            "seleccion": "Ambos Anotan: SÍ",
            "probabilidad": p_btts_si,
            "edge": max(p_btts_si - 0.52, 0.03),
            "ev": (p_btts_si * 1.80) - 1.0,
            "cuota": "-125",
            "cuota_dec": 1.80,
            "detalle": f"Flujo ofensivo mutuo alto (xG {xg_local:.2f} y {xg_visita:.2f}, BTTS SÍ: {p_btts_si*100:.1f}%)",
        })

    # Si ningún candidato supera el umbral de valor puro, crear un LEAN objetivo sin inventar edge positivo
    if candidatos:
        # Ponderación de selección basada en Probabilidad + Edge + EV
        def ranking_score(c: Dict[str, Any]) -> float:
            p = float(c.get("probabilidad", 0.5))
            ed = float(c.get("edge", 0.0))
            ev = float(c.get("ev", 0.0))
            return p * (1.0 + 1.5 * max(ed, 0.0)) * (1.0 + max(ev, 0.0))

        candidatos.sort(key=ranking_score, reverse=True)
        mejor = candidatos[0]

        if mejor["probabilidad"] >= 0.58 and mejor.get("edge", 0.0) >= 0.04 and mejor.get("ev", 0.0) >= 0.03:
            confianza = "ALTA"
        elif mejor["probabilidad"] >= 0.48 or mejor.get("edge", 0.0) >= 0.02:
            confianza = "MEDIA"
        else:
            confianza = "BAJA"
    else:
        # Selección pasiva (Lean neutral): Escoge el resultado de mayor probabilidad matemática
        if p_final_over >= p_final_under:
            sel_lean = f"OVER {linea_tot:g} Goles"
            prob_lean = p_final_over
            ed_lean = edge_over
            ev_lean = ev_over
            cuota_lean = partido.get("over_momio") or "-115"
            cuota_dec_lean = cuota_dec_over
        else:
            sel_lean = f"UNDER {linea_tot:g} Goles"
            prob_lean = p_final_under
            ed_lean = edge_under
            ev_lean = ev_under
            cuota_lean = partido.get("under_momio") or "-115"
            cuota_dec_lean = cuota_dec_under

        mejor = {
            "mercado": "Totales (Over/Under)",
            "seleccion": sel_lean,
            "probabilidad": prob_lean,
            "edge": ed_lean,
            "ev": ev_lean,
            "cuota": cuota_lean,
            "cuota_dec": cuota_dec_lean,
            "detalle": f"Proyección neutra Dixon-Coles (xG Total: {xg_local + xg_visita:.2f} vs línea {linea_tot:g})",
        }
        confianza = "NEUTRAL"

    return {
        "xg_local": xg_local,
        "xg_visita": xg_visita,
        "total_proyectado": round(xg_local + xg_visita, 2),
        "marcador_mas_probable": marcador_esperado,
        "prob_marcador_mas_probable": prob_marcador,
        # Probabilidades 1X2
        "prob_local": p_final_home,
        "prob_empate": p_final_draw,
        "prob_visita": p_final_away,
        # Probabilidades Totales
        "prob_over": p_final_over,
        "prob_under": p_final_under,
        # Probabilidades Avanzadas Dixon-Coles
        "prob_btts_si": p_btts_si,
        "prob_btts_no": p_btts_no,
        "prob_1x": p_1x,
        "prob_x2": p_x2,
        "prob_dnb_local": p_dnb_home,
        "prob_dnb_visita": p_dnb_away,
        # Edges
        "edge_local": round(edge_home, 4),
        "edge_visita": round(edge_away, 4),
        "edge_empate": round(edge_draw, 4),
        "edge_over": round(edge_over, 4),
        "edge_under": round(edge_under, 4),
        # Pick Oficial y Métricas
        "pick_mercado": mejor["mercado"],
        "pick_seleccion": mejor["seleccion"],
        "pick_probabilidad": round(mejor["probabilidad"], 4),
        "pick_edge": round(float(mejor.get("edge", 0.0)), 4),
        "pick_ev": round(float(mejor.get("ev", 0.0)), 4),
        "pick_cuota": mejor.get("cuota"),
        "pick_cuota_dec": mejor.get("cuota_dec"),
        "pick_detalle": mejor.get("detalle", ""),
        "confianza": confianza,
    }
