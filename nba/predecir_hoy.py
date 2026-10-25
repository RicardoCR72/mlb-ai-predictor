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
from core.calibracion_probabilidades import calibrar_probabilidad

RUTA_DATASET = RAIZ / "data" / "nba" / "processed" / "dataset_partidos_nba.parquet"
RUTA_MODELO_SPREAD = RAIZ / "modelos_nba" / "modelo_spread_ml.joblib"
RUTA_MODELO_TOTALES = RAIZ / "modelos_nba" / "modelo_totales.joblib"
RUTA_PREDICCIONES = RAIZ / "data" / "nba" / "predictions"
RUTA_PREDICCIONES.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def cargar_perfiles_recientes_equipos() -> Dict[str, Dict[str, float]]:
    """Extrae el perfil rodante más reciente de cada franquicia con regresión a medias de temporada regular."""
    if not RUTA_DATASET.exists():
        raise FileNotFoundError(f"Falta el dataset procesado en {RUTA_DATASET}.")

    df = pd.read_parquet(RUTA_DATASET)
    cols_base = [
        "REST_DAYS", "IS_B2B", "IS_3_IN_4",
        "PTS_L5", "OPP_PTS_L5", "PACE_L5", "ORTG_L5", "DRTG_L5", "NET_RTG_L5",
        "EFG_PCT_L5", "TOV_PCT_L5", "ORB_PCT_L5", "FT_RATE_L5", "WIN_L5",
        "PTS_L10", "OPP_PTS_L10", "PACE_L10", "ORTG_L10", "DRTG_L10", "NET_RTG_L10",
        "EFG_PCT_L10", "TOV_PCT_L10", "ORB_PCT_L10", "FT_RATE_L10", "WIN_L10",
        "PTS_L20", "OPP_PTS_L20", "PACE_L20", "ORTG_L20", "DRTG_L20", "NET_RTG_L20",
        "EFG_PCT_L20", "TOV_PCT_L20", "ORB_PCT_L20", "FT_RATE_L20", "WIN_L20"
    ]

    perfiles: Dict[str, Dict[str, float]] = {}
    todos_equipos = set(df["HOME_TEAM"].unique()).union(set(df["AWAY_TEAM"].unique()))

    # Promedios de liga regular NBA moderna (para desinflar estadísticas de playoffs de junio 2025)
    baseline_pts = 114.5
    baseline_pace = 100.2
    baseline_rtg = 114.5

    for team in todos_equipos:
        matches = df[(df["HOME_TEAM"] == team) | (df["AWAY_TEAM"] == team)].sort_values("GAME_DATE")
        if matches.empty:
            continue
        last_match = matches.iloc[-1]
        is_home = (last_match["HOME_TEAM"] == team)
        pref = "HOME_" if is_home else "AWAY_"

        prof = {c: float(last_match.get(pref + c, 0.0)) for c in cols_base}
        last_dt = str(last_match["GAME_DATE"])

        # Si el partido proviene de la postemporada anterior, regresionar hacia la media de regular season
        if last_dt < "2026-01-01":
            for c in ["PTS_L5", "PTS_L10", "PTS_L20", "OPP_PTS_L5", "OPP_PTS_L10", "OPP_PTS_L20"]:
                prof[c] = 0.50 * prof.get(c, baseline_pts) + 0.50 * baseline_pts
            for c in ["PACE_L5", "PACE_L10", "PACE_L20"]:
                prof[c] = 0.50 * prof.get(c, baseline_pace) + 0.50 * baseline_pace
            for c in ["ORTG_L5", "ORTG_L10", "ORTG_L20", "DRTG_L5", "DRTG_L10", "DRTG_L20"]:
                prof[c] = 0.50 * prof.get(c, baseline_rtg) + 0.50 * baseline_rtg

        prof["LAST_DATE"] = last_dt
        perfiles[team] = prof

    return perfiles


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

    for j in juegos:
        id_ev = str(j.get("id_evento", "")).strip()
        prev = predicciones_previas.get(id_ev)

        estado_juego = str(j.get("estado", "")).upper()
        es_final = ("FINAL" in estado_juego) or ("FULL_TIME" in estado_juego) or ("STATUS_FINAL" in estado_juego)
        en_vivo = ("PROGRESS" in estado_juego) or ("HALFTIME" in estado_juego)
        ya_comenzo = es_final or en_vivo or (j.get("marcador_local") is not None)
        cuotas_vacias = (j.get("moneyline_local") is None and j.get("total_linea") is None)

        if prev and (ya_comenzo or cuotas_vacias) and prev.get("pick_seleccion"):
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
                    res, u_gan = liquidar_partido(pd.Series({
                        "equipo_local": prev_actualizado.get("equipo_local"),
                        "equipo_visitante": prev_actualizado.get("equipo_visita"),
                        "mercado": prev_actualizado.get("pick_mercado"),
                        "seleccion": prev_actualizado.get("pick_seleccion"),
                        "linea": prev_actualizado.get("linea_total") if "Totales" in prev_actualizado.get("pick_mercado", "") else prev_actualizado.get("linea_spread"),
                        "cuota": prev_actualizado.get("ml_local_dec") or 1.909,
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

        home_prof = perfiles.get(home_abbr, perfiles.get("BOS", {}))
        away_prof = perfiles.get(away_abbr, perfiles.get("DET", {}))

        # Diferenciales clave
        diff_net_l5 = home_prof.get("NET_RTG_L5", 0.0) - away_prof.get("NET_RTG_L5", 0.0)
        diff_net_l10 = home_prof.get("NET_RTG_L10", 0.0) - away_prof.get("NET_RTG_L10", 0.0)
        diff_net_l20 = home_prof.get("NET_RTG_L20", 0.0) - away_prof.get("NET_RTG_L20", 0.0)
        diff_ortg_l10 = home_prof.get("ORTG_L10", 114.5) - away_prof.get("ORTG_L10", 114.5)
        diff_drtg_l10 = home_prof.get("DRTG_L10", 114.5) - away_prof.get("DRTG_L10", 114.5)
        diff_efg_l10 = home_prof.get("EFG_PCT_L10", 0.54) - away_prof.get("EFG_PCT_L10", 0.54)
        diff_win_l10 = home_prof.get("WIN_L10", 0.5) - away_prof.get("WIN_L10", 0.5)
        diff_rest = home_prof.get("REST_DAYS", 2.0) - away_prof.get("REST_DAYS", 2.0)
        pace_proj = (home_prof.get("PACE_L10", 100.2) + away_prof.get("PACE_L10", 100.2)) / 2.0
        off_vs_def_home = home_prof.get("ORTG_L10", 114.5) - away_prof.get("DRTG_L10", 114.5)
        off_vs_def_away = away_prof.get("ORTG_L10", 114.5) - home_prof.get("DRTG_L10", 114.5)

        feats_spread = {
            "DIFF_NET_RTG_L5": diff_net_l5,
            "DIFF_NET_RTG_L10": diff_net_l10,
            "DIFF_NET_RTG_L20": diff_net_l20,
            "DIFF_ORTG_L10": diff_ortg_l10,
            "DIFF_DRTG_L10": diff_drtg_l10,
            "DIFF_EFG_L10": diff_efg_l10,
            "DIFF_WIN_L10": diff_win_l10,
            "DIFF_REST": diff_rest,
            "HOME_NET_RTG_L10": home_prof.get("NET_RTG_L10", 0.0),
            "AWAY_NET_RTG_L10": away_prof.get("NET_RTG_L10", 0.0),
            "HOME_ORTG_L10": home_prof.get("ORTG_L10", 114.5),
            "AWAY_ORTG_L10": away_prof.get("ORTG_L10", 114.5),
            "HOME_DRTG_L10": home_prof.get("DRTG_L10", 114.5),
            "AWAY_DRTG_L10": away_prof.get("DRTG_L10", 114.5),
            "HOME_EFG_PCT_L10": home_prof.get("EFG_PCT_L10", 0.54),
            "AWAY_EFG_PCT_L10": away_prof.get("EFG_PCT_L10", 0.54),
            "HOME_WIN_L10": home_prof.get("WIN_L10", 0.5),
            "AWAY_WIN_L10": away_prof.get("WIN_L10", 0.5),
            "HOME_REST_DAYS": home_prof.get("REST_DAYS", 2.0),
            "AWAY_REST_DAYS": away_prof.get("REST_DAYS", 2.0),
            "HOME_IS_B2B": home_prof.get("IS_B2B", 0),
            "AWAY_IS_B2B": away_prof.get("IS_B2B", 0),
            "OFF_VS_DEF_HOME": off_vs_def_home,
            "OFF_VS_DEF_AWAY": off_vs_def_away,
        }

        feats_totales = {
            "PACE_PROYECTADO_L10": pace_proj,
            "HOME_PACE_L5": home_prof.get("PACE_L5", 100.2),
            "AWAY_PACE_L5": away_prof.get("PACE_L5", 100.2),
            "HOME_PACE_L10": home_prof.get("PACE_L10", 100.2),
            "AWAY_PACE_L10": away_prof.get("PACE_L10", 100.2),
            "HOME_PTS_L10": home_prof.get("PTS_L10", 114.5),
            "AWAY_PTS_L10": away_prof.get("PTS_L10", 114.5),
            "HOME_OPP_PTS_L10": home_prof.get("OPP_PTS_L10", 114.5),
            "AWAY_OPP_PTS_L10": away_prof.get("OPP_PTS_L10", 114.5),
            "HOME_ORTG_L10": home_prof.get("ORTG_L10", 114.5),
            "AWAY_ORTG_L10": away_prof.get("ORTG_L10", 114.5),
            "HOME_DRTG_L10": home_prof.get("DRTG_L10", 114.5),
            "AWAY_DRTG_L10": away_prof.get("DRTG_L10", 114.5),
            "HOME_EFG_PCT_L10": home_prof.get("EFG_PCT_L10", 0.54),
            "AWAY_EFG_PCT_L10": away_prof.get("EFG_PCT_L10", 0.54),
            "HOME_TOV_PCT_L10": home_prof.get("TOV_PCT_L10", 0.135),
            "AWAY_TOV_PCT_L10": away_prof.get("TOV_PCT_L10", 0.135),
            "HOME_REST_DAYS": home_prof.get("REST_DAYS", 2.0),
            "AWAY_REST_DAYS": away_prof.get("REST_DAYS", 2.0),
            "HOME_IS_B2B": home_prof.get("IS_B2B", 0),
            "AWAY_IS_B2B": away_prof.get("IS_B2B", 0),
        }

        spread_val = float(j.get("spread_linea") or 0.0)
        res_spread = proyectar_partido_spread(bundle_spread, feats_spread, spread_line=spread_val)

        linea_tot = float(j.get("total_linea") or 228.0)
        res_tot = proyectar_partido_totales(bundle_totales, feats_totales, linea_total=linea_tot)

        # Probabilidades implícitas desparasitadas de mercado
        prob_ml_home_book = j.get("moneyline_local_prob") or 0.50
        prob_ml_away_book = j.get("moneyline_visita_prob") or 0.50
        cuota_dec_home = float(j.get("moneyline_local_dec") or 1.91)
        cuota_dec_away = float(j.get("moneyline_visita_dec") or 1.91)
        cuota_dec_std = 1.909  # -110

        # Calibración Logística (Platt Scaling) de Moneyline
        prob_ml_home_raw = res_spread["prob_local_win"]
        prob_ml_away_raw = res_spread["prob_visita_win"]
        prob_ml_home_cal = float(calibrar_probabilidad(prob_ml_home_raw, cuota_dec_home))
        prob_ml_away_cal = float(calibrar_probabilidad(prob_ml_away_raw, cuota_dec_away))

        edge_ml_home = prob_ml_home_cal - prob_ml_home_book
        edge_ml_away = prob_ml_away_cal - prob_ml_away_book
        ev_ml_home = (prob_ml_home_cal * cuota_dec_home) - 1.0
        ev_ml_away = (prob_ml_away_cal * cuota_dec_away) - 1.0

        # Selección rigurosa de candidatos con filtro EV > 0 y Dead Zone
        picks_candidatos = []

        # 1. Totales Over / Under (Calibrado)
        if res_tot["recomendacion"] in ["OVER", "UNDER"]:
            prob_tot_raw = res_tot["prob_over"] if res_tot["recomendacion"] == "OVER" else res_tot["prob_under"]
            prob_tot_cal = float(calibrar_probabilidad(prob_tot_raw, cuota_dec_std))
            edge_tot = prob_tot_cal - 0.5238
            ev_tot = (prob_tot_cal * cuota_dec_std) - 1.0
            if edge_tot >= 0.045 and ev_tot >= 0.025:
                picks_candidatos.append({
                    "mercado": f"Totales ({res_tot['recomendacion']})",
                    "seleccion": f"{res_tot['recomendacion']} {linea_tot}",
                    "probabilidad": round(prob_tot_cal, 4),
                    "probabilidad_cruda": round(prob_tot_raw, 4),
                    "edge": round(edge_tot, 4),
                    "ev": round(ev_tot, 4),
                    "cuota": "-110",
                    "cuota_dec": cuota_dec_std,
                    "confianza": "ALTA" if edge_tot >= 0.065 and ev_tot >= 0.04 else "MEDIA",
                    "detalle": f"Proyección Calibrada: {res_tot['total_proyectado']} pts vs línea {linea_tot} (Edge: {edge_tot*100:+.1f}%, EV: {ev_tot*100:+.1f}%)"
                })

        # 2. Moneyline con valor real calibrado
        if edge_ml_home >= 0.045 and ev_ml_home >= 0.025 and prob_ml_home_cal >= 0.45:
            picks_candidatos.append({
                "mercado": "Moneyline",
                "seleccion": f"{j['equipo_local']} ML",
                "probabilidad": round(prob_ml_home_cal, 4),
                "probabilidad_cruda": round(prob_ml_home_raw, 4),
                "edge": round(edge_ml_home, 4),
                "ev": round(ev_ml_home, 4),
                "cuota": j.get("moneyline_local") or "-110",
                "cuota_dec": cuota_dec_home,
                "confianza": "ALTA" if edge_ml_home >= 0.065 and ev_ml_home >= 0.04 else "MEDIA",
                "detalle": f"Prob Calibrada: {prob_ml_home_cal*100:.1f}% vs Book: {prob_ml_home_book*100:.1f}% (EV: +{ev_ml_home*100:.1f}%)"
            })
        elif edge_ml_away >= 0.045 and ev_ml_away >= 0.025 and prob_ml_away_cal >= 0.45:
            picks_candidatos.append({
                "mercado": "Moneyline",
                "seleccion": f"{j['equipo_visita']} ML",
                "probabilidad": round(prob_ml_away_cal, 4),
                "probabilidad_cruda": round(prob_ml_away_raw, 4),
                "edge": round(edge_ml_away, 4),
                "ev": round(ev_ml_away, 4),
                "cuota": j.get("moneyline_visita") or "-110",
                "cuota_dec": cuota_dec_away,
                "confianza": "ALTA" if edge_ml_away >= 0.065 and ev_ml_away >= 0.04 else "MEDIA",
                "detalle": f"Prob Calibrada: {prob_ml_away_cal*100:.1f}% vs Book: {prob_ml_away_book*100:.1f}% (EV: +{ev_ml_away*100:.1f}%)"
            })

        # 3. Spread / Hándicap (Calibrado)
        prob_cov_home_raw = res_spread["prob_cover_home"]
        prob_cov_away_raw = res_spread["prob_cover_away"]
        prob_cov_home_cal = float(calibrar_probabilidad(prob_cov_home_raw, cuota_dec_std))
        prob_cov_away_cal = float(calibrar_probabilidad(prob_cov_away_raw, cuota_dec_std))

        edge_cov_home = prob_cov_home_cal - 0.5238
        edge_cov_away = prob_cov_away_cal - 0.5238
        ev_cov_home = (prob_cov_home_cal * cuota_dec_std) - 1.0
        ev_cov_away = (prob_cov_away_cal * cuota_dec_std) - 1.0

        if edge_cov_home >= 0.035 and ev_cov_home >= 0.02:
            picks_candidatos.append({
                "mercado": "Spread",
                "seleccion": f"{j['equipo_local']} {spread_val:+0.1f}",
                "probabilidad": round(prob_cov_home_cal, 4),
                "probabilidad_cruda": round(prob_cov_home_raw, 4),
                "edge": round(edge_cov_home, 4),
                "ev": round(ev_cov_home, 4),
                "cuota": "-110",
                "cuota_dec": cuota_dec_std,
                "confianza": "ALTA" if edge_cov_home >= 0.06 and ev_cov_home >= 0.04 else "MEDIA",
                "detalle": f"Margen Proyectado: {res_spread['margen_local_esperado']:+0.1f} pts (Spread: {spread_val:+0.1f})"
            })
        elif edge_cov_away >= 0.035 and ev_cov_away >= 0.02:
            picks_candidatos.append({
                "mercado": "Spread",
                "seleccion": f"{j['equipo_visita']} {-spread_val:+0.1f}",
                "probabilidad": round(prob_cov_away_cal, 4),
                "probabilidad_cruda": round(prob_cov_away_raw, 4),
                "edge": round(edge_cov_away, 4),
                "ev": round(ev_cov_away, 4),
                "cuota": "-110",
                "cuota_dec": cuota_dec_std,
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
            # Proyecciones del Modelo V2
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
