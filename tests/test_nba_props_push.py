"""Pruebas unitarias para la liquidación de Player Props de la NBA y regla de PUSH para jugadores DNP / Inactivos."""
import unittest
from unittest.mock import Mock, patch
import pandas as pd

from nba.evaluar_props import liquidar_prop_nba, registrar_devolucion_nba_dnp
from core.devoluciones import apply_refunds, save_refund


class TestNBAPropsPushRule(unittest.TestCase):
    def setUp(self):
        # Boxscore simulado donde Jarrett Allen NO participó (DNP / ausente) y Donovan Mitchell sí jugó
        self.boxscore = pd.DataFrame([
            {
                "player_name": "Donovan Mitchell",
                "minutos": 34.5,
                "pts": 28,
                "reb": 5,
                "ast": 6,
                "t3_made": 4,
                "pra": 39,
                "pr": 33,
                "pa": 34,
            },
            {
                "player_name": "Evan Mobley",
                "minutos": 32.0,
                "pts": 18,
                "reb": 11,
                "ast": 3,
                "t3_made": 0,
                "pra": 32,
                "pr": 29,
                "pa": 21,
            },
            {
                # Jugador en banca con 0 minutos
                "player_name": "Emoni Bates",
                "minutos": 0.0,
                "pts": 0,
                "reb": 0,
                "ast": 0,
                "t3_made": 0,
                "pra": 0,
                "pr": 0,
                "pa": 0,
            }
        ])

    def test_jugador_inactivo_ausente_de_boxscore_es_push(self):
        """Si un jugador no jugó (como Jarrett Allen hoy), el pick jamás es PERDIDA sino PUSH."""
        prop_jarrett_allen = {
            "player_name": "Jarrett Allen",
            "player_clean": "Jarrett Allen",
            "market": "Total Points",
            "line": 12.5,
            "pick_type": "OVER",
            "pick_odds_decimal": 2.05,
        }
        res = liquidar_prop_nba(prop_jarrett_allen, self.boxscore, partido_finalizado=True)
        self.assertEqual(res["resultado"], "PUSH")
        self.assertEqual(res["unidades_ganadas"], 0.0)
        self.assertIn("no participó", res["motivo"])

    def test_jugador_con_cero_minutos_es_push(self):
        """Si el jugador estuvo en el roster pero jugó 0.0 minutos, se marca como PUSH."""
        prop_cero_min = {
            "player_name": "Emoni Bates",
            "player_clean": "Emoni Bates",
            "market": "Total Points",
            "line": 4.5,
            "pick_type": "OVER",
            "pick_odds_decimal": 1.91,
        }
        res = liquidar_prop_nba(prop_cero_min, self.boxscore, partido_finalizado=True)
        self.assertEqual(res["resultado"], "PUSH")
        self.assertEqual(res["unidades_ganadas"], 0.0)
        self.assertIn("0 minutos", res["motivo"])

    def test_jugador_activo_que_supera_linea_es_ganada(self):
        """Si Donovan Mitchell supera su línea de puntos, el pick es GANADA."""
        prop_mitchell = {
            "player_name": "Donovan Mitchell",
            "player_clean": "Donovan Mitchell",
            "market": "Total Points",
            "line": 25.5,
            "pick_type": "OVER",
            "pick_odds_decimal": 1.91,
        }
        res = liquidar_prop_nba(prop_mitchell, self.boxscore, partido_finalizado=True)
        self.assertEqual(res["resultado"], "GANADA")
        self.assertAlmostEqual(res["unidades_ganadas"], 0.91)
        self.assertEqual(res["valor_real"], 28.0)

    def test_jugador_activo_que_no_supera_linea_es_perdida(self):
        """Si Evan Mobley no supera su línea de triples, es PERDIDA con -1 unidad."""
        prop_mobley = {
            "player_name": "Evan Mobley",
            "player_clean": "Evan Mobley",
            "market": "Total Triples",
            "line": 0.5,
            "pick_type": "OVER",
            "pick_odds_decimal": 2.10,
        }
        res = liquidar_prop_nba(prop_mobley, self.boxscore, partido_finalizado=True)
        self.assertEqual(res["resultado"], "PERDIDA")
        self.assertEqual(res["unidades_ganadas"], -1.0)
        self.assertEqual(res["valor_real"], 0.0)

    def test_partido_no_finalizado_permanece_pendiente(self):
        """Si el partido aún está en juego, el pick debe permanecer PENDIENTE."""
        prop = {
            "player_name": "Donovan Mitchell",
            "market": "Total Points",
            "line": 25.5,
        }
        res = liquidar_prop_nba(prop, self.boxscore, partido_finalizado=False)
        self.assertEqual(res["resultado"], "PENDIENTE")
        self.assertIsNone(res["unidades_ganadas"])

    def test_core_devoluciones_soporta_nba(self):
        """Verifica que el libro universal de devoluciones aplique correctamente a picks NBA."""
        refunds = [{
            "deporte": "NBA",
            "id_juego": "401909944",
            "id_jugador": "Jarrett Allen",
            "mercado": "Total Points",
            "motivo": "Jugador inactivo (DNP confirmado)",
        }]
        frame = pd.DataFrame([{
            "deporte": "NBA",
            "identidad": "401909944|Jarrett Allen|Total Points",
            "resultado": "PENDIENTE",
            "unidades": float("nan"),
        }])
        resultado = apply_refunds(frame, refunds, sport="NBA")
        self.assertEqual(resultado["resultado"].iloc[0], "PUSH")
        self.assertEqual(resultado["unidades"].iloc[0], 0.0)
        self.assertEqual(resultado["motivo_devolucion"].iloc[0], "Jugador inactivo (DNP confirmado)")


if __name__ == "__main__":
    unittest.main()

