"""Compatibilidad con la API pública anterior."""
import sys
import core.application.nfl_predictions as _implementation
sys.modules[__name__] = _implementation
