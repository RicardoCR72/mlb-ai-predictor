"""Pipeline de inferencia diaria para la NBA (V2).

Innovaciones V2:
1. Regresión hacia la media de temporada regular para perfiles de equipo provenientes de playoffs pasados.
2. Ensamble híbrido (HistGradientBoosting + RidgeCV) para Spread, Moneyline y Totales.
3. Shrinkage Bayesiano hacia líneas de mercado DraftKings en Totales y Spreads.
4. Filtro riguroso de Valor Esperado (EV > 0 y Edge >= +2.5%) eliminando el sesgo sistemático a UNDER.
5. Congelación de momios previa al juego y liquidación automática de marcadores finales.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nba.proveedor_cuotas import (
    obtener_calendario_y_cuotas_nba,
    normalizar_equipo,
    american_to_decimal,
    american_to_prob
)
from nba.entrenar_spread_ml import proyectar_partido_spread, FEATURES_SPREAD
from nba.entrenar_totales import proyectar_partido_totales, FEATURES_TOTALES
from core.constants import NBA_TEAMS, ZONA_CDMX
from core.calibracion_probabilidades import calibrar_probabilidades_2way

RUTA_RAW = RAIZ / "data" / "nba" / "raw" / "partidos_historicos_nba.parquet"
RUTA_DATASET = RAIZ / "data" / "nba" / "processed" / "dataset_partidos_nba.parquet"
RUTA_MODELO_SPREAD = RAIZ / "modelos_nba" / "modelo_spread_ml.joblib"
RUTA_MODELO_TOTALES = RAIZ / "modelos_nba" / "modelo_totales.joblib"
RUTA_PREDICCIONES = RAIZ / "data" / "nba" / "predictions"
RUTA_PREDICCIONES.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def cargar_perfiles_recientes_equipos() -> Dict[str, Dict[str, Any]]:
    """Calcula el perfil rodante ACTUALIZADO (incluyendo el último juego disputado) por equipo dentro de su temporada."""
    if RUTA_RAW.exists():
        from nba.construir_dataset import (
            resolver_local_visitante,
            calcular_metricas_avanzadas_equipo,
            fusionar_datos_rival,
        )

        df_raw = pd.read_parquet(RUTA_RAW)
        df_raw = df_raw[df_raw["GAME_ID"].str[:3].isin(["002", "004", "005"])].copy()
        df_home = resolver_local_visitante(df_raw)
        df_metrics = calcular_metricas_avanzadas_equipo(df_home)
        df_team = fusionar_datos_rival(df_metrics)
        df_team["GAME_DATE_DT"] = pd.to_datetime(df_team["GAME_DATE"])
        df_team = df_team.sort_values(["TEAM_ABBREVIATION", "SEASON", "GAME_DATE_DT"]).reset_index(drop=True)

        metricas_calc = [
            "PTS", "OPP_PTS", "PACE", "ORTG", "DRTG", "NET_RTG",
            "EFG_PCT", "OPP_EFG_PCT", "TOV_PCT", "ORB_PCT", "FT_RATE", "WIN",
        ]

        # Promedios dinámicos derivados de la temporada actual
        latest_season_global = str(df_team["SEASON"].max())
        df_act = df_team[df_team["SEASON"] == latest_season_global]
        if not df_act.empty and len(df_act) >= 40:
            baseline_pts = round(float(df_act["PTS"].mean()), 1)
            baseline_pace = round(float(df_act["PACE"].mean()), 1)
            baseline_rtg = round(float(df_act["ORTG"].mean()), 1)
        else:
            baseline_pts = 113.6
            baseline_pace = 100.2
            baseline_rtg = 113.6

        perfiles: Dict[str, Dict[str, Any]] = {}
        for team, grp in df_team.groupby("TEAM_ABBREVIATION"):
            latest_season = grp["SEASON"].max()
            grp_season = grp[grp["SEASON"] == latest_season].sort_values("GAME_DATE_DT")
            if grp_season.empty:
                continue

            prof: Dict[str, Any] = {}
            for ventana in [5, 10, 20]:
                tail = grp_season.tail(ventana)
                for m in metricas_calc:
                    prof[f"{m}_L{ventana}"] = float(tail[m].mean())

            # Promedios de temporada completa del equipo
            prof["PACE_SEASON"] = float(grp_season["PACE"].mean())
            prof["ORTG_SEASON"] = float(grp_season["ORTG"].mean())
            prof["DRTG_SEASON"] = float(grp_season["DRTG"].mean())
            prof["NET_RTG_SEASON"] = float(grp_season["NET_RTG"].mean())

            fechas = grp_season["GAME_DATE_DT"].tolist()
            last_dt_ts = fechas[-1]
            last_dt = last_dt_ts.strftime("%Y-%m-%d")
            prev_dt_2 = fechas[-2].strftime("%Y-%m-%d") if len(fechas) >= 2 else ""

            if len(fechas) >= 2:
                rest_hist = float(max(0, min((fechas[-1] - fechas[-2]).days, 7)))
            else:
                rest_hist = 3.0
            prof["REST_DAYS"] = rest_hist
            prof["IS_B2B"] = 1 if rest_hist == 1.0 else 0
            prof["IS_3_IN_4"] = 1 if (len(fechas) >= 3 and (fechas[-1] - fechas[-3]).days <= 4) else 0

            # Regresión si el equipo no ha debutado aún en la temporada 2026-27
            if last_dt < "2026-01-01":
                for c in ["PTS_L5", "PTS_L10", "PTS_L20", "OPP_PTS_L5", "OPP_PTS_L10", "OPP_PTS_L20"]:
                    prof[c] = 0.50 * prof.get(c, baseline_pts) + 0.50 * baseline_pts
                for c in ["PACE_L5", "PACE_L10", "PACE_L20"]:
                    prof[c] = 0.50 * prof.get(c, baseline_pace) + 0.50 * baseline_pace
                for c in ["ORTG_L5", "ORTG_L10", "ORTG_L20", "DRTG_L5", "DRTG_L10", "DRTG_L20"]:
                    prof[c] = 0.50 * prof.get(c, baseline_rtg) + 0.50 * baseline_rtg

            prof["LAST_DATE"] = last_dt
            prof["PREV_DATE_2"] = prev_dt_2
            perfiles[str(team)] = prof

        if perfiles:
            return perfiles

    if not RUTA_DATASET.exists():
        raise FileNotFoundError(f"Falta el dataset procesado en {RUTA_DATASET}.")

    df = pd.read_parquet(RUTA_DATASET)
    cols_base = [
        "REST_DAYS", "IS_B2B", "IS_3_IN_4",
        "PTS_L5", "OPP_PTS_L5", "PACE_L5", "ORTG_L5", "DRTG_L5", "NET_RTG_L5",
        "EFG_PCT_L5", "TOV_PCT_L5", "ORB_PCT_L5", "FT_RATE_L5", "WIN_L5",
        "PTS_L10", "OPP_PTS_L10", "PACE_L10", "ORTG_L10", "DRTG_L10", "NET_RTG_L10",
        "EFG_PCT_L10", "OPP_EFG_PCT_L10", "TOV_PCT_L10", "ORB_PCT_L10", "FT_RATE_L10", "WIN_L10",
        "PTS_L20", "OPP_PTS_L20", "PACE_L20", "ORTG_L20", "DRTG_L20", "NET_RTG_L20",
        "EFG_PCT_L20", "TOV_PCT_L20", "ORB_PCT_L20", "FT_RATE_L20", "WIN_L20",
    ]

    perfiles = {}
    todos_equipos = set(df["HOME_TEAM"].unique()).union(set(df["AWAY_TEAM"].unique()))

    for team in todos_equipos:
        matches = df[(df["HOME_TEAM"] == team) | (df["AWAY_TEAM"] == team)].sort_values("GAME_DATE")
        if matches.empty:
            continue
        last_match = matches.iloc[-1]
        is_home = (last_match["HOME_TEAM"] == team)
        pref = "HOME_" if is_home else "AWAY_"

        prof = {c: float(last_match.get(pref + c, 0.0)) for c in cols_base}
        prof["LAST_DATE"] = str(last_match["GAME_DATE"])[:10]
        prof["PREV_DATE_2"] = ""
        perfiles[team] = prof

    return perfiles


def _calcular_fatiga_en_fecha(prof: Dict[str, Any], fecha_juego_str: Any) -> tuple[float, int, int]:
    """Calcula REST_DAYS, IS_B2B e IS_3_IN_4 exactos para la fecha del partido."""
    last_dt_str = str(prof.get("LAST_DATE", "") or "")[:10]
    prev_2_str = str(prof.get("PREV_DATE_2", "") or "")[:10]
    if not last_dt_str or not fecha_juego_str:
        return float(prof.get("REST_DAYS", 2.0)), int(prof.get("IS_B2B", 0)), int(prof.get("IS_3_IN_4", 0))
    try:
        dt_juego = datetime.strptime(str(fecha_juego_str)[:10], "%Y-%m-%d").date()
        dt_last = datetime.strptime(last_dt_str, "%Y-%m-%d").date()
        diff = max(0, (dt_juego - dt_last).days)
        if diff > 20:
            return 3.0, 0, 0
        rest = float(min(diff, 7))
        is_b2b = 1 if diff == 1 else 0
        is_3_in_4 = 0
        if prev_2_str:
            dt_prev2 = datetime.strptime(prev_2_str, "%Y-%m-%d").date()
            if (dt_juego - dt_prev2).days <= 4:
                is_3_in_4 = 1
        return rest, is_b2b, is_3_in_4
    except Exception:
        return float(prof.get("REST_DAYS", 2.0)), int(prof.get("IS_B2B", 0)), int(prof.get("IS_3_IN_4", 0))


def predecir_partidos_hoy(force_refresh: bool = False, fecha: Optional[str] = None) -> List[Dict[str, Any]]:
    """Genera las predicciones completas para la cartelera de hoy en la NBA con el motor V2."""
    logger.info("🏀 Iniciando pipeline de predicciones diarias NBA V2...")

    if not RUTA_MODELO_SPREAD.exists() or not RUTA_MODELO_TOTALES.exists():
        raise FileNotFoundError("Los modelos de la NBA no están entrenados. Ejecuta nba/entrenar_spread_ml.py y nba/entrenar_totales.py.")

    bundle_spread = joblib.load(RUTA_MODELO_SPREAD)
    bundle_totales = joblib.load(RUTA_MODELO_TOTALES)
    perfiles = cargar_perfiles_recientes_equipos()

    hoy_cdmx = fecha or datetime.now(ZONA_CDMX).strftime("%Y%m%d")
    juegos = obtener_calendario_y_cuotas_nba(fecha=hoy_cdmx, force_refresh=force_refresh)
    if not juegos and not fecha:
        juegos = obtener_calendario_y_cuotas_nba(force_refresh=force_refresh)

    archivo_json = RUTA_PREDICCIONES / "predicciones_nba_hoy.json"

    if not juegos:
        logger.info("No hay partidos programados para hoy en el calendario de ESPN.")
        return []

    # Cargar predicciones previas para congelar cuotas y selecciones pre-partido
    predicciones_previas: Dict[str, Dict[str, Any]] = {}
    if archivo_json.exists():
        try:
            with open(archivo_json, "r", encoding="utf-8") as f:
                preds_existentes = json.load(f)
            for p in preds_existentes:
                if p.get("id_evento"):
                    predicciones_previas[str(p["id_evento"])] = p
        except Exception:
            pass

    predicciones = []

    # Perfil promedio de la liga como fallback neutral (elimina sesgo BOS como local y DET como visita)
    perfil_liga_neutral = {
        "NET_RTG_L5": 0.0, "NET_RTG_L10": 0.0, "NET_RTG_L20": 0.0,
        "ORTG_L10": 113.6, "DRTG_L10": 113.6, "EFG_PCT_L10": 0.54,
        "TOV_PCT_L10": 0.135, "ORB_PCT_L10": 0.24, "FT_RATE_L10": 0.22,
        "PTS_L10": 113.6, "OPP_PTS_L10": 113.6,
        "WIN_L10": 0.5, "REST_DAYS": 2.0, "PACE_L5": 100.2, "PACE_L10": 100.2,
        "PACE_SEASON": 100.2, "ORTG_SEASON": 113.6, "DRTG_SEASON": 113.6, "NET_RTG_SEASON": 0.0,
    }
    if perfiles:
        try:
            for k in list(perfil_liga_neutral.keys()):
                vals = [p[k] for p in perfiles.values() if k in p and pd.notna(p.get(k))]
                if vals:
                    perfil_liga_neutral[k] = float(np.mean(vals))
        except Exception:
            pass

    for j in juegos:
        id_ev = str(j.get("id_evento", "")).strip()
        prev = predicciones_previas.get(id_ev)

        estado_juego = str(j.get("estado", "")).upper()
        es_final = ("FINAL" in estado_juego) or ("FULL_TIME" in estado_juego) or ("STATUS_FINAL" in estado_juego)
        en_vivo = ("PROGRESS" in estado_juego) or ("HALFTIME" in estado_juego)
        # Solo se considera comenzado si está en vivo/final o si tiene marcador > 0 y no está en estado programado
        marcador_activo = (j.get("marcador_local") is not None and j.get("marcador_local") > 0)
        ya_comenzo = es_final or en_vivo or (marcador_activo and "SCHEDULED" not in estado_juego)
        cuotas_vacias = (j.get("moneyline_local") is None and j.get("total_linea") is None)

        if prev and (ya_comenzo or (cuotas_vacias and not force_refresh)) and prev.get("pick_seleccion"):
            prev_actualizado = dict(prev)
            prev_actualizado["estado"] = j.get("estado", prev.get("estado"))
            prev_actualizado["descripcion_estado"] = j.get("descripcion_estado", prev.get("descripcion_estado"))
            if j.get("marcador_local") is not None:
                prev_actualizado["marcador_local"] = j["marcador_local"]
            if j.get("marcador_visita") is not None:
                prev_actualizado["marcador_visita"] = j["marcador_visita"]

            if "candidatos" not in prev_actualizado or not prev_actualizado["candidatos"]:
                if prev_actualizado.get("confianza") in ["ALTA", "MEDIA"] and prev_actualizado.get("pick_seleccion"):
                    prev_actualizado["candidatos"] = [{
                        "mercado": prev_actualizado.get("pick_mercado", "Moneyline"),
                        "seleccion": prev_actualizado.get("pick_seleccion"),
                        "probabilidad": float(prev_actualizado.get("pick_probabilidad") or 0.5),
                        "edge": float(prev_actualizado.get("pick_edge") or 0.0),
                        "ev": float(prev_actualizado.get("pick_ev") or 0.0),
                        "cuota": str(prev_actualizado.get("pick_cuota") or "-110"),
                        "cuota_dec": float(prev_actualizado.get("pick_cuota_dec") or 1.91),
                        "confianza": prev_actualizado.get("confianza", "MEDIA"),
                        "detalle": prev_actualizado.get("pick_detalle", ""),
                    }]
                else:
                    prev_actualizado["candidatos"] = []

            # Si ya terminó y aún está pendiente, liquidar
            if es_final and prev_actualizado.get("marcador_local") is not None:
                try:
                    from nba.registro import liquidar_partido
                    cuota_calc = float(prev_actualizado.get("pick_cuota_dec") or 0.0)
                    if cuota_calc <= 1.0:
                        from core.ui_boleta import parsear_cuota_decimal
                        cuota_calc = parsear_cuota_decimal(prev_actualizado.get("pick_cuota"))
                    if cuota_calc <= 1.0:
                        cuota_calc = 1.909

                    res, u_gan = liquidar_partido(pd.Series({
                        "equipo_local": prev_actualizado.get("equipo_local"),
                        "equipo_visitante": prev_actualizado.get("equipo_visita"),
                        "mercado": prev_actualizado.get("pick_mercado"),
                        "seleccion": prev_actualizado.get("pick_seleccion"),
                        "linea": prev_actualizado.get("linea_total") if "Totales" in prev_actualizado.get("pick_mercado", "") else prev_actualizado.get("linea_spread"),
                        "cuota": cuota_calc,
                        "marcador_local": prev_actualizado.get("marcador_local"),
                        "marcador_visitante": prev_actualizado.get("marcador_visita"),
                    }))
                    if res != "PENDIENTE":
                        prev_actualizado["resultado"] = res
                        prev_actualizado["unidades_ganadas"] = u_gan
                except Exception:
                    pass

            predicciones.append(prev_actualizado)
            continue

        home_abbr = normalizar_equipo(j["abbr_local"])
        away_abbr = normalizar_equipo(j["abbr_visita"])

        home_prof = perfiles.get(home_abbr, perfil_liga_neutral)
        away_prof = perfiles.get(away_abbr, perfil_liga_neutral)

        home_rest, home_b2b, _ = _calcular_fatiga_en_fecha(home_prof, j.get("fecha_cdmx"))
        away_rest, away_b2b, _ = _calcular_fatiga_en_fecha(away_prof, j.get("fecha_cdmx"))
        is_playoff = int(j.get("is_playoff", 0) or 0)

        # Diferenciales clave no redundantes
        diff_net_l5 = home_prof.get("NET_RTG_L5", 0.0) - away_prof.get("NET_RTG_L5", 0.0)
        diff_net_l20 = home_prof.get("NET_RTG_L20", 0.0) - away_prof.get("NET_RTG_L20", 0.0)

        feats_spread = {
            "DIFF_NET_RTG_L5": diff_net_l5,
            "DIFF_NET_RTG_L20": diff_net_l20,
            "HOME_ORTG_L10": home_prof.get("ORTG_L10", 113.6),
            "AWAY_ORTG_L10": away_prof.get("ORTG_L10", 113.6),
            "HOME_DRTG_L10": home_prof.get("DRTG_L10", 113.6),
            "AWAY_DRTG_L10": away_prof.get("DRTG_L10", 113.6),
            "HOME_EFG_PCT_L10": home_prof.get("EFG_PCT_L10", 0.54),
            "AWAY_EFG_PCT_L10": away_prof.get("EFG_PCT_L10", 0.54),
            "HOME_TOV_PCT_L10": home_prof.get("TOV_PCT_L10", 0.135),
            "AWAY_TOV_PCT_L10": away_prof.get("TOV_PCT_L10", 0.135),
            "HOME_ORB_PCT_L10": home_prof.get("ORB_PCT_L10", 0.24),
            "AWAY_ORB_PCT_L10": away_prof.get("ORB_PCT_L10", 0.24),
            "HOME_REST_DAYS": home_rest,
            "AWAY_REST_DAYS": away_rest,
            "HOME_IS_B2B": home_b2b,
            "AWAY_IS_B2B": away_b2b,
            "IS_PLAYOFF": is_playoff,
        }

        feats_totales = {
            "HOME_PACE_L5": home_prof.get("PACE_L5", 100.2),
            "AWAY_PACE_L5": away_prof.get("PACE_L5", 100.2),
            "HOME_PACE_L10": home_prof.get("PACE_L10", 100.2),
            "AWAY_PACE_L10": away_prof.get("PACE_L10", 100.2),
            "HOME_PTS_L10": home_prof.get("PTS_L10", 113.6),
            "AWAY_PTS_L10": away_prof.get("PTS_L10", 113.6),
            "HOME_OPP_PTS_L10": home_prof.get("OPP_PTS_L10", 113.6),
            "AWAY_OPP_PTS_L10": away_prof.get("OPP_PTS_L10", 113.6),
            "HOME_ORTG_L10": home_prof.get("ORTG_L10", 113.6),
            "AWAY_ORTG_L10": away_prof.get("ORTG_L10", 113.6),
            "HOME_DRTG_L10": home_prof.get("DRTG_L10", 113.6),
            "AWAY_DRTG_L10": away_prof.get("DRTG_L10", 113.6),
            "HOME_EFG_PCT_L10": home_prof.get("EFG_PCT_L10", 0.54),
            "AWAY_EFG_PCT_L10": away_prof.get("EFG_PCT_L10", 0.54),
            "HOME_TOV_PCT_L10": home_prof.get("TOV_PCT_L10", 0.135),
            "AWAY_TOV_PCT_L10": away_prof.get("TOV_PCT_L10", 0.135),
            "HOME_FT_RATE_L10": home_prof.get("FT_RATE_L10", 0.22),
            "AWAY_FT_RATE_L10": away_prof.get("FT_RATE_L10", 0.22),
            "HOME_REST_DAYS": home_rest,
            "AWAY_REST_DAYS": away_rest,
            "HOME_IS_B2B": home_b2b,
            "AWAY_IS_B2B": away_b2b,
            "IS_PLAYOFF": is_playoff,
        }

        # 0. Evaluación oficial del impacto de lesiones y ausencias
        from nba.servicio_lesiones import calcular_impacto_lesiones_partido
        info_les = calcular_impacto_lesiones_partido(j["equipo_visita"], j["equipo_local"])
        ajuste_spread_les = float(info_les.get("ajuste_neto_spread", 0.0))
        ajuste_tot_les = float(info_les.get("ajuste_total_puntos", 0.0))
        candado_les = bool(info_les.get("candado_lesion", False))
        alertas_les = info_les.get("alertas", [])

        spread_val = float(j.get("spread_linea") or 0.0)
        res_spread = proyectar_partido_spread(
            bundle_spread, feats_spread, spread_line=spread_val, ajuste_lesiones=ajuste_spread_les
        )

        linea_tot_raw = j.get("total_linea")
        linea_tot = float(linea_tot_raw) if linea_tot_raw is not None and float(linea_tot_raw) > 0 else None
        res_tot = proyectar_partido_totales(
            bundle_totales, feats_totales, linea_total=linea_tot if linea_tot else 0.0, ajuste_lesiones=ajuste_tot_les
        )

        # Probabilidades implícitas desparasitadas de mercado (sin vig)
        raw_ml_home = float(j.get("moneyline_local_prob") or 0.50)
        raw_ml_away = float(j.get("moneyline_visita_prob") or 0.50)
        suma_ml = raw_ml_home + raw_ml_away
        if suma_ml > 0:
            prob_ml_home_book = raw_ml_home / suma_ml
            prob_ml_away_book = raw_ml_away / suma_ml
        else:
            prob_ml_home_book = 0.50
            prob_ml_away_book = 0.50
        cuota_dec_home = float(j.get("moneyline_local_dec") or 1.91)
        cuota_dec_away = float(j.get("moneyline_visita_dec") or 1.91)
        cuota_dec_std = 1.909  # -110 fallback

        # Calibración Logística conjunta en el símplex 2-way (Moneyline)
        prob_ml_home_raw = res_spread["prob_local_win"]
        prob_ml_away_raw = res_spread["prob_visita_win"]
        prob_ml_home_cal, prob_ml_away_cal = calibrar_probabilidades_2way(
            prob_ml_home_raw, prob_ml_away_raw, temp=1.04
        )

        edge_ml_home = prob_ml_home_cal - prob_ml_home_book
        edge_ml_away = prob_ml_away_cal - prob_ml_away_book
        ev_ml_home = (prob_ml_home_cal * cuota_dec_home) - 1.0
        ev_ml_away = (prob_ml_away_cal * cuota_dec_away) - 1.0

        # Selección rigurosa de candidatos con filtro EV > 0 y Dead Zone
        picks_candidatos = []

        # 1. Totales Over / Under (Calibrado con Temperature Scaling 2-way, usando momio real)
        if linea_tot is not None and linea_tot > 0 and res_tot["recomendacion"] in ["OVER", "UNDER"]:
            prob_tot_raw = res_tot["prob_over"] if res_tot["recomendacion"] == "OVER" else res_tot["prob_under"]
            prob_tot_cal, _ = calibrar_probabilidades_2way(prob_tot_raw, 1.0 - prob_tot_raw, temp=1.04)
            cuota_tot_str = str(
                (j.get("over_momio") if res_tot["recomendacion"] == "OVER" else j.get("under_momio")) or "-110"
            )
            cuota_tot_dec = american_to_decimal(cuota_tot_str) or cuota_dec_std
            breakeven_tot = 1.0 / cuota_tot_dec
            edge_tot = prob_tot_cal - breakeven_tot
            ev_tot = (prob_tot_cal * cuota_tot_dec) - 1.0
            if edge_tot >= 0.025 and ev_tot >= 0.020:
                picks_candidatos.append({
                    "mercado": f"Totales ({res_tot['recomendacion']})",
                    "seleccion": f"{res_tot['recomendacion']} {linea_tot}",
                    "probabilidad": round(prob_tot_cal, 4),
                    "probabilidad_cruda": round(prob_tot_raw, 4),
                    "edge": round(edge_tot, 4),
                    "ev": round(ev_tot, 4),
                    "cuota": cuota_tot_str,
                    "cuota_dec": cuota_tot_dec,
                    "confianza": "ALTA" if edge_tot >= 0.055 and ev_tot >= 0.04 else "MEDIA",
                    "detalle": f"Proyección Calibrada: {res_tot['total_proyectado']} pts vs línea {linea_tot} (Edge: {edge_tot*100:+.1f}%, EV: {ev_tot*100:+.1f}%)"
                })

        # 2. Moneyline con valor real calibrado (permite underdogs con +EV real y P >= 32%)
        if prob_ml_home_cal >= 0.32 and edge_ml_home >= 0.035 and ev_ml_home >= 0.030:
            conf_h = "ALTA" if (edge_ml_home >= 0.060 and ev_ml_home >= 0.04 and prob_ml_home_cal >= 0.55) else "MEDIA"
            picks_candidatos.append({
                "mercado": "Moneyline",
                "seleccion": f"{j['equipo_local']} ML",
                "probabilidad": round(prob_ml_home_cal, 4),
                "probabilidad_cruda": round(prob_ml_home_raw, 4),
                "edge": round(edge_ml_home, 4),
                "ev": round(ev_ml_home, 4),
                "cuota": j.get("moneyline_local") or "-110",
                "cuota_dec": cuota_dec_home,
                "confianza": conf_h,
                "detalle": f"Prob Calibrada: {prob_ml_home_cal*100:.1f}% vs Book: {prob_ml_home_book*100:.1f}% (Edge: {edge_ml_home*100:+.1f}%, EV: +{ev_ml_home*100:.1f}%)"
            })
        elif prob_ml_away_cal >= 0.32 and edge_ml_away >= 0.035 and ev_ml_away >= 0.030:
            conf_a = "ALTA" if (edge_ml_away >= 0.060 and ev_ml_away >= 0.04 and prob_ml_away_cal >= 0.55) else "MEDIA"
            picks_candidatos.append({
                "mercado": "Moneyline",
                "seleccion": f"{j['equipo_visita']} ML",
                "probabilidad": round(prob_ml_away_cal, 4),
                "probabilidad_cruda": round(prob_ml_away_raw, 4),
                "edge": round(edge_ml_away, 4),
                "ev": round(ev_ml_away, 4),
                "cuota": j.get("moneyline_visita") or "-110",
                "cuota_dec": cuota_dec_away,
                "confianza": conf_a,
                "detalle": f"Prob Calibrada: {prob_ml_away_cal*100:.1f}% vs Book: {prob_ml_away_book*100:.1f}% (Edge: {edge_ml_away*100:+.1f}%, EV: +{ev_ml_away*100:.1f}%)"
            })

        # 3. Spread / Hándicap (Calibrado con Temperature Scaling 2-way, usando momio real)
        prob_cov_home_raw = res_spread["prob_cover_home"]
        prob_cov_away_raw = res_spread["prob_cover_away"]
        prob_cov_home_cal, prob_cov_away_cal = calibrar_probabilidades_2way(
            prob_cov_home_raw, prob_cov_away_raw, temp=1.04
        )

        cuota_sp_home_str = str(j.get("spread_local_momio") or "-110")
        cuota_sp_away_str = str(j.get("spread_visita_momio") or "-110")
        cuota_dec_sp_home = american_to_decimal(cuota_sp_home_str) or cuota_dec_std
        cuota_dec_sp_away = american_to_decimal(cuota_sp_away_str) or cuota_dec_std

        edge_cov_home = prob_cov_home_cal - (1.0 / cuota_dec_sp_home)
        edge_cov_away = prob_cov_away_cal - (1.0 / cuota_dec_sp_away)
        ev_cov_home = (prob_cov_home_cal * cuota_dec_sp_home) - 1.0
        ev_cov_away = (prob_cov_away_cal * cuota_dec_sp_away) - 1.0

        if j.get("spread_linea") is not None and abs(spread_val) > 0.0 and edge_cov_home >= 0.035 and ev_cov_home >= 0.02:
            picks_candidatos.append({
                "mercado": "Spread",
                "seleccion": f"{j['equipo_local']} {spread_val:+0.1f}",
                "probabilidad": round(prob_cov_home_cal, 4),
                "probabilidad_cruda": round(prob_cov_home_raw, 4),
                "edge": round(edge_cov_home, 4),
                "ev": round(ev_cov_home, 4),
                "cuota": cuota_sp_home_str,
                "cuota_dec": cuota_dec_sp_home,
                "confianza": "ALTA" if edge_cov_home >= 0.06 and ev_cov_home >= 0.04 else "MEDIA",
                "detalle": f"Margen Proyectado: {res_spread['margen_local_esperado']:+0.1f} pts (Spread: {spread_val:+0.1f})"
            })
        elif j.get("spread_linea") is not None and abs(spread_val) > 0.0 and edge_cov_away >= 0.035 and ev_cov_away >= 0.02:
            picks_candidatos.append({
                "mercado": "Spread",
                "seleccion": f"{j['equipo_visita']} {-spread_val:+0.1f}",
                "probabilidad": round(prob_cov_away_cal, 4),
                "probabilidad_cruda": round(prob_cov_away_raw, 4),
                "edge": round(edge_cov_away, 4),
                "ev": round(ev_cov_away, 4),
                "cuota": cuota_sp_away_str,
                "cuota_dec": cuota_dec_sp_away,
                "confianza": "ALTA" if edge_cov_away >= 0.06 and ev_cov_away >= 0.04 else "MEDIA",
                "detalle": f"Margen Proyectado Visita: {-res_spread['margen_local_esperado']:+0.1f} pts (Spread: {-spread_val:+0.1f})"
            })

        # Ordenar candidatos priorizando P * (1 + Edge) * (1 + EV)
        if picks_candidatos:
            picks_candidatos.sort(
                key=lambda x: x["probabilidad"] * (1.0 + 1.5 * max(x.get("edge", 0), 0)) * (1.0 + max(x.get("ev", 0), 0)),
                reverse=True
            )
            mejor_pick = picks_candidatos[0]
            confianza = mejor_pick.get("confianza", "MEDIA")
            # Candado de lesión: Si hay una megaestrella en duda (Questionable), limitar confianza a MEDIA
            if candado_les and confianza == "ALTA":
                confianza = "MEDIA"
                mejor_pick["confianza"] = "MEDIA"
                mejor_pick["detalle"] += " (⚠️ Candado Lesión: Monitorear estatus previo al juego)"
        else:
            # Lean pasivo neutral sin inventar edge artificial
            if res_spread["prob_local_win"] >= res_spread["prob_visita_win"]:
                sel_lean = f"{j['equipo_local']} ML"
                pr_lean = prob_ml_home_cal
                ed_lean = edge_ml_home
                ev_lean = ev_ml_home
                c_lean = j.get("moneyline_local") or "-110"
                c_dec_lean = cuota_dec_home
            else:
                sel_lean = f"{j['equipo_visita']} ML"
                pr_lean = prob_ml_away_cal
                ed_lean = edge_ml_away
                ev_lean = ev_ml_away
                c_lean = j.get("moneyline_visita") or "-110"
                c_dec_lean = cuota_dec_away

            mejor_pick = {
                "mercado": "Moneyline",
                "seleccion": sel_lean,
                "probabilidad": round(pr_lean, 4),
                "edge": round(ed_lean, 4),
                "ev": round(ev_lean, 4),
                "cuota": c_lean,
                "cuota_dec": c_dec_lean,
                "detalle": f"Líneas de mercado eficientes (Sin ventaja clara. Margen: {res_spread['margen_local_esperado']:+0.1f} pts)"
            }
            confianza = "NEUTRAL"

        prediccion_partido = {
            "id_evento": j["id_evento"],
            "partido": j["partido"],
            "equipo_local": j["equipo_local"],
            "equipo_visita": j["equipo_visita"],
            "abbr_local": home_abbr,
            "abbr_visita": away_abbr,
            "fecha_cdmx": j["fecha_cdmx"],
            "hora_cdmx": j["hora_cdmx"],
            "estado": j["estado"],
            "provider": j["provider"],
            # Cuotas de mercado
            "linea_spread": spread_val,
            "spread_detalles": j["spread_detalles"],
            "linea_total": linea_tot,
            "ml_local": j["moneyline_local"],
            "ml_visita": j["moneyline_visita"],
            "ml_local_dec": j["moneyline_local_dec"],
            "ml_visita_dec": j["moneyline_visita_dec"],
            # Proyecciones del Modelo V2 con ajuste de lesiones
            "margen_local_esperado": res_spread["margen_local_esperado"],
            "prob_local_win": round(prob_ml_home_cal, 4),
            "prob_visita_win": round(prob_ml_away_cal, 4),
            "prob_local_win_cruda": round(prob_ml_home_raw, 4),
            "prob_visita_win_cruda": round(prob_ml_away_raw, 4),
            "prob_cover_home": round(prob_cov_home_cal, 4),
            "prob_cover_away": round(prob_cov_away_cal, 4),
            "total_proyectado": res_tot["total_proyectado"],
            "prob_over": round(res_tot["prob_over"], 4),
            "prob_under": round(res_tot["prob_under"], 4),
            "edge_puntos_total": res_tot["edge_puntos"],
            # Reporte de lesiones e impacto oficial
            "candado_lesion": candado_les,
            "alertas_lesiones": alertas_les,
            "ajuste_spread_lesiones": ajuste_spread_les,
            "ajuste_totales_lesiones": ajuste_tot_les,
            "lesiones_visita": info_les.get("lesiones_visita", []),
            "lesiones_local": info_les.get("lesiones_local", []),
            # Recomendación final y candidatos con valor
            "pick_mercado": mejor_pick["mercado"],
            "pick_seleccion": mejor_pick["seleccion"],
            "pick_probabilidad": round(float(mejor_pick["probabilidad"]), 4),
            "pick_edge": round(float(mejor_pick.get("edge", 0.0)), 4),
            "pick_ev": round(float(mejor_pick.get("ev", 0.0)), 4),
            "pick_cuota": mejor_pick.get("cuota", "-110"),
            "pick_cuota_dec": mejor_pick.get("cuota_dec", 1.91),
            "pick_detalle": mejor_pick["detalle"],
            "confianza": confianza,
            "candidatos": picks_candidatos,
            "timestamp": datetime.now(ZONA_CDMX).isoformat(),
        }

        predicciones.append(prediccion_partido)

    # Control de Sesgo de Cartera (Circuito Antisesgo de Totales):
    # Si más del 70% de los picks del día apuntan unidireccionalmente a Totales UNDER,
    # el sistema activa un filtro de disciplina: solo mantiene aquellos con un Edge real robusto
    # (|edge_puntos| >= 4.0 pts y EV >= 4.0%), descartando picks marginales producto de drift colectivo.
    picks_totales = [p for p in predicciones if "Totales" in str(p.get("pick_mercado", "")) and p.get("confianza") != "NEUTRAL"]
    if len(picks_totales) >= 3:
        unders = [p for p in picks_totales if "UNDER" in str(p.get("pick_seleccion", "")).upper()]
        ratio_under = len(unders) / len(picks_totales)
        if ratio_under > 0.70:
            logger.warning(
                f"🛡️ [Antisesgo NBA] Se detectó concentración extrema en Totales UNDER ({len(unders)}/{len(picks_totales)} = {ratio_under*100:.1f}%). "
                f"Aplicando filtro estricto de convicción (Edge >= 4.0 pts, EV >= 4.0%)."
            )
            for p in predicciones:
                if "Totales (UNDER)" in str(p.get("pick_mercado", "")) and p.get("confianza") != "NEUTRAL":
                    edge_pts = abs(float(p.get("edge_puntos_total", 0.0) or 0.0))
                    ev_val = float(p.get("pick_ev", 0.0) or 0.0)
                    if edge_pts < 4.0 or ev_val < 0.04:
                        p["confianza"] = "NEUTRAL"
                        p["pick_detalle"] += " (🛡️ Descartado por sesgo de cartera colectivo: Edge < 4.0 pts)"

    archivo_json = RUTA_PREDICCIONES / "predicciones_nba_hoy.json"
    with open(archivo_json, "w", encoding="utf-8") as f:
        json.dump(predicciones, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 Predicciones guardadas en {archivo_json}")

    archivo_parquet = RUTA_PREDICCIONES / "predicciones_nba_hoy.parquet"
    pd.DataFrame(predicciones).to_parquet(archivo_parquet, index=False)

    try:
        from nba.registro import guardar_predicciones_nba
        guardar_predicciones_nba(predicciones)
    except Exception as exc:
        logger.warning(f"No se pudo sincronizar en base de datos: {exc}")

    return predicciones


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    preds = predecir_partidos_hoy(force_refresh=True)
    print(f"Total procesados: {len(preds)}")
    for p in preds:
        print(f"[{p['partido']}] -> {p['pick_mercado']}: {p['pick_seleccion']} ({p['pick_cuota']}) [Prob: {p['pick_probabilidad']*100:.1f}%, EV: {p.get('pick_ev', 0)*100:+.1f}%] [{p['confianza']}]")
