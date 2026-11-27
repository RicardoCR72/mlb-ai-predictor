"""Tests unitarios de integridad, calibración y ausencia de sesgos/fugas en modelos NFL."""
from pathlib import Path
from unittest.mock import patch
import json

import joblib
import numpy as np
import pandas as pd

from nfl.ensamble_spread_v1 import EnsambleSpreadNFLv1
from nfl.predecir_moneyline import calcular_descanso_fecha, es_juego_divisional
from nfl.predecir_spread import generar_predicciones_spread
from nfl.predecir_props_semana_actual import agregar_lineas_y_probabilidades
from nfl.services.totals_engine import NFL_TOTALS_INTERCEPT_BIAS, generar_predicciones
from nfl.feature_spec import FEATURES_BASE, FEATURES_CATEGORICAS, FEATURES_MERCADO


RAIZ = Path(__file__).resolve().parents[1]


def test_moneyline_v2_carga_sin_lightgbm_y_suma_uno():
    bundle = joblib.load(RAIZ / "modelos_nfl" / "modelo_moneyline_nfl.joblib")
    features = bundle["features"]

    assert "diff_def_pass_epa_8" in features
    assert "diff_def_rush_epa_8" in features
    assert "diff_def_sacks_8" in features
    assert "diff_total_epa_8" not in features
    assert "diff_margin_avg_8" not in features

    row_fav = {c: 0.0 for c in features}
    row_fav["spread_line"] = 7.0
    probs = bundle["modelo"].predict_proba(pd.DataFrame([row_fav]))

    assert probs.shape == (1, 2)
    assert np.isclose(probs.sum(), 1.0, atol=1e-6)
    assert 0.0 < probs[0, 1] < 1.0
    assert probs[0, 1] > 0.60


def test_spread_signo_espn_division_y_umbral_0530(tmp_path):
    assert es_juego_divisional("LAR", "SF") == 1
    assert es_juego_divisional("LA", "SF") == 1
    assert calcular_descanso_fecha("2026-11-22", "2026-11-29") == 7.0
    assert calcular_descanso_fecha("2026-11-22", "2026-11-26") == 4.0

    with (
        patch("nfl.predecir_spread.RUTA_PREDICCIONES_DIR", tmp_path),
        patch("nfl.predecir_spread.RUTA_PREDICCIONES_JSON", tmp_path / "spread.json"),
        patch("nfl.predecir_spread.RUTA_PREDICCIONES_PARQUET", tmp_path / "spread.parquet"),
        patch("nfl.predecir_spread.obtener_metricas_recientes_equipos", return_value={}),
    ):
        preds = generar_predicciones_spread(
            jornada_partidos=[
                {
                    "id_evento": "espn_test_1",
                    "equipo_local": "KC",
                    "equipo_visita": "LV",
                    "spread_line": -7.0,  # Convención ESPN: local favorito por 7
                    "fecha_cdmx": "2026-11-29",
                    "estado": "STATUS_SCHEDULED",
                }
            ]
        )

    assert len(preds) == 1
    assert preds[0]["spread_line_raw"] == 7.0
    assert preds[0]["game_id"] == "espn_test_1"

    class _MockProb:
        def __init__(self, p_home: float):
            self._p = p_home

        def predict_proba(self, X):
            return np.array([[1.0 - self._p, self._p]] * len(X))

    ensamble_edge_insuf = EnsambleSpreadNFLv1(_MockProb(0.521), _MockProb(0.521), ["spread_line"])
    res_pass = ensamble_edge_insuf.evaluar_partido({"spread_line": 3.0}, 3.0, "KC", "LV")
    assert res_pass["recomendar"] is False
    assert res_pass["lado"] == "PASS"

    ensamble_edge_valido = EnsambleSpreadNFLv1(_MockProb(0.535), _MockProb(0.535), ["spread_line"])
    res_pick = ensamble_edge_valido.evaluar_partido({"spread_line": 3.0}, 3.0, "KC", "LV")
    assert res_pick["recomendar"] is True
    assert res_pick["lado"] == "HOME"
    assert res_pick["ev_esperado_pct"] > 0.0


def test_totals_engine_sin_sesgo_fijo_under():
    assert NFL_TOTALS_INTERCEPT_BIAS == 0.0

    class _MockModel:
        def __init__(self, cols, preds):
            self.feature_names_in_ = np.array(cols)
            self._preds = np.array(preds, dtype=float)

        def predict(self, X):
            return self._preds

    class _MockCal:
        def predict_proba(self, X):
            return np.array([[0.40, 0.60]] * len(X))

    cols_base = FEATURES_BASE + FEATURES_CATEGORICAS
    cols_mkt = FEATURES_MERCADO + FEATURES_CATEGORICAS
    rows = []
    for total_line in [45.0, 45.0]:
        r = {c: 0.0 for c in set(cols_base + cols_mkt)}
        r["roof"] = "outdoors"
        r["surface"] = "grass"
        r["total_line"] = total_line
        r["over_odds"] = -110
        r["under_odds"] = -110
        rows.append(r)

    df_in = pd.DataFrame(rows)
    res = generar_predicciones(
        df_in,
        modelo_mercado=_MockModel(cols_mkt, [50.0, 40.0]),
        modelo_base=_MockModel(cols_base, [45.0, 45.0]),
        calibrador=_MockCal(),
    )

    assert res.loc[0, "pick"] == "OVER"
    assert res.loc[1, "pick"] == "UNDER"
    assert np.isclose(res.loc[0, "prob_over"], 0.60, atol=1e-6)
    assert np.isclose(res.loc[1, "prob_under"], 0.60, atol=1e-6)


def test_props_nfl_sin_sesgo_fijo_under(tmp_path):
    valid_path = tmp_path / "valid.csv"
    cfg_path = tmp_path / "cfg.json"
    res_path = tmp_path / "resids.npz"

    # Residuos exactamente simétricos centrados en 0
    pd.DataFrame({
        "season": [2024] * 120,
        "objetivo": ["receiving_yards"] * 120,
        "position": ["WR"] * 120,
        "error": np.concatenate([np.linspace(-20, -0.5, 60), np.linspace(0.5, 20, 60)]),
    }).to_csv(valid_path, index=False)
    cfg_path.write_text(json.dumps({"yardas": {}, "passing_tds": {"lineas": {}}}), encoding="utf-8")
    np.savez(res_path, passing_yards=np.array([0.0]), rushing_yards=np.array([0.0]))

    proy = pd.DataFrame([{
        "game_id": "2026_10_KC_BUF",
        "player_id": "P1",
        "player_name": "WR Test",
        "position": "WR",
        "team": "KC",
        "opponent_team": "BUF",
        "tipo_prop": "receiving_yards",
        "proyeccion": 65.0,
        "player_carries_avg_5": 0.0,
        "is_primary_rusher": 0,
        "depth_rank": 1,
        "player_injury_status": "healthy_or_unlisted",
    }])
    lineas = pd.DataFrame([{
        "game_id": "2026_10_KC_BUF",
        "player_id": "P1",
        "tipo_prop": "receiving_yards",
        "id_linea": 1,
        "casa_apuestas": "DraftKings",
        "linea": 65.0,
        "cuota_over": -110,
        "cuota_under": -110,
    }])

    with (
        patch("nfl.predecir_props_semana_actual.RUTA_VALIDACION", valid_path),
        patch("nfl.predecir_props_semana_actual.RUTA_CALIBRACION_PC", cfg_path),
        patch("nfl.predecir_props_semana_actual.RUTA_RESIDUOS_PC", res_path),
    ):
        res = agregar_lineas_y_probabilidades(proy, lineas)

    assert np.isclose(res.iloc[0]["probabilidad_over"], 0.50, atol=1e-4)
    assert np.isclose(res.iloc[0]["probabilidad_under"], 0.50, atol=1e-4)


def test_epa_rolling_sin_fuga_entre_temporadas_y_defensivo():
    df_epa = pd.read_parquet(RAIZ / "data" / "nfl" / "processed" / "nfl_team_epa_rolling.parquet")
    for col in [
        "passing_epa",
        "rushing_epa",
        "def_pass_epa_allowed",
        "def_rush_epa_allowed",
        "def_sacks_gen",
        "roll_def_pass_epa_8",
        "roll_def_rush_epa_8",
        "roll_def_sacks_8",
    ]:
        assert col in df_epa.columns

    df_sorted = df_epa.sort_values(["team", "season", "gameday", "week"]).reset_index(drop=True)
    first_games = df_sorted.groupby(["team", "season"], as_index=False).nth(0)
    assert first_games["roll_pass_epa_8"].isna().all()
    assert first_games["roll_def_pass_epa_8"].isna().all()
