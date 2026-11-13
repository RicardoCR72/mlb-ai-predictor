"""Pruebas unitarias para el motor de Player Props NBA con Bovada (0 créditos)."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from nba.servicio_bovada_props import (
    _limpiar_nombre_jugador,
    _american_a_decimal,
    extraer_props_nba,
    RUTA_CACHE_PROPS,
)
from nba.servicio_jugadores_boxscores import (
    _parse_split,
    _parse_min,
    calcular_perfil_jugador,
    RUTA_PARQUET_JUGADORES,
)
from nba.predecir_props import (
    _calcular_probabilidad_poisson,
    _calcular_probabilidad_normal,
    _calcular_hit_rate,
    generar_predicciones_props_hoy,
    RUTA_PRED_PARQUET,
)
from nba.ui_props import renderizar_ui_props_nba


def test_helpers_bovada():
    """Verifica limpieza de sufijos de nombres y conversión de momios."""
    assert _limpiar_nombre_jugador("Kelly Oubre Jr.") == "Kelly Oubre"
    assert _limpiar_nombre_jugador("Marvin Bagley III") == "Marvin Bagley"
    assert _limpiar_nombre_jugador("Nikola Jokic") == "Nikola Jokic"

    assert _american_a_decimal("-110") == pytest.approx(1.909, rel=1e-2)
    assert _american_a_decimal("+100") == 2.0
    assert _american_a_decimal("EVEN") == 2.0
    assert _american_a_decimal("+150") == 2.5


def test_parse_stats_boxscore():
    """Verifica parser de minutos y Made-Attempted."""
    m_val = _parse_min("34:30")
    assert m_val == 34.5
    assert _parse_min("28") == 28.0

    made, att = _parse_split("4-9")
    assert made == 4
    assert att == 9


def test_perfil_jugador_calculo():
    """Verifica el cálculo de perfiles de jugador con min_minutos=8.0."""
    mock_data = pd.DataFrame([
        {"player_name": "Test Player", "team": "DEN", "position": "C", "fecha": "2026-10-25", "min": 32, "pts": 20, "reb": 10, "ast": 5, "t3_made": 1, "pra": 35, "pr": 30, "pa": 25, "stl": 1, "blk": 1},
        {"player_name": "Test Player", "team": "DEN", "position": "C", "fecha": "2026-10-27", "min": 34, "pts": 30, "reb": 12, "ast": 7, "t3_made": 2, "pra": 49, "pr": 42, "pa": 37, "stl": 2, "blk": 1},
        {"player_name": "Test Player", "team": "DEN", "position": "C", "fecha": "2026-10-30", "min": 30, "pts": 25, "reb": 8, "ast": 6, "t3_made": 0, "pra": 39, "pr": 33, "pa": 31, "stl": 0, "blk": 0},
    ])
    # Se pasa explícitamente min_minutos=8.0 para certificar que el parámetro es válido y nativo
    perfil = calcular_perfil_jugador(mock_data, min_minutos=8.0)
    assert len(perfil) == 1
    p0 = perfil.iloc[0]
    assert p0["player_name"] == "Test Player"
    assert p0["games_played"] == 3
    assert p0["pts_avg"] == 25.0
    assert p0["reb_avg"] == 10.0
    assert p0["pra_avg"] == 41.0


def test_probabilidades_y_ev():
    """Verifica límites y coherencia matemática de Poisson y Gaussiana."""
    # Si promedia 3.5 triples y la línea es 1.5, prob over debe ser alta (> 80%)
    p_t3 = _calcular_probabilidad_poisson(1.5, lam=3.5)
    assert 0.80 <= p_t3 <= 0.99

    # Si promedia 25 pts con sigma 5 y línea es 24.5, prob over debe rondar ~50%
    p_pts = _calcular_probabilidad_normal(24.5, mu=25.0, sigma=5.0)
    assert 0.45 <= p_pts <= 0.60

    # Hit rate estándar
    serie = pd.Series([20, 25, 30, 15, 28])
    rate, ov, tot = _calcular_hit_rate(serie, 22.5)
    assert ov == 3
    assert tot == 5
    assert rate == 0.6

    # Hit rate con empate exacto (push): la línea 25.0 debe excluir el 25 del denominador
    serie_con_push = pd.Series([20, 25, 30, 15, 28])  # 25 es push; válidos: [20, 30, 15, 28] (2 over de 4)
    rate_p, ov_p, tot_p = _calcular_hit_rate(serie_con_push, 25.0)
    assert ov_p == 2
    assert tot_p == 4
    assert rate_p == 0.50


def test_bovada_props_cache():
    """Verifica que el caché de Bovada existe y tiene las columnas requeridas."""
    df_props = extraer_props_nba(usar_cache=True)
    assert not df_props.empty
    columnas_esperadas = {"game", "player_clean", "team", "market", "line", "over_american", "over_decimal"}
    assert columnas_esperadas.issubset(set(df_props.columns))
    assert len(df_props) >= 50


def test_predicciones_generadas():
    """Verifica que el pipeline de predicciones genera picks con EV válido."""
    df_preds = generar_predicciones_props_hoy(usar_cache_bovada=True)
    assert not df_preds.empty
    assert "ev_pct" in df_preds.columns
    assert "stars" in df_preds.columns
    assert "pick_type" in df_preds.columns
    assert df_preds["pick_type"].isin(["OVER", "UNDER"]).all()
    # Debe haber picks con EV positivo
    assert (df_preds["ev_pct"] > 0).any()


def test_grafica_cobertura_nba_props():
    """Verifica que la extracción de los últimos 5 juegos para gráficas de props NBA funcione correctamente."""
    from core.ui_grafica_cobertura import obtener_datos_cobertura

    # Test Puntos
    res_pts = obtener_datos_cobertura(
        deporte="NBA",
        mercado="Total Points",
        seleccion="OVER 13.5",
        linea=13.5,
        jugador="Aaron Gordon",
        n_juegos=5
    )
    assert res_pts["unidad"] == "pts"
    assert len(res_pts["df"]) == 5
    assert 0 <= res_pts["cubiertos"] <= 5
    assert 0.0 <= res_pts["tasa_pct"] <= 100.0

    # Test Triples
    res_t3 = obtener_datos_cobertura(
        deporte="NBA",
        mercado="Total Triples",
        seleccion="OVER 3.5",
        linea=3.5,
        jugador="Stephen Curry",
        n_juegos=5
    )
    assert res_t3["unidad"] == "3pm"
    assert len(res_t3["df"]) == 5

    # Test PRA
    res_pra = obtener_datos_cobertura(
        deporte="NBA",
        mercado="Total PRA",
        seleccion="OVER 40.5",
        linea=40.5,
        jugador="Nikola Jokic",
        n_juegos=5
    )
    assert res_pra["unidad"] == "pra"
    assert len(res_pra["df"]) == 5


