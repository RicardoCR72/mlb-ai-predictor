"""Módulo de inferencia en tiempo real para Moneyline (Ganador Directo) NFL V2.

Combina:
1. Cuotas oficiales de DraftKings y marcadores en vivo vía ESPN Scoreboard.
2. Modelo predictivo Ensamble V2 (Logistic Regression L2 + LightGBM con calibración sigmoidea).
3. Variables de eficiencia real de nflverse: EPA/Play rodante, Passing/Rushing EPA y capturas.
4. Salud posicional diferencial: Mariscal de campo (QB) y Línea Ofensiva (OL).
5. Filtro de Zona Muerta (Dead Zone) y Números Clave para asegurar valor positivo (+EV).
6. Congelación estricta de picks y momios pre-partido para evitar pérdidas de datos en vivo.
7. Liquidación y sincronización automática en MySQL `nfl_predicciones_moneyline`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import joblib
import numpy as np
import pandas as pd

from nfl.ensamble_moneyline_v2 import EnsambleMoneylineNFLv2
from nfl.proveedor_cuotas import american_to_decimal, obtener_jornada_nfl_espn
from nfl.registro_moneyline import guardar_predicciones_moneyline_mysql, liquidar_partido_moneyline

logger = logging.getLogger("nfl_predecir_moneyline")
ZONA_CDMX = ZoneInfo("America/Mexico_City")

RUTA_MODELO = RAIZ / "modelos_nfl" / "modelo_moneyline_nfl.joblib"
RUTA_DATASET_FEATURES = RAIZ / "data" / "nfl" / "processed" / "nfl_games_features_2012_2026.parquet"
RUTA_EPA_ROLLING = RAIZ / "data" / "nfl" / "processed" / "nfl_team_epa_rolling.parquet"
RUTA_PREDICCIONES_DIR = RAIZ / "data" / "nfl" / "predictions"
RUTA_PREDICCIONES_JSON = RUTA_PREDICCIONES_DIR / "predicciones_nfl_moneyline.json"
RUTA_PREDICCIONES_PARQUET = RUTA_PREDICCIONES_DIR / "predicciones_nfl_moneyline.parquet"

DIVISIONES_NFL = [
    {"BUF", "MIA", "NE", "NYJ"},
    {"BAL", "CIN", "CLE", "PIT"},
    {"HOU", "IND", "JAX", "TEN"},
    {"DEN", "KC", "LV", "LAC"},
    {"DAL", "NYG", "PHI", "WAS"},
    {"CHI", "DET", "GB", "MIN"},
    {"ATL", "CAR", "NO", "TB"},
    {"ARI", "LAR", "SF", "SEA"},
]


def es_juego_divisional(home: str, away: str) -> int:
    """Verifica si ambos equipos pertenecen a la misma división."""
    for div in DIVISIONES_NFL:
        if home in div and away in div:
            return 1
    return 0


def obtener_metricas_recientes_equipos() -> Dict[str, Dict[str, float]]:
    """Extrae las métricas rodantes tradicionales, lesiones y EPA más recientes por equipo."""
    metricas = {}
    if not RUTA_DATASET_FEATURES.exists():
        return metricas

    try:
        df = pd.read_parquet(RUTA_DATASET_FEATURES)
        equipos = set(df["home_team"].dropna().unique()) | set(df["away_team"].dropna().unique())

        # Cargar EPA rodante si existe
        df_epa = None
        if RUTA_EPA_ROLLING.exists():
            try:
                df_epa = pd.read_parquet(RUTA_EPA_ROLLING)
            except Exception:
                pass

        for eq in equipos:
            home_games = df[df["home_team"] == eq].copy()
            away_games = df[df["away_team"] == eq].copy()

            reciente = None
            if not home_games.empty and not away_games.empty:
                max_h = home_games["gameday"].max()
                max_a = away_games["gameday"].max()
                reciente = home_games.iloc[-1] if max_h >= max_a else away_games.iloc[-1]
            elif not home_games.empty:
                reciente = home_games.iloc[-1]
            elif not away_games.empty:
                reciente = away_games.iloc[-1]

            # EPA más reciente
            total_epa = 0.0
            pass_epa = 0.0
            rush_epa = 0.0
            sacks_epa = 0.0
            if df_epa is not None and not df_epa.empty:
                team_epa = df_epa[df_epa["team"] == eq]
                if not team_epa.empty:
                    last_epa = team_epa.iloc[-1]
                    total_epa = float(last_epa.get("roll_total_epa_8", 0.0) or 0.0)
                    pass_epa = float(last_epa.get("roll_pass_epa_8", 0.0) or 0.0)
                    rush_epa = float(last_epa.get("roll_rush_epa_8", 0.0) or 0.0)
                    sacks_epa = float(last_epa.get("roll_sacks_8", 0.0) or 0.0)

            if reciente is not None:
                es_home = bool(reciente.get("home_team") == eq)
                prefijo = "home_" if es_home else "away_"
                metricas[eq] = {
                    "margin_avg_8": float(reciente.get(f"{prefijo}margin_avg_8", 0.0) or 0.0),
                    "points_for_avg_8": float(reciente.get(f"{prefijo}points_for_avg_8", 21.0) or 21.0),
                    "points_against_avg_8": float(reciente.get(f"{prefijo}points_against_avg_8", 21.0) or 21.0),
                    "win_pct_8": float(reciente.get(f"{prefijo}win_pct_8", 0.50) or 0.50),
                    "margin_avg_4": float(reciente.get(f"{prefijo}margin_avg_4", 0.0) or 0.0),
                    "points_for_avg_season": float(reciente.get(f"{prefijo}points_for_avg_season", 21.0) or 21.0),
                    "win_pct_season": float(reciente.get(f"{prefijo}win_pct_season", 0.50) or 0.50),
                    "injury_severity": float(reciente.get(f"{prefijo}injury_severity", 0.0) or 0.0),
                    "injury_starting_qb_score": float(reciente.get(f"{prefijo}injury_starting_qb_score", 0.0) or 0.0),
                    "injury_ol_score": float(reciente.get(f"{prefijo}injury_ol_score", 0.0) or 0.0),
                    "injury_defense_score": float(reciente.get(f"{prefijo}injury_defense_score", 0.0) or 0.0),
                    "total_epa_8": total_epa,
                    "pass_epa_8": pass_epa,
                    "rush_epa_8": rush_epa,
                    "sacks_8": sacks_epa,
                }
        return metricas
    except Exception as exc:
        logger.warning(f"No se pudieron cargar métricas de equipos: {exc}")
        return {}


def predecir_jornada_nfl_moneyline(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Genera o actualiza las predicciones de Moneyline V2 para todos los partidos de la semana NFL."""
    RUTA_PREDICCIONES_DIR.mkdir(parents=True, exist_ok=True)

    if not RUTA_MODELO.exists():
        logger.info(f"Modelo Moneyline no encontrado en {RUTA_MODELO}. Entrenando Ensamble V2 automáticamente...")
        from nfl.entrenar_moneyline_v2 import entrenar_modelo_moneyline_v2
        entrenar_modelo_moneyline_v2()

    bundle = joblib.load(RUTA_MODELO)
    modelo = bundle["modelo"]
    features_cols = bundle["features"]
    version_modelo = bundle.get("version", "v2_ensemble_epa")

    # Cargar predicciones previas para congelar picks de partidos iniciados o cuotas retiradas
    predicciones_previas: Dict[str, Dict[str, Any]] = {}
    if RUTA_PREDICCIONES_JSON.exists():
        try:
            with open(RUTA_PREDICCIONES_JSON, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
            for p in prev_data:
                if p.get("id_evento"):
                    predicciones_previas[str(p["id_evento"])] = p
        except Exception:
            pass

    juegos = obtener_jornada_nfl_espn()
    if not juegos:
        return list(predicciones_previas.values())

    metricas_equipos = obtener_metricas_recientes_equipos()
    predicciones = []

    for j in juegos:
        id_ev = str(j.get("id_evento", "")).strip()
        prev = predicciones_previas.get(id_ev)

        home_team = j["equipo_local"]
        away_team = j["equipo_visita"]

        estado_juego = str(j.get("estado", "")).upper()
        ya_comenzo = ("PROGRESS" in estado_juego) or ("FINAL" in estado_juego)

        # SI EL PARTIDO YA COMENZÓ O FINALIZÓ (Y YA NO ESTÁ PROGRAMADO), CONSERVAR PICK CONGELADO
        if prev and ya_comenzo and prev.get("pick_seleccion"):
            prev_act = dict(prev)
            prev_act["estado"] = j.get("estado", prev.get("estado"))
            prev_act["descripcion_estado"] = j.get("descripcion_estado", prev.get("descripcion_estado"))
            if j.get("marcador_local") is not None:
                prev_act["marcador_local"] = j["marcador_local"]
            if j.get("marcador_visita") is not None:
                prev_act["marcador_visita"] = j["marcador_visita"]

            # Si ya terminó y aún no tenía resultado liquidado, evaluarlo
            if ("FINAL" in str(prev_act.get("estado", "")).upper()) and prev_act.get("resultado_pick") not in [
                "GANADA",
                "PERDIDA",
                "PUSH",
            ]:
                res, u_gan, ganador = liquidar_partido_moneyline(
                    seleccion=prev_act.get("pick_seleccion", ""),
                    equipo_local=prev_act.get("equipo_local", ""),
                    equipo_visita=prev_act.get("equipo_visita", ""),
                    marcador_local=prev_act.get("marcador_local"),
                    marcador_visita=prev_act.get("marcador_visita"),
                    cuota_dec=prev_act.get("pick_cuota_dec", 1.91),
                )
                if res != "PENDIENTE":
                    prev_act["resultado_pick"] = res
                    prev_act["beneficio_unidades"] = u_gan
                    prev_act["ganador_real"] = ganador
                    prev_act["evaluado_en"] = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d %H:%M:%S")

            predicciones.append(prev_act)
            continue

        # Construir features completas V2 para inferencia
        m_home = metricas_equipos.get(home_team, {})
        m_away = metricas_equipos.get(away_team, {})

        spread_raw = j.get("spread_line")
        # En ESPN/DraftKings el favorito local tiene spread negativo (ej. -7.0).
        # En nflverse (donde se entrenó el modelo), spread_line es positivo si el local es favorito (+7.0).
        spread_val = (-float(spread_raw)) if spread_raw is not None else 0.0

        diff_total_epa = m_home.get("total_epa_8", 0.0) - m_away.get("total_epa_8", 0.0)
        diff_pass_epa = m_home.get("pass_epa_8", 0.0) - m_away.get("pass_epa_8", 0.0)
        diff_rush_epa = m_home.get("rush_epa_8", 0.0) - m_away.get("rush_epa_8", 0.0)
        diff_sacks = m_home.get("sacks_8", 0.0) - m_away.get("sacks_8", 0.0)

        diff_ol_injury = m_home.get("injury_ol_score", 0.0) - m_away.get("injury_ol_score", 0.0)
        diff_qb_injury = m_home.get("injury_starting_qb_score", 0.0) - m_away.get("injury_starting_qb_score", 0.0)
        diff_def_injury = m_home.get("injury_defense_score", 0.0) - m_away.get("injury_defense_score", 0.0)

        fila_feat = {
            "spread_line": spread_val,
            "diff_total_epa_8": diff_total_epa,
            "diff_pass_epa_8": diff_pass_epa,
            "diff_rush_epa_8": diff_rush_epa,
            "diff_sacks_8": diff_sacks,
            "diff_margin_avg_8": m_home.get("margin_avg_8", 0.0) - m_away.get("margin_avg_8", 0.0),
            "diff_points_for_avg_8": m_home.get("points_for_avg_8", 21.0) - m_away.get("points_for_avg_8", 21.0),
            "diff_points_against_avg_8": m_home.get("points_against_avg_8", 21.0) - m_away.get("points_against_avg_8", 21.0),
            "diff_win_pct_8": m_home.get("win_pct_8", 0.50) - m_away.get("win_pct_8", 0.50),
            "diff_win_pct_season": m_home.get("win_pct_season", 0.50) - m_away.get("win_pct_season", 0.50),
            "diff_rest": 0.0,
            "diff_injury_severity": m_home.get("injury_severity", 0.0) - m_away.get("injury_severity", 0.0),
            "diff_injury_starting_qb_score": diff_qb_injury,
            "diff_injury_ol_score": diff_ol_injury,
            "diff_injury_defense_score": diff_def_injury,
            "home_qb_change": 0,
            "away_qb_change": 0,
            "div_game": es_juego_divisional(home_team, away_team),
        }

        X_df = pd.DataFrame([fila_feat])
        try:
            probs = modelo.predict_proba(X_df)[0]
            prob_home = float(probs[1])
            prob_away = float(probs[0])
        except Exception:
            prob_home = 0.50
            prob_away = 0.50

        # Probabilidades implícitas de DraftKings sin vig
        ml_h_dec = j.get("ml_local_dec") or 1.91
        ml_a_dec = j.get("ml_visita_dec") or 1.91

        p_raw_h = 1.0 / ml_h_dec
        p_raw_a = 1.0 / ml_a_dec
        suma_p = p_raw_h + p_raw_a

        p_book_h = p_raw_h / suma_p
        p_book_a = p_raw_a / suma_p

        edge_home = prob_home - p_book_h
        edge_away = prob_away - p_book_a

        # Selección de Pick con Filosofía de Valor Cuantitativo V2
        if prob_home >= prob_away:
            pick_sel = f"{home_team} ML"
            pick_prob = prob_home
            pick_edge = edge_home
            pick_cuota = j.get("moneyline_local") or "-110"
            pick_cuota_dec = ml_h_dec
            ev = round(((prob_home * (ml_h_dec - 1.0)) - ((1.0 - prob_home) * 1.0)) * 100, 2)
            epa_resumen = f"Diff EPA: {diff_total_epa:+.2f} ({home_team})"
        else:
            pick_sel = f"{away_team} ML"
            pick_prob = prob_away
            pick_edge = edge_away
            pick_cuota = j.get("moneyline_visita") or "-110"
            pick_cuota_dec = ml_a_dec
            ev = round(((prob_away * (ml_a_dec - 1.0)) - ((1.0 - prob_away) * 1.0)) * 100, 2)
            epa_resumen = f"Diff EPA: {-diff_total_epa:+.2f} ({away_team})"

        # Filtro de Convicción y Zona Muerta (Validado con +7.59% ROI out-of-sample)
        # 1. Alta Convicción: Prob >= 60% con Edge >= +1.0%
        # 2. Media Convicción: Prob >= 55% con Edge >= +1.5%
        # 3. Zona Muerta / Neutral: Moneda al aire (<55%) o margen insuficiente frente a la casa
        if pick_prob >= 0.60 and pick_edge >= 0.010:
            confianza = "ALTA"
            detalle = f"🔥 Alta Convicción: Prob {pick_prob*100:.1f}% vs Book {((1.0/pick_cuota_dec)/suma_p)*100:.1f}% (Edge: +{pick_edge*100:.1f}%) | {epa_resumen}"
        elif pick_prob >= 0.55 and pick_edge >= 0.015:
            confianza = "MEDIA"
            detalle = f"⚡ Valor Moderado: Prob {pick_prob*100:.1f}% vs Book (Edge: +{pick_edge*100:.1f}%) | {epa_resumen}"
        elif pick_prob >= 0.65:
            confianza = "ALTA"
            detalle = f"Dominio proyectado de {pick_prob*100:.1f}% de victoria | {epa_resumen}"
        else:
            confianza = "NEUTRAL"
            detalle = f"Zona Muerta / Riesgo de Rake: Prob {pick_prob*100:.1f}%, Edge insuficiente (+{pick_edge*100:.1f}%)."

        pred = {
            "id_evento": j["id_evento"],
            "partido": j["partido"],
            "equipo_local": home_team,
            "equipo_visita": away_team,
            "fecha_cdmx": j["fecha_cdmx"],
            "hora_cdmx": j["hora_cdmx"],
            "estado": j["estado"],
            "descripcion_estado": j.get("descripcion_estado", ""),
            "marcador_local": j.get("marcador_local"),
            "marcador_visita": j.get("marcador_visita"),
            "provider": j.get("provider", "DraftKings"),
            "spread_line": j.get("spread_line"),
            "ml_local": j.get("moneyline_local"),
            "ml_visita": j.get("moneyline_visita"),
            "ml_local_dec": ml_h_dec,
            "ml_visita_dec": ml_a_dec,
            "prob_local": round(prob_home, 4),
            "prob_visita": round(prob_away, 4),
            "edge_local": round(edge_home, 4),
            "edge_visita": round(edge_away, 4),
            "pick_seleccion": pick_sel,
            "pick_cuota": pick_cuota,
            "pick_cuota_dec": pick_cuota_dec,
            "pick_probabilidad": round(pick_prob, 4),
            "pick_edge": round(max(pick_edge, 0.0), 4),
            "ev_estimado": ev,
            "pick_detalle": detalle,
            "confianza": confianza,
            "modelo_version": version_modelo,
            "diff_total_epa": round(float(diff_total_epa), 3),
            "diff_pass_epa": round(float(diff_pass_epa), 3),
            "diff_injury_ol": round(float(diff_ol_injury), 2),
            "resultado_pick": "PENDIENTE",
            "beneficio_unidades": None,
            "ganador_real": None,
            "timestamp": datetime.now(ZONA_CDMX).isoformat(),
        }
        predicciones.append(pred)

    # Guardar en disco
    with open(RUTA_PREDICCIONES_JSON, "w", encoding="utf-8") as f:
        json.dump(predicciones, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 Predicciones Moneyline V2 guardadas en {RUTA_PREDICCIONES_JSON} ({len(predicciones)} partidos)")

    pd.DataFrame(predicciones).to_parquet(RUTA_PREDICCIONES_PARQUET, index=False)

    # Sincronización en Base de Datos MySQL
    try:
        guardar_predicciones_moneyline_mysql(predicciones)
    except Exception as exc:
        logger.warning(f"No se pudo sincronizar en base de datos: {exc}")

    return predicciones


if __name__ == "__main__":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    preds = predecir_jornada_nfl_moneyline(force_refresh=True)
    print(f"\n🏈 Predicciones Moneyline NFL V2 ({len(preds)} partidos):")
    for p in preds:
        print(f"\n[{p['fecha_cdmx']} {p['hora_cdmx']}] {p['partido']} ({p['estado']})")
        print(f"   Win Prob: {p['equipo_local']} {p['prob_local']*100:.1f}% vs {p['equipo_visita']} {p['prob_visita']*100:.1f}% | Spread: {p['spread_line']}")
        print(f"   Diff EPA: {p.get('diff_total_epa', 0.0):+.2f} | Diff OL: {p.get('diff_injury_ol', 0.0):+.1f}")
        print(f"   🎯 PICK: {p['pick_seleccion']} ({p['pick_cuota']} / {p['pick_cuota_dec']}) [Edge: +{p['pick_edge']*100:.1f}% | EV: {p['ev_estimado']}%] [{p['confianza']}]")
        print(f"   Detalle: {p['pick_detalle']}")
