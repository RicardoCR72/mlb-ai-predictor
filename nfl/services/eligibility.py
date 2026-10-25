"""Elegibilidad prepartido compartida por las vistas NFL."""
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from nfl.persistence.calendar import nfl_starts


def upcoming(frame, now=None):
    if frame.empty:
        return frame.copy()
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    result = frame.copy()
    starts = nfl_starts(Path(__file__).resolve().parents[2])
    if 'inicio_utc' in result:
        values = pd.to_datetime(result.inicio_utc, utc=True, errors='coerce')
    else:
        values = pd.to_datetime(result.id_juego.astype(str).map(starts), utc=True, errors='coerce')
    result['inicio_utc'] = values
    states = result.resultado_pick.fillna('PENDIENTE').astype(str).str.strip().str.upper()
    return result[values.gt(now) & ~states.isin(['GANADA','PERDIDA','PUSH'])].copy()
