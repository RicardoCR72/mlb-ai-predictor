"""Horas oficiales NFL, sin importar modelos ni funciones retiradas."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

def nfl_starts(root):
    result={}
    try:
        calendar=pd.read_parquet(Path(root)/'data/nfl/raw/nfl_schedules_2012_2026.parquet',
                                 columns=['game_id','gameday','gametime'])
        for row in calendar.to_dict('records'):
            try:
                if pd.isna(row['gametime']):continue
                start=datetime.fromisoformat(str(pd.Timestamp(row['gameday']).date())+'T'+str(row['gametime']))
                result[str(row['game_id'])]=start.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
            except (TypeError,ValueError):continue
    except (OSError,ValueError,KeyError,ImportError):pass
    return result
