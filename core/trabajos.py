"""Compatibilidad pública para el servicio de trabajos."""
import sys
from core.application import jobs as _implementation
sys.modules[__name__] = _implementation
