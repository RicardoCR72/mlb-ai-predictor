"""Compatibilidad con la API pública anterior."""
import sys
import core.infrastructure.database as _implementation
sys.modules[__name__] = _implementation
