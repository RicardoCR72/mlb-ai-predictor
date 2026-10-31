import unittest
import numpy as np
import pandas as pd
from core.calibracion_probabilidades import calibrar_probabilidad, calcular_ev_calibrado, parsear_cuota_decimal, calibrar_probabilidades_1x2


class TestCalibracionProbabilidades(unittest.TestCase):
    def test_parsear_cuotas(self):
        self.assertAlmostEqual(parsear_cuota_decimal(1.91), 1.91)
        self.assertAlmostEqual(parsear_cuota_decimal("-110"), 1.9090909, places=4)
        self.assertAlmostEqual(parsear_cuota_decimal("+150"), 2.50)
        self.assertIsNone(parsear_cuota_decimal(None))
        self.assertIsNone(parsear_cuota_decimal(0.5))

    def test_shrinkage_on_extreme_probability(self):
        # 95% raw probability on -110 odds must be shrunk to around 68-75%
        p_cal = calibrar_probabilidad(0.95, cuota=1.91)
        self.assertLess(p_cal, 0.76)
        self.assertGreater(p_cal, 0.60)

    def test_moderate_probability_remains_near_55(self):
        # 55% raw probability remains around 53-56%
        p_cal = calibrar_probabilidad(0.55, cuota=1.91)
        self.assertAlmostEqual(p_cal, 0.548, places=2)

    def test_series_support(self):
        s = pd.Series([0.55, 0.92])
        c = pd.Series([1.91, 1.91])
        res = calibrar_probabilidad(s, c)
        self.assertEqual(len(res), 2)
        self.assertLess(res.iloc[1], 0.72)

    def test_ev_calculation(self):
        ev = calcular_ev_calibrado(0.60, 2.0)
        self.assertAlmostEqual(ev, 0.20, places=2)

    def test_underdog_no_phantom_inflation(self):
        # Un underdog de 16% con cuota 4.10 (+310, impl ~24.4%) no debe inflarse a 40%+ ni generar edge positivo
        p_cal = calibrar_probabilidad(0.163, cuota=4.10)
        self.assertLessEqual(p_cal, 0.244)
        self.assertAlmostEqual(p_cal, 0.163, places=3)
        # El EV debe ser estrictamente negativo
        ev = calcular_ev_calibrado(p_cal, 4.10)
        self.assertLess(ev, 0.0)


    def test_calibrar_probabilidades_1x2_simplex(self):
        # En mercado 1X2, las probabilidades deben sumar exactamente 1.0 (símplex)
        ph, pd, pa = calibrar_probabilidades_1x2(0.75, 0.16, 0.09)
        self.assertAlmostEqual(ph + pd + pa, 1.0, places=3)
        # El favorito de 75% debe ser suavizado levemente sin destruirse a 60%
        self.assertGreater(ph, 0.70)
        self.assertLess(ph, 0.75)
        # El orden jerárquico debe respetarse
        self.assertGreater(ph, pd)
        self.assertGreater(pd, pa)

if __name__ == "__main__":
    unittest.main()
