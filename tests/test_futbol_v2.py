"""Tests unitarios para el Motor Cuantitativo Dixon-Coles Fútbol V2."""
import unittest
import numpy as np
from futbol.modelo_futbol import (
    desparasitar_cuotas_1x2,
    desparasitar_cuotas_totales,
    construir_matriz_dixon_coles,
    estimar_xg_partido,
    proyectar_partido_futbol,
    calcular_ev,
)
from futbol.predecir_jornada import (
    liquidar_seleccion_futbol,
    es_partido_en_curso,
    es_partido_finalizado,
)


class TestFutbolV2(unittest.TestCase):
    def test_desparasitar_cuotas(self):
        h, d, a = desparasitar_cuotas_1x2(0.50, 0.30, 0.30)
        self.assertAlmostEqual(h + d + a, 1.0, places=2)
        self.assertGreater(h, d)

        o, u = desparasitar_cuotas_totales(0.55, 0.55)
        self.assertAlmostEqual(o + u, 1.0, places=2)
        self.assertEqual(o, 0.5)

    def test_matriz_dixon_coles(self):
        lam, mu, rho = 1.45, 1.15, -0.115
        grid = construir_matriz_dixon_coles(lam, mu, rho=rho, max_goles=10)

        # Matriz debe sumar 1.0
        self.assertAlmostEqual(float(np.sum(grid)), 1.0, places=4)

        # Probabilidad de empate Dixon-Coles debe ser mayor que el Poisson puro
        from scipy.stats import poisson
        g_indep = np.outer(
            [poisson.pmf(i, lam) for i in range(10)],
            [poisson.pmf(j, mu) for j in range(10)]
        )
        g_indep /= np.sum(g_indep)

        prob_draw_dc = float(np.sum(np.diag(grid)))
        prob_draw_indep = float(np.sum(np.diag(g_indep)))

        self.assertGreater(prob_draw_dc, prob_draw_indep)
        self.assertGreater(grid[0, 0], g_indep[0, 0])
        self.assertGreater(grid[1, 1], g_indep[1, 1])

    def test_proyectar_partido_futbol(self):
        partido = {
            "liga_codigo": "eng.1",
            "equipo_local": "Arsenal",
            "equipo_visita": "Chelsea",
            "linea_total": 2.5,
            "ml_local_prob": 0.55,
            "ml_empate_prob": 0.25,
            "ml_visita_prob": 0.25,
            "over_prob_implicita": 0.53,
            "under_prob_implicita": 0.51,
            "ml_local_dec": 1.75,
            "ml_empate_dec": 3.70,
            "ml_visita_dec": 4.50,
            "over_momio_dec": 1.90,
            "under_momio_dec": 1.95,
        }
        proj = proyectar_partido_futbol(partido)

        self.assertIn("xg_local", proj)
        self.assertIn("xg_visita", proj)
        self.assertIn("prob_local", proj)
        self.assertIn("prob_empate", proj)
        self.assertIn("prob_visita", proj)
        self.assertIn("prob_btts_si", proj)
        self.assertIn("prob_1x", proj)
        self.assertIn("prob_x2", proj)
        self.assertIn("pick_ev", proj)

        # Probabilidades 1X2 deben sumar 1.0
        suma_1x2 = proj["prob_local"] + proj["prob_empate"] + proj["prob_visita"]
        self.assertAlmostEqual(suma_1x2, 1.0, places=2)

        # 1X debe ser prob_local + prob_empate
        self.assertAlmostEqual(proj["prob_1x"], proj["prob_local"] + proj["prob_empate"], places=3)

    def test_liquidaciones_mercados(self):
        # 1. Ambos Anotan (BTTS)
        res_si, u_si = liquidar_seleccion_futbol("Ambos Anotan", "Ambos Anotan: SÍ", 2.5, 1.80, 2, 1, "Arsenal", "Chelsea")
        self.assertEqual(res_si, "GANADA")
        self.assertAlmostEqual(u_si, 0.80)

        res_no, u_no = liquidar_seleccion_futbol("Ambos Anotan", "Ambos Anotan: SÍ", 2.5, 1.80, 2, 0, "Arsenal", "Chelsea")
        self.assertEqual(res_no, "PERDIDA")
        self.assertEqual(u_no, -1.0)

        # 2. Doble Oportunidad
        res_1x, u_1x = liquidar_seleccion_futbol("Doble Oportunidad", "1X (Arsenal o Empate)", 2.5, 1.45, 1, 1, "Arsenal", "Chelsea")
        self.assertEqual(res_1x, "GANADA")
        self.assertAlmostEqual(u_1x, 0.45)

        # 3. Draw No Bet (DNB)
        res_dnb, u_dnb = liquidar_seleccion_futbol("DNB", "Arsenal DNB", 2.5, 1.60, 1, 1, "Arsenal", "Chelsea")
        self.assertEqual(res_dnb, "PUSH")
        self.assertEqual(u_dnb, 0.0)

        # 4. Totales
        res_ov, u_ov = liquidar_seleccion_futbol("Totales", "OVER 2.5 Goles", 2.5, 1.90, 2, 1, "Arsenal", "Chelsea")
        self.assertEqual(res_ov, "GANADA")
        self.assertAlmostEqual(u_ov, 0.90)

    def test_deteccion_estados(self):
        self.assertTrue(es_partido_finalizado("STATUS_FULL_TIME"))
        self.assertTrue(es_partido_finalizado("STATUS_FINAL"))
        self.assertTrue(es_partido_en_curso("STATUS_IN_PROGRESS"))
        self.assertFalse(es_partido_finalizado("STATUS_IN_PROGRESS"))
        self.assertFalse(es_partido_finalizado("STATUS_SCHEDULED"))


if __name__ == "__main__":
    unittest.main()
