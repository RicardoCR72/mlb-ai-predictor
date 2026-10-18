"""Lecturas CSV versionadas por modificación, sin escrituras de la interfaz."""
from pathlib import Path
import pandas as pd
import streamlit as st


@st.cache_data(ttl=300,max_entries=12)
def _read(path,mtime):
    frame=pd.read_csv(path)
    frame['fecha']=pd.to_datetime(frame['fecha'])
    return frame


def read_games(path):
    path=Path(path)
    if not path.exists():return pd.DataFrame()
    return _read(str(path),path.stat().st_mtime_ns)
