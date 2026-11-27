"""Pruebas unitarias para el filtro automático Top 5 de máxima confianza y +EV."""
from __future__ import annotations

import pandas as pd

from core.filtro_top5 import (
    TOP_N_PICKS,
    etiqueta_top,
    filtrar_top5_dataframe,
    filtrar_top5_picks_dict,
)
from nba.predecir_props import seleccionar_top_props_diarios


def test_filtrar_top5_picks_dict_excluye_neutrales_y_limita_a_5():
    """Debe excluir NEUTRAL/LONGSHOT/SIN VALOR/ev<=0/prob baja y devolver máximo 5 ordenados."""
    items = [
        {"id": f"G{i}", "conf": "ALTA", "prob": 0.55 + i * 0.005, "ev": 4.0 + i}
        for i in range(8)
    ]
    items.extend([
        {"id": "NEUT", "conf": "NEUTRAL", "prob": 0.70, "ev": 15.0},
        {"id": "PASS1", "conf": "PASS", "prob": 0.65, "ev": 12.0},
        {"id": "LONG", "conf": "LONGSHOT", "prob": 0.35, "ev": 25.0},
        {"id": "NEG", "conf": "ALTA", "prob": 0.62, "ev": -1.5},
        {"id": "LOWP", "conf": "MEDIA", "prob": 0.49, "ev": 5.0},
        {"id": "MED1", "conf": "MEDIA", "prob": 0.68, "ev": 20.0},
    ])

    top = filtrar_top5_picks_dict(
        items,
        get_conf=lambda x: x["conf"],
        get_prob=lambda x: x["prob"],
        get_ev=lambda x: x["ev"],
        get_id_unico=lambda x: x["id"],
    )

    assert len(top) == TOP_N_PICKS == 5
    ids = {x["id"] for x in top}
    assert ids.isdisjoint({"NEUT", "PASS1", "LONG", "NEG", "LOWP", "MED1"})
    # Todos ALTA y ordenados descendentemente por probabilidad
    assert all(x["conf"] == "ALTA" for x in top)
    probs = [x["prob"] for x in top]
    assert probs == sorted(probs, reverse=True)


def test_filtrar_top5_dataframe_deduplica_jugador_y_recorta():
    """Debe conservar 1 fila por jugador (la más segura/EV), excluir <=0 y cortar en 5."""
    rows = []
    for i in range(10):
        rows.append({
            "player_name": f"Player_{i % 7}",
            "model_prob": 0.55 + (i % 4) * 0.02,
            "ev_pct": 3.0 + i * 0.5,
            "stars": "⭐⭐⭐",
        })
    rows.append({"player_name": "Neutral_Guy", "model_prob": 0.72, "ev_pct": 12.0, "stars": "⚪"})
    rows.append({"player_name": "Negative_EV", "model_prob": 0.68, "ev_pct": -0.5, "stars": "⭐⭐"})

    df = pd.DataFrame(rows)
    res = filtrar_top5_dataframe(
        df,
        prob_col="model_prob",
        ev_col="ev_pct",
        valid_mask=(df["stars"] != "⚪"),
        dedupe_col="player_name",
        limite=5,
        min_prob=0.54,
        min_ev=0.0,
    )

    assert len(res) == 5
    assert "Neutral_Guy" not in set(res["player_name"])
    assert "Negative_EV" not in set(res["player_name"])
    assert res["player_name"].nunique() == 5
    assert (res["ev_pct"] > 0).all()
    assert (res["model_prob"] >= 0.54).all()


def test_etiqueta_top_sin_estrellas():
    """Las insignias Top no deben contener estrellas ruidosas."""
    for pos in range(1, 6):
        lbl = etiqueta_top(pos)
        assert f"#{pos}" in lbl
        assert "⭐" not in lbl
        assert "⚪" not in lbl


def test_seleccionar_top_props_diarios_top5_y_1_por_jugador():
    """seleccionar_top_props_diarios debe respetar límite 5 por defecto y 1 prop por jugador."""
    rows = []
    for i in range(12):
        rows.append({
            "player_name": f"Jugador_{i // 2}",
            "game": f"A{i % 3} @ B{i % 3}",
            "market": "Total Points" if i % 2 == 0 else "Total Rebounds",
            "pick_type": "UNDER",
            "model_prob": 0.56 + (i % 5) * 0.015,
            "ev_pct": 4.0 + i * 0.4,
            "stars": "⭐⭐⭐",
            "games_played": 15,
            "hit_rate_l5": 0.2,
            "hit_rate_season": 0.3,
            "es_candado": i == 11,
        })
    rows.append({
        "player_name": "Neutro",
        "game": "X @ Y",
        "market": "Total Points",
        "pick_type": "OVER",
        "model_prob": 0.70,
        "ev_pct": 10.0,
        "stars": "⚪",
        "games_played": 20,
        "hit_rate_l5": 0.8,
        "hit_rate_season": 0.8,
        "es_candado": False,
    })

    df_top = seleccionar_top_props_diarios(pd.DataFrame(rows))
    assert len(df_top) == 5
    assert df_top["player_name"].nunique() == 5
    assert "Neutro" not in set(df_top["player_name"])
    assert (df_top["ev_pct"] > 0).all()
    assert (df_top["model_prob"] >= 0.54).all()
