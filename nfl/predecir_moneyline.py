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
RUTA_SCHEDULES = RAIZ / "data" / "nfl" / "raw" / "nfl_schedules_2012_2026.parquet"
RUTA_INJURIES = RAIZ / "data" / "nfl" / "raw" / "nfl_injuries_2012_2026.parquet"
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
    {"ARI", "LA", "SF", "SEA"},
]


def normalizar_equipo(nombre: str) -> str:
    """Mapea nombres o siglas de ESPN a las siglas estándar de nflverse."""
    mapeo = {
        "WSH": "WAS",
        "LAR": "LA",
        "OAK": "LV",
        "SD": "LAC",
    }
    return mapeo.get(str(nombre or "").upper().strip(), str(nombre or "").upper().strip())


def es_juego_divisional(home: str, away: str) -> int:
    """Verifica si ambos equipos pertenecen a la misma división."""
    h_norm = normalizar_equipo(home)
    a_norm = normalizar_equipo(away)
    for div in DIVISIONES_NFL:
        if h_norm in div and a_norm in div:
            return 1
    return 0


def calcular_descanso_fecha(
    last_gameday_str: Any,
    fecha_objetivo: Any,
    default_rest: float = 7.0,
) -> float:
    """Calcula días reales de descanso respecto a la fecha del partido próximo."""
    if not last_gameday_str or not fecha_objetivo:
        return float(default_rest)
    try:
        dt_last = datetime.strptime(str(last_gameday_str)[:10], "%Y-%m-%d").date()
        dt_obj = datetime.strptime(str(fecha_objetivo)[:10], "%Y-%m-%d").date()
        diff = (dt_obj - dt_last).days
        if 0 <= diff <= 21:
            return float(min(max(diff, 4), 14))
        return float(default_rest)
    except Exception:
        return float(default_rest)


def _cargar_lesiones_recientes_equipos(sched_df: Optional[pd.DataFrame]) -> Dict[str, Dict[str, float]]:
    """Calcula los puntajes de lesiones más recientes por equipo desde nfl_injuries."""
    lesiones_por_eq: Dict[str, Dict[str, float]] = {}
    if not RUTA_INJURIES.exists():
        return lesiones_por_eq
    try:
        from nfl.features_lesiones import construir_features_lesiones

        df_inj = pd.read_parquet(RUTA_INJURIES)
        if df_inj.empty:
            return lesiones_por_eq
        df_inj["season"] = pd.to_numeric(df_inj["season"], errors="coerce")
        df_inj["week"] = pd.to_numeric(df_inj["week"], errors="coerce")
        max_season = df_inj["season"].max()
        sub_s = df_inj[df_inj["season"] == max_season]
        max_week = sub_s["week"].max()
        sub_w = sub_s[sub_s["week"] == max_week].copy()

        if sched_df is not None and not sched_df.empty:
            partidos_ref = sched_df[
                (sched_df["season"] == max_season) & (sched_df["week"] == max_week)
            ].copy()
            if partidos_ref.empty:
                partidos_ref = sched_df[sched_df["season"] == max_season].tail(16).copy()
        else:
            partidos_ref = pd.DataFrame(columns=["season", "week", "home_team", "away_team", "home_qb_id", "away_qb_id"])

        resumen = construir_features_lesiones(sub_w, partidos_ref)
        for _, row in resumen.iterrows():
            eq = normalizar_equipo(row["team"])
            lesiones_por_eq[eq] = {
                "injury_severity": float(row.get("injury_severity", 0.0) or 0.0),
                "injury_starting_qb_score": float(row.get("injury_starting_qb_score", 0.0) or 0.0),
                "injury_ol_score": float(row.get("injury_ol_score", 0.0) or 0.0),
                "injury_defense_score": float(row.get("injury_defense_score", 0.0) or 0.0),
            }
    except Exception as exc:
        logger.warning(f"No se pudieron cargar lesiones recientes de NFL: {exc}")
    return lesiones_por_eq


def obtener_metricas_recientes_equipos() -> Dict[str, Dict[str, Any]]:
    """Calcula métricas frescas (incluyendo el último juego disputado), EPA ofensivo/defensivo y lesiones."""
    metricas: Dict[str, Dict[str, Any]] = {}
    sched_raw: Optional[pd.DataFrame] = None
    df_feat: Optional[pd.DataFrame] = None

    if RUTA_SCHEDULES.exists():
        try:
            sched_raw = pd.read_parquet(RUTA_SCHEDULES)
        except Exception:
            sched_raw = None

    if RUTA_DATASET_FEATURES.exists():
        try:
            df_feat = pd.read_parquet(RUTA_DATASET_FEATURES)
        except Exception:
            df_feat = None

    # 1. Construir historial fresco equipo-partido desde schedules completados (sin rezago .shift(1))
    eq_rows = []
    if sched_raw is not None and not sched_raw.empty:
        reg = sched_raw[
            (sched_raw["game_type"] == "REG")
            & sched_raw["home_score"].notna()
            & sched_raw["away_score"].notna()
        ].copy()
        reg["gameday_dt"] = pd.to_datetime(reg["gameday"], errors="coerce")
        for lado, col_tm, col_pf, col_pa in [
            ("H", "home_team", "home_score", "away_score"),
            ("A", "away_team", "away_score", "home_score"),
        ]:
            sub = pd.DataFrame({
                "game_id": reg["game_id"],
                "season": pd.to_numeric(reg["season"], errors="coerce"),
                "week": pd.to_numeric(reg["week"], errors="coerce"),
                "gameday": reg["gameday_dt"],
                "team": reg[col_tm].astype(str).map(normalizar_equipo),
                "points_for": pd.to_numeric(reg[col_pf], errors="coerce"),
                "points_against": pd.to_numeric(reg[col_pa], errors="coerce"),
            })
            eq_rows.append(sub)

    df_team_games = pd.concat(eq_rows, ignore_index=True) if eq_rows else pd.DataFrame()
    if not df_team_games.empty:
        df_team_games["win"] = (df_team_games["points_for"] > df_team_games["points_against"]).astype(float)
        df_team_games["margin"] = df_team_games["points_for"] - df_team_games["points_against"]

    # 2. Cargar EPA fresco por equipo (medias sobre últimos 8 partidos crudos de la última temporada)
    df_epa = None
    if RUTA_EPA_ROLLING.exists():
        try:
            df_epa = pd.read_parquet(RUTA_EPA_ROLLING)
            df_epa["team"] = df_epa["team"].astype(str).map(normalizar_equipo)
            df_epa["gameday"] = pd.to_datetime(df_epa["gameday"], errors="coerce")
        except Exception:
            df_epa = None

    # 3. Cargar lesiones recientes
    lesiones_eq = _cargar_lesiones_recientes_equipos(sched_raw)

    equipos: set[str] = set()
    if not df_team_games.empty:
        equipos |= set(df_team_games["team"].dropna().unique())
    if df_feat is not None and not df_feat.empty:
        equipos |= set(df_feat["home_team"].dropna().map(normalizar_equipo).unique())
        equipos |= set(df_feat["away_team"].dropna().map(normalizar_equipo).unique())

    for eq in equipos:
        prof: Dict[str, Any] = {
            "margin_avg_8": 0.0,
            "margin_avg_4": 0.0,
            "points_for_avg_8": 21.0,
            "points_against_avg_8": 21.0,
            "points_for_avg_season": 21.0,
            "win_pct_8": 0.50,
            "win_pct_season": 0.50,
            "rest": 7.0,
            "last_gameday": "",
            "injury_severity": 0.0,
            "injury_starting_qb_score": 0.0,
            "injury_ol_score": 0.0,
            "injury_defense_score": 0.0,
            "total_epa_8": 0.0,
            "pass_epa_8": 0.0,
            "rush_epa_8": 0.0,
            "sacks_8": 0.0,
            "def_pass_epa_8": 0.0,
            "def_rush_epa_8": 0.0,
            "def_sacks_8": 0.0,
        }

        if not df_team_games.empty:
            grp = df_team_games[df_team_games["team"] == eq]
            if not grp.empty:
                latest_season = grp["season"].max()
                grp_s = grp[grp["season"] == latest_season].sort_values(["gameday", "week", "game_id"])
                tail8 = grp_s.tail(8)
                tail4 = grp_s.tail(4)
                prof["points_for_avg_8"] = float(tail8["points_for"].mean())
                prof["points_against_avg_8"] = float(tail8["points_against"].mean())
                prof["win_pct_8"] = float(tail8["win"].mean())
                prof["margin_avg_8"] = float(tail8["margin"].mean())
                prof["margin_avg_4"] = float(tail4["margin"].mean())
                prof["points_for_avg_season"] = float(grp_s["points_for"].mean())
                prof["win_pct_season"] = float(grp_s["win"].mean())
                last_gd = grp_s["gameday"].iloc[-1]
                if pd.notna(last_gd):
                    prof["last_gameday"] = last_gd.strftime("%Y-%m-%d")

        if df_epa is not None and not df_epa.empty:
            team_epa = df_epa[df_epa["team"] == eq]
            if not team_epa.empty:
                if "season" in team_epa.columns:
                    max_s_epa = team_epa["season"].max()
                    team_epa = team_epa[team_epa["season"] == max_s_epa]
                team_epa = team_epa.sort_values(["gameday", "week"])
                tail_epa = team_epa.tail(8)
                if "passing_epa" in tail_epa.columns:
                    prof["pass_epa_8"] = float(tail_epa["passing_epa"].mean() or 0.0)
                    prof["rush_epa_8"] = float(tail_epa["rushing_epa"].mean() or 0.0)
                    prof["total_epa_8"] = float(tail_epa["total_epa"].mean() or 0.0)
                    prof["sacks_8"] = float(tail_epa["sacks_suffered"].mean() or 0.0)
                    if "def_pass_epa_allowed" in tail_epa.columns:
                        prof["def_pass_epa_8"] = float(tail_epa["def_pass_epa_allowed"].mean() or 0.0)
                        prof["def_rush_epa_8"] = float(tail_epa["def_rush_epa_allowed"].mean() or 0.0)
                        prof["def_sacks_8"] = float(tail_epa["def_sacks_gen"].mean() or 0.0)
                else:
                    last_epa = team_epa.iloc[-1]
                    prof["pass_epa_8"] = float(last_epa.get("roll_pass_epa_8", 0.0) or 0.0)
                    prof["rush_epa_8"] = float(last_epa.get("roll_rush_epa_8", 0.0) or 0.0)
                    prof["total_epa_8"] = float(last_epa.get("roll_total_epa_8", 0.0) or 0.0)
                    prof["sacks_8"] = float(last_epa.get("roll_sacks_8", 0.0) or 0.0)

        if eq in lesiones_eq:
            prof.update(lesiones_eq[eq])
        elif df_feat is not None and not df_feat.empty:
            home_g = df_feat[df_feat["home_team"].map(normalizar_equipo) == eq]
            away_g = df_feat[df_feat["away_team"].map(normalizar_equipo) == eq]
            rec = None
            if not home_g.empty and not away_g.empty:
                rec = home_g.iloc[-1] if home_g["gameday"].max() >= away_g["gameday"].max() else away_g.iloc[-1]
            elif not home_g.empty:
                rec = home_g.iloc[-1]
            elif not away_g.empty:
                rec = away_g.iloc[-1]
            if rec is not None:
                pref = "home_" if normalizar_equipo(rec["home_team"]) == eq else "away_"
                for col_inj in ["injury_severity", "injury_starting_qb_score", "injury_ol_score", "injury_defense_score"]:
                    prof[col_inj] = float(rec.get(f"{pref}{col_inj}", 0.0) or 0.0)

        metricas[eq] = prof

    return metricas


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

        home_team = normalizar_equipo(j["equipo_local"])
        away_team = normalizar_equipo(j["equipo_visita"])

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
        diff_def_pass_epa = m_home.get("def_pass_epa_8", 0.0) - m_away.get("def_pass_epa_8", 0.0)
        diff_def_rush_epa = m_home.get("def_rush_epa_8", 0.0) - m_away.get("def_rush_epa_8", 0.0)
        diff_def_sacks = m_home.get("def_sacks_8", 0.0) - m_away.get("def_sacks_8", 0.0)

        diff_ol_injury = m_home.get("injury_ol_score", 0.0) - m_away.get("injury_ol_score", 0.0)
        diff_qb_injury = m_home.get("injury_starting_qb_score", 0.0) - m_away.get("injury_starting_qb_score", 0.0)
        diff_def_injury = m_home.get("injury_defense_score", 0.0) - m_away.get("injury_defense_score", 0.0)

        home_rest = calcular_descanso_fecha(m_home.get("last_gameday"), j.get("fecha_cdmx"), 7.0)
        away_rest = calcular_descanso_fecha(m_away.get("last_gameday"), j.get("fecha_cdmx"), 7.0)
        diff_rest = home_rest - away_rest

        fila_feat = {
            "spread_line": spread_val,
            "diff_pass_epa_8": diff_pass_epa,
            "diff_rush_epa_8": diff_rush_epa,
            "diff_sacks_8": diff_sacks,
            "diff_def_pass_epa_8": diff_def_pass_epa,
            "diff_def_rush_epa_8": diff_def_rush_epa,
            "diff_def_sacks_8": diff_def_sacks,
            "diff_points_for_avg_8": m_home.get("points_for_avg_8", 21.0) - m_away.get("points_for_avg_8", 21.0),
            "diff_points_against_avg_8": m_home.get("points_against_avg_8", 21.0) - m_away.get("points_against_avg_8", 21.0),
            "diff_win_pct_8": m_home.get("win_pct_8", 0.50) - m_away.get("win_pct_8", 0.50),
            "diff_win_pct_season": m_home.get("win_pct_season", 0.50) - m_away.get("win_pct_season", 0.50),
            "diff_rest": diff_rest,
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

        # Evaluar ambos lados (favorito y underdog) buscando +EV real frente a DraftKings
        ev_home = round(((prob_home * (ml_h_dec - 1.0)) - (1.0 - prob_home)) * 100.0, 2)
        ev_away = round(((prob_away * (ml_a_dec - 1.0)) - (1.0 - prob_away)) * 100.0, 2)

        candidatos_ml = []
        for lado_nom, prob_l, edge_l, ev_l, c_str, c_dec, epa_txt, book_l in [
            (
                f"{home_team} ML",
                prob_home,
                edge_home,
                ev_home,
                j.get("moneyline_local") or "-110",
                ml_h_dec,
                f"Diff EPA: {diff_total_epa:+.2f} ({home_team})",
                p_book_h,
            ),
            (
                f"{away_team} ML",
                prob_away,
                edge_away,
                ev_away,
                j.get("moneyline_visita") or "-110",
                ml_a_dec,
                f"Diff EPA: {-diff_total_epa:+.2f} ({away_team})",
                p_book_a,
            ),
        ]:
            if ev_l > 0 and prob_l >= 0.60 and edge_l >= 0.010:
                conf_l = "ALTA"
                det_l = f"🔥 Alta Convicción (+EV): Prob {prob_l*100:.1f}% vs Book {book_l*100:.1f}% (Edge: +{edge_l*100:.1f}%) | {epa_txt}"
                candidatos_ml.append((ev_l, lado_nom, prob_l, edge_l, c_str, c_dec, conf_l, det_l))
            elif (prob_l >= 0.30 and edge_l >= 0.025 and ev_l >= 3.0) or (ev_l > 0 and prob_l >= 0.50 and edge_l >= 0.015):
                conf_l = "MEDIA"
                det_l = f"⚡ Valor Cuantitativo (+EV): Prob {prob_l*100:.1f}% vs Book {book_l*100:.1f}% (Edge: +{edge_l*100:.1f}%) | {epa_txt}"
                candidatos_ml.append((ev_l, lado_nom, prob_l, edge_l, c_str, c_dec, conf_l, det_l))

        if candidatos_ml:
            candidatos_ml.sort(key=lambda x: x[0], reverse=True)
            ev, pick_sel, pick_prob, pick_edge, pick_cuota, pick_cuota_dec, confianza, detalle = candidatos_ml[0]
        else:
            if prob_home >= prob_away:
                pick_sel = f"{home_team} ML"
                pick_prob = prob_home
                pick_edge = edge_home
                pick_cuota = j.get("moneyline_local") or "-110"
                pick_cuota_dec = ml_h_dec
                ev = ev_home
            else:
                pick_sel = f"{away_team} ML"
                pick_prob = prob_away
                pick_edge = edge_away
                pick_cuota = j.get("moneyline_visita") or "-110"
                pick_cuota_dec = ml_a_dec
                ev = ev_away
            confianza = "NEUTRAL"
            detalle = f"Zona Muerta / Sin +EV: Prob {pick_prob*100:.1f}%, Edge {pick_edge*100:+.1f}%, EV {ev:+.1f}%."

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
