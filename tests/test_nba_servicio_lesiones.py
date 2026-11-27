"""Tests para el motor de lesiones e impacto cuantitativo NBA."""
import pytest
from nba.servicio_lesiones import (
    _normalizar_estado_medico,
    calcular_impacto_lesiones_partido,
    obtener_reporte_lesiones_nba,
    IMPACTO_JUGADORES,
    PESO_ESTADO_LESION,
)


def test_normalizar_estado_medico():
    """Valida la detección precisa de estados médicos desde etiquetas y comentarios."""
    assert _normalizar_estado_medico("Out", "Haliburton is out for Saturday") == "OUT"
    assert _normalizar_estado_medico("Day-To-Day", "ruled out for tonight") == "OUT"
    assert _normalizar_estado_medico("Day-To-Day", "is questionable with ankle sprain") == "QUESTIONABLE"
    assert _normalizar_estado_medico("Day-To-Day", "doubtful to play") == "DOUBTFUL"
    assert _normalizar_estado_medico("Day-To-Day", "probable for tonight's game") == "PROBABLE"


def test_impacto_jugadores_y_pesos():
    """Valida los pesos y tiers de las estrellas de la NBA."""
    assert IMPACTO_JUGADORES["Nikola Jokic"]["tier"] == 1
    assert IMPACTO_JUGADORES["Luka Doncic"]["tier"] == 1
    assert IMPACTO_JUGADORES["Tyrese Haliburton"]["tier"] == 2
    assert IMPACTO_JUGADORES["Paolo Banchero"]["tier"] == 2

    assert PESO_ESTADO_LESION["OUT"] == 1.0
    assert PESO_ESTADO_LESION["DOUBTFUL"] == 0.75
    assert PESO_ESTADO_LESION["QUESTIONABLE"] == 0.45
    assert PESO_ESTADO_LESION["PROBABLE"] == 0.10


def test_obtener_reporte_lesiones_nba():
    """Valida la descarga y estructuración del reporte de lesiones."""
    reporte = obtener_reporte_lesiones_nba()
    assert isinstance(reporte, dict)
    # Debe contener equipos de la NBA
    if reporte:
        sample_team = list(reporte.keys())[0]
        assert isinstance(reporte[sample_team], list)
        if reporte[sample_team]:
            inj = reporte[sample_team][0]
            assert "jugador" in inj
            assert "estado" in inj
            assert "impacto_spread" in inj
            assert "impacto_total" in inj


def test_calcular_impacto_lesiones_partido():
    """Valida el cálculo de penalizaciones netas para un enfrentamiento."""
    res = calcular_impacto_lesiones_partido("Denver Nuggets", "Indiana Pacers")
    assert isinstance(res, dict)
    assert "ajuste_neto_spread" in res
    assert "ajuste_total_puntos" in res
    assert "alertas" in res
    assert "candado_lesion" in res
    # El ajuste total debe ser negativo o cero (las lesiones reducen puntos)
    assert res["ajuste_total_puntos"] <= 0.0


def test_topes_lesiones_y_anclas_defensivas(monkeypatch):
    """Valida topes por equipo (8.5 spread, 6.5 total) y total=0.0 en anclas defensivas."""
    for anchor in ["Rudy Gobert", "Draymond Green", "Jarrett Allen", "Clint Capela", "Steven Adams"]:
        assert IMPACTO_JUGADORES[anchor]["total"] == 0.0

    mock_report = {
        "BOS": [
            {"jugador": "Player A", "estado": "OUT", "impacto_spread": 5.0, "impacto_total": 4.0, "es_estrella": True, "tier": 1},
            {"jugador": "Player B", "estado": "OUT", "impacto_spread": 5.0, "impacto_total": 4.0, "es_estrella": True, "tier": 2},
            {"jugador": "Player C", "estado": "OUT", "impacto_spread": 3.0, "impacto_total": 2.0, "es_estrella": False, "tier": 3},
        ],
        "LAL": [],
    }
    monkeypatch.setattr("nba.servicio_lesiones.obtener_reporte_lesiones_nba", lambda force_refresh=False: mock_report)

    res = calcular_impacto_lesiones_partido("BOS", "LAL")
    assert res["penalizacion_spread_visita"] == 8.5
    assert res["ajuste_neto_spread"] == 8.5
    assert res["ajuste_total_puntos"] == -6.5

