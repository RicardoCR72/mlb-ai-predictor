"""Pipeline de inferencia diaria para la NBA.

1. Consulta los partidos y líneas en vivo de ESPN (DraftKings) a costo cero.
2. Recupera el perfil estadístico más reciente de cada franquicia.
3. Ejecuta los modelos de Machine Learning (Spread/ML y Totales).
4. Calcula el valor esperado (+EV), edges y recomendaciones de apuesta.
5. Almacena las predicciones en data/nba/predictions/.
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

RUTA_DATASET = RAIZ / "data" / "nba" / "processed" / "dataset_partidos_nba.parquet"
RUTA_MODELO_SPREAD = RAIZ / "modelos_nba" / "modelo_spread_ml.joblib"
RUTA_MODELO_TOTALES = RAIZ / "modelos_nba" / "modelo_totales.joblib"
RUTA_PREDICCIONES = RAIZ / "data" / "nba" / "predictions"
RUTA_PREDICCIONES.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def cargar_perfiles_recientes_equipos() -> Dict[str, Dict[str, float]]:
    """Extrae el perfil rodante más reciente de cada una de las 30 franquicias de la NBA."""
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

    for team in todos_equipos:
        matches = df[(df["HOME_TEAM"] == team) | (df["AWAY_TEAM"] == team)].sort_values("GAME_DATE")
        if matches.empty:
            continue
        last_match = matches.iloc[-1]
        is_home = (last_match["HOME_TEAM"] == team)
        pref = "HOME_" if is_home else "AWAY_"
        
        perfiles[team] = {c: float(last_match.get(pref + c, 0.0)) for c in cols_base}
        perfiles[team]["LAST_DATE"] = str(last_match["GAME_DATE"])

    return perfiles


def predecir_partidos_hoy(force_refresh: bool = False, fecha: Optional[str] = None) -> List[Dict[str, Any]]:
    """Genera las predicciones completas para la cartelera de hoy en la NBA."""
    logger.info("🏀 Iniciando pipeline de predicciones diarias de la NBA...")

    if not RUTA_MODELO_SPREAD.exists() or not RUTA_MODELO_TOTALES.exists():
        raise FileNotFoundError("Los modelos de la NBA no están entrenados. Ejecuta nba/entrenar_spread_ml.py y nba/entrenar_totales.py.")

    bundle_spread = joblib.load(RUTA_MODELO_SPREAD)
    bundle_totales = joblib.load(RUTA_MODELO_TOTALES)
    perfiles = cargar_perfiles_recientes_equipos()

    # Consultar eventos del día (usar fecha actual CDMX o la fecha especificada)
    hoy_cdmx = fecha or datetime.now(ZONA_CDMX).strftime("%Y%m%d")
    juegos = obtener_calendario_y_cuotas_nba(fecha=hoy_cdmx, force_refresh=force_refresh)
    if not juegos and not fecha:
        juegos = obtener_calendario_y_cuotas_nba(force_refresh=force_refresh)

    archivo_json = RUTA_PREDICCIONES / "predicciones_nba_hoy.json"

    if not juegos:
        logger.info("No hay partidos programados para hoy en el calendario de ESPN.")
        if archivo_json.exists():
            try:
                with open(archivo_json, "w", encoding="utf-8") as f:
                    json.dump([], f)
            except Exception:
                pass
        return []

    # Cargar predicciones previas para preservar picks congelados y cuotas pre-partido
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

        # Si el partido ya inició (STATUS_IN_PROGRESS), finalizó (STATUS_FINAL)
        # o ESPN retiró las cuotas pre-partido, PRESERVAR el pick y momios originales
        estado_juego = str(j.get("estado", "")).upper()
        ya_comenzo = ("PROGRESS" in estado_juego) or ("FINAL" in estado_juego) or (j.get("marcador_local") is not None)
        cuotas_vacias = (j.get("moneyline_local") is None and j.get("total_linea") is None)

        if prev and (ya_comenzo or cuotas_vacias) and prev.get("pick_seleccion"):
            prev_actualizado = dict(prev)
            prev_actualizado["estado"] = j.get("estado", prev.get("estado"))
            prev_actualizado["descripcion_estado"] = j.get("descripcion_estado", prev.get("descripcion_estado"))
            if j.get("marcador_local") is not None:
                prev_actualizado["marcador_local"] = j["marcador_local"]
            if j.get("marcador_visita") is not None:
                prev_actualizado["marcador_visita"] = j["marcador_visita"]

            if ("FINAL" in str(prev_actualizado.get("estado", "")).upper()) and prev_actualizado.get("marcador_local") is not None:
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
                    prev_actualizado["resultado"] = res
                    prev_actualizado["unidades_ganadas"] = u_gan
                except Exception:
                    pass

            predicciones.append(prev_actualizado)
            continue

        home_abbr = normalizar_equipo(j["abbr_local"])
        away_abbr = normalizar_equipo(j["abbr_visita"])

        # Si el equipo no está en el perfil histórico, usar promedio de la liga
        home_prof = perfiles.get(home_abbr, perfiles.get("BOS", {}))
        away_prof = perfiles.get(away_abbr, perfiles.get("DET", {}))

        # Construir variables diferenciales
        diff_net_l5 = home_prof.get("NET_RTG_L5", 0.0) - away_prof.get("NET_RTG_L5", 0.0)
        diff_net_l10 = home_prof.get("NET_RTG_L10", 0.0) - away_prof.get("NET_RTG_L10", 0.0)
        diff_net_l20 = home_prof.get("NET_RTG_L20", 0.0) - away_prof.get("NET_RTG_L20", 0.0)
        diff_ortg_l10 = home_prof.get("ORTG_L10", 110.0) - away_prof.get("ORTG_L10", 110.0)
        diff_drtg_l10 = home_prof.get("DRTG_L10", 110.0) - away_prof.get("DRTG_L10", 110.0)
        diff_efg_l10 = home_prof.get("EFG_PCT_L10", 0.52) - away_prof.get("EFG_PCT_L10", 0.52)
        diff_win_l10 = home_prof.get("WIN_L10", 0.5) - away_prof.get("WIN_L10", 0.5)
        diff_rest = home_prof.get("REST_DAYS", 2.0) - away_prof.get("REST_DAYS", 2.0)
        pace_proj = (home_prof.get("PACE_L10", 99.0) + away_prof.get("PACE_L10", 99.0)) / 2.0
        off_vs_def_home = home_prof.get("ORTG_L10", 110.0) - away_prof.get("DRTG_L10", 110.0)
        off_vs_def_away = away_prof.get("ORTG_L10", 110.0) - home_prof.get("DRTG_L10", 110.0)

        # Vector de features para el modelo de Spread y Moneyline
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
            "HOME_ORTG_L10": home_prof.get("ORTG_L10", 110.0),
            "AWAY_ORTG_L10": away_prof.get("ORTG_L10", 110.0),
            "HOME_DRTG_L10": home_prof.get("DRTG_L10", 110.0),
            "AWAY_DRTG_L10": away_prof.get("DRTG_L10", 110.0),
            "HOME_EFG_PCT_L10": home_prof.get("EFG_PCT_L10", 0.52),
            "AWAY_EFG_PCT_L10": away_prof.get("EFG_PCT_L10", 0.52),
            "HOME_WIN_L10": home_prof.get("WIN_L10", 0.5),
            "AWAY_WIN_L10": away_prof.get("WIN_L10", 0.5),
            "HOME_REST_DAYS": home_prof.get("REST_DAYS", 2.0),
            "AWAY_REST_DAYS": away_prof.get("REST_DAYS", 2.0),
            "HOME_IS_B2B": home_prof.get("IS_B2B", 0),
            "AWAY_IS_B2B": away_prof.get("IS_B2B", 0),
            "OFF_VS_DEF_HOME": off_vs_def_home,
            "OFF_VS_DEF_AWAY": off_vs_def_away,
        }

        # Vector de features para Totales
        feats_totales = {
            "PACE_PROYECTADO_L10": pace_proj,
            "HOME_PACE_L5": home_prof.get("PACE_L5", 99.0),
            "AWAY_PACE_L5": away_prof.get("PACE_L5", 99.0),
            "HOME_PACE_L10": home_prof.get("PACE_L10", 99.0),
            "AWAY_PACE_L10": away_prof.get("PACE_L10", 99.0),
            "HOME_PTS_L10": home_prof.get("PTS_L10", 112.0),
            "AWAY_PTS_L10": away_prof.get("PTS_L10", 112.0),
            "HOME_OPP_PTS_L10": home_prof.get("OPP_PTS_L10", 112.0),
            "AWAY_OPP_PTS_L10": away_prof.get("OPP_PTS_L10", 112.0),
            "HOME_ORTG_L10": home_prof.get("ORTG_L10", 110.0),
            "AWAY_ORTG_L10": away_prof.get("ORTG_L10", 110.0),
            "HOME_DRTG_L10": home_prof.get("DRTG_L10", 110.0),
            "AWAY_DRTG_L10": away_prof.get("DRTG_L10", 110.0),
            "HOME_EFG_PCT_L10": home_prof.get("EFG_PCT_L10", 0.52),
            "AWAY_EFG_PCT_L10": away_prof.get("EFG_PCT_L10", 0.52),
            "HOME_TOV_PCT_L10": home_prof.get("TOV_PCT_L10", 0.13),
            "AWAY_TOV_PCT_L10": away_prof.get("TOV_PCT_L10", 0.13),
            "HOME_REST_DAYS": home_prof.get("REST_DAYS", 2.0),
            "AWAY_REST_DAYS": away_prof.get("REST_DAYS", 2.0),
            "HOME_IS_B2B": home_prof.get("IS_B2B", 0),
            "AWAY_IS_B2B": away_prof.get("IS_B2B", 0),
        }

        # Ejecutar modelo de Spread / Moneyline
        spread_val = float(j.get("spread_linea") or 0.0)
        res_spread = proyectar_partido_spread(bundle_spread, feats_spread, spread_line=spread_val)

        # Ejecutar modelo de Totales
        linea_tot = float(j.get("total_linea") or 220.0)
        res_tot = proyectar_partido_totales(bundle_totales, feats_totales, linea_total=linea_tot)

        # Cálculo de Edges y Valor Esperado (+EV)
        prob_ml_home_book = j.get("moneyline_local_prob") or 0.5
        prob_ml_away_book = j.get("moneyline_visita_prob") or 0.5
        edge_ml_home = res_spread["prob_local_win"] - prob_ml_home_book
        edge_ml_away = res_spread["prob_visita_win"] - prob_ml_away_book

        # Determinar el mejor PICK del encuentro
        picks_candidatos = []

        # Candidato 1: Totales
        if res_tot["recomendacion"] != "PASAR":
            prob_tot = res_tot["prob_over"] if res_tot["recomendacion"] == "OVER" else res_tot["prob_under"]
            edge_tot = prob_tot - 0.5238  # Ventaja probabilística real vs cuota estándar de -110 (52.38%)
            picks_candidatos.append({
                "mercado": f"Totales ({res_tot['recomendacion']})",
                "seleccion": f"{res_tot['recomendacion']} {linea_tot}",
                "probabilidad": prob_tot,
                "edge": round(edge_tot, 4),
                "detalle": f"Proyección: {res_tot['total_proyectado']} pts (Edge: {res_tot['edge_puntos']} pts)"
            })

        # Candidato 2: Moneyline con valor
        if edge_ml_home >= 0.04 and res_spread["prob_local_win"] >= 0.45:
            picks_candidatos.append({
                "mercado": "Moneyline",
                "seleccion": f"{j['equipo_local']} ML",
                "probabilidad": res_spread["prob_local_win"],
                "edge": edge_ml_home,
                "detalle": f"Prob Modelo: {res_spread['prob_local_win']*100:.1f}% vs Book: {prob_ml_home_book*100:.1f}%"
            })
        elif edge_ml_away >= 0.04 and res_spread["prob_visita_win"] >= 0.45:
            picks_candidatos.append({
                "mercado": "Moneyline",
                "seleccion": f"{j['equipo_visita']} ML",
                "probabilidad": res_spread["prob_visita_win"],
                "edge": edge_ml_away,
                "detalle": f"Prob Modelo: {res_spread['prob_visita_win']*100:.1f}% vs Book: {prob_ml_away_book*100:.1f}%"
            })

        # Candidato 3: Spread si hay alta confianza
        if res_spread["prob_cover_home"] >= 0.55:
            picks_candidatos.append({
                "mercado": "Spread",
                "seleccion": f"{j['equipo_local']} {spread_val:+0.1f}",
                "probabilidad": res_spread["prob_cover_home"],
                "edge": res_spread["prob_cover_home"] - 0.5238,
                "detalle": f"Margen estimado: {res_spread['margen_local_esperado']:+0.1f} pts"
            })
        elif res_spread["prob_cover_away"] >= 0.55:
            picks_candidatos.append({
                "mercado": "Spread",
                "seleccion": f"{j['equipo_visita']} {-spread_val:+0.1f}",
                "probabilidad": res_spread["prob_cover_away"],
                "edge": res_spread["prob_cover_away"] - 0.5238,
                "detalle": f"Margen estimado local: {res_spread['margen_local_esperado']:+0.1f} pts"
            })

        # Ordenar candidatos: priorizar selecciones con alta probabilidad y ventaja matemática positiva
        picks_candidatos.sort(
            key=lambda x: (
                x["edge"] > 0,
                x["probabilidad"] >= 0.70,
                round(x["probabilidad"], 4),
                round(x["edge"], 4),
            ),
            reverse=True,
        )
        mejor_pick = picks_candidatos[0] if picks_candidatos else {
            "mercado": "Moneyline",
            "seleccion": f"{j['equipo_local'] if res_spread['prob_local_win'] > 0.5 else j['equipo_visita']} ML",
            "probabilidad": max(res_spread["prob_local_win"], res_spread["prob_visita_win"]),
            "edge": max(edge_ml_home, edge_ml_away),
            "detalle": "Líneas de mercado muy ajustadas."
        }

        # Nivel de confianza
        if mejor_pick["edge"] >= 0.06 and mejor_pick["probabilidad"] >= 0.56:
            confianza = "ALTA"
        elif mejor_pick["edge"] >= 0.03:
            confianza = "MEDIA"
        else:
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
            # Proyecciones del Modelo
            "margen_local_esperado": res_spread["margen_local_esperado"],
            "prob_local_win": res_spread["prob_local_win"],
            "prob_visita_win": res_spread["prob_visita_win"],
            "prob_cover_home": res_spread["prob_cover_home"],
            "prob_cover_away": res_spread["prob_cover_away"],
            "total_proyectado": res_tot["total_proyectado"],
            "prob_over": res_tot["prob_over"],
            "prob_under": res_tot["prob_under"],
            "edge_puntos_total": res_tot["edge_puntos"],
            # Recomendación final
            "pick_mercado": mejor_pick["mercado"],
            "pick_seleccion": mejor_pick["seleccion"],
            "pick_probabilidad": round(mejor_pick["probabilidad"], 4),
            "pick_edge": round(mejor_pick["edge"], 4),
            "pick_detalle": mejor_pick["detalle"],
            "confianza": confianza,
            "timestamp": datetime.now(ZONA_CDMX).isoformat(),
        }

        predicciones.append(prediccion_partido)

    # Guardar en JSON y Parquet
    archivo_json = RUTA_PREDICCIONES / "predicciones_nba_hoy.json"
    with open(archivo_json, "w", encoding="utf-8") as f:
        json.dump(predicciones, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 Predicciones guardadas en {archivo_json}")

    archivo_parquet = RUTA_PREDICCIONES / "predicciones_nba_hoy.parquet"
    pd.DataFrame(predicciones).to_parquet(archivo_parquet, index=False)

    # Sincronización en Base de Datos MySQL e historial acumulado
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
    print(f"\n🏀 Resumen de Predicciones NBA Hoy ({len(preds)} partidos):")
    for p in preds:
        print(f"\n[{p['hora_cdmx']} CDMX] {p['partido']}")
        print(f"   Spread Book: {p['spread_detalles']} | Margen Proyectado: {p['margen_local_esperado']:+0.1f} pts")
        print(f"   Moneyline Prob: {p['equipo_local']} {p['prob_local_win']*100:.1f}% vs {p['equipo_visita']} {p['prob_visita_win']*100:.1f}%")
        print(f"   Totales: Línea {p['linea_total']} vs Proyectado {p['total_proyectado']} pts")
        print(f"   🎯 PICK RECOMENDADO: {p['pick_seleccion']} ({p['confianza']}) -> {p['pick_detalle']}")
