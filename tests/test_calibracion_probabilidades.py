import unittest
import numpy as np
import pandas as pd
from core.calibracion_probabilidades import (
    calibrar_probabilidad,
    calcular_ev_calibrado,
    parsear_cuota_decimal,
    calibrar_probabilidades_1x2,
    calibrar_probabilidades_2way,
)


class TestCalibracionProbabilidades(unittest.TestCase):
    def test_shrinkage_alta_probabilidad(self):
        # Una probabilidad extrema (ej 88%) con cuota moderada (ej 1.50) debe contraerse
        p_cal = calibrar_probabilidad(0.88, cuota=1.50)
        self.assertLess(p_cal, 0.88)
        self.assertLessEqual(p_cal, 0.78)
        self.assertGreaterEqual(p_cal, 0.65)

    def test_conservacion_probabilidades_intermedias(self):
        p_cal = calibrar_probabilidad(0.55, cuota=1.91)
        self.assertAlmostEqual(p_cal, 0.55, delta=0.03)

    def test_market_edge_cap(self):
        # La probabilidad calibrada no debe exceder implícita + 12%
        p_impl = 1.0 / 2.0  # 50%
        p_cal = calibrar_probabilidad(0.80, cuota=2.0)
        self.assertLessEqual(p_cal, p_impl + 0.12 + 1e-5)

    def test_calcular_ev_calibrado(self):
        ev = calcular_ev_calibrado(0.60, cuota=2.0)
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

    def test_calibrar_probabilidades_2way_simplex(self):
        # En mercado 2-way (NBA/MLB ML), las probabilidades deben sumar exactamente 1.0
        ph, pa = calibrar_probabilidades_2way(0.75, 0.25)
        self.assertAlmostEqual(ph + pa, 1.0, places=3)
        self.assertGreater(ph, 0.70)
        self.assertLess(ph, 0.75)
        self.assertGreater(ph, pa)


if __name__ == "__main__":
    unittest.main()
