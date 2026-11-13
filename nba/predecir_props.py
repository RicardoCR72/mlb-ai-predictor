"""Motor predictivo y de valor esperado (EV) para Player Props NBA.

Combina:
1. Líneas y cuotas en tiempo real de Bovada (0 créditos).
2. Estadísticas de temporada 2026-27 y tendencia reciente (L5) de ESPN.
3. Impacto de lesiones en tiempo real de compañeros de equipo (Usage Boost).
4. Modelado probabilístico (Poisson para Triples/Asistencias/Rebotes, Gaussiano/Empírico para Puntos/PRA).
5. Cálculo de Valor Esperado (EV%) y asignación de estrellas de confianza.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX
from nba.servicio_bovada_props import extraer_props_nba, _limpiar_nombre_jugador
from nba.servicio_jugadores_boxscores import (
    RUTA_PARQUET_JUGADORES,
    sincronizar_boxscores_jugadores,
    calcular_perfil_jugador
)
from nba.servicio_lesiones import obtener_reporte_lesiones_nba

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nba_predecir_props")

DIR_PRED = RAIZ / "data" / "nba" / "predictions"
RUTA_PRED_PARQUET = DIR_PRED / "predicciones_props_nba_hoy.parquet"
RUTA_PRED_JSON = DIR_PRED / "predicciones_props_nba_hoy.json"

MAPA_SIGLAS_CANONICAS = {
    "GS": "GSW", "GSW": "GSW", "GOLDEN STATE WARRIORS": "GSW",
    "SA": "SAS", "SAS": "SAS", "SAN ANTONIO SPURS": "SAS",
    "NO": "NOP", "NOP": "NOP", "NEW ORLEANS PELICANS": "NOP",
    "NY": "NYK", "NYK": "NYK", "NEW YORK KNICKS": "NYK",
    "PHO": "PHX", "PHX": "PHX", "PHOENIX SUNS": "PHX",
    "WSH": "WAS", "WAS": "WAS", "WASHINGTON WIZARDS": "WAS",
    "LAC": "LAC", "LA CLIPPERS": "LAC", "LOS ANGELES CLIPPERS": "LAC", "CLIPPERS": "LAC",
    "LAL": "LAL", "LA LAKERS": "LAL", "LOS ANGELES LAKERS": "LAL", "LAKERS": "LAL",
    "BKN": "BKN", "BRK": "BKN", "BROOKLYN NETS": "BKN",
    "CHA": "CHA", "CHO": "CHA", "CHARLOTTE HORNETS": "CHA",
    "UTA": "UTA", "UTAH": "UTA", "UTAH JAZZ": "UTA",
    "BOS": "BOS", "BOSTON CELTICS": "BOS",
    "CHI": "CHI", "CHICAGO BULLS": "CHI",
    "CLE": "CLE", "CLEVELAND CAVALIERS": "CLE",
    "DAL": "DAL", "DALLAS MAVERICKS": "DAL",
    "DEN": "DEN", "DENVER NUGGETS": "DEN",
    "DET": "DET", "DETROIT PISTONS": "DET",
    "HOU": "HOU", "HOUSTON ROCKETS": "HOU",
    "IND": "IND", "INDIANA PACERS": "IND",
    "MEM": "MEM", "MEMPHIS GRIZZLIES": "MEM",
    "MIA": "MIA", "MIAMI HEAT": "MIA",
    "MIL": "MIL", "MILWAUKEE BUCKS": "MIL",
    "MIN": "MIN", "MINNESOTA TIMBERWOLVES": "MIN",
    "OKC": "OKC", "OKLAHOMA CITY THUNDER": "OKC",
    "ORL": "ORL", "ORLANDO MAGIC": "ORL",
    "PHI": "PHI", "PHILADELPHIA 76ERS": "PHI",
    "POR": "POR", "PORTLAND TRAIL BLAZERS": "POR",
    "SAC": "SAC", "SACRAMENTO KINGS": "SAC",
    "TOR": "TOR", "TORONTO RAPTORS": "TOR",
    "ATL": "ATL", "ATLANTA HAWKS": "ATL",
}

MAPA_FAMILIAS_MERCADOS = {
    "Total Points": "pts_combos",
    "Total PRA": "pts_combos",
    "Total PR": "pts_combos",
    "Total PA": "pts_combos",
    "Total Rebounds": "rebotes",
    "Total Assists": "asistencias",
    "Total Triples": "triples",
}

_SIGLAS_AVISADAS: set[str] = set()


def normalizar_sigla_equipo(equipo_raw: Any) -> str:
    """Normaliza cualquier sigla o nombre de franquicia NBA a sigla canónica estándar."""
    if not equipo_raw:
        return ""
    s = str(equipo_raw).strip().upper()
    canon = MAPA_SIGLAS_CANONICAS.get(s)
    if not canon:
        if s not in _SIGLAS_AVISADAS:
            _SIGLAS_AVISADAS.add(s)
            logger.warning(f"Sigla de equipo NBA no reconocida en mapa canónico: '{s}'. Se usará tal cual.")
        return s
    return canon

MAPA_MERCADOS_COLUMNAS = {
    # formato: (col_raw, col_avg, col_std, col_l5, sigma_floor, sigma_prior)
    "Total Points": ("pts", "pts_avg", "pts_std", "pts_l5", 3.0, 5.5),
    "Total Rebounds": ("reb", "reb_avg", "reb_std", "reb_l5", 1.8, 2.8),
    "Total Assists": ("ast", "ast_avg", "ast_std", "ast_l5", 1.5, 2.2),
    "Total Triples": ("t3_made", "t3_avg", "t3_std", "t3_l5", 0.8, 1.2),
    "Total PRA": ("pra", "pra_avg", "pra_std", "pra_l5", 4.5, 7.5),
    "Total PR": ("pr", "pr_avg", "pr_std", "pr_l5", 3.5, 6.0),
    "Total PA": ("pa", "pa_avg", "pa_std", "pa_l5", 3.5, 5.8),
}


def _calcular_hit_rate(serie: pd.Series, linea: float, suavizado: bool = False) -> Tuple[float, int, int]:
    """Calcula el porcentaje de partidos en que el jugador superó la línea, excluyendo empates (push)."""
    if serie.empty:
        return 0.5, 0, 0
    # En líneas enteras, excluir empates exactos para no distorsionar el hit rate (evitar contar push como Under)
    serie_decisiva = serie[serie != linea]
    total = len(serie_decisiva)
    if total == 0:
        return 0.5, 0, 0
    overs = int((serie_decisiva > linea).sum())
    if suavizado:
        # Suavizado bayesiano Beta(4, 4) para evitar extremos 0% o 100% en muestras cortas
        rate = round((overs + 4) / (total + 8), 3)
    else:
        rate = round(overs / total, 3)
    return rate, overs, total


def _comprimir_ev_suave(ev_raw: float) -> float:
    """Aplica compresión suave hiperbólica (tanh) para visualización y evitar mesetas."""
    if ev_raw <= 15.0:
        return round(ev_raw, 1)
    # Curva asintótica continua
    comprimido = 15.0 + 20.0 * math.tanh((ev_raw - 15.0) / 25.0)
    return round(comprimido, 1)


def _calcular_probabilidades_mercado(mercado: str, linea: float, mu: float, sigma: float) -> Tuple[float, float, float]:
    """Calcula P(Over), P(Under) y P(Push) con continuidad exacta y manejo riguroso de líneas enteras."""
    if sigma <= 0.1:
        sigma = 1.5

    es_entera = (linea % 1 == 0)

    if mercado == "Total Triples":
        if mu <= 0.05:
            return 0.02, 0.98, 0.0
        k = math.floor(linea)
        if es_entera:
            # P(X > k) = 1 - PoissonCDF(k, mu)
            # P(X < k) = PoissonCDF(k - 1, mu)
            # P(X == k) = PoissonPMF(k, mu)
            p_over = float(1.0 - stats.poisson.cdf(k, mu=mu))
            p_under = float(stats.poisson.cdf(k - 1, mu=mu)) if k > 0 else 0.0
            p_push = float(stats.poisson.pmf(k, mu=mu))
        else:
            # Línea fraccionaria (ej. 2.5 triples): el push es imposible
            p_over = float(1.0 - stats.poisson.cdf(k, mu=mu))
            p_push = 0.0
            p_under = 1.0 - p_over
    else:
        # Distribución Normal para puntos, rebotes, asistencias y combos
        if es_entera:
            # P(X > linea) = 1 - Phi((linea + 0.5 - mu) / sigma)
            # P(X < linea) = Phi((linea - 0.5 - mu) / sigma)
            # P(X == linea) = 1 - p_over - p_under
            z_over = (linea + 0.5 - mu) / sigma
            z_under = (linea - 0.5 - mu) / sigma
            p_over = float(1.0 - stats.norm.cdf(z_over))
            p_under = float(stats.norm.cdf(z_under))
            p_push = max(0.0, 1.0 - p_over - p_under)
        else:
            z = (linea - mu) / sigma
            p_over = float(1.0 - stats.norm.cdf(z))
            p_push = 0.0
            p_under = 1.0 - p_over

    p_over = float(np.clip(p_over, 0.02, 0.98))
    p_under = float(np.clip(p_under, 0.02, 0.98))
    return p_over, p_under, p_push


def _calcular_probabilidad_poisson(linea: float, lam: float) -> float:
    """Función de compatibilidad: P(X > linea) con Poisson para triples."""
    p_over, _, _ = _calcular_probabilidades_mercado("Total Triples", linea, lam, 1.0)
    return p_over


def _calcular_probabilidad_normal(linea: float, mu: float, sigma: float) -> float:
    """Función de compatibilidad: P(X > linea) con Normal para puntos/reb/ast."""
    p_over, _, _ = _calcular_probabilidades_mercado("Total Points", linea, mu, sigma)
    return p_over


def generar_predicciones_props_hoy(
    usar_cache_bovada: bool = True,
    min_juegos_muestra: int = 3,
    fecha_referencia: Optional[str] = None,
) -> pd.DataFrame:
    """Genera predicciones con Valor Esperado (EV%) para todos los props de hoy.
    Nota sobre anti-leakage: El parámetro fecha_referencia aplica filtrado temporal estricto
    únicamente sobre el histórico de boxscores. Las líneas de Bovada y el reporte de lesiones
    corresponden a las cotizaciones y estado en vivo al momento de la ejecución.
    """
    DIR_PRED.mkdir(parents=True, exist_ok=True)

    hoy_cdmx = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
    fecha_corte = str(fecha_referencia or hoy_cdmx)[:10]

    # 1. Cargar o sincronizar boxscores de jugadores
    if not RUTA_PARQUET_JUGADORES.exists():
        logger.info("Boxscores de jugadores no encontrados. Sincronizando...")
        df_boxscores = sincronizar_boxscores_jugadores()
    else:
        df_boxscores = pd.read_parquet(RUTA_PARQUET_JUGADORES)

    if df_boxscores.empty:
        logger.error("No hay boxscores disponibles para generar predicciones.")
        return pd.DataFrame()

    # Filtro estricto anti-leakage: solo estadísticas de partidos jugados ANTES de la fecha objetivo
    if "fecha" in df_boxscores.columns:
        df_boxscores = df_boxscores[df_boxscores["fecha"].astype(str) < fecha_corte].copy()

    if df_boxscores.empty:
        logger.error(f"No hay boxscores disponibles previos a {fecha_corte} para generar predicciones.")
        return pd.DataFrame()

    # Unificación estricta de muestra (minutos >= 8.0):
    # Filtramos df_boxscores ANTES de calcular el perfil de jugador para que stat_avg, stat_l5,
    # stat_std y las series de hit rate se deriven con exactitud sobre la misma muestra limpia.
    col_min = "min" if "min" in df_boxscores.columns else ("minutos" if "minutos" in df_boxscores.columns else None)
    if col_min:
        df_boxscores = df_boxscores[df_boxscores[col_min] >= 8.0].copy()
    else:
        logger.warning("No se encontró columna de minutos ('min' o 'minutos') en boxscores; no se pudo filtrar partidos cortos.")

    df_perfiles = calcular_perfil_jugador(df_boxscores, min_minutos=8.0)
    # Crear diccionario de acceso rápido por nombre normalizado
    df_boxscores["player_norm"] = df_boxscores["player_name"].apply(_limpiar_nombre_jugador).str.lower()
    df_perfiles["player_norm"] = df_perfiles["player_name"].apply(_limpiar_nombre_jugador).str.lower()

    perfiles_dict = {
        row["player_norm"]: row.to_dict()
        for _, row in df_perfiles.iterrows()
    }

    # 2. Cargar reporte de lesiones para detectar bajas estelares y descartar jugadores inactivos
    bajas_por_equipo: Dict[str, float] = {}
    jugadores_inactivos: set[str] = set()
    try:
        reporte_les = obtener_reporte_lesiones_nba()
        for t_abbr, lista_les in reporte_les.items():
            t_canon = normalizar_sigla_equipo(t_abbr)
            for les in lista_les:
                estado_les = str(les.get("estado", "")).upper()
                if estado_les in ["OUT", "DOUBTFUL"]:
                    factor_estado = 1.0 if estado_les == "OUT" else 0.75
                    # Default en 0.0 para que suplentes sin spread estimado no sumen 1.0 falso
                    imp = float(les.get("impacto_spread", 0.0) or 0.0) * factor_estado
                    bajas_por_equipo[t_canon] = bajas_por_equipo.get(t_canon, 0.0) + imp
                    nom = les.get("jugador", "").strip().lower()
                    if nom:
                        jugadores_inactivos.add(nom)
                        jugadores_inactivos.add(_limpiar_nombre_jugador(nom).lower())
    except Exception as e:
        logger.warning(f"No se pudo consultar el servicio de lesiones: {e}")

    # Pre-agrupamiento de boxscores por jugador para acelerar el cálculo
    hist_por_jugador = {
        p_name: grp.sort_values("fecha")
        for p_name, grp in df_boxscores.groupby("player_norm")
    }

    # 3. Descargar o leer líneas de Bovada
    df_bovada = extraer_props_nba(usar_cache=usar_cache_bovada)
    if df_bovada.empty:
        logger.warning("No se obtuvieron props de Bovada.")
        return pd.DataFrame()

    predicciones: List[Dict[str, Any]] = []

    for _, row in df_bovada.iterrows():
        p_clean = row["player_clean"]
        p_norm = p_clean.lower()
        mercado = row["market"]
        linea = float(row["line"])
        equipo = row["team"]

        # Si el jugador está confirmado como baja (OUT / DOUBTFUL), no sugerir sus props
        if p_norm in jugadores_inactivos or p_clean.lower() in jugadores_inactivos:
            continue

        # Buscar perfil de estadísticas
        perfil = perfiles_dict.get(p_norm)
        if not perfil or perfil.get("games_played", 0) < min_juegos_muestra:
            continue

        cols_stat = MAPA_MERCADOS_COLUMNAS.get(mercado)
        if not cols_stat:
            continue

        raw_col, avg_col, std_col, l5_col, sigma_floor, sigma_prior = cols_stat
        
        stat_avg = float(perfil.get(avg_col, 0.0) or 0.0)
        stat_l5 = float(perfil.get(l5_col, stat_avg) or stat_avg) if l5_col else stat_avg
        stat_std_raw = float(perfil.get(std_col, sigma_prior) or sigma_prior) if std_col else sigma_prior

        if stat_avg <= 0:
            continue

        # Filtrar historial de este jugador para calcular hit rate exacto (excluyendo empates en líneas enteras)
        hist_player = hist_por_jugador.get(p_norm, pd.DataFrame())
        serie_stat = hist_player[raw_col].dropna() if not hist_player.empty else pd.Series(dtype=float)

        hit_rate_season, ov_season, n_season = _calcular_hit_rate(serie_stat, linea)
        hit_rate_l5, ov_l5, n_l5 = _calcular_hit_rate(serie_stat.tail(5), linea)

        # Proyección ponderada: 60% forma reciente (L5), 40% temporada
        proj_base = 0.60 * stat_l5 + 0.40 * stat_avg

        # Boost de volumen si un compañero estrella está lesionado (OUT / DOUBTFUL)
        equipo_canon = normalizar_sigla_equipo(equipo)
        impacto_bajas = bajas_por_equipo.get(equipo_canon, 0.0)
        boost_lesion = 1.0
        if impacto_bajas >= 3.0:
            boost_lesion = 1.14  # +14% si hay bajas severas acumuladas
        elif impacto_bajas >= 2.0:
            boost_lesion = 1.08  # +8% de volumen / tiros

        # El boost por lesiones impacta principalmente en uso ofensivo y tiros (puntos, triples, PRA, PA);
        # en rebotes y asistencias defensivas el impacto es moderado (50% del boost)
        factor_mercado = 1.0 if mercado in ["Total Points", "Total Triples", "Total PRA", "Total PA"] else 0.5
        boost_mercado = round(1.0 + (boost_lesion - 1.0) * factor_mercado, 3)

        # Detección de titular basada estrictamente en minutaje real en cancha
        minutos_prom = float(perfil.get("min_avg", 0.0) or 0.0)
        minutos_l5 = float(perfil.get("min_l5", minutos_prom) or minutos_prom)
        es_titular = (minutos_prom >= 24.0) or (minutos_l5 >= 25.0)

        # Descuento de minutos por riesgo de blowout:
        # En partidos desbalanceados (spread >= 8.5 pts), si el juego se abre por 20+ pts,
        # los titulares descansan casi todo el 4Q (perdiendo de 6 a 10 minutos de producción).
        game_spread = abs(float(row.get("game_spread") or 0.0))
        descuento_blowout = 1.0
        if game_spread >= 8.5 and es_titular:
            if game_spread >= 11.5:
                descuento_blowout = 0.86  # -14% de expectativa en partidos con spread >= 11.5
            else:
                descuento_blowout = 0.92  # -8% de expectativa en partidos con spread 8.5 - 11.0

        proy_continua = proj_base * boost_mercado * descuento_blowout
        proyeccion = round(proy_continua, 1)

        # Shrinkage empírico bayesiano para sigma en muestras cortas (3-10 partidos)
        # Combina la sigma muestral con la desviación previa del mercado en la NBA,
        # y escala con la raíz del cambio de expectativa (minutos y uso ofensivo).
        n_partidos = float(perfil.get("games_played", 5) or 5)
        peso_prior_sigma = 5.0 / (n_partidos + 5.0)  # 5 juegos de peso al prior de liga
        stat_std_blended = (1.0 - peso_prior_sigma) * max(stat_std_raw, sigma_floor) + peso_prior_sigma * sigma_prior
        factor_escala = max(0.1, boost_mercado * descuento_blowout)
        stat_std = max(sigma_floor, stat_std_blended * math.sqrt(factor_escala))

        # Cálculo de probabilidades según tipo de estadística usando el valor continuo sin redondear
        # Retorna p_over, p_under y p_push para modelar exactamente el push en líneas enteras
        prob_over_raw, prob_under_raw, prob_push_raw = _calcular_probabilidades_mercado(
            mercado=mercado,
            linea=linea,
            mu=proy_continua,
            sigma=stat_std
        )

        # Cuotas decimales de Bovada
        over_dec = row.get("over_decimal")
        under_dec = row.get("under_decimal")

        # Quitar el vigorish (margen del sportsbook) para obtener la probabilidad justa de mercado (Fair Implied Probability)
        if over_dec and under_dec and over_dec > 1.0 and under_dec > 1.0:
            io = 1.0 / over_dec
            iu = 1.0 / under_dec
            implied_over = io / (io + iu)
            implied_under = iu / (io + iu)
        elif over_dec and over_dec > 1.0:
            io = 1.0 / over_dec
            # En milestones one-sided de plus-money el vig real del casino suele ser 8-10%
            implied_over = float(np.clip(io / 1.095, 0.05, 0.95))
            implied_under = 1.0 - implied_over
        else:
            implied_over = 0.50
            implied_under = 0.50

        # 1. Normalizar el modelo condicionado a NO-PUSH (donde Over + Under = 1.0)
        # Esto alinea el espacio probabilístico del modelo con las cuotas del mercado
        p_no_push = prob_over_raw + prob_under_raw
        p_over_cond_raw = (prob_over_raw / p_no_push) if p_no_push > 0 else 0.50

        # 2. Shrinkage bayesiano sobre la probabilidad condicionada
        peso_mercado = 0.65 if (over_dec and over_dec >= 2.15) else 0.50
        p_over_cond_shrunk = (1.0 - peso_mercado) * p_over_cond_raw + peso_mercado * implied_over

        # 3. Techo y piso de seguridad estadística: UN SOLO CLIP sobre la probabilidad condicionada
        p_over_cond_clipped = float(np.clip(p_over_cond_shrunk, 0.28, 0.72))
        p_under_cond_clipped = 1.0 - p_over_cond_clipped

        # 4. Reescalar por (1 - prob_push_raw) para obtener probabilidades finales coherentes
        prob_push_blended = round(prob_push_raw, 4) if (linea % 1 == 0) else 0.0
        prob_over_blended = round(p_over_cond_clipped * (1.0 - prob_push_blended), 4)
        prob_under_blended = round(p_under_cond_clipped * (1.0 - prob_push_blended), 4)

        # 5. Cálculo de EV% real considerando empates (push devuelve stake a ganancia 0)
        raw_ev_over = (prob_over_blended * (over_dec - 1.0) - prob_under_blended * 1.0) * 100.0 if over_dec else -100.0
        raw_ev_under = (prob_under_blended * (under_dec - 1.0) - prob_over_blended * 1.0) * 100.0 if under_dec else -100.0
        ev_over = _comprimir_ev_suave(raw_ev_over) if over_dec else -100.0
        ev_under = _comprimir_ev_suave(raw_ev_under) if under_dec else -100.0

        # Selección del Pick recomendado
        is_milestone = int(row.get("is_milestone", 0))
        if is_milestone:
            # En milestones solo existe la opción Over (+X triples)
            pick_tipo = "OVER"
            pick_ev = ev_over
            pick_ev_raw = raw_ev_over
            pick_prob = prob_over_blended
            pick_cuota_am = row.get("over_american")
            pick_cuota_dec = over_dec
            pick_implied_fair = implied_over
        else:
            if raw_ev_over >= raw_ev_under:
                pick_tipo = "OVER"
                pick_ev = ev_over
                pick_ev_raw = raw_ev_over
                pick_prob = prob_over_blended
                pick_cuota_am = row.get("over_american")
                pick_cuota_dec = over_dec
                pick_implied_fair = implied_over
            else:
                pick_tipo = "UNDER"
                pick_ev = ev_under
                pick_ev_raw = raw_ev_under
                pick_prob = prob_under_blended
                pick_cuota_am = row.get("under_american")
                pick_cuota_dec = under_dec
                pick_implied_fair = implied_under

        # Criterios Rigurosos de Candados / Convicción por Estrellas
        colchon_linea = abs(proyeccion - linea)
        games_p = int(perfil.get("games_played", 0) or 0)
        min_colchon = 0.8 if mercado in ["Total Triples", "Total Assists"] else 1.5

        es_top_pick = (
            pick_ev >= 7.0
            and colchon_linea >= min_colchon
            and (hit_rate_l5 >= 0.60 if pick_tipo == "OVER" else hit_rate_l5 <= 0.40)
            and (hit_rate_season >= 0.52 if pick_tipo == "OVER" else hit_rate_season <= 0.48)
            and games_p >= 4
            and (pick_cuota_dec <= 2.30)
        )

        es_alta_confianza = (
            pick_ev >= 3.5
            and colchon_linea >= (min_colchon * 0.6)
            and games_p >= 3
        )

        if es_top_pick:
            estrellas = "⭐⭐⭐"
            confianza = "ALTA"
        elif es_alta_confianza:
            estrellas = "⭐⭐"
            confianza = "MEDIA"
        elif pick_ev >= 1.0:
            estrellas = "⭐"
            confianza = "MODERADA"
        else:
            estrellas = "⚪"
            confianza = "NEUTRAL"

        # Candado de Ultra Convicción (Top Picks de élite para operar con máximo control de riesgo)
        es_candado = bool(
            es_top_pick
            and (hit_rate_l5 >= 0.80 if pick_tipo == "OVER" else hit_rate_l5 <= 0.20)
            and colchon_linea >= (min_colchon * 1.25)
            and (1.68 <= pick_cuota_dec <= 2.15)
        )

        # Reglas defensivas contra Blowouts y Milestones para Candados y Estrellas:
        # 1. Candado de Oro estrictamente prohibido para titulares en OVER si el spread es >= 8.5 pts
        # 2. Si el spread es muy abierto (>= 11.5 pts), ningún titular puede ser Top Pick (⭐⭐⭐) en OVER (máximo ⭐⭐)
        # 3. Milestones (mercados one-sided con alto vig) no pueden ser Candados ni Top Picks (máximo ⭐⭐)
        if es_titular and pick_tipo == "OVER":
            if game_spread >= 8.5:
                es_candado = False
            if game_spread >= 11.5 and es_top_pick:
                es_top_pick = False
                es_alta_confianza = True
                estrellas = "⭐⭐"
                confianza = "MEDIA"

        if is_milestone:
            es_candado = False
            if es_top_pick:
                es_top_pick = False
                es_alta_confianza = True
                estrellas = "⭐⭐"
                confianza = "MEDIA"

        # Resumen de tendencia empírica reciente (L5) vs línea
        prom_l5_val = stat_l5 if n_l5 > 0 else stat_avg
        if pick_tipo == "OVER":
            tendencia = f"Over en {ov_l5}/{n_l5} últimos (promedia {prom_l5_val:.1f} en L5 vs línea {linea})"
        else:
            tendencia = f"Under en {n_l5 - ov_l5}/{n_l5} últimos (promedia {prom_l5_val:.1f} en L5 vs línea {linea})"

        predicciones.append({
            "game": row["game"],
            "fecha": row["fecha"],
            "hora": row["hora"],
            "away_team": row["away_team"],
            "home_team": row["home_team"],
            "player_name": row["player_name"],
            "player_clean": p_clean,
            "team": equipo,
            "position": perfil.get("position", ""),
            "market": mercado,
            "line": linea,
            "projection": proyeccion,
            "stat_avg": stat_avg,
            "stat_l5": stat_l5,
            "games_played": perfil.get("games_played", 0),
            "hit_rate_season": hit_rate_season,
            "hit_rate_l5": hit_rate_l5,
            "pick_type": pick_tipo,
            "pick_odds_american": pick_cuota_am,
            "pick_odds_decimal": pick_cuota_dec,
            "model_prob": pick_prob,
            "implied_prob_vig": round(1.0 / pick_cuota_dec, 4) if pick_cuota_dec else 0.5,
            "fair_implied_prob": round(pick_implied_fair, 4),
            "implied_prob": round(pick_implied_fair, 4),
            "market_family": MAPA_FAMILIAS_MERCADOS.get(mercado, mercado),
            "ev_pct": pick_ev,
            "ev_raw": round(pick_ev_raw, 1),
            "stars": estrellas,
            "confidence": confianza,
            "trend": tendencia,
            "boost_lesion_pct": round((boost_lesion - 1.0) * 100.0, 1),
            "game_spread": game_spread,
            "descuento_blowout_pct": round((1.0 - descuento_blowout) * 100.0, 1),
            "is_milestone": is_milestone,
            "es_candado": es_candado,
        })

    df_res = pd.DataFrame(predicciones)

    if not df_res.empty:
        # Ordenar por EV matemático real (ev_raw) descendente antes de deduplicar y aplicar caps
        df_res.sort_values(by="ev_raw", ascending=False, inplace=True)
        # Deduplicar por familia de mercado para el mismo jugador:
        # Conserva el mejor pick dentro de la misma familia correlacionada (Puntos, PRA, PR, PA),
        # pero permite picks independientes si el jugador tiene ventaja en Rebounds, Assists o Triples.
        df_res.drop_duplicates(subset=["player_name", "market_family"], keep="first", inplace=True)
        df_res.reset_index(drop=True, inplace=True)

        # Cap de exposición por partido:
        # Máximo 3 picks de 3 estrellas (⭐⭐⭐ Top Picks) por juego.
        # Si un partido genera más de 3 picks Top, los excedentes se degradan a ⭐⭐ (Alta Confianza)
        # para evitar sobre-concentración y blindar el bankroll contra blowouts o ritmos anómalos.
        # Además, si se degrada un pick, se limpia rigurosamente su condición de Candado (es_candado = False).
        conteo_por_juego: Dict[str, int] = {}
        estrellas_ajustadas = []
        confianzas_ajustadas = []
        candados_ajustados = []
        for _, r in df_res.iterrows():
            juego = r["game"]
            estrellas_act = r["stars"]
            conf_act = r["confidence"]
            candado_act = bool(r.get("es_candado", False))
            if estrellas_act == "⭐⭐⭐":
                c = conteo_por_juego.get(juego, 0)
                if c >= 3:
                    estrellas_ajustadas.append("⭐⭐")
                    confianzas_ajustadas.append("MEDIA")
                    candados_ajustados.append(False)  # Un pick degradado a 2 estrellas jamás puede ser Candado
                else:
                    conteo_por_juego[juego] = c + 1
                    estrellas_ajustadas.append("⭐⭐⭐")
                    confianzas_ajustadas.append(conf_act)
                    candados_ajustados.append(candado_act)
            else:
                estrellas_ajustadas.append(estrellas_act)
                confianzas_ajustadas.append(conf_act)
                candados_ajustados.append(candado_act if estrellas_act == "⭐⭐⭐" else False)

        df_res["stars"] = estrellas_ajustadas
        df_res["confidence"] = confianzas_ajustadas
        df_res["es_candado"] = candados_ajustados
        
        df_res.to_parquet(RUTA_PRED_PARQUET, index=False)
        with open(RUTA_PRED_JSON, "w", encoding="utf-8") as f:
            json.dump(df_res.to_dict(orient="records"), f, indent=2, ensure_ascii=False)
        
        # Persistir de inmediato en el historial de props como PENDIENTE para asegurar auditoría
        try:
            from nba.evaluar_props import registrar_props_pendientes
            registrar_props_pendientes(df_res)
        except Exception as e_reg:
            logger.warning(f"No se pudieron registrar props pendientes en el historial: {e_reg}")

        logger.info(f"🎯 Generadas exitosamente {len(df_res)} predicciones de props. Top EV: +{df_res['ev_pct'].max()}%")

    return df_res


if __name__ == "__main__":
    t0 = time.time()
    df_preds = generar_predicciones_props_hoy(usar_cache_bovada=True)
    print(f"Predicciones listas en {time.time() - t0:.2f}s. Total: {len(df_preds)}")
    if not df_preds.empty:
        top = df_preds[df_preds["ev_pct"] >= 5.0]
        print(f"\nPicks con EV >= 5%: {len(top)}")
        cols = ["player_name", "team", "market", "line", "projection", "pick_type", "pick_odds_american", "ev_pct", "stars", "trend"]
        print(top.head(15)[cols].to_string())
