"""Pruebas unitarias para validar que los colores de selecciones OVER (verde) y UNDER (azul) no se mezclen por dígitos en las líneas."""
import unittest
from core.ui_tarjeta_universal import _color_por_seleccion


class TestColoresPick(unittest.TestCase):
    def test_todos_los_under_son_azules(self):
        """Cualquier línea UNDER, incluso aquellas que contienen los dígitos '1' o '2', debe ser azul."""
        lineas_under = [
            "UNDER 0.5",
            "UNDER 1.5",
            "UNDER 4.5",
            "UNDER 10.5",
            "UNDER 11.5",
            "UNDER 12.5",
            "UNDER 14.5",
            "UNDER 16.5",
            "UNDER 19.5",
            "UNDER 20.5",
            "UNDER 21.5",
            "Menos de 2.5",
        ]
        for sel in lineas_under:
            with self.subTest(sel=sel):
                color = _color_por_seleccion(sel)
                self.assertEqual(color, "#3B82F6", f"Se esperaba azul (#3B82F6) para '{sel}', pero se obtuvo '{color}'")

    def test_todos_los_over_son_verdes(self):
        """Cualquier línea OVER, incluso aquellas con '2' o '1', debe ser verde."""
        lineas_over = [
            "OVER 0.5",
            "OVER 1.5",
            "OVER 2.5",
            "OVER 3.5",
            "OVER 4.5",
            "OVER 14.5",
            "OVER 21.5",
            "Más de 2.5",
        ]
        for sel in lineas_over:
            with self.subTest(sel=sel):
                color = _color_por_seleccion(sel)
                self.assertEqual(color, "#10B981", f"Se esperaba verde (#10B981) para '{sel}', pero se obtuvo '{color}'")

    def test_futbol_1x2_colores(self):
        """Verifica que el mercado 1X2 conserve sus colores semánticos sin colisionar."""
        self.assertEqual(_color_por_seleccion("1"), "#10B981")
        self.assertEqual(_color_por_seleccion("Local"), "#10B981")
        self.assertEqual(_color_por_seleccion("2"), "#3B82F6")
        self.assertEqual(_color_por_seleccion("Visita"), "#3B82F6")
        self.assertEqual(_color_por_seleccion("X"), "#8B5CF6")
        self.assertEqual(_color_por_seleccion("Empate"), "#8B5CF6")


if __name__ == "__main__":
    unittest.main()

