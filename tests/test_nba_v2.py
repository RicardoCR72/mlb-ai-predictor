"""Tests unitarios para el Motor Cuantitativo NBA V2 (Ensamble Spread/ML y Totales)."""
import unittest
import joblib
from pathlib import Path
import pandas as pd

from nba.entrenar_spread_ml import proyectar_partido_spread, RUTA_MODELOS as RUTA_MOD_SPREAD
from nba.entrenar_totales import proyectar_partido_totales, RUTA_MODELOS as RUTA_MOD_TOTALES
from nba.predecir_hoy import cargar_perfiles_recientes_equipos, RUTA_MODELO_SPREAD, RUTA_MODELO_TOTALES
from nba.registro import liquidar_partido, _es_seleccion_local


class TestNbaV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle_sp = joblib.load(RUTA_MODELO_SPREAD)
        cls.bundle_tot = joblib.load(RUTA_MODELO_TOTALES)

    def test_ensamble_spread_ml(self):
        feats = {c: 0.0 for c in self.bundle_sp["features"]}
        feats["DIFF_NET_RTG_L10"] = 4.5
        feats["DIFF_ORTG_L10"] = 3.2
        feats["HOME_WIN_L10"] = 0.7
        feats["AWAY_WIN_L10"] = 0.4

        res = proyectar_partido_spread(self.bundle_sp, feats, spread_line=-4.5)

        self.assertIn("margen_local_esperado", res)
        self.assertIn("prob_local_win", res)
        self.assertIn("prob_visita_win", res)
        self.assertIn("prob_cover_home", res)
        self.assertIn("prob_cover_away", res)

        # Probabilidades deben sumar 1.0
        self.assertAlmostEqual(res["prob_local_win"] + res["prob_visita_win"], 1.0, places=3)
        self.assertAlmostEqual(res["prob_cover_home"] + res["prob_cover_away"], 1.0, places=3)
        self.assertGreater(res["prob_local_win"], 0.50)

    def test_ensamble_totales_shrinkage(self):
        feats = {c: 0.0 for c in self.bundle_tot["features"]}
        feats["PACE_PROYECTADO_L10"] = 101.5
        feats["HOME_PTS_L10"] = 118.0
        feats["AWAY_PTS_L10"] = 116.0
        feats["HOME_ORTG_L10"] = 116.0
        feats["AWAY_ORTG_L10"] = 115.0

        linea_mercado = 232.5
        res = proyectar_partido_totales(self.bundle_tot, feats, linea_total=linea_mercado)

        self.assertIn("total_proyectado", res)
        self.assertIn("prob_over", res)
        self.assertIn("prob_under", res)
        self.assertIn("recomendacion", res)

        self.assertAlmostEqual(res["prob_over"] + res["prob_under"], 1.0, places=3)
        # El total proyectado debe estar anclado razonablemente cerca de la línea del mercado
        self.assertGreater(res["total_proyectado"], 220.0)
        self.assertLess(res["total_proyectado"], 245.0)

    def test_regresion_perfiles_recientes(self):
        perfiles = cargar_perfiles_recientes_equipos()
        self.assertIn("BOS", perfiles)
        self.assertIn("LAL", perfiles)

        bos_pace = perfiles["BOS"]["PACE_L10"]
        # Debe haber sido regresionado hacia la media de regular season (~100.2)
        # y no estar en el mínimo de playoffs (~92.8)
        self.assertGreater(bos_pace, 95.0)

    def test_liquidaciones_nba(self):
        # Totales Over
        fila_over = pd.Series({
            "mercado": "Totales (OVER)",
            "seleccion": "OVER 225.5",
            "linea": 225.5,
            "cuota": 1.91,
            "marcador_local": 118,
            "marcador_visitante": 115,
        })
        res, u = liquidar_partido(fila_over)
        self.assertEqual(res, "GANADA")
        self.assertAlmostEqual(u, 0.91, places=2)

        # Moneyline
        fila_ml = pd.Series({
            "mercado": "Moneyline",
            "seleccion": "Boston Celtics ML",
            "equipo_local": "Boston Celtics",
            "equipo_visitante": "New York Knicks",
            "cuota": 1.70,
            "marcador_local": 112,
            "marcador_visitante": 104,
        })
        res_ml, u_ml = liquidar_partido(fila_ml)
        self.assertEqual(res_ml, "GANADA")
        self.assertAlmostEqual(u_ml, 0.70, places=2)

        # Spread
        fila_sp = pd.Series({
            "mercado": "Spread",
            "seleccion": "Boston Celtics -5.5",
            "equipo_local": "Boston Celtics",
            "equipo_visitante": "New York Knicks",
            "linea": -5.5,
            "cuota": 1.91,
            "marcador_local": 112,
            "marcador_visitante": 104,  # Margen +8 > 5.5
        })
        res_sp, u_sp = liquidar_partido(fila_sp)
        self.assertEqual(res_sp, "GANADA")
        self.assertAlmostEqual(u_sp, 0.91, places=2)

        # Spread Underdog (+5.5) cubre la línea en derrota cerrada (ej. 109 - 114)
        fila_sp_underdog = pd.Series({
            "mercado": "Spread",
            "seleccion": "Indiana Pacers +5.5",
            "equipo_local": "Indiana Pacers",
            "equipo_visitante": "Philadelphia 76ers",
            "linea": 5.5,
            "cuota": 1.909,
            "marcador_local": 109,
            "marcador_visitante": 114,
        })
        res_und, u_und = liquidar_partido(fila_sp_underdog)
        self.assertEqual(res_und, "GANADA")
        self.assertAlmostEqual(u_und, 0.909, places=3)

        # Partidos incompletos o en juego (0-0 o parcial <100 pts) NUNCA deben liquidarse
        fila_incompleta = pd.Series({
            "mercado": "Moneyline",
            "seleccion": "Boston Celtics ML",
            "equipo_local": "Boston Celtics",
            "equipo_visitante": "New York Knicks",
            "cuota": 1.70,
            "marcador_local": 0,
            "marcador_visitante": 0,
        })
        res_inc, u_inc = liquidar_partido(fila_incompleta)
        self.assertEqual(res_inc, "PENDIENTE")
        self.assertIsNone(u_inc)

        fila_cuarto = pd.Series({
            "mercado": "Moneyline",
            "seleccion": "Brooklyn Nets ML",
            "equipo_local": "Brooklyn Nets",
            "equipo_visitante": "Indiana Pacers",
            "cuota": 1.91,
            "marcador_local": 26,
            "marcador_visitante": 24,
        })
        res_q, u_q = liquidar_partido(fila_cuarto)
        self.assertEqual(res_q, "PENDIENTE")
        self.assertIsNone(u_q)

    def test_desambiguacion_equipos_ciudad(self):
        """Verifica que equipos que comparten ciudad/estado no colisionen en la selección."""
        # Lakers vs Clippers (ambos comparten 'Los Angeles')
        self.assertTrue(_es_seleccion_local("Los Angeles Lakers -3.5", "Los Angeles Lakers", "Los Angeles Clippers"))
        self.assertFalse(_es_seleccion_local("Los Angeles Clippers +3.5", "Los Angeles Lakers", "Los Angeles Clippers"))
        self.assertTrue(_es_seleccion_local("Lakers ML", "Los Angeles Lakers", "Los Angeles Clippers"))
        self.assertFalse(_es_seleccion_local("Clippers ML", "Los Angeles Lakers", "Los Angeles Clippers"))

        # Nets vs Knicks (ambos en New York)
        self.assertTrue(_es_seleccion_local("Brooklyn Nets ML", "Brooklyn Nets", "New York Knicks"))
        self.assertFalse(_es_seleccion_local("New York Knicks ML", "Brooklyn Nets", "New York Knicks"))

    def test_moneyline_sin_cuotas_bookmaker(self):
        """Verifica que obtener_pick_para_mercado maneje sin errores momios faltantes o None de ESPN."""
        import importlib.util
        page_path = Path(__file__).resolve().parents[1] / "pages" / "4_🏀_NBA.py"
        spec = importlib.util.spec_from_file_location("nba_page", page_path)
        nba_page = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nba_page)

        partido_sin_cuotas = {
            "equipo_local": "Los Angeles Lakers",
            "equipo_visita": "Los Angeles Clippers",
            "prob_local_win": 0.65,
            "prob_visita_win": 0.35,
            "ml_local": None,
            "ml_visita": None,
            "ml_local_dec": None,
            "ml_visita_dec": None,
        }
        pick = nba_page.obtener_pick_para_mercado(partido_sin_cuotas, "Moneyline (ML)")
        self.assertIsNotNone(pick)
        self.assertIn("seleccion", pick)
        self.assertIsInstance(pick["edge"], float)
        self.assertIsInstance(pick["ev"], float)
        self.assertGreater(pick["ev"], 0.0)


if __name__ == "__main__":
    unittest.main()
