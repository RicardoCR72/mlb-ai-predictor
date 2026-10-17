"""Contexto descriptivo anterior al pick, con mercado, versión y reloj verificables."""
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from core.db import get_db_connection
from core.confianza import prepare,VERIFIED

MARKETS={'receiving_yards':'Yardas de recepción','receptions':'Recepciones','rushing_yards':'Yardas terrestres',
         'passing_yards':'Yardas por pase','passing_tds':'Pases de touchdown','anytime_td':'Anota touchdown'}


@st.cache_data(ttl=300,show_spinner=False)
def load_history():
    conn=None
    try:
        from core.confianza_datos import read_confidence
        conn=get_db_connection()
        frame,_=read_confidence(conn,Path(__file__).resolve().parents[1])
        if not frame.empty:
            frame['evento']=[str(r.identidad).split('|')[0] if r.deporte=='NFL' else str(r.identidad) for r in frame.itertuples()]
        return prepare(frame)[0]
    except Exception:return pd.DataFrame()
    finally:
        if conn is not None:conn.close()


def context(pick,history):
    empty=dict(status='insuficiente',n=0,games=0,rate=None,band=None)
    version=pick.get('modelo');market=pick.get('mercado_confianza');p=pick.get('probabilidad')
    try:
        p=float(p);day=pd.Timestamp(pick['fecha'])
        day=(day.tz_convert('America/Mexico_City') if day.tzinfo else day).date()
        if pd.isna(day) or not np.isfinite(p) or not 0<=p<=1 or not version or not market:return empty
        if pick.get('origen')=='mlb_total':
            push=float(pick['p_push'])
            if not np.isfinite(push) or not 0<=push<1:return empty
            p=p/(1-push)
            if p>1:return empty
    except (TypeError,ValueError,KeyError):return empty
    if history.empty:return empty
    required=['fecha','deporte','mercado','modelo','procedencia','probabilidad','y','evento','identidad']
    if not all(c in history for c in required):return empty
    f=history[(history.deporte==pick['deporte'])&(history.modelo==str(version))&
        (history.mercado==MARKETS.get(market,market))&(history.procedencia==VERIFIED)].copy()
    if f.empty:return empty
    def local_day(value):
        stamp=pd.to_datetime(value,errors='coerce')
        if pd.isna(stamp):return None
        return (stamp.tz_convert('America/Mexico_City') if stamp.tzinfo else stamp).date()
    dates=f.fecha.map(local_day)
    f=f[dates.map(lambda value:value is not None and value<day)]
    game=str(pick.get('referencia',{}).get('game_id',''))
    if game:f=f[f.identidad.astype(str).str.split('|').str[0].ne(game)]
    if 'apto_ajuste' in f:f=f[~f.apto_ajuste.astype(str).str.lower().eq('false')]
    band=min(int(p*10),9)
    values=pd.to_numeric(f.probabilidad,errors='coerce')
    f=f[np.floor(values*10).clip(upper=9).eq(band)]
    n=len(f);games=f.evento.nunique()
    return dict(status='disponible' if n>=100 and games>=30 else 'insuficiente',n=n,games=int(games),
                rate=float(f.y.mean()) if n else None,band=f'{band*10}–{(band+1)*10}%',conditional=pick.get('origen')=='mlb_total')


def for_pick(pick):
    if not isinstance(pick.get('modelo'),str) or not pick['modelo'].strip() or not isinstance(pick.get('mercado_confianza'),str):
        return context(pick,pd.DataFrame())
    return context(pick,load_history())


def text(record):
    if record['status']!='disponible':
        return 'Muestra insuficiente'+(f" · {record['n']} picks anteriores en este rango" if record['n'] else ' · sin historial comparable verificado')
    kind='Histórico sin push' if record.get('conditional') else 'Histórico comparable'
    return f"{kind}: {record['rate']:.1%} de acierto · {record['n']} picks / {record['games']} partidos · rango {record['band']}. No garantiza el próximo resultado."
