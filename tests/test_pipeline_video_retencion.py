"""Pruebas unitarias para el pipeline de video de alta retención (sin FFmpeg ni APIs)."""
from __future__ import annotations

from PIL import Image

from core.pipeline_video_retencion import (
    generar_guion_fallback_con_reglas,
    generar_tarjetas_revelacion,
    limpiar_texto_para_imagen,
)


PALABRAS_PROHIBIDAS = [
    "apuesta",
    "apuestas",
    "apostar",
    "parlay",
    "momio",
    "cuotas",
    "cuota",
    "dinero",
    "dólares",
    "lock",
    "fija",
    "bank",
    "stake",
    "casino",
    "bookie",
]


def test_guion_fallback_cumple_longitud_y_vocabulario():
    """El guion determinista debe tener 38-45 palabras y evitar todo vocabulario prohibido."""
    datos = {
        "jugador": "Nikola Jokic",
        "equipo": "DEN",
        "rival": "DAL @ DEN",
        "mercado": "TOTAL REBOTES",
        "linea": "11.5",
        "tipo_pick": "Under",
        "proyeccion": "10.4",
    }
    guion = generar_guion_fallback_con_reglas(datos)
    palabras = guion.split()
    assert 38 <= len(palabras) <= 45, f"Longitud fuera de rango: {len(palabras)} palabras -> {guion}"
    guion_low = guion.lower()
    for prohibida in PALABRAS_PROHIBIDAS:
        assert prohibida not in guion_low, f"Contiene término prohibido: {prohibida}"
    assert guion.endswith("?")


def test_limpiar_texto_para_imagen_quita_emojis():
    """Debe remover emojis y símbolos sin glifo para evitar cuadros blancos."""
    limpio = limpiar_texto_para_imagen("⚡ 🔒 ANOMALÍA DETECTADA 🏀 4 DE 5 🔥")
    assert "⚡" not in limpio
    assert "🔒" not in limpio
    assert "🏀" not in limpio
    assert "🔥" not in limpio
    assert "ANOMALÍA DETECTADA" in limpio


def test_generar_tarjetas_revelacion_crea_pngs(tmp_path):
    """Debe generar ambas tarjetas (teaser y reveal) con dimensiones 1000x480 válidas."""
    datos = {
        "deporte": "NBA · BASKETBALL",
        "fecha_str": "JUEVES 26 DE NOVIEMBRE 2026",
        "jugador": "Nikola Jokic",
        "equipo": "DEN",
        "mercado": "TOTAL REBOTES",
        "linea": "11.5",
        "tipo_pick": "Under",
        "proyeccion": "10.4",
        "ventaja": "-1.1 Reb",
        "racha_texto": "⚡ 4 DE SUS ÚLTIMOS 5 POR DEBAJO",
        "promedio_texto": "PROYECCIÓN: 10.4",
    }
    p_teaser = str(tmp_path / "teaser.png")
    p_reveal = str(tmp_path / "reveal.png")

    r1, r2 = generar_tarjetas_revelacion(datos, p_teaser, p_reveal)
    assert r1 == p_teaser and r2 == p_reveal

    with Image.open(p_teaser) as im1, Image.open(p_reveal) as im2:
        assert im1.size == (1000, 480)
        assert im2.size == (1000, 480)
