import unittest
import numpy as np
import pandas as pd
from core.calibracion_probabilidades import calibrar_probabilidad, calcular_ev_calibrado, parsear_cuota_decimal


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


if __name__ == "__main__":
    unittest.main()
