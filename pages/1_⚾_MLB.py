import os
import html
import streamlit as st
import pandas as pd
import numpy as np
import mysql.connector
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Input
import joblib
import warnings
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import sys
warnings.filterwarnings('ignore')

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

RUTA_MODELOS_MLB = RAIZ / "modelos_mlb"
RUTA_DATA_MLB = RAIZ / "data" / "mlb"

from core.constants import ZONA_MX, MLB_TEAMS_ABBR, MLB_STADIUM_TIMEZONES
from core.db import get_db_connection

def hoy_mx():
    return datetime.now(ZONA_MX).date()

st.set_page_config(page_title="MLB Oráculo", page_icon="⚾", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 85% 0%, rgba(183,255,60,.055), transparent 28rem),
            #080c13;
        color: #eef3f8;
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container {
        max-width: 1480px;
        padding-top: 1.15rem;
        padding-bottom: 2.5rem;
    }
    [data-testid="stSidebar"] {
        background: #0d131d;
        border-right: 1px solid #202938;
    }
    .mlb-shell {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #202938;
        border-radius: 13px;
        background: #111720;
        margin-bottom: .75rem;
    }
    .mlb-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .mlb-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #b7ff3c;
        color: #071006;
        font-weight: 900;
    }
    .mlb-accent { color: #b7ff3c; }
    .mlb-status { color: #8e99a9; font-size: .78rem; }
    .mlb-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: 1.1rem 0 1.25rem;
    }
    .mlb-eyebrow {
        color: #b7ff3c;
        font-size: .72rem;
        font-weight: 850;
        letter-spacing: .12em;
    }
    .mlb-hero h1 {
        margin: .22rem 0 .2rem;
        color: #f5f8fb;
        font-size: clamp(1.9rem, 3.2vw, 2.65rem);
    }
    .mlb-subtitle { color: #8994a5; font-size: .9rem; }
    .mlb-live {
        display: inline-flex;
        align-items: center;
        gap: .45rem;
        padding: .42rem .7rem;
        border: 1px solid #263143;
        border-radius: 999px;
        background: #111720;
        color: #b8c2cf;
        font-size: .75rem;
        white-space: nowrap;
    }
    .mlb-live-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #b7ff3c;
        box-shadow: 0 0 0 4px rgba(183,255,60,.1);
    }
    div[role="radiogroup"] {
        display: flex;
        gap: .4rem;
        width: fit-content;
        max-width: 100%;
        padding: .35rem;
        margin-bottom: 1rem;
        border: 1px solid #202938;
        border-radius: 11px;
        background: #0d131d;
    }
    div[role="radiogroup"] label {
        flex: 1;
        justify-content: center;
        padding: .42rem .8rem;
        border-radius: 8px;
    }
    div[role="radiogroup"] label:has(input:checked) {
        background: #b7ff3c;
        color: #071006;
        font-weight: 850;
    }
    div[data-testid="stMetric"] {
        background: #111720;
        border: 1px solid #202938;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8994a5; }
    div[data-testid="stMetricValue"] { color: #f4f7fb; }
    .mlb-pick-card, .mlb-best-card, .mlb-roi-card {
        position: relative;
        overflow: hidden;
        min-height: 100%;
        padding: 1rem;
        border: 1px solid #263143;
        border-radius: 12px;
        background: linear-gradient(145deg, #121a25, #0e141e);
        box-shadow: 0 12px 28px rgba(0,0,0,.13);
    }
    .mlb-pick-card::before, .mlb-best-card::before, .mlb-roi-card::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 4px;
        background: #b7ff3c;
    }
    .mlb-card-kicker {
        color: #b7ff3c;
        font-size: .64rem;
        font-weight: 850;
        letter-spacing: .1em;
    }
    .mlb-card-title {
        margin-top: .25rem;
        color: #f5f8fb;
        font-size: 1.08rem;
        font-weight: 850;
    }
    .mlb-card-meta { margin-top: .22rem; color: #8e99a9; font-size: .76rem; }
    .mlb-pick-line {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: .7rem;
        margin: .9rem 0;
    }
    .mlb-pick-name { color: #fff; font-size: 1.12rem; font-weight: 900; }
    .mlb-odds {
        padding: .27rem .48rem;
        border-radius: 7px;
        background: #1b2431;
        color: #b7ff3c;
        font-size: .75rem;
        font-weight: 850;
    }
    .mlb-card-values {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .55rem;
        padding-top: .75rem;
        border-top: 1px solid #263143;
    }
    .mlb-value-label {
        display: block;
        color: #748095;
        font-size: .59rem;
        font-weight: 800;
        letter-spacing: .07em;
    }
    .mlb-value {
        display: block;
        margin-top: .18rem;
        color: #eef3f8;
        font-size: .84rem;
        font-weight: 750;
    }
    .mlb-confidence {
        height: 5px;
        overflow: hidden;
        margin-top: .8rem;
        border-radius: 999px;
        background: #253040;
    }
    .mlb-confidence span { display: block; height: 100%; background: #b7ff3c; }
    .mlb-audit-card {
        position: relative;
        overflow: hidden;
        min-height: 100%;
        padding: .9rem 1rem;
        border: 1px solid #263143;
        border-radius: 12px;
        background: #111720;
    }
    .mlb-audit-card::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 4px;
        background: #b7ff3c;
    }
    .mlb-audit-card.lost::before { background: #ff5d68; }
    .mlb-audit-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: .7rem;
    }
    .mlb-audit-date { color: #8994a5; font-size: .7rem; font-weight: 750; }
    .mlb-result-badge {
        padding: .22rem .5rem;
        border-radius: 999px;
        background: #183825;
        color: #b7ff3c;
        font-size: .65rem;
        font-weight: 850;
    }
    .mlb-result-badge.lost { background: #3b1d25; color: #ff7881; }
    .mlb-audit-match {
        margin-top: .55rem;
        color: #f2f6fa;
        font-size: .9rem;
        font-weight: 800;
    }
    .mlb-audit-pick { margin-top: .18rem; color: #a7b2c2; font-size: .76rem; }
    .mlb-audit-values {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .45rem;
        margin-top: .7rem;
        padding-top: .65rem;
        border-top: 1px solid #263143;
    }
    .mlb-profit-positive { color: #b7ff3c; }
    .mlb-profit-negative { color: #ff7881; }
    .mlb-empty {
        padding: 1.25rem;
        border: 1px dashed #334054;
        border-radius: 12px;
        background: #0f151e;
        color: #8994a5;
        text-align: center;
    }
    [data-testid="stDataFrame"] {
        overflow: hidden;
        border: 1px solid #263143;
        border-radius: 12px;
    }
    .stButton button, .stDownloadButton button, .stFormSubmitButton button {
        border: 1px solid #b7ff3c !important;
        border-radius: 9px !important;
        background: #111720 !important;
        color: #b7ff3c !important;
        font-weight: 800 !important;
    }
    .stButton button:hover, .stDownloadButton button:hover,
    .stFormSubmitButton button:hover {
        background: #b7ff3c !important;
        color: #071006 !important;
    }
    [data-testid="stSlider"] [role="slider"] {
        border-color: #b7ff3c !important;
        background: #b7ff3c !important;
    }
    [data-testid="stSlider"] [data-baseweb="slider"] > div > div {
        background-color: #b7ff3c !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    div[data-baseweb="select"] > div {
        border: 1px solid #b7ff3c !important;
        border-radius: 10px !important;
        background: #111720 !important;
        color: #eef3f8 !important;
        box-shadow: 0 0 0 1px rgba(183,255,60,.08) !important;
    }
    div[data-baseweb="select"] svg { fill: #b7ff3c !important; }
    [role="option"]:hover, [role="option"][aria-selected="true"] {
        background: #b7ff3c !important;
        color: #071006 !important;
        font-weight: 800 !important;
    }
    @media (max-width: 760px) {
        .mlb-status { display: none; }
        .mlb-hero { align-items: flex-start; flex-direction: column; }
        .mlb-card-values { grid-template-columns: 1fr 1fr; }
    }
    </style>
    <div class="mlb-shell">
        <div class="mlb-brand">
            <span class="mlb-logo">O</span>
            <span>ORACLE <span class="mlb-accent">MLB</span></span>
        </div>
        <div class="mlb-status">MONEYLINE · TOTALES · ABRIDORES · RENDIMIENTO</div>
    </div>
    <div class="mlb-hero">
        <div>
            <div class="mlb-eyebrow">MODELO + MERCADO + CONTEXTO</div>
            <h1>MLB Oráculo</h1>
            <div class="mlb-subtitle">Edge matemático, fatiga de viaje, splits, abridores y bullpen.</div>
        </div>
        <div class="mlb-live"><span class="mlb-live-dot"></span>Moneyline V4 · Totales V2</div>
    </div>
    """,
    unsafe_allow_html=True,
)


def html_seguro(valor):
    return html.escape(str(valor))


def mostrar_pick_mlb(fila):
    confianza = float(fila["Confianza (%)"])
    cuota = float(fila["Paga del Favorito"])
    st.markdown(
        f"""
        <div class="mlb-pick-card">
            <div class="mlb-card-kicker">PRONÓSTICO MLB</div>
            <div class="mlb-card-title">{html_seguro(fila['Partido'])}</div>
            <div class="mlb-card-meta">Abridores: {html_seguro(fila['Abridores'])}</div>
            <div class="mlb-pick-line">
                <span class="mlb-pick-name">{html_seguro(fila['Pick de la IA'])}</span>
                <span class="mlb-odds">{cuota:.2f}</span>
            </div>
            <div class="mlb-card-values">
                <div><span class="mlb-value-label">CONFIANZA</span><span class="mlb-value">{confianza:.1f}%</span></div>
            </div>
            <div class="mlb-confidence"><span style="width:{min(max(confianza, 0), 100):.1f}%"></span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_registro_auditoria(fila):
    resultado = str(fila["Resultado"])
    ganada = "Ganada" in resultado
    clase = "won" if ganada else "lost"
    etiqueta = "GANADA" if ganada else "PERDIDA"
    profit = float(fila["Profit ($)"])
    clase_profit = (
        "mlb-profit-positive" if profit >= 0 else "mlb-profit-negative"
    )
    fecha = pd.to_datetime(fila["Fecha"]).strftime("%d/%m/%Y")
    st.markdown(
        f"""
        <div class="mlb-audit-card {clase}">
            <div class="mlb-audit-head">
                <span class="mlb-audit-date">{fecha}</span>
                <span class="mlb-result-badge {clase}">{etiqueta}</span>
            </div>
            <div class="mlb-audit-match">{html_seguro(fila['Partido'])}</div>
            <div class="mlb-audit-pick">Pick: {html_seguro(fila['Pick de la IA'])}</div>
            <div class="mlb-audit-values">
                <div><span class="mlb-value-label">CONFIANZA</span><span class="mlb-value">{float(fila['Confianza (%)']):.1f}%</span></div>
                <div><span class="mlb-value-label">STAKE</span><span class="mlb-value">${float(fila['Stake ($)']):,.0f}</span></div>
                <div><span class="mlb-value-label">CUOTA</span><span class="mlb-value">{float(fila['Cuota']):.2f}</span></div>
                <div><span class="mlb-value-label">PROFIT</span><span class="mlb-value {clase_profit}">${profit:+,.0f}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ==========================================================
# 1. CARGAR LA INTELIGENCIA ARTIFICIAL V4.0
# ==========================================================
@st.cache_resource
def cargar_oraculo():
    try:
        # Arquitectura V4: Recibe 18 variables continuas
        modelo = Sequential([
            Input(shape=(18,)),
            Dense(64, activation='relu'),
            Dropout(0.3),
            Dense(32, activation='relu'),
            Dropout(0.2),
            Dense(16, activation='relu'),
            Dropout(0.2),
            Dense(1, activation='sigmoid')
        ])

        modelo.load_weights(str(RUTA_MODELOS_MLB / 'pesos_mlb_v4.weights.h5'))
        scaler = joblib.load(RUTA_MODELOS_MLB / 'scaler_v4.pkl')
        columnas_v4 = joblib.load(RUTA_MODELOS_MLB / 'columnas_v4.pkl')

        return modelo, scaler, columnas_v4
    except Exception as e:
        st.error(f"Error cargando la IA V4.0: {e}")
        return None, None, None

def conectar_bd():
    return get_db_connection()

MAPEO_EQUIPOS = MLB_TEAMS_ABBR
ZONAS_HORARIAS = MLB_STADIUM_TIMEZONES

def normalizar_equipo(nombre):
    return MAPEO_EQUIPOS.get(nombre, nombre)

@st.cache_data(ttl=60)
def cargar_datos_hoy():
    conexion = conectar_bd()
    consulta = """
        SELECT j.equipo_local AS 'Equipo Local', j.equipo_visitante AS 'Equipo Visitante',
               MAX(c.cuota_local) AS 'Paga Local', MAX(c.cuota_visitante) AS 'Paga Visitante'
        FROM juegos j
        JOIN cuotas_moneyline c ON j.id_juego = c.id_juego
        WHERE j.marcador_local IS NULL AND DATE(j.fecha) = %s
        GROUP BY j.id_juego
    """
    df = pd.read_sql(consulta, conexion, params=(hoy_mx(),))
    conexion.close()
    if not df.empty:
        df = df.drop_duplicates(subset=['Equipo Local', 'Equipo Visitante'], keep='last').reset_index(drop=True)
    return df


# ==========================================================
# 2. MOTORES DE EXTRACCIÓN Y LIMPIEZA
# ==========================================================
def obtener_estado_actual(equipo, df_hist, fecha_objetivo=None):
    if fecha_objetivo is None: fecha_objetivo = hoy_mx()
    else: fecha_objetivo = pd.to_datetime(fecha_objetivo).date()

    df_hist_copy = df_hist.copy()
    df_hist_copy['fecha_solo_dia'] = pd.to_datetime(df_hist_copy['fecha']).dt.date

    df_equipo = df_hist_copy[
        ((df_hist_copy['equipo_local'] == equipo) | (df_hist_copy['equipo_visitante'] == equipo)) &
        (df_hist_copy['fecha_solo_dia'] < fecha_objetivo)
    ].sort_values('fecha_solo_dia')

    if df_equipo.empty: return 0.500, 0, 3, 0.5, equipo

    juegos_jugados = len(df_equipo)
    victorias = 0
    carreras_anotadas = 0
    carreras_recibidas = 0
    ultimos_5 = []

    for _, row in df_equipo.iterrows():
        es_local = row['equipo_local'] == equipo
        runs_fav = row['marcador_local'] if es_local else row['marcador_visitante']
        runs_con = row['marcador_visitante'] if es_local else row['marcador_local']

        carreras_anotadas += runs_fav
        carreras_recibidas += runs_con
        gano = 1 if runs_fav > runs_con else 0
        victorias += gano
        ultimos_5.append(gano)

    win_pct = victorias / juegos_jugados
    run_diff = carreras_anotadas - carreras_recibidas
    racha_5 = np.mean(ultimos_5[-5:]) if len(ultimos_5) > 0 else 0.5

    fecha_ultimo = df_equipo.iloc[-1]['fecha_solo_dia']
    estadio_anterior = df_equipo.iloc[-1]['equipo_local']
    descanso = (fecha_objetivo - fecha_ultimo).days

    return win_pct, run_diff, descanso, racha_5, estadio_anterior

def limpiar_cuotas_v4(cuota_l_raw, cuota_v_raw):
    def to_decimal(val):
        if val <= -100: return (100 / abs(val)) + 1
        elif val >= 100: return (val / 100) + 1
        return val

    c_l = to_decimal(float(cuota_l_raw))
    c_v = to_decimal(float(cuota_v_raw))

    if c_l <= 1 or c_v <= 1: return 0.5, 0.5
    prob_l_cruda = 1 / c_l
    prob_v_cruda = 1 / c_v
    overround = prob_l_cruda + prob_v_cruda

    return prob_l_cruda / overround, prob_v_cruda / overround

@st.cache_data(ttl=300)
def cargar_metricas_avanzadas():
    try:
        conexion = conectar_bd()
        query = "SELECT equipo, ops_vs_zurdo, ops_vs_derecho, era_bullpen_7d FROM metricas_equipos WHERE fecha = (SELECT MAX(fecha) FROM metricas_equipos)"
        df = pd.read_sql(query, conexion)
        conexion.close()
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_lesiones_hoy():
    try:
        conexion = conectar_bd()
        query = "SELECT equipo, impacto_total FROM factor_lesiones WHERE fecha = (SELECT MAX(fecha) FROM factor_lesiones)"
        df_les = pd.read_sql(query, conexion)
        conexion.close()
        return df_les
    except: return pd.DataFrame()

def aplicar_filtro_medico(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_lesiones):
    if df_lesiones.empty: return confianza_base
    imp_l = df_lesiones.loc[df_lesiones['equipo'] == equipo_local, 'impacto_total'].values
    imp_v = df_lesiones.loc[df_lesiones['equipo'] == equipo_visitante, 'impacto_total'].values
    impacto_local = imp_l[0] if len(imp_l) > 0 else 0
    impacto_visita = imp_v[0] if len(imp_v) > 0 else 0

    ajuste = impacto_local - impacto_visita if equipo_elegido == equipo_local else impacto_visita - impacto_local
    confianza_final = confianza_base + ajuste
    return max(50.1, min(99.0, round(confianza_final, 1)))

@st.cache_data(ttl=300)
def cargar_pitchers_hoy():
    try:
        conexion = conectar_bd()
        query = "SELECT equipo, nombre_pitcher, era, era_ultimas_3 FROM abridores WHERE fecha = (SELECT MAX(fecha) FROM abridores)"
        df_pitchers = pd.read_sql(query, conexion)
        conexion.close()
        return df_pitchers
    except: return pd.DataFrame()

def aplicar_filtro_pitchers(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_pitchers):
    if df_pitchers.empty: return confianza_base, "TBD", "TBD"

    def obtener_era_real(equipo):
        row = df_pitchers[df_pitchers['equipo'] == equipo]
        if row.empty: return 4.50
        era_3 = row['era_ultimas_3'].values[0]
        era_g = row['era'].values[0]
        return float(era_3) if pd.notna(era_3) and float(era_3) > 0 else float(era_g)

    era_local = obtener_era_real(equipo_local)
    era_visita = obtener_era_real(equipo_visitante)

    nom_l = df_pitchers.loc[df_pitchers['equipo'] == equipo_local, 'nombre_pitcher'].values
    nom_v = df_pitchers.loc[df_pitchers['equipo'] == equipo_visitante, 'nombre_pitcher'].values
    pitcher_local = nom_l[0] if len(nom_l) > 0 else "Por anunciar"
    pitcher_visita = nom_v[0] if len(nom_v) > 0 else "Por anunciar"

    ventaja = era_visita - era_local if equipo_elegido == equipo_local else era_local - era_visita
    confianza_final = confianza_base + (ventaja * 2.5)

    return max(50.1, min(99.0, round(confianza_final, 1))), f"{pitcher_local} ({era_local:.2f})", f"{pitcher_visita} ({era_visita:.2f})"

@st.cache_data(ttl=300)
def fusionar_historiales(df_csv, df_xampp):
    df_memoria = df_csv.copy()
    if df_xampp.empty: return df_memoria

    df_xampp = df_xampp.sort_values(by='fecha').reset_index(drop=True)
    for i in range(len(df_xampp)):
        local = df_xampp.loc[i, 'Equipo Local']
        visita = df_xampp.loc[i, 'Equipo Visitante']
        fecha_juego = df_xampp.loc[i, 'fecha']
        marcador_l = df_xampp.loc[i, 'marcador_local']
        marcador_v = df_xampp.loc[i, 'marcador_visitante']

        nueva_fila = pd.DataFrame([{
            'fecha': fecha_juego, 'equipo_local': local, 'equipo_visitante': visita,
            'marcador_local': marcador_l, 'marcador_visitante': marcador_v,
        }])
        df_memoria = pd.concat([df_memoria, nueva_fila], ignore_index=True)
    return df_memoria

@st.cache_data(ttl=300)
def cargar_historial_xampp():
    conexion = conectar_bd()
    consulta = """
        SELECT j.fecha, j.equipo_local AS 'Equipo Local', j.equipo_visitante AS 'Equipo Visitante',
               j.marcador_local, j.marcador_visitante,
               MAX(c.cuota_local) AS 'Paga Local', MAX(c.cuota_visitante) AS 'Paga Visitante'
        FROM juegos j
        JOIN cuotas_moneyline c ON j.id_juego = c.id_juego
        WHERE j.marcador_local IS NOT NULL AND DATE(j.fecha) < %s
        GROUP BY j.id_juego ORDER BY j.fecha ASC
    """
    df = pd.read_sql(consulta, conexion, params=(hoy_mx(),))
    conexion.close()

    if not df.empty:
        df['solo_fecha'] = pd.to_datetime(df['fecha']).dt.date
        df = df.drop_duplicates(subset=['solo_fecha', 'Equipo Local', 'Equipo Visitante'], keep='last')
        df = df.drop(columns=['solo_fecha']).reset_index(drop=True)
    return df

# ==========================================================
# NUEVO: histórico completo de métricas / lesiones / abridores
# (para que Tab 2 use los MISMOS filtros que Tab 1, con datos
#  de la fecha real de cada juego, no valores neutros fijos)
# ==========================================================
@st.cache_data(ttl=3600)
def cargar_metricas_historico():
    try:
        conexion = conectar_bd()
        query = "SELECT fecha, equipo, ops_vs_zurdo, ops_vs_derecho, era_bullpen_7d FROM metricas_equipos"
        df = pd.read_sql(query, conexion)
        conexion.close()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_lesiones_historico():
    try:
        conexion = conectar_bd()
        query = "SELECT fecha, equipo, impacto_total FROM factor_lesiones"
        df = pd.read_sql(query, conexion)
        conexion.close()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_pitchers_historico():
    try:
        conexion = conectar_bd()
        query = "SELECT fecha, equipo, nombre_pitcher, era, era_ultimas_3 FROM abridores"
        df = pd.read_sql(query, conexion)
        conexion.close()
        return df
    except Exception:
        return pd.DataFrame()

def _fila_mas_reciente(df_hist, equipo, fecha_objetivo):
    """Fila del equipo con la fecha más reciente <= fecha_objetivo (o None)."""
    if df_hist.empty:
        return None
    fecha_objetivo = pd.to_datetime(fecha_objetivo).date()
    d = df_hist.copy()
    d['fecha'] = pd.to_datetime(d['fecha']).dt.date
    filtro = d[(d['equipo'] == equipo) & (d['fecha'] <= fecha_objetivo)]
    if filtro.empty:
        return None
    return filtro.sort_values('fecha').iloc[-1]

def obtener_metricas_avanzadas_fecha(df_metricas_hist, equipo, fecha_objetivo):
    fila = _fila_mas_reciente(df_metricas_hist, equipo, fecha_objetivo)
    if fila is None:
        return 0.700, 0.700, 4.50
    ops_l = float(fila['ops_vs_zurdo']) if pd.notna(fila['ops_vs_zurdo']) else 0.700
    ops_r = float(fila['ops_vs_derecho']) if pd.notna(fila['ops_vs_derecho']) else 0.700
    era_bp = float(fila['era_bullpen_7d']) if pd.notna(fila['era_bullpen_7d']) else 4.50
    return ops_l, ops_r, era_bp

# ==========================================================
# NUEVO: registro_picks_ia — la fuente única de verdad de la
# confianza. Tab 1 la escribe al calcular cada pick; Tab 2 la
# LEE (no recalcula) cuando el juego ya tiene resultado.
# ==========================================================
def guardar_pick_ia(fecha, equipo_local, equipo_visitante, pick_ia, confianza, cuota):
    """Guarda/actualiza el pick del día en registro_picks_ia."""
    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO registro_picks_ia (fecha, equipo_local, equipo_visitante, pick_ia, confianza, cuota)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE pick_ia = VALUES(pick_ia), confianza = VALUES(confianza), cuota = VALUES(cuota)
        """, (fecha, equipo_local, equipo_visitante, pick_ia, float(confianza), float(cuota)))
        conexion.commit()
        cursor.close()
        conexion.close()
    except Exception:
        pass  # No tumbar el dashboard si falla el guardado del registro

@st.cache_data(ttl=300)
def cargar_registro_picks_historico():
    """Trae todo registro_picks_ia (la confianza YA calculada por Tab 1 cada día)."""
    try:
        conexion = conectar_bd()
        query = "SELECT fecha, equipo_local, equipo_visitante, pick_ia, confianza, cuota FROM registro_picks_ia"
        df = pd.read_sql(query, conexion)
        conexion.close()
        return df
    except Exception:
        return pd.DataFrame()

def obtener_confianza_registrada(df_registro, fecha_juego, equipo_local, equipo_visitante):
    """
    Busca en registro_picks_ia la fila exacta para ese juego.
    Regresa (confianza, pick_ia, cuota) o (None, None, None) si no existe
    (típicamente juegos anteriores a que se empezara a registrar).
    """
    if df_registro.empty:
        return None, None, None
    fecha_obj = pd.to_datetime(fecha_juego).date()
    d = df_registro.copy()
    d['fecha'] = pd.to_datetime(d['fecha']).dt.date
    fila = d[
        (d['fecha'] == fecha_obj) &
        (d['equipo_local'] == equipo_local) &
        (d['equipo_visitante'] == equipo_visitante)
    ]
    if fila.empty:
        return None, None, None
    fila = fila.iloc[0]
    return float(fila['confianza']), fila['pick_ia'], float(fila['cuota'])

# ---------------- FLUJO PRINCIPAL ----------------
vista_mlb = st.radio(
    "Sección MLB",
    ["⚾ Picks de hoy", "📈 Rendimiento", "⚾ Totales V2", "📊 Rendimiento Totales"],
    horizontal=True, label_visibility="collapsed", key="mlb_vista_principal",
)
if vista_mlb in ("⚾ Totales V2", "📊 Rendimiento Totales"):
    from mlb_totales.ui_totales_mlb import render_picks, render_performance
    if vista_mlb == "⚾ Totales V2":
        render_picks(conectar_bd)
    else:
        render_performance(conectar_bd)
    st.stop()

modelo, scaler, columnas_v4 = cargar_oraculo()
df = cargar_datos_hoy()
if not df.empty: df = df.drop_duplicates(subset=['Equipo Local', 'Equipo Visitante']).reset_index(drop=True)

if not df.empty and modelo is not None:
    df_csv_estatico = pd.read_csv(RUTA_DATA_MLB / 'mlb_dataset_ia.csv')
    df_pasado = cargar_historial_xampp()
    df_hist = fusionar_historiales(df_csv_estatico, df_pasado)
    df_metricas_adv = cargar_metricas_avanzadas()

    if vista_mlb == "⚾ Picks de hoy":
        resultados = []
        for i in range(len(df)):
            local_api = df.loc[i, 'Equipo Local']
            visita_api = df.loc[i, 'Equipo Visitante']

            local = normalizar_equipo(local_api)
            visita = normalizar_equipo(visita_api)

            # 1. Rendimiento Básico y Estadio Anterior
            w_l, d_l, desc_l, r5_l, est_ant_l = obtener_estado_actual(local, df_hist)
            w_v, d_v, desc_v, r5_v, est_ant_v = obtener_estado_actual(visita, df_hist)

            # 2. Desgaste por Viaje (Jetlag)
            zona_estadio_hoy = ZONAS_HORARIAS.get(local, -5)
            zona_ant_l = ZONAS_HORARIAS.get(normalizar_equipo(est_ant_l), -5)
            zona_ant_v = ZONAS_HORARIAS.get(normalizar_equipo(est_ant_v), -5)
            jetlag_l = abs(zona_estadio_hoy - zona_ant_l)
            jetlag_v = abs(zona_estadio_hoy - zona_ant_v)

            # 3. Métricas Avanzadas (Splits y Bullpen)
            met_l = df_metricas_adv[df_metricas_adv['equipo'] == local_api]
            met_v = df_metricas_adv[df_metricas_adv['equipo'] == visita_api]

            ops_l_team = float(met_l['ops_vs_zurdo'].values[0]) if not met_l.empty else 0.700
            ops_r_team = float(met_l['ops_vs_derecho'].values[0]) if not met_l.empty else 0.700
            era_bp_team = float(met_l['era_bullpen_7d'].values[0]) if not met_l.empty else 4.50

            ops_l_opp = float(met_v['ops_vs_zurdo'].values[0]) if not met_v.empty else 0.700
            ops_r_opp = float(met_v['ops_vs_derecho'].values[0]) if not met_v.empty else 0.700
            era_bp_opp = float(met_v['era_bullpen_7d'].values[0]) if not met_v.empty else 4.50

            # 4. Desparasitar Cuotas
            prob_p_l, prob_p_v = limpiar_cuotas_v4(df.loc[i, 'Paga Local'], df.loc[i, 'Paga Visitante'])

            # 5. MATRIZ EXACTA V4.0 (18 Variables)
            fila_dic = {
                'win_pct_team': w_l, 'win_pct_opp': w_v,
                'run_diff_team': d_l, 'run_diff_opp': d_v,
                'dias_descanso_team': desc_l, 'dias_descanso_opp': desc_v,
                'racha_5_team': r5_l, 'racha_5_opp': r5_v,
                'jetlag_team': jetlag_l, 'jetlag_opp': jetlag_v,
                'ops_l_team': ops_l_team, 'ops_r_team': ops_r_team, 'era_bullpen_team': era_bp_team,
                'ops_l_opp': ops_l_opp, 'ops_r_opp': ops_r_opp, 'era_bullpen_opp': era_bp_opp,
                'prob_pure_team': prob_p_l, 'prob_pure_opp': prob_p_v
            }

            fila_ia = pd.DataFrame([fila_dic])
            fila_ia = fila_ia[columnas_v4]

            vars_escaladas = scaler.transform(fila_ia)
            prob_local = modelo.predict(vars_escaladas, verbose=0)[0][0] * 100
            prob_visitante = 100 - prob_local

            favorito = local_api if prob_local > 50 else visita_api
            confianza = max(prob_local, prob_visitante)
            paga = df.loc[i, 'Paga Local'] if prob_local > 50 else df.loc[i, 'Paga Visitante']

            df_lesiones_hoy = cargar_lesiones_hoy()
            df_pitchers_hoy = cargar_pitchers_hoy()

            confianza_filtrada = aplicar_filtro_medico(favorito, confianza, local_api, visita_api, df_lesiones_hoy)
            confianza_final, p_local, p_visita = aplicar_filtro_pitchers(favorito, confianza_filtrada, local_api, visita_api, df_pitchers_hoy)

            # NUEVO: persistimos el pick de moneyline en registro_picks_ia.
            # Esto es lo que Tab 2 va a leer más adelante cuando el juego termine,
            # en vez de recalcularlo con otra lógica.
            guardar_pick_ia(hoy_mx(), local_api, visita_api, favorito, confianza_final, paga)

            resultados.append({
                "Partido": f"{local_api} vs {visita_api}",
                "Abridores": f"{p_local} vs {p_visita}",
                "Pick de la IA": favorito,
                "Confianza (%)": confianza_final,
                "Paga del Favorito": paga
            })

        df_resultados = pd.DataFrame(resultados)
        if df_resultados.empty:
            st.warning("📭 No se pudo generar ningún pick hoy.")
            st.stop()

        df_resultados = df_resultados.sort_values(by="Confianza (%)", ascending=False).reset_index(drop=True)

        mejor_pick = df_resultados.loc[0]
        metricas_hoy = st.columns(4)
        metricas_hoy[0].metric("Partidos", len(df_resultados))
        metricas_hoy[1].metric(
            "Mejor pick", str(mejor_pick["Pick de la IA"])
        )
        metricas_hoy[2].metric(
            "Confianza máxima", f"{mejor_pick['Confianza (%)']:.1f}%"
        )
        metricas_hoy[3].metric(
            "Cuota", f"{float(mejor_pick['Paga del Favorito']):.2f}"
        )

        st.subheader("🔥 Pick más fuerte del día")
        st.markdown(
            f"""
            <div class="mlb-best-card">
                <div class="mlb-card-kicker">SELECCIÓN PRINCIPAL</div>
                <div class="mlb-card-title">{html_seguro(mejor_pick['Pick de la IA'])}</div>
                <div class="mlb-card-meta">{html_seguro(mejor_pick['Partido'])} · Confianza {float(mejor_pick['Confianza (%)']):.1f}% · Cuota {float(mejor_pick['Paga del Favorito']):.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.subheader("Pronósticos del día")

        columna_filtro, columna_ayuda = st.columns([1, 3], gap="medium")
        with columna_filtro:
            filtro_hoy = st.selectbox(
                "Confianza mínima",
                options=list(range(50, 91)),
                index=24,
                format_func=lambda valor: f"{valor}%",
                key="filtro_confianza_hoy",
            )
        with columna_ayuda:
            st.caption(
                "Aumenta el porcentaje para mostrar solamente los "
                "pronósticos de mayor confianza."
            )
        df_filtrado = df_resultados[df_resultados['Confianza (%)'] >= filtro_hoy]

        if not df_filtrado.empty:
            filas_picks = list(df_filtrado.iterrows())
            for inicio in range(0, len(filas_picks), 2):
                columnas_picks = st.columns(2, gap="medium")
                for columna, (_, fila) in zip(
                    columnas_picks, filas_picks[inicio:inicio + 2]
                ):
                    with columna:
                        mostrar_pick_mlb(fila)
        else:
            st.markdown(
                '<div class="mlb-empty">No hay pronósticos que superen '
                'el filtro de confianza seleccionado.</div>',
                unsafe_allow_html=True,
            )

    if vista_mlb == "📈 Rendimiento":
        st.subheader("Rendimiento histórico")
        st.caption(
            "Simulación basada en los picks y cuotas registrados antes "
            "de cada partido."
        )

        columna_filtro, columna_ayuda = st.columns([1, 3], gap="medium")
        with columna_filtro:
            filtro_confianza = st.selectbox(
                "Confianza mínima para evaluar",
                options=list(range(50, 96)),
                index=13,
                format_func=lambda valor: f"{valor}%",
                key="filtro_confianza_roi",
            )
        with columna_ayuda:
            st.caption(
                "El ROI, el profit y el bankroll se recalculan con el "
                "umbral seleccionado."
            )
        df_pasado = cargar_historial_xampp()
        
        # NUEVO: registro_picks_ia = la confianza que Tab 1 ya calculó y guardó.
        df_registro = cargar_registro_picks_historico()

        # Fallback (solo para juegos ANTERIORES a que existiera el registro)
        df_metricas_hist = cargar_metricas_historico()
        df_lesiones_hist = cargar_lesiones_historico()
        df_pitchers_hist = cargar_pitchers_historico()

        if not df_pasado.empty:
            # 1. EVALUAMOS TODOS LOS JUEGOS SIN IMPORTAR EL SLIDER
            registros_completos = []

            for i in range(len(df_pasado)):
                fecha_juego = df_pasado.loc[i, 'fecha']
                local_api = df_pasado.loc[i, 'Equipo Local']
                visita_api = df_pasado.loc[i, 'Equipo Visitante']
                cuota_l_raw = df_pasado.loc[i, 'Paga Local']
                cuota_v_raw = df_pasado.loc[i, 'Paga Visitante']

                local = normalizar_equipo(local_api)
                visita = normalizar_equipo(visita_api)

                confianza_registrada, pick_registrado, cuota_registrada = obtener_confianza_registrada(
                    df_registro, fecha_juego, local_api, visita_api
                )

                if confianza_registrada is not None:
                    confianza = confianza_registrada
                    favorito = pick_registrado
                    ia_pick_local = (favorito == local_api)
                    cuota_favorito = cuota_registrada if cuota_registrada else (cuota_l_raw if ia_pick_local else cuota_v_raw)
                else:
                    w_l, d_l, desc_l, r5_l, est_ant_l = obtener_estado_actual(local, df_hist, fecha_objetivo=fecha_juego)
                    w_v, d_v, desc_v, r5_v, est_ant_v = obtener_estado_actual(visita, df_hist, fecha_objetivo=fecha_juego)

                    zona_estadio_hoy = ZONAS_HORARIAS.get(local, -5)
                    zona_ant_l = ZONAS_HORARIAS.get(normalizar_equipo(est_ant_l), -5)
                    zona_ant_v = ZONAS_HORARIAS.get(normalizar_equipo(est_ant_v), -5)

                    ops_l_team, ops_r_team, era_bp_team = obtener_metricas_avanzadas_fecha(df_metricas_hist, local_api, fecha_juego)
                    ops_l_opp, ops_r_opp, era_bp_opp = obtener_metricas_avanzadas_fecha(df_metricas_hist, visita_api, fecha_juego)

                    fila_dic = {
                        'win_pct_team': w_l, 'win_pct_opp': w_v,
                        'run_diff_team': d_l, 'run_diff_opp': d_v,
                        'dias_descanso_team': desc_l, 'dias_descanso_opp': desc_v,
                        'racha_5_team': r5_l, 'racha_5_opp': r5_v,
                        'jetlag_team': abs(zona_estadio_hoy - zona_ant_l),
                        'jetlag_opp': abs(zona_estadio_hoy - zona_ant_v),
                        'ops_l_team': ops_l_team, 'ops_r_team': ops_r_team, 'era_bullpen_team': era_bp_team,
                        'ops_l_opp': ops_l_opp, 'ops_r_opp': ops_r_opp, 'era_bullpen_opp': era_bp_opp,
                        'prob_pure_team': limpiar_cuotas_v4(cuota_l_raw, cuota_v_raw)[0],
                        'prob_pure_opp': limpiar_cuotas_v4(cuota_l_raw, cuota_v_raw)[1]
                    }

                    fila_ia = pd.DataFrame([fila_dic])
                    fila_ia = fila_ia[columnas_v4]

                    vars_escaladas = scaler.transform(fila_ia)
                    prob_local_val = modelo.predict(vars_escaladas, verbose=0)[0][0]
                    prob_visitante_val = 1 - prob_local_val
                    confianza_base = max(prob_local_val, prob_visitante_val) * 100

                    ia_pick_local = prob_local_val > 0.50
                    favorito = local_api if ia_pick_local else visita_api
                    cuota_favorito = cuota_l_raw if ia_pick_local else cuota_v_raw

                    fila_les_l = _fila_mas_reciente(df_lesiones_hist, local_api, fecha_juego)
                    fila_les_v = _fila_mas_reciente(df_lesiones_hist, visita_api, fecha_juego)
                    df_lesiones_fecha = pd.DataFrame([r for r in [fila_les_l, fila_les_v] if r is not None])

                    fila_pit_l = _fila_mas_reciente(df_pitchers_hist, local_api, fecha_juego)
                    fila_pit_v = _fila_mas_reciente(df_pitchers_hist, visita_api, fecha_juego)
                    df_pitchers_fecha = pd.DataFrame([r for r in [fila_pit_l, fila_pit_v] if r is not None])

                    confianza_filtrada = aplicar_filtro_medico(favorito, confianza_base, local_api, visita_api, df_lesiones_fecha)
                    confianza, _, _ = aplicar_filtro_pitchers(favorito, confianza_filtrada, local_api, visita_api, df_pitchers_fecha)

                gano_local_real = df_pasado.loc[i, 'marcador_local'] > df_pasado.loc[i, 'marcador_visitante']

                if confianza >= 70.0: apuesta = 300
                elif confianza >= 65.0: apuesta = 200
                else: apuesta = 100

                if ia_pick_local == gano_local_real:
                    ganancia = (apuesta * float(cuota_favorito)) - apuesta
                    resultado_txt = "✅ Ganada"
                else:
                    ganancia = -apuesta
                    resultado_txt = "❌ Perdida"

                registros_completos.append({
                    "Fecha": fecha_juego,
                    "Partido": f"{local_api} vs {visita_api}",
                    "Pick de la IA": favorito,
                    "Confianza (%)": round(confianza, 1),
                    "Stake ($)": apuesta,
                    "Cuota": round(float(cuota_favorito), 2),
                    "Resultado": resultado_txt,
                    "Profit ($)": round(ganancia, 2)
                })

            df_todas = pd.DataFrame(registros_completos)

            # 2. 🔥 LA MAGIA: EL ESCÁNER DE ROI ÓPTIMO
            if st.button("🔍 Encontrar mejor umbral de ROI"):
                mejores_escenarios = []
                # Va a iterar desde el 50% al 95% de confianza probando los números
                for t in np.arange(50.0, 95.0, 0.5):
                    df_t = df_todas[df_todas['Confianza (%)'] >= t]
                    if len(df_t) >= 5: # Filtro de seguridad: mínimo 5 apuestas para que el % sea real
                        inv = df_t['Stake ($)'].sum()
                        gan = df_t['Profit ($)'].sum()
                        roi_t = (gan / inv) * 100 if inv > 0 else 0
                        mejores_escenarios.append({"Confianza Mínima": t, "ROI (%)": roi_t, "Apuestas Realizadas": len(df_t)})
                
                if mejores_escenarios:
                    df_optimo = pd.DataFrame(mejores_escenarios)
                    mejor_escenario = df_optimo.loc[df_optimo['ROI (%)'].idxmax()]
                    st.markdown(
                        f"""
                        <div class="mlb-roi-card">
                            <div class="mlb-card-kicker">MEJOR UMBRAL HISTÓRICO</div>
                            <div class="mlb-card-title">Confianza mínima: {float(mejor_escenario['Confianza Mínima']):.1f}%</div>
                            <div class="mlb-card-meta">ROI {float(mejor_escenario['ROI (%)']):.2f}% en {int(mejor_escenario['Apuestas Realizadas'])} apuestas simuladas.</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.line_chart(df_optimo.set_index('Confianza Mínima')['ROI (%)'], use_container_width=True)

            # 3. FILTRADO FINAL Y GRÁFICAS (Usando tu Slider)
            df_filtrado = df_todas[df_todas['Confianza (%)'] >= filtro_confianza]

            apuestas_realizadas = len(df_filtrado)
            inversion_total = df_filtrado['Stake ($)'].sum() if apuestas_realizadas > 0 else 0
            ganancia_neta = df_filtrado['Profit ($)'].sum() if apuestas_realizadas > 0 else 0
            roi = (ganancia_neta / inversion_total) * 100 if inversion_total > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Apuestas Realizadas", f"{apuestas_realizadas} de {len(df_pasado)}")
            col2.metric("Inversión Simulada", f"${inversion_total:,.2f}")
            col3.metric("Profit Neto", f"${ganancia_neta:,.2f}")
            col4.metric("ROI", f"{roi:.2f}%")

            st.subheader("Crecimiento del bankroll")
            if apuestas_realizadas > 0:
                df_filtrado = df_filtrado.sort_values(by="Fecha").reset_index(drop=True)
                historial_banco = [0] + df_filtrado['Profit ($)'].cumsum().tolist()
                st.area_chart(historial_banco, color="#b7ff3c")
            else:
                st.markdown(
                    '<div class="mlb-empty">Ningún partido histórico '
                    'alcanzó esa confianza.</div>',
                    unsafe_allow_html=True,
                )

            st.subheader("Libro de auditoría")
            st.caption("Detalle de las apuestas incluidas en el cálculo.")
            if not df_todas.empty:
                auditoria_base = df_todas.copy()
                auditoria_base['Fecha'] = pd.to_datetime(
                    auditoria_base['Fecha']
                )
                auditoria_base = auditoria_base.sort_values(
                    "Fecha", ascending=False
                ).reset_index(drop=True)

                fechas_disponibles = sorted(
                    auditoria_base["Fecha"].dt.date.unique(),
                    reverse=True,
                )
                controles_auditoria = st.columns(
                    [1.25, 1.25, 1, 1.65], gap="medium"
                )
                with controles_auditoria[0]:
                    fecha_auditoria = st.selectbox(
                        "Fecha",
                        ["Todas las fechas"] + fechas_disponibles,
                        format_func=lambda valor: (
                            valor
                            if isinstance(valor, str)
                            else valor.strftime("%d/%m/%Y")
                        ),
                        key="fecha_auditoria_mlb",
                    )
                with controles_auditoria[1]:
                    confianza_auditoria = st.selectbox(
                        "Confianza mínima",
                        ["Umbral del ROI"] + list(range(50, 100)),
                        format_func=lambda valor: (
                            valor
                            if isinstance(valor, str)
                            else f"{valor}%"
                        ),
                        key="confianza_auditoria_mlb",
                    )
                with controles_auditoria[2]:
                    limite_auditoria = st.selectbox(
                        "Registros a mostrar",
                        [10, 20, 50, "Todos"],
                        index=1,
                        key="limite_auditoria_mlb",
                    )
                auditoria_filtrada = auditoria_base.copy()
                if fecha_auditoria != "Todas las fechas":
                    auditoria_filtrada = auditoria_filtrada[
                        auditoria_filtrada["Fecha"].dt.date
                        == fecha_auditoria
                    ]

                umbral_auditoria = (
                    float(filtro_confianza)
                    if confianza_auditoria == "Umbral del ROI"
                    else float(confianza_auditoria)
                )
                auditoria_filtrada = auditoria_filtrada[
                    auditoria_filtrada["Confianza (%)"]
                    >= umbral_auditoria
                ].reset_index(drop=True)

                with controles_auditoria[3]:
                    csv_auditoria = auditoria_filtrada.assign(
                        Fecha=auditoria_filtrada["Fecha"].dt.date
                    ).to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "⬇️ Descargar resultados filtrados",
                        data=csv_auditoria,
                        file_name="auditoria_picks_mlb_filtrada.csv",
                        mime="text/csv",
                        disabled=auditoria_filtrada.empty,
                    )

                st.caption(
                    f"{len(auditoria_filtrada)} registros encontrados "
                    f"con confianza mínima de {umbral_auditoria:.0f}%."
                )

                if limite_auditoria == "Todos":
                    auditoria_visible = auditoria_filtrada
                else:
                    auditoria_visible = auditoria_filtrada.head(
                        int(limite_auditoria)
                    )

                filas_auditoria = list(auditoria_visible.iterrows())
                if not filas_auditoria:
                    st.markdown(
                        '<div class="mlb-empty">No existen partidos que '
                        'coincidan con los filtros seleccionados.</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    for inicio in range(0, len(filas_auditoria), 2):
                        columnas_auditoria = st.columns(2, gap="medium")
                        for columna, (_, fila) in zip(
                            columnas_auditoria,
                            filas_auditoria[inicio:inicio + 2],
                        ):
                            with columna:
                                mostrar_registro_auditoria(fila)
        else:
            st.info("⏳ Aún no hay partidos terminados en la base de datos para generar el ROI histórico.")
else:
    if df.empty:
        st.error("🚨 ERROR DE DATOS: La base de datos de XAMPP no tiene juegos nuevos registrados para hoy.")
    elif modelo is None:
        st.error("🚨 ERROR DE IA: Faltan archivos de la V4.0.")
