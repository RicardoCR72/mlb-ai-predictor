import unittest
import pandas as pd
import numpy as np
from nfl.predecir_props_semana_actual import seleccionar_candidatos

class TestNFLPropsCandados(unittest.TestCase):
    def setUp(self):
        # Base dataframe simulating predictions
        self.sample = pd.DataFrame([
            {
                "game_id": "2026_09_JAX_BAL",
                "player_id": "P_BATEMAN",
                "player_name": "Rashod Bateman",
                "position": "WR",
                "team": "BAL",
                "opponent_team": "JAX",
                "tipo_prop": "receiving_yards",
                "linea": 13.5,  # Trap line! (<= 22.0)
                "proyeccion": 31.4,
                "edge": 17.9,
                "seleccion": "OVER",
                "probabilidad_over": 0.65,
                "probabilidad_under": 0.35,
                "probabilidad_pick": 0.65,
                "cuota_over": -110,
                "cuota_under": -110,
                "cuota_pick": -110,
                "player_injury_status": "healthy"
            },
            {
                "game_id": "2026_09_JAX_BAL",
                "player_id": "P_ANDREWS",
                "player_name": "Mark Andrews",
                "position": "TE",
                "team": "BAL",
                "opponent_team": "JAX",
                "tipo_prop": "receiving_yards",
                "linea": 18.5,  # Trap line! (<= 22.0)
                "proyeccion": 32.7,
                "edge": 14.2,
                "seleccion": "OVER",
                "probabilidad_over": 0.63,
                "probabilidad_under": 0.37,
                "probabilidad_pick": 0.63,
                "cuota_over": -110,
                "cuota_under": -110,
                "cuota_pick": -110,
                "player_injury_status": "healthy"
            },
            {
                "game_id": "2026_09_JAX_BAL",
                "player_id": "P_STRANGE",
                "player_name": "Brenton Strange",
                "position": "TE",
                "team": "JAX",
                "opponent_team": "BAL",
                "tipo_prop": "receiving_yards",
                "linea": 35.5,  # Normal line (> 22.0)
                "proyeccion": 45.3,
                "edge": 9.8,   # Qualifies under new 8.0 threshold!
                "seleccion": "OVER",
                "probabilidad_over": 0.63,
                "probabilidad_under": 0.37,
                "probabilidad_pick": 0.63,
                "cuota_over": -110,
                "cuota_under": -110,
                "cuota_pick": -110,
                "player_injury_status": "healthy"
            },
            {
                "game_id": "2026_09_JAX_BAL",
                "player_id": "P_LAWRENCE",
                "player_name": "Trevor Lawrence",
                "position": "QB",
                "team": "JAX",
                "opponent_team": "BAL",
                "tipo_prop": "passing_yards",
                "linea": 233.5,
                "proyeccion": 260.0,
                "edge": 26.5,
                "seleccion": "OVER",
                "probabilidad_over": 0.63,
                "probabilidad_under": 0.37,
                "probabilidad_pick": 0.63,
                "cuota_over": -110,
                "cuota_under": -110,
                "cuota_pick": -110,
                "player_injury_status": "healthy"
            }
        ])

    def test_trap_lines_are_blocked(self):
        res = seleccionar_candidatos(self.sample.copy())
        # Bateman and Andrews must be blocked as NO PICK
        bateman = res[res["player_name"] == "Rashod Bateman"].iloc[0]
        andrews = res[res["player_name"] == "Mark Andrews"].iloc[0]
        self.assertEqual(bateman["estado_pick"], "NO PICK")
        self.assertEqual(andrews["estado_pick"], "NO PICK")

    def test_favorite_receiver_with_solid_edge_qualifies(self):
        res = seleccionar_candidatos(self.sample.copy())
        strange = res[res["player_name"] == "Brenton Strange"].iloc[0]
        self.assertEqual(strange["estado_pick"], "CANDIDATO")

    def test_qb_killswitch_blocks_receivers_when_qb_lines_missing(self):
        # Baltimore has no passing lines while JAX does, so Baltimore passing attack is blocked
        res = seleccionar_candidatos(self.sample.copy())
        bal_candidatos = res[(res["team"] == "BAL") & (res["estado_pick"] == "CANDIDATO")]
        self.assertEqual(len(bal_candidatos), 0)

if __name__ == "__main__":
    unittest.main()
