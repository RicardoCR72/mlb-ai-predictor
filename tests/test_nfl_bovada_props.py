"""Pruebas unitarias para el servicio de extracción de NFL Player Props desde Bovada (0 Créditos)."""
import pytest
import pandas as pd
from nfl.servicio_bovada_props import (
    _limpiar_nombre,
    _american_a_decimal,
    _resolver_jugador_nfl,
    EQUIPOS_BOVADA_A_SIGLA,
)


def test_limpiar_nombre():
    assert _limpiar_nombre("Patrick Mahomes II") == "patrick mahomes"
    assert _limpiar_nombre("Kenneth Walker III") == "kenneth walker"
    assert _limpiar_nombre("A.J. Brown") == "aj brown"
    assert _limpiar_nombre("Ja'Marr Chase") == "jamarr chase"
    assert _limpiar_nombre("Marvin Harrison Jr.") == "marvin harrison"


def test_american_a_decimal():
    assert _american_a_decimal("+100") == 2.0
    assert _american_a_decimal("EVEN") == 2.0
    assert _american_a_decimal("-110") == pytest.approx(1.9091, 0.001)
    assert _american_a_decimal("+150") == 2.5
    assert _american_a_decimal("-200") == 1.5


def test_equipos_bovada_a_sigla():
    assert EQUIPOS_BOVADA_A_SIGLA["Kansas City Chiefs"] == "KC"
    assert EQUIPOS_BOVADA_A_SIGLA["San Francisco 49ers"] == "SF"
    assert EQUIPOS_BOVADA_A_SIGLA["Philadelphia Eagles"] == "PHI"
    assert EQUIPOS_BOVADA_A_SIGLA["Baltimore Ravens"] == "BAL"


def test_resolver_jugador_nfl():
    indice = {
        "por_equipo": {
            "KC": {
                "patrick mahomes": {
                    "id_jugador": "00-0033873",
                    "nombre": "Patrick Mahomes",
                    "posicion": "QB",
                    "equipo": "KC",
                }
            }
        },
        "global": {
            "patrick mahomes": {
                "id_jugador": "00-0033873",
                "nombre": "Patrick Mahomes",
                "posicion": "QB",
                "equipo": "KC",
            }
        },
    }

    # Coincidencia directa con equipo
    res1 = _resolver_jugador_nfl("Patrick Mahomes", "KC", indice)
    assert res1 is not None
    assert res1["id_jugador"] == "00-0033873"

    # Coincidencia con sufijo (II)
    res2 = _resolver_jugador_nfl("Patrick Mahomes II", "KC", indice)
    assert res2 is not None
    assert res2["id_jugador"] == "00-0033873"

    # Búsqueda global si equipo no coincide o falta
    res3 = _resolver_jugador_nfl("Patrick Mahomes", "", indice)
    assert res3 is not None
    assert res3["id_jugador"] == "00-0033873"

