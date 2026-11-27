"""Motor predictivo y de valor esperado (EV) para Player Props NBA.

Combina:
1. Líneas y cuotas en tiempo real de Bovada (0 créditos).
2. Estadísticas de temporada 2026-27 y tendencia reciente (L5) de ESPN.
3. Impacto de lesiones en tiempo real de compañeros de equipo (Usage Boost).
4. Modelado probabilístico:
   - Triples y Asistencias (conteo): Binomial Negativa si la varianza supera a la media,
     Poisson en caso contrario. Un solo modelo para todas las asistencias (sin saltos de distribución).
   - Puntos, Rebotes y Combos (PRA, PR, PA): Gaussiana con corrección de continuidad.
   - Modelado exacto de push (empates) en líneas enteras con devolución del stake.
   - Distribución predictiva con ensanchamiento por incertidumbre de la media muestral.
5. Cálculo de Valor Esperado (EV%) con remoción de vig y asignación de estrellas de confianza.

Notas:
- fecha_referencia solo filtra boxscores; líneas y lesiones son las de la ejecución.
- Milestones ("N+"): se modelan como línea N - 0.5 (X >= N), sin push. El campo "line" conserva
  el valor original de Bovada y "line_modelo" el valor usado en el cálculo.
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
from core.filtro_top5 import MERCADOS_PROPS_NBA_EXCLUIDOS_TOP5
from nba.servicio_bovada_props import extraer_props_nba, _limpiar_nombre_jugador
from nba.servicio_jugadores_boxscores import (
    RUTA_PARQUET_JUGADORES,
    sincronizar_boxscores_jugadores,
    calcular_perfil_jugador
)
from nba.modelo_minutos_props import (
    proyectar_prop_por_minuto,
    proyectar_minutos_jugador,
    calcular_tasa_por_minuto_bayesiana,
)
from nba.servicio_lesiones import obtener_reporte_lesiones_nba

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nba_predecir_props")


def _obtener_model_version() -> str:
    """Retorna la versión del modelo anclada al commit de git para auditoría inmutable."""
    try:
        import subprocess
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        return f"v2.5_bayesian_{commit}"
    except Exception:
        return "v2.5_bayesian_props"

DIR_PRED = RAIZ / "data" / "nba" / "predictions"
RUTA_PRED_PARQUET = DIR_PRED / "predicciones_props_nba_hoy.parquet"
RUTA_PRED_JSON = DIR_PRED / "predicciones_props_nba_hoy.json"

# Milestones (one-sided, plus-money, vig estimado): se les exige más para evitar winner's curse.
FACTOR_UMBRAL_MILESTONE = 1.5       # multiplica los umbrales de EV de estrellas
PENALIZACION_EV_MILESTONE = 3.0     # puntos de EV que debe superar un milestone a una línea regular al deduplicar

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

MERCADOS_CONTEO = {"Total Triples", "Total Assists"}

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


def _calcular_hit_rate(serie: pd.Series, linea: float) -> Tuple[float, int, int]:
    """Porcentaje de partidos en que el jugador superó la línea, excluyendo empates (push)."""
    if serie.empty:
        return 0.5, 0, 0
    serie_decisiva = serie[serie != linea]
    total = len(serie_decisiva)
    if total == 0:
        return 0.5, 0, 0
    overs = int((serie_decisiva > linea).sum())
    return round(overs / total, 3), overs, total


def _comprimir_ev_suave(ev_raw: float) -> float:
    """Compresión suave (tanh) del EV para calibración profesional (rango realista máx ~12%)."""
    if ev_raw <= 6.0:
        return round(ev_raw, 1)
    return round(6.0 + 6.0 * math.tanh((ev_raw - 6.0) / 8.0), 1)


def _decimal_a_americana(dec: Any) -> Optional[str]:
    """Convierte cuota decimal (> 1.0) a formato americano legible (ej. '+110', '-115', 'EVEN')."""
    try:
        d = float(dec)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(d) or d <= 1.0:
        return None
    if abs(d - 2.0) < 1e-3:
        return "EVEN"
    if d > 2.0:
        return f"+{int(round((d - 1.0) * 100.0))}"
    return f"{int(round(-100.0 / (d - 1.0)))}"


def _calcular_probabilidades_mercado(mercado: str, linea: float, mu: float, sigma: float) -> Tuple[float, float, float]:
    """Calcula P(Over), P(Under) y P(Push).

    Conteos (triples, asistencias): Binomial Negativa si sigma^2 > mu, Poisson si no.
    Resto: Normal con corrección de continuidad. El push solo existe en líneas enteras.
    """
    if sigma <= 0.1:
        sigma = 1.5

    es_entera = (linea % 1 == 0)

    if mercado in MERCADOS_CONTEO:
        if mu <= 0.05:
            return 0.02, 0.98, 0.0
        k = math.floor(linea)

        var = sigma ** 2
        if var > (mu + 0.05):
            p_nb = float(np.clip(mu / var, 0.01, 0.99))
            r_nb = float(max(0.1, (mu ** 2) / (var - mu)))
            dist = stats.nbinom(n=r_nb, p=p_nb)
        else:
            dist = stats.poisson(mu=mu)

        if es_entera:
            p_over = float(1.0 - dist.cdf(k))
            p_under = float(dist.cdf(k - 1)) if k > 0 else 0.0
            p_push = float(dist.pmf(k))
        else:
            p_over = float(1.0 - dist.cdf(k))
            p_push = 0.0
            p_under = 1.0 - p_over
    else:
        if es_entera:
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

    # Clip mínimo solo para evitar ceros numéricos; el clip real de seguridad se aplica
    # una única vez después de condicionar a no-push.
    eps = 1e-6
    p_over = float(np.clip(p_over, eps, 1.0 - eps))
    p_under = float(np.clip(p_under, 0.0, 1.0 - eps))
    return p_over, p_under, p_push


def seleccionar_top_props_diarios(df_preds: pd.DataFrame, limite: int = 5) -> pd.DataFrame:
    """Selecciona hasta `limite` (por defecto Top 5) props más seguros con EV positivo (+EV).

    Criterios estrictos de Selección:
    1. Probabilidad calibrada mínima >= 54.0% y EV positivo (`ev_pct > 0`), excluyendo líneas neutrales (`⚪`).
    2. Ordenamiento que prioriza seguridad (probabilidad y consistencia histórica) + valor esperado (+EV).
    3. Diversificación estricta: máximo 1 pick por jugador y máximo 2 picks por partido.
    4. Corte estricto en `limite` (Top 5 diarios por defecto).
    """
    if df_preds is None or df_preds.empty:
        return pd.DataFrame()

    df = df_preds.copy()
    if "market" in df.columns:
        df = df[~df["market"].astype(str).isin(MERCADOS_PROPS_NBA_EXCLUIDOS_TOP5)].copy()
    if "model_prob" in df.columns:
        probs = pd.to_numeric(df["model_prob"], errors="coerce").fillna(0.0)
        df = df[probs >= 0.54].copy()
    if "ev_pct" in df.columns:
        evs = pd.to_numeric(df["ev_pct"], errors="coerce").fillna(0.0)
        df = df[evs > 0.0].copy()
    if "stars" in df.columns:
        df = df[df["stars"].astype(str).str.strip() != "⚪"].copy()
    if df.empty:
        return pd.DataFrame()

    def _calcular_score_seleccion(r: pd.Series) -> float:
        prob_val = float(r.get("model_prob", 0.54) or 0.54)
        tier_puntos = prob_val * 100.0  # Base por probabilidad pura (seguridad primero)
        if bool(r.get("es_candado")):
            tier_puntos += 12.0

        ev_val = float(r.get("ev_pct", 0.0) or 0.0)
        ev_capped = min(max(ev_val, 0.0), 12.0)

        gp = float(r.get("games_played", 5) or 5)
        bonus_muestra = min(gp / 5.0, 3.0)

        hr_l5 = float(r.get("hit_rate_l5", 0.5) or 0.5)
        hr_sea = float(r.get("hit_rate_season", 0.5) or 0.5)
        if str(r.get("pick_type")).upper() == "UNDER":
            hr_l5 = 1.0 - hr_l5
            hr_sea = 1.0 - hr_sea

        bonus_consistencia = (hr_l5 * 4.0) + (hr_sea * 3.0)
        return tier_puntos + ev_capped + bonus_muestra + bonus_consistencia

    df["_score_ranking"] = df.apply(_calcular_score_seleccion, axis=1)
    df.sort_values(by=["_score_ranking", "model_prob", "ev_pct"], ascending=[False, False, False], inplace=True)

    jugadores_usados: set[str] = set()
    juegos_conteo: Dict[str, int] = {}
    top_indices = []

    for idx, r in df.iterrows():
        p_name = str(r.get("player_name", "")).strip()
        game = str(r.get("game", "")).strip()

        # Máximo 1 pick por jugador
        if p_name and p_name in jugadores_usados:
            continue
        # Máximo 2 picks por partido para evitar exposición a blowouts
        if juegos_conteo.get(game, 0) >= 2:
            continue

        if p_name:
            jugadores_usados.add(p_name)
        juegos_conteo[game] = juegos_conteo.get(game, 0) + 1
        top_indices.append(idx)

        if len(top_indices) >= limite:
            break

    df_top = df.loc[top_indices].copy()
    df_top.drop(columns=["_score_ranking"], inplace=True)
    return df_top


def generar_predicciones_props_hoy(
    usar_cache_bovada: bool = True,
    min_juegos_muestra: int = 3,
    fecha_referencia: Optional[str] = None,
    permitir_odds_api: bool = True,
) -> pd.DataFrame:
    """Genera predicciones con Valor Esperado (EV%) para todos los props de hoy."""
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

    # Anti-leakage (solo boxscores): partidos jugados ANTES de la fecha objetivo
    if "fecha" in df_boxscores.columns:
        df_boxscores = df_boxscores[df_boxscores["fecha"].astype(str) < fecha_corte].copy()

    if df_boxscores.empty:
        logger.error(f"No hay boxscores disponibles previos a {fecha_corte} para generar predicciones.")
        return pd.DataFrame()

    # Verificación de columnas requeridas: los mercados sin columna se omiten con aviso
    columnas_faltantes = {
        info[0] for info in MAPA_MERCADOS_COLUMNAS.values() if info[0] not in df_boxscores.columns
    }
    if columnas_faltantes:
        logger.warning(
            f"Faltan columnas en boxscores: {sorted(columnas_faltantes)}. "
            f"Los mercados que las usan serán omitidos."
        )

    # Misma muestra (minutos >= 8) para perfil e hit rates
    col_min = "min" if "min" in df_boxscores.columns else ("minutos" if "minutos" in df_boxscores.columns else None)
    if col_min:
        df_boxscores = df_boxscores[df_boxscores[col_min] >= 8.0].copy()
    else:
        logger.warning("No se encontró columna de minutos ('min' o 'minutos'); no se pudo filtrar partidos cortos.")

    try:
        df_perfiles = calcular_perfil_jugador(df_boxscores, min_minutos=8.0)
    except TypeError:
        logger.warning(
            "calcular_perfil_jugador no acepta 'min_minutos'. Se llama sin el argumento "
            "(el filtro de minutos ya se aplicó sobre df_boxscores)."
        )
        df_perfiles = calcular_perfil_jugador(df_boxscores)

    df_boxscores["player_norm"] = df_boxscores["player_name"].apply(_limpiar_nombre_jugador).str.lower()
    df_perfiles["player_norm"] = df_perfiles["player_name"].apply(_limpiar_nombre_jugador).str.lower()

    perfiles_dict = {
        row["player_norm"]: row.to_dict()
        for _, row in df_perfiles.iterrows()
    }

    # 2. Reporte de lesiones
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
                    imp = float(les.get("impacto_spread", 0.0) or 0.0) * factor_estado
                    bajas_por_equipo[t_canon] = bajas_por_equipo.get(t_canon, 0.0) + imp
                    nom = les.get("jugador", "").strip().lower()
                    if nom:
                        jugadores_inactivos.add(nom)
                        jugadores_inactivos.add(_limpiar_nombre_jugador(nom).lower())
    except Exception as e:
        logger.warning(f"No se pudo consultar el servicio de lesiones: {e}")

    hist_por_jugador = {
        p_name: grp.sort_values("fecha")
        for p_name, grp in df_boxscores.groupby("player_norm")
    }

    try:
        from nba.predecir_hoy import cargar_perfiles_recientes_equipos
        perfiles_equipos = cargar_perfiles_recientes_equipos()
    except Exception as e_eq:
        logger.warning(f"No se pudieron cargar perfiles de equipos para ritmo y defensa: {e_eq}")
        perfiles_equipos = {}

    # Contexto de spread y total del partido desde las predicciones diarias de equipos
    contexto_partidos: Dict[Tuple[str, str], Dict[str, float]] = {}
    ruta_preds_juego = DIR_PRED / "predicciones_nba_hoy.json"
    if ruta_preds_juego.exists():
        try:
            with open(ruta_preds_juego, "r", encoding="utf-8") as fj:
                preds_hoy_eq = json.load(fj)
            for pj in preds_hoy_eq:
                h_s = normalizar_sigla_equipo(pj.get("abbr_local", ""))
                a_s = normalizar_sigla_equipo(pj.get("abbr_visita", ""))
                if h_s and a_s:
                    contexto_partidos[(h_s, a_s)] = {
                        "game_spread": float(pj.get("linea_spread") or 0.0),
                        "total_line": float(pj.get("linea_total") or 226.0),
                    }
        except Exception as e_ctx:
            logger.warning(f"No se pudo cargar contexto de spreads/totales desde predicciones_nba_hoy.json: {e_ctx}")

    # 3. Líneas de Bovada
    df_bovada = extraer_props_nba(usar_cache=usar_cache_bovada, permitir_odds_api=permitir_odds_api)
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
        is_milestone = int(row.get("is_milestone", 0) or 0)

        if p_norm in jugadores_inactivos:
            continue

        perfil = perfiles_dict.get(p_norm)
        if not perfil or perfil.get("games_played", 0) < min_juegos_muestra:
            continue

        cols_stat = MAPA_MERCADOS_COLUMNAS.get(mercado)
        if not cols_stat:
            continue

        raw_col, avg_col, std_col, l5_col, sigma_floor, sigma_prior = cols_stat
        if raw_col in columnas_faltantes:
            continue

        # Cuotas: se necesita al menos un lado válido
        over_dec = row.get("over_decimal")
        under_dec = row.get("under_decimal")
        over_ok = bool(over_dec) and over_dec > 1.0
        under_ok = bool(under_dec) and under_dec > 1.0
        if not over_ok and not under_ok:
            continue
        if not over_ok:
            over_dec = None
        if not under_ok:
            under_dec = None

        # Línea efectiva para el modelo: "N+" equivale a X >= N, es decir línea N - 0.5 sin push.
        linea_modelo = linea
        if is_milestone and linea % 1 == 0:
            linea_modelo = linea - 0.5

        stat_avg = float(perfil.get(avg_col, 0.0) or 0.0)
        stat_l5 = float(perfil.get(l5_col, stat_avg) or stat_avg) if l5_col else stat_avg
        stat_std_raw = float(perfil.get(std_col, sigma_prior) or sigma_prior) if std_col else sigma_prior

        if stat_avg <= 0:
            continue

        hist_player = hist_por_jugador.get(p_norm, pd.DataFrame())
        serie_stat = hist_player[raw_col].dropna() if not hist_player.empty else pd.Series(dtype=float)

        hit_rate_season, ov_season, n_season = _calcular_hit_rate(serie_stat, linea_modelo)
        hit_rate_l5, ov_l5, n_l5 = _calcular_hit_rate(serie_stat.tail(5), linea_modelo)

        # Contexto de rival, ritmo (Pace) y eficiencia defensiva (DRTG)
        equipo_canon = normalizar_sigla_equipo(equipo)
        home_sigla = normalizar_sigla_equipo(row.get("home_team", ""))
        away_sigla = normalizar_sigla_equipo(row.get("away_team", ""))
        rival_sigla = away_sigla if equipo_canon == home_sigla else home_sigla

        prof_home = perfiles_equipos.get(home_sigla, {})
        prof_away = perfiles_equipos.get(away_sigla, {})
        prof_rival = perfiles_equipos.get(rival_sigla, {})

        pace_home = float(prof_home.get("PACE_L10", 100.2) or 100.2)
        pace_away = float(prof_away.get("PACE_L10", 100.2) or 100.2)
        rival_drtg = float(prof_rival.get("DRTG_L10", 114.5) or 114.5)

        factor_defensa_rival = 1.0
        if raw_col in ["pts", "ast", "t3_made", "pra", "pa"]:
            # DRTG > 114.5 indica defensa permisiva (>1.0); DRTG < 114.5 defensa de élite (<1.0)
            factor_defensa_rival = float(np.clip(rival_drtg / 114.5, 0.93, 1.07))

        # Boost por lesiones de compañeros moderado y calibrado
        impacto_bajas = bajas_por_equipo.get(equipo_canon, 0.0)
        boost_lesion = 1.0
        if impacto_bajas >= 3.5:
            boost_lesion = 1.06  # +6% de volumen máximo en ausencias críticas
        elif impacto_bajas >= 2.0:
            boost_lesion = 1.03  # +3% de volumen moderado

        factor_mercado = 0.70 if mercado in ["Total Points", "Total Triples", "Total PRA", "Total PA"] else 0.35
        boost_mercado = round(1.0 + (boost_lesion - 1.0) * factor_mercado, 3)

        # Contexto del partido (spread, total y B2B real) con fallback a predicciones diarias de equipo
        ctx_partido = contexto_partidos.get((home_sigla, away_sigla), {})
        raw_spread = row.get("game_spread")
        if raw_spread is None or (isinstance(raw_spread, float) and math.isnan(raw_spread)) or float(raw_spread or 0.0) == 0.0:
            raw_spread = ctx_partido.get("game_spread", 0.0)
        game_spread = abs(float(raw_spread or 0.0))

        raw_total = row.get("total_line")
        if raw_total is None or (isinstance(raw_total, float) and math.isnan(raw_total)) or float(raw_total or 0.0) <= 0.0:
            raw_total = ctx_partido.get("total_line", 226.0)
        total_line_val = float(raw_total or 226.0)

        es_b2b_jugador = bool(row.get("es_b2b", False))
        if not es_b2b_jugador:
            last_dt_eq = str(perfiles_equipos.get(equipo_canon, {}).get("LAST_DATE", "") or "")[:10]
            if last_dt_eq and fecha_corte:
                try:
                    dt_corte = datetime.strptime(fecha_corte, "%Y-%m-%d").date()
                    dt_last = datetime.strptime(last_dt_eq, "%Y-%m-%d").date()
                    es_b2b_jugador = (dt_corte - dt_last).days == 1
                except Exception:
                    es_b2b_jugador = False

        # Desacoplamiento Cuantitativo: Minutos Proyectados × Tasa por Minuto (con Shrinkage Bayesiano)
        col_min = "min" if (not hist_player.empty and "min" in hist_player.columns) else None
        has_min_data = col_min is not None and len(hist_player.dropna(subset=[col_min, raw_col])) >= 3

        pos_jugador = str(perfil.get("position", "") or "")
        minutos_proyectados = None
        tasa_por_minuto = None
        descuento_blowout = 1.0

        if has_min_data:
            res_cuant = proyectar_prop_por_minuto(
                df_boxscores_jugador=hist_player,
                posicion=pos_jugador,
                clave_stat=raw_col,
                spread_partido=game_spread,
                total_partido=total_line_val,
                pace_local=pace_home,
                pace_visita=pace_away,
                es_b2b=es_b2b_jugador,
                defensa_rival_factor=factor_defensa_rival,
            )
            proj_cuant = res_cuant["proyeccion"]
            minutos_proyectados = res_cuant["minutos_proyectados"]
            tasa_por_minuto = res_cuant["tasa_por_minuto"]
            descuento_blowout = res_cuant["factor_blowout"]
            es_titular = res_cuant["es_titular"]
            minutos_prom = minutos_proyectados

            # Ponderación: 75% modelo desacoplado cuantitativo / 25% forma ponderada
            proj_base = 0.75 * proj_cuant + 0.25 * (0.35 * stat_l5 + 0.65 * stat_avg)
            # Evitar doble descuento por blowout: ya aplicado en proyectar_minutos_jugador()
            factor_blowout_extra = 1.0
        else:
            proj_base = 0.35 * stat_l5 + 0.65 * stat_avg
            minutos_prom = float(perfil.get("min_avg", 0.0) or 0.0)
            minutos_l5 = float(perfil.get("min_l5", minutos_prom) or minutos_prom)
            es_titular = (minutos_prom >= 24.0) or (minutos_l5 >= 25.0)
            if game_spread >= 8.5 and es_titular:
                descuento_blowout = 0.88 if game_spread >= 11.5 else 0.94
            factor_blowout_extra = descuento_blowout

        proy_bruta = proj_base * boost_mercado * factor_blowout_extra

        # Shrinkage Bayesiano hacia la línea de mercado de Las Vegas / Bovada:
        # Ponderación 60% a la línea de mercado, 40% al modelo bruto del jugador.
        # Esto elimina la "Maldición del Ganador" y evita que el sistema elija picks
        # simplemente porque el modelo se equivocó por 5 puntos contra la casa.
        w_mercado = 0.60
        proy_continua = (1.0 - w_mercado) * proy_bruta + w_mercado * linea_modelo
        proyeccion = round(proy_continua, 1)

        # Sigma: shrinkage hacia prior de liga, escalado por cambio de expectativa
        # y ensanchamiento predictivo por incertidumbre de la media.
        n_partidos = float(perfil.get("games_played", 5) or 5)
        peso_prior_sigma = 5.0 / (n_partidos + 5.0)
        stat_std_blended = (1.0 - peso_prior_sigma) * max(stat_std_raw, sigma_floor) + peso_prior_sigma * sigma_prior
        factor_escala = max(0.1, boost_mercado * factor_blowout_extra)
        sigma_floor_adj = sigma_floor * math.sqrt(factor_escala)
        stat_std = max(sigma_floor_adj, stat_std_blended * math.sqrt(factor_escala))
        stat_std *= math.sqrt(1.0 + 1.0 / max(n_partidos, 1.0))

        prob_over_raw, prob_under_raw, prob_push_raw = _calcular_probabilidades_mercado(
            mercado=mercado,
            linea=linea_modelo,
            mu=proy_continua,
            sigma=stat_std,
        )

        # Probabilidad justa de mercado (sin vig)
        if over_dec and under_dec:
            io = 1.0 / over_dec
            iu = 1.0 / under_dec
            implied_over = io / (io + iu)
            implied_under = iu / (io + iu)
        elif over_dec:
            io = 1.0 / over_dec
            # One-sided plus-money: vig típico 8-10% (estimado, no medido)
            implied_over = float(np.clip(io / 1.095, 0.05, 0.95))
            implied_under = None
        else:
            iu = 1.0 / under_dec
            implied_under = float(np.clip(iu / 1.095, 0.05, 0.95))
            implied_over = 1.0 - implied_under

        # 1. Modelo condicionado a no-push (Over + Under = 1)
        p_no_push = prob_over_raw + prob_under_raw
        p_over_cond_raw = (prob_over_raw / p_no_push) if p_no_push > 0 else 0.50

        # 2. Shrinkage hacia el mercado
        peso_mercado = 0.65 if (over_dec and over_dec >= 2.15) else 0.50
        p_over_cond_shrunk = (1.0 - peso_mercado) * p_over_cond_raw + peso_mercado * implied_over

        # 3. Clip de seguridad proporcional a la probabilidad implícita justa del mercado
        # En apuestas deportivas, una ventaja analítica real oscila entre +/- 1% y +/- 8% sobre el mercado.
        # Un clip estático en [0.36, 0.64] inflaba artificialmente cuotas altas (ej. cuota 3.40 con prob justa 27%
        # se forzaba a 36%, inventando un EV falso de +11.8%).
        max_edge_prob = 0.08
        min_p = max(0.04, implied_over - max_edge_prob)
        max_p = min(0.96, implied_over + max_edge_prob)
        p_over_shrunk = float(np.clip(p_over_cond_shrunk, min_p, max_p))

        p_over_cond_clipped = float(np.clip(p_over_shrunk, 0.05, 0.95))
        p_under_cond_clipped = 1.0 - p_over_cond_clipped

        # 4. Reescalar por (1 - push)
        prob_push_blended = round(prob_push_raw, 4) if (linea_modelo % 1 == 0) else 0.0
        prob_over_blended = round(p_over_cond_clipped * (1.0 - prob_push_blended), 4)
        prob_under_blended = round(p_under_cond_clipped * (1.0 - prob_push_blended), 4)

        # 5. EV real (push devuelve el stake)
        raw_ev_over = (prob_over_blended * (over_dec - 1.0) - prob_under_blended) * 100.0 if over_dec else -100.0
        raw_ev_under = (prob_under_blended * (under_dec - 1.0) - prob_over_blended) * 100.0 if under_dec else -100.0
        ev_over = _comprimir_ev_suave(raw_ev_over) if over_dec else -100.0
        ev_under = _comprimir_ev_suave(raw_ev_under) if under_dec else -100.0

        # Selección del pick con Candado de Coherencia Direccional (Proyección vs Línea)
        if is_milestone:
            if not over_dec or proyeccion <= linea_modelo:
                continue
            pick_tipo = "OVER"
            pick_ev, pick_ev_raw = ev_over, raw_ev_over
            pick_prob = prob_over_blended
            pick_cuota_am = row.get("over_american")
            pick_cuota_dec = over_dec
            pick_implied_fair = implied_over
        else:
            # Candado de Coherencia Direccional (Proyección vs Línea de Mercado):
            # 1. Si la proyección supera la línea (proyeccion > linea_modelo), SOLO se permite evaluar OVER.
            # 2. Si la proyección está por debajo de la línea (proyeccion < linea_modelo), SOLO se permite evaluar UNDER.
            # 3. Si proyeccion == linea_modelo, no existe margen direccional del modelo y se descarta el pick.
            # Esto evita contradicciones visuales y analíticas donde se recomienda UNDER a pesar de proyectar más que la línea
            # simplemente porque la casa ofreció un momio positivo asimétrico (+140) en el lado perdedor esperado.
            if proyeccion > linea_modelo:
                if not over_dec:
                    continue
                pick_tipo = "OVER"
                pick_ev, pick_ev_raw = ev_over, raw_ev_over
                pick_prob = prob_over_blended
                pick_cuota_am = row.get("over_american")
                pick_cuota_dec = over_dec
                pick_implied_fair = implied_over
            elif proyeccion < linea_modelo:
                if not under_dec:
                    continue
                pick_tipo = "UNDER"
                pick_ev, pick_ev_raw = ev_under, raw_ev_under
                pick_prob = prob_under_blended
                pick_cuota_am = row.get("under_american")
                pick_cuota_dec = under_dec
                pick_implied_fair = implied_under
            else:
                continue

        if not pick_cuota_dec:
            continue

        # Umbrales de estrellas calibrados profesionalmente (EV y Edge reales)
        umbral_factor = FACTOR_UMBRAL_MILESTONE if is_milestone else 1.0

        colchon_linea = abs(proyeccion - linea_modelo)
        games_p = int(perfil.get("games_played", 0) or 0)
        
        # En asistencias, la dependencia del tiro del compañero exige un colchón más seguro (0.5 vs 0.3)
        if mercado == "Total Assists":
            min_colchon = 0.5
        elif mercado in MERCADOS_CONTEO:
            min_colchon = 0.3
        else:
            min_colchon = 0.6

        # Candado Anti-Varianza / Filtro de Divergencia Extrema en NBA (>35% de la línea en líneas >= 5.0)
        divergencia_extrema = False
        if linea_modelo >= 5.0 and (colchon_linea / linea_modelo) > 0.35:
            divergencia_extrema = True

        # Edge matemático real contra la probabilidad implícita justa de la casa
        edge_pick = (pick_prob - pick_implied_fair) if pick_implied_fair else (pick_prob - 0.5238)

        # Coherencia direccional: Temporada y L5 deben apuntar en la misma dirección
        misma_direccion = (
            (hit_rate_l5 >= 0.50 and hit_rate_season >= 0.50) if pick_tipo == "OVER"
            else (hit_rate_l5 <= 0.50 and hit_rate_season <= 0.50)
        )

        es_asistencias = (mercado == "Total Assists")
        min_ev_top = (3.0 if es_asistencias else 2.0) * umbral_factor
        min_prob_top = 0.55 if es_asistencias else 0.52

        es_top_pick = (
            pick_prob >= min_prob_top
            and pick_ev >= min_ev_top
            and edge_pick >= 0.015
            and colchon_linea >= min_colchon
            and misma_direccion
            and (hit_rate_l5 >= 0.60 if pick_tipo == "OVER" else hit_rate_l5 <= 0.40)
            and games_p >= 5
            and minutos_prom >= 18.0
            and pick_cuota_dec <= 2.25
            and not divergencia_extrema
        )

        es_alta_confianza = (
            pick_prob >= 0.52
            and pick_ev >= 1.0 * umbral_factor
            and edge_pick >= 0.008
            and games_p >= 5
            and minutos_prom >= 16.0
            and misma_direccion
            and pick_cuota_dec <= 2.25
            and not divergencia_extrema
        )

        if es_top_pick:
            estrellas, confianza = "⭐⭐⭐", "ALTA"
        elif es_alta_confianza:
            estrellas, confianza = "⭐⭐", "MEDIA"
        elif pick_ev >= 0.5 * umbral_factor:
            estrellas, confianza = "⭐", "MODERADA"
        else:
            estrellas, confianza = "⚪", "NEUTRAL"

        es_candado = bool(
            es_top_pick
            and (hit_rate_l5 >= 0.80 if pick_tipo == "OVER" else hit_rate_l5 <= 0.20)
            and (hit_rate_season >= 0.55 if pick_tipo == "OVER" else hit_rate_season <= 0.45)
            and colchon_linea >= (min_colchon * 1.20)
            and (1.70 <= pick_cuota_dec <= 2.15)
            and minutos_prom >= 22.0
            and game_spread < 9.5
        )

        # Reglas defensivas: blowouts y milestones
        if es_titular and pick_tipo == "OVER":
            if game_spread >= 8.5:
                es_candado = False
            if game_spread >= 11.5 and es_top_pick:
                es_top_pick = False
                estrellas, confianza = "⭐⭐", "MEDIA"

        if is_milestone:
            es_candado = False
            if es_top_pick:
                es_top_pick = False
                estrellas, confianza = "⭐⭐", "MEDIA"

        prom_l5_val = stat_l5 if n_l5 > 0 else stat_avg
        if pick_tipo == "OVER":
            tendencia = f"Over en {ov_l5}/{n_l5} últimos (promedia {prom_l5_val:.1f} en L5 vs línea {linea_modelo})"
        else:
            tendencia = f"Under en {n_l5 - ov_l5}/{n_l5} últimos (promedia {prom_l5_val:.1f} en L5 vs línea {linea_modelo})"

        predicciones.append({
            "game": row["game"],
            "fecha": row["fecha"],
            "hora": row["hora"],
            "commence_ts": row.get("commence_ts"),
            "away_team": row["away_team"],
            "home_team": row["home_team"],
            "player_name": row["player_name"],
            "player_clean": p_clean,
            "team": equipo,
            "position": perfil.get("position", ""),
            "market": mercado,
            "line": linea,
            "line_modelo": linea_modelo,
            "projection": proyeccion,
            "stat_avg": stat_avg,
            "stat_l5": stat_l5,
            "games_played": perfil.get("games_played", 0),
            "hit_rate_season": hit_rate_season,
            "hit_rate_l5": hit_rate_l5,
            "pick_type": pick_tipo,
            "pick_odds_american": (
                str(pick_cuota_am).strip()
                if pick_cuota_am is not None and not pd.isna(pick_cuota_am) and str(pick_cuota_am).strip() not in ("", "None", "nan")
                else _decimal_a_americana(pick_cuota_dec)
            ),
            "pick_odds_decimal": pick_cuota_dec,
            "model_prob": pick_prob,
            "implied_prob_vig": round(1.0 / pick_cuota_dec, 4),
            "fair_implied_prob": round(pick_implied_fair, 4) if pick_implied_fair is not None else None,
            "implied_prob": round(pick_implied_fair, 4) if pick_implied_fair is not None else None,
            "market_family": MAPA_FAMILIAS_MERCADOS.get(mercado, mercado),
            "ev_pct": pick_ev,
            "ev_raw": round(pick_ev_raw, 1),
            "stars": estrellas,
            "confidence": confianza,
            "trend": tendencia,
            "boost_lesion_pct": round((boost_lesion - 1.0) * 100.0, 1),
            "game_spread": game_spread,
            "descuento_blowout_pct": round((1.0 - descuento_blowout) * 100.0, 1),
            "minutos_proyectados": minutos_proyectados,
            "tasa_por_minuto": tasa_por_minuto,
            "factor_defensa_rival": round(factor_defensa_rival, 3),
            "is_milestone": is_milestone,
            "es_candado": es_candado,
            "registrado_en": datetime.now(ZONA_CDMX).isoformat(),
            "timestamp_cuota": str(row.get("timestamp_cuota") or datetime.now(ZONA_CDMX).isoformat()),
            "model_version": _obtener_model_version(),
        })

    df_res = pd.DataFrame(predicciones)

    if not df_res.empty:
        # Deduplicar por jugador + familia de mercado.
        # Un milestone debe superar en PENALIZACION_EV_MILESTONE puntos a la línea regular para
        # desplazarla; una línea regular con EV inválido (-100) pierde de forma natural.
        df_res["_ev_ajustado"] = df_res["ev_raw"] - df_res["is_milestone"] * PENALIZACION_EV_MILESTONE
        df_res.sort_values(by="_ev_ajustado", ascending=False, inplace=True)
        df_res.drop_duplicates(subset=["player_name", "market_family"], keep="first", inplace=True)
        df_res.drop(columns=["_ev_ajustado"], inplace=True)

        # Presentación y cap por partido en orden de EV real
        df_res.sort_values(by="ev_raw", ascending=False, inplace=True)
        df_res.reset_index(drop=True, inplace=True)

        # Cap: máximo 3 picks ⭐⭐⭐ por partido; los excedentes bajan a ⭐⭐ y pierden el candado.
        conteo_por_juego: Dict[str, int] = {}
        estrellas_ajustadas, confianzas_ajustadas, candados_ajustados = [], [], []
        for _, r in df_res.iterrows():
            estrellas_act = r["stars"]
            conf_act = r["confidence"]
            candado_act = bool(r.get("es_candado", False))
            if estrellas_act == "⭐⭐⭐":
                c = conteo_por_juego.get(r["game"], 0)
                if c >= 3:
                    estrellas_ajustadas.append("⭐⭐")
                    confianzas_ajustadas.append("MEDIA")
                    candados_ajustados.append(False)
                else:
                    conteo_por_juego[r["game"]] = c + 1
                    estrellas_ajustadas.append("⭐⭐⭐")
                    confianzas_ajustadas.append(conf_act)
                    candados_ajustados.append(candado_act)
            else:
                estrellas_ajustadas.append(estrellas_act)
                confianzas_ajustadas.append(conf_act)
                candados_ajustados.append(False)

        df_res["stars"] = estrellas_ajustadas
        df_res["confidence"] = confianzas_ajustadas
        df_res["es_candado"] = candados_ajustados

        # Selección oficial de los Top 5 picks más seguros del día (+EV)
        df_res["es_top5_oficial"] = False
        df_res["es_top20_oficial"] = False
        df_top5 = seleccionar_top_props_diarios(df_res, limite=5)
        if not df_top5.empty:
            df_res.loc[df_top5.index, "es_top5_oficial"] = True
            df_res.loc[df_top5.index, "es_top20_oficial"] = True

        df_res.to_parquet(RUTA_PRED_PARQUET, index=False)
        with open(RUTA_PRED_JSON, "w", encoding="utf-8") as f:
            json.dump(df_res.to_dict(orient="records"), f, indent=2, ensure_ascii=False, default=str)

        try:
            from nba.evaluar_props import registrar_props_pendientes
            # Solo registramos en el historial oficial el Top 5 de máxima confianza
            props_para_registro = df_top5
            if not props_para_registro.empty:
                registrar_props_pendientes(props_para_registro)
            logger.info(f"💾 Registrados {len(props_para_registro)} props oficiales (Top 5) en el historial de rendimiento.")
        except Exception as e_reg:
            logger.warning(f"No se pudieron registrar props pendientes en el historial: {e_reg}")

        try:
            from nba.auditoria_publica import registrar_picks
            res_audit = registrar_picks(df_res)
            logger.info(
                f"🔒 Ledger criptográfico sellado: {res_audit['nuevos']} nuevos, "
                f"{res_audit['duplicados']} duplicados, {res_audit['rechazados']} rechazados."
            )
        except Exception as e_audit:
            logger.warning(f"No se pudo registrar en ledger criptográfico de auditoría: {e_audit}")

        logger.info(f"🎯 Generadas {len(df_res)} predicciones de props ({len(df_top5)} Top 5 oficiales). Top EV: +{df_res['ev_pct'].max()}%")

    return df_res


if __name__ == "__main__":
    t0 = time.time()
    df_preds = generar_predicciones_props_hoy(usar_cache_bovada=True)
    print(f"Predicciones listas en {time.time() - t0:.2f}s. Total: {len(df_preds)}")
    if not df_preds.empty:
        # Revisión rápida de milestones para validar el ajuste de línea
        ms = df_preds[df_preds["is_milestone"] == 1]
        if not ms.empty:
            print("\nMuestra de milestones (line original vs line_modelo):")
            print(ms.head(5)[["player_name", "market", "line", "line_modelo", "pick_odds_american", "ev_raw"]].to_string())

        top = df_preds[df_preds["ev_pct"] >= 5.0]
        print(f"\nPicks con EV >= 5%: {len(top)}")
        cols = ["player_name", "team", "market", "line", "projection", "pick_type", "pick_odds_american", "ev_pct", "stars", "trend"]
        print(top.head(15)[cols].to_string())