"""Vigencia de cuotas y protección de recapturas por evento."""
from datetime import datetime, timezone
import pandas as pd

MAX_AGE_MINUTES = 120


def fresh_quotes(frame, now=None, max_age_minutes=MAX_AGE_MINUTES):
    if frame.empty:
        return frame.copy()
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    stamps = pd.to_datetime(frame['timestamp_captura'], utc=True, errors='coerce')
    age = (now - stamps).dt.total_seconds() / 60
    return frame[age.between(0, max_age_minutes)].copy()
