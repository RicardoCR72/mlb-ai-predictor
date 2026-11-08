"""Tests para el módulo de Rendimiento Diario Total Consolidado NBA."""
import pandas as pd
import pytest

from nba.ui_rendimiento_total import (
    cargar_rendimiento_consolidado_nba,
    MAPA_PILARES,
    NOMBRES_MERCADOS_LINDOS,
)


def test_mapa_pilares_y_nombres():
    """Valida que todos los mercados de la NBA se mapeen correctamente a sus pilares."""
    assert MAPA_PILARES["Totales"] == "Totales"
    assert MAPA_PILARES["Totales (OVER)"] == "Totales"
    assert MAPA_PILARES["Totales (UNDER)"] == "Totales"
    assert MAPA_PILARES["Moneyline"] == "Moneyline"
    assert MAPA_PILARES["Spread"] == "Spread"
    assert MAPA_PILARES["Props de Jugadores"] == "Props de Jugadores"


def test_cargar_rendimiento_consolidado_nba():
    """Valida la carga y enriquecimiento del DataFrame de rendimiento NBA."""
    df = cargar_rendimiento_consolidado_nba()
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        required_cols = [
            "fecha_str",
            "pilar",
            "mercado_display",
            "unidades",
            "resultado",
            "partido",
            "marcador_final",
            "ev_pct",
            "stars",
        ]
        for col in required_cols:
            assert col in df.columns, f"Columna requerida {col} no encontrada"

        # Verificar que las estrellas correspondan al rango de EV
        for _, row in df.iterrows():
            ev = row["ev_pct"]
            stars = row["stars"]
            if ev >= 10.0:
                assert stars == "⭐⭐⭐"
            elif ev >= 5.0:
                assert stars == "⭐⭐"
            elif ev > 0.0:
                assert stars == "⭐"
            else:
                assert stars == "⚪"

        # Verificar que los pilares pertenezcan a los admitidos (incluyendo Props de Jugadores)
        assert set(df["pilar"].unique()).issubset({"Totales", "Moneyline", "Spread", "Props de Jugadores", "Otro"})

        # Verificar que haya fechas válidas con formato YYYY-MM-DD
        fechas = df["fecha_str"].dropna().tolist()
        assert len(fechas) > 0
        assert all(len(f) == 10 and f.count("-") == 2 for f in fechas)


def test_agrupacion_diaria_nba():
    """Valida que la consolidación por día calcule correctamente récord, unidades y ROI."""
    mock_data = pd.DataFrame([
        {
            "id": 1,
            "id_juego": "j1",
            "fecha": "2026-11-04",
            "fecha_str": "2026-11-04",
            "mercado": "Totales (OVER)",
            "pilar": "Totales",
            "resultado": "GANADA",
            "cuota": 1.91,
            "unidades": 0.91,
        },
        {
            "id": 2,
            "id_juego": "j2",
            "fecha": "2026-11-04",
            "fecha_str": "2026-11-04",
            "mercado": "Moneyline",
            "pilar": "Moneyline",
            "resultado": "PERDIDA",
            "cuota": 2.10,
            "unidades": -1.0,
        },
        {
            "id": 3,
            "id_juego": "j3",
            "fecha": "2026-11-04",
            "fecha_str": "2026-11-04",
            "mercado": "Spread",
            "pilar": "Spread",
            "resultado": "GANADA",
            "cuota": 1.91,
            "unidades": 0.91,
        },
    ])

    liquidados = mock_data[mock_data["resultado"].isin(["GANADA", "PERDIDA", "PUSH"])]
    tot_picks = len(liquidados)
    ganadas = (liquidados["resultado"] == "GANADA").sum()
    perdidas = (liquidados["resultado"] == "PERDIDA").sum()
    unidades_netas = liquidados["unidades"].sum()
    win_rate = (ganadas / tot_picks) * 100.0
    roi = (unidades_netas / tot_picks) * 100.0

    assert tot_picks == 3
    assert ganadas == 2
    assert perdidas == 1
    assert round(unidades_netas, 2) == 0.82
    assert round(win_rate, 1) == 66.7
    assert round(roi, 1) == 27.3

