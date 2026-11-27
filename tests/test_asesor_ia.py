"""Pruebas unitarias para el Asesor IA de Overdog Sports AI."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd

from core import asesor_ia


def test_rechaza_datos_desactualizados_y_emite_advertencia(tmp_path, monkeypatch):
    """Si el parquet/JSON NBA es de una fecha pasada, no debe cargarse ni recomendarse."""
    pred_dir = tmp_path / "data" / "nba" / "predictions"
    pred_dir.mkdir(parents=True)
    nfl_dir = tmp_path / "data" / "nfl" / "predictions"
    nfl_dir.mkdir(parents=True)

    df_viejo = pd.DataFrame([
        {
            "fecha": "2026-11-24",
            "player_name": "Josh Hart",
            "game": "NYK @ IND",
            "team": "NYK",
            "market": "Total Rebounds",
            "pick_type": "UNDER",
            "line": 7.5,
            "projection": 6.2,
            "model_prob": 0.58,
            "ev_pct": 6.4,
            "pick_odds_american": None,
            "pick_odds_decimal": 1.909,
            "stars": "⭐⭐⭐",
            "trend": "Under 4/5",
            "game_spread": 3.5,
        }
    ])
    df_viejo.to_parquet(pred_dir / "predicciones_props_nba_hoy.parquet", index=False)

    with open(pred_dir / "predicciones_nba_hoy.json", "w", encoding="utf-8") as f:
        json.dump([{"fecha_cdmx": "2026-11-24", "equipo_visita": "NYK", "equipo_local": "IND", "candidatos": [{"mercado": "ML", "seleccion": "NYK ML", "probabilidad": 0.6, "ev": 0.05}]}], f)

    monkeypatch.setattr(asesor_ia, "RAIZ", tmp_path)
    cands = asesor_ia.cargar_candidatos_hoy(fecha_objetivo="2026-11-26")

    assert cands["nba_props"] == []
    assert cands["nba_partidos"] == []
    assert any("2026-11-24" in adv for adv in cands["advertencias"])


def test_cuota_nunca_es_none_y_convierte_decimal(tmp_path, monkeypatch):
    """Cuando pick_odds_american es None, debe convertir desde pick_odds_decimal o devolver N/D."""
    assert asesor_ia._formatear_cuota(None, 1.909) == "-110"
    assert asesor_ia._formatear_cuota("None", 2.0) == "EVEN"
    assert asesor_ia._formatear_cuota(None, 2.25) == "+125"
    assert asesor_ia._formatear_cuota(None, None) == "N/D"

    pred_dir = tmp_path / "data" / "nba" / "predictions"
    pred_dir.mkdir(parents=True)
    nfl_dir = tmp_path / "data" / "nfl" / "predictions"
    nfl_dir.mkdir(parents=True)

    df_hoy = pd.DataFrame([
        {
            "fecha": "2026-11-26",
            "player_name": "Nikola Jokic",
            "game": "DAL @ DEN",
            "team": "DEN",
            "market": "Total Rebounds",
            "pick_type": "UNDER",
            "line": 11.5,
            "projection": 10.4,
            "model_prob": 0.56,
            "ev_pct": 5.5,
            "pick_odds_american": None,
            "pick_odds_decimal": 1.909,
            "stars": "⭐⭐⭐",
            "trend": "Under 4/5",
            "game_spread": 4.0,
        }
    ])
    df_hoy.to_parquet(pred_dir / "predicciones_props_nba_hoy.parquet", index=False)

    monkeypatch.setattr(asesor_ia, "RAIZ", tmp_path)
    cands = asesor_ia.cargar_candidatos_hoy(fecha_objetivo="2026-11-26")
    assert len(cands["nba_props"]) == 1
    assert cands["nba_props"][0]["cuota"] == "-110"


def test_enrutamiento_nfl_nunca_devuelve_nba_ni_confunde_combinada():
    """Una consulta de NFL sin picks NFL no debe devolver picks de NBA."""
    candidatos = {
        "nba_props": [
            {
                "deporte": "NBA",
                "tipo": "PROP",
                "jugador": "Josh Hart",
                "partido": "NYK @ IND",
                "equipo": "NYK",
                "mercado": "Total Rebounds",
                "seleccion": "UNDER 7.5",
                "probabilidad": 0.58,
                "ev": 6.4,
                "cuota": "-105",
                "estrellas": "⭐⭐⭐",
                "spread_juego": 2.5,
            },
            {
                "deporte": "NBA",
                "tipo": "PROP",
                "jugador": "Nikola Jokic",
                "partido": "DAL @ DEN",
                "equipo": "DEN",
                "mercado": "Total Rebounds",
                "seleccion": "UNDER 11.5",
                "probabilidad": 0.56,
                "ev": 5.2,
                "cuota": "-110",
                "estrellas": "⭐⭐",
                "spread_juego": 4.0,
            },
        ],
        "nba_partidos": [],
        "nfl_props": [],
        "nfl_partidos": [],
        "fecha_referencia": "2026-11-26",
        "advertencias": [],
    }

    resp_nfl = asesor_ia.responder_consulta_asesor(
        "¿Cuáles son las mejores selecciones y tendencias para la NFL hoy?",
        candidatos=candidatos,
        gemini_api_key="fake-key",
    )
    assert "Josh Hart" not in resp_nfl
    assert "NBA" not in resp_nfl
    assert "NFL" in resp_nfl

    resp_comb = asesor_ia.responder_consulta_asesor(
        "Arma la combinada o parlay más seguro del día de 2 selecciones de baja varianza.",
        candidatos=candidatos,
        gemini_api_key="",
    )
    assert "Combinada de Baja Varianza" in resp_comb
    assert "Pata 1" in resp_comb and "Pata 2" in resp_comb

    resp_cand = asesor_ia.responder_consulta_asesor(
        "¿Cuál es el partido o pick más seguro del día según el doble filtro?",
        candidatos=candidatos,
        gemini_api_key="",
    )
    assert "El Candado del Día" in resp_cand
    assert "Josh Hart" in resp_cand


def test_gemini_envia_api_key_en_header_no_en_url():
    """La clave de Gemini debe ir en el header x-goog-api-key, nunca como query string en la URL."""
    candidatos = {
        "nba_props": [
            {
                "deporte": "NBA",
                "tipo": "PROP",
                "jugador": "Nikola Jokic",
                "partido": "DAL @ DEN",
                "equipo": "DEN",
                "mercado": "Total Rebounds",
                "seleccion": "UNDER 11.5",
                "probabilidad": 0.58,
                "ev": 5.5,
                "cuota": "-110",
                "estrellas": "⭐⭐⭐",
                "spread_juego": 3.0,
            }
        ],
        "nba_partidos": [],
        "nfl_props": [],
        "nfl_partidos": [],
        "fecha_referencia": "2026-11-26",
        "advertencias": [],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Análisis válido para Nikola Jokic."}]}}]
    }

    with patch("core.asesor_ia.requests.post", return_value=mock_resp) as mock_post:
        res = asesor_ia.responder_consulta_asesor(
            "¿Cuál es el pick más seguro hoy?",
            candidatos=candidatos,
            gemini_api_key="SECRET_TEST_KEY",
        )
        assert "Nikola Jokic" in res
        called_url = mock_post.call_args.args[0]
        called_headers = mock_post.call_args.kwargs.get("headers", {})
        assert "key=" not in called_url
        assert called_headers.get("x-goog-api-key") == "SECRET_TEST_KEY"


def test_modo_offline_no_llama_gemini(monkeypatch):
    """Con gemini_api_key='' debe operar el motor determinista sin peticiones HTTP externas."""
    candidatos = {
        "nba_props": [
            {
                "deporte": "NBA",
                "tipo": "PROP",
                "jugador": "Nikola Jokic",
                "partido": "DAL @ DEN",
                "equipo": "DEN",
                "mercado": "Total Rebounds",
                "seleccion": "UNDER 11.5",
                "probabilidad": 0.58,
                "ev": 5.5,
                "cuota": "-110",
                "estrellas": "⭐⭐⭐",
                "spread_juego": 3.0,
            }
        ],
        "nba_partidos": [],
        "nfl_props": [],
        "nfl_partidos": [],
        "fecha_referencia": "2026-11-26",
        "advertencias": [],
    }
    with patch("core.asesor_ia.requests.post") as mock_post:
        res = asesor_ia.responder_consulta_asesor(
            "¿Cuál es el pick más seguro?",
            candidatos=candidatos,
            gemini_api_key="",
        )
        mock_post.assert_not_called()
        assert "El Candado del Día" in res
        assert "Nikola Jokic" in res
