from core.graficas_rendimiento import render_performance_charts
from core.ui_controles import state_message, roi_sample, render_order
from core.ui_unidades import render_model_equivalence
from core.ui_picks import render_pick, nfl_pick
from core.ui_rendimiento import performance_filters, safe_select
import hmac
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import mysql.connector
import numpy as np
import pandas as pd
import streamlit as st


ZONA_MEXICO = ZoneInfo("America/Mexico_City")


def filtrar_partidos_pendientes(datos):
    """Conserva props de hoy o posteriores que todavía no tienen resultado."""
    if datos.empty:
        return datos.copy()

    hoy_mexico = pd.Timestamp(datetime.now(ZONA_MEXICO).date())
    fechas = pd.to_datetime(datos["gameday"], errors="coerce").dt.normalize()
    resultados = (
        datos["resultado_pick"]
        .fillna("PENDIENTE")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    sin_resultado = ~resultados.isin(["GANADA", "PERDIDA", "PUSH"])
    return datos[(fechas >= hoy_mexico) & sin_resultado].copy()


def opciones_partidos(datos):
    """Construye etiquetas legibles y conserva el ID único para filtrar."""
    opciones = {"Todos los partidos": None}
    if datos.empty:
        return opciones

    juegos = (
        datos.sort_values("gameday", ascending=False, na_position="last")
        .drop_duplicates("id_juego")
    )
    for _, juego in juegos.iterrows():
        fecha = (
            juego["gameday"].strftime("%d/%m/%Y")
            if pd.notna(juego["gameday"]) else "Sin fecha"
        )
        etiqueta = (
            f"{juego['away_team']} @ {juego['home_team']} · {fecha}"
            f" · {int(juego['season'])} S{int(juego['week'])}"
        )
        opciones[etiqueta] = juego["id_juego"]
    return opciones


st.markdown(
    """
    <style>
    .prop-card {
        border: 1px solid #30363d;
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.9rem;
        background: rgba(17, 24, 39, 0.30);
    }
    .badge-candidato {
        display: inline-block;
        background: #0f9d58;
        color: white;
        font-weight: 700;
        padding: .22rem .65rem;
        border-radius: 999px;
    }
    .badge-no-pick {
        display: inline-block;
        background: #5f6368;
        color: white;
        font-weight: 700;
        padding: .22rem .65rem;
        border-radius: 999px;
    }
    .badge-sin-linea {
        display: inline-block;
        background: #d97706;
        color: white;
        font-weight: 700;
        padding: .22rem .65rem;
        border-radius: 999px;
    }
    .badge-revisar {
        display: inline-block;
        background: #b45309;
        color: white;
        font-weight: 700;
        padding: .22rem .65rem;
        border-radius: 999px;
    }
    .pick-over { color: #ef4444; font-weight: 750; }
    .pick-under { color: #3b82f6; font-weight: 750; }
    .pick-anota { color: #22c55e; font-weight: 750; }
    .muted { color: #9ca3af; font-size: .88rem; }

    /* Base visual híbrida + sportsbook */
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
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #eef3f8; }
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] input {
        background: #151d28;
        border-color: #2a3546;
        color: #eef3f8;
    }
    [data-testid="stMain"] [data-baseweb="select"] > div {
        background: #111720;
        border-color: #b7ff3c !important;
        color: #eef3f8;
        box-shadow: 0 0 0 1px rgba(183,255,60,.08) !important;
    }
    [data-testid="stMain"] [data-baseweb="select"] > div:hover,
    [data-testid="stMain"] [data-baseweb="select"] > div:focus-within {
        border-color: #b7ff3c !important;
        box-shadow: 0 0 0 2px rgba(183,255,60,.18) !important;
    }
    [data-testid="stMain"] [data-testid="stNumberInput"] input {
        background: #111720;
        color: #eef3f8;
    }
    [data-testid="stMain"] [data-testid="stNumberInput"]
    [data-baseweb="input"] {
        border-color: #b7ff3c !important;
        background: #111720;
        box-shadow: 0 0 0 1px rgba(183,255,60,.08) !important;
    }
    [data-testid="stMain"] [data-testid="stNumberInput"]
    [data-baseweb="input"]:focus-within {
        box-shadow: 0 0 0 2px rgba(183,255,60,.18) !important;
    }
    .oracle-topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #202938;
        border-radius: 13px;
        background: #111720;
        margin-bottom: 1.35rem;
    }
    .oracle-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .oracle-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #b7ff3c;
        color: #071006;
        font-weight: 900;
    }
    .oracle-brand-accent { color: #b7ff3c; }
    .oracle-nav {
        display: flex;
        align-items: center;
        gap: 1.15rem;
        color: #8e99a9;
        font-size: .88rem;
    }
    .oracle-nav-active {
        color: #fff;
        border-bottom: 2px solid #b7ff3c;
        padding-bottom: .35rem;
    }
    .oracle-week {
        padding: .5rem .7rem;
        border-radius: 9px;
        background: #19212d;
        border: 1px solid #283345;
        color: #dce4ee;
        font-size: .82rem;
    }
    .oracle-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin-bottom: 1rem;
    }
    .oracle-eyebrow {
        color: #b7ff3c;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .12em;
    }
    .oracle-hero h1 {
        margin: .22rem 0 .15rem;
        font-size: clamp(1.75rem, 3vw, 2.45rem);
        color: #f5f8fb;
    }
    .oracle-subtitle { color: #8994a5; font-size: .88rem; }
    .oracle-live {
        color: #b7ff3c;
        font-size: .8rem;
        white-space: nowrap;
    }
    .oracle-live-dot {
        display: inline-block;
        width: 7px;
        height: 7px;
        border-radius: 999px;
        background: #b7ff3c;
        box-shadow: 0 0 12px rgba(183,255,60,.8);
        margin-right: .4rem;
    }
    div[data-testid="stMetric"] {
        background: #111720;
        border: 1px solid #202938;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8994a5; }
    div[data-testid="stMetricValue"] { color: #f4f7fb; }
    div[data-baseweb="tab-list"] {
        gap: .3rem;
        border-bottom: 1px solid #202938;
    }
    button[data-baseweb="tab"] {
        color: #8994a5;
        border-radius: 8px 8px 0 0;
        padding-left: .85rem;
        padding-right: .85rem;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #071006;
        background: #b7ff3c;
        font-weight: 800;
    }
    button[data-baseweb="tab"][aria-selected="true"] p { color: #071006; }
    .sports-pick {
        position: relative;
        overflow: hidden;
        min-height: 228px;
        padding: 1rem 1rem .9rem 1.15rem;
        margin-bottom: .8rem;
        border: 1px solid #263143;
        border-radius: 13px;
        background: linear-gradient(145deg, #121924, #0e141d);
    }
    .sports-pick::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: #b7ff3c;
    }
    .sports-pick.review::before { background: #f2b84b; }
    .sports-pick-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: .7rem;
    }
    .sports-player { color: #f5f8fb; font-size: 1.03rem; font-weight: 800; }
    .sports-context { color: #8994a5; font-size: .73rem; margin-top: .18rem; }
    .sports-badge {
        color: #b7ff3c;
        background: #1b3518;
        border-radius: 999px;
        padding: .3rem .48rem;
        font-size: .65rem;
        font-weight: 800;
        white-space: nowrap;
    }
    .sports-badge.review { color: #f6c761; background: #3a2d16; }
    .sports-selection {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: .6rem;
        margin: .9rem 0;
    }
    .sports-pick-name { color: #fff; font-size: 1.08rem; font-weight: 900; }
    .sports-odds {
        padding: .27rem .45rem;
        border-radius: 7px;
        background: #1b2431;
        color: #f2f5f8;
        font-weight: 800;
    }
    .sports-values {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .45rem;
        padding-top: .7rem;
        border-top: 1px solid #222d3e;
    }
    .sports-value-label { color: #798596; font-size: .62rem; }
    .sports-value {
        display: block;
        margin-top: .16rem;
        color: #eef3f8;
        font-weight: 800;
    }
    .sports-positive { color: #b7ff3c; }
    .sports-confidence {
        height: 4px;
        margin-top: .75rem;
        border-radius: 999px;
        background: #273141;
        overflow: hidden;
    }
    .sports-confidence > span { display: block; height: 100%; background: #b7ff3c; }
    .pulse-panel {
        padding: 1rem;
        border: 1px solid #202938;
        border-radius: 12px;
        background: #111720;
    }
    .pulse-title { color: #f5f8fb; font-weight: 800; }
    .pulse-ring {
        width: 116px;
        height: 116px;
        display: grid;
        place-items: center;
        position: relative;
        margin: .9rem auto 1rem;
        border-radius: 50%;
        background: conic-gradient(#b7ff3c 0 var(--pulse), #273141 var(--pulse) 100%);
    }
    .pulse-ring::before {
        content: "";
        position: absolute;
        width: 84px;
        height: 84px;
        border-radius: 50%;
        background: #111720;
    }
    .pulse-ring strong { position: relative; z-index: 1; font-size: 1.35rem; }
    .pulse-row {
        display: flex;
        justify-content: space-between;
        gap: .6rem;
        padding: .55rem 0;
        border-bottom: 1px solid #202938;
        font-size: .8rem;
    }
    .pulse-row span { color: #8994a5; }
    .pulse-note {
        margin-top: .8rem;
        padding: .65rem;
        border-radius: 8px;
        background: #19220f;
        color: #c9fb77;
        font-size: .72rem;
    }
    .empty-state {
        padding: 1rem;
        border: 1px dashed #334155;
        border-radius: 11px;
        background: #111720;
        color: #9aa6b6;
        font-size: .84rem;
    }
    .result-card, .injury-card, .market-result-card {
        position: relative;
        padding: .9rem 1rem;
        margin-bottom: .7rem;
        border: 1px solid #263143;
        border-radius: 12px;
        background: linear-gradient(145deg, #121924, #0e141d);
    }
    .result-card::before, .injury-card::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        border-radius: 12px 0 0 12px;
        background: #b7ff3c;
    }
    .result-card.lost::before { background: #ff5d68; }
    .result-card.push::before { background: #f2b84b; }
    .injury-card::before { background: #f2b84b; }
    .result-head, .injury-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: .6rem;
    }
    .result-title, .injury-name, .market-result-title {
        color: #f5f8fb;
        font-weight: 850;
    }
    .result-meta, .injury-meta, .market-result-meta {
        color: #8994a5;
        font-size: .7rem;
        margin-top: .18rem;
    }
    .result-badge, .injury-badge {
        padding: .26rem .46rem;
        border-radius: 999px;
        background: #1b3518;
        color: #b7ff3c;
        font-size: .62rem;
        font-weight: 850;
    }
    .result-badge.lost { background: #3b1d25; color: #ff7881; }
    .result-badge.push, .injury-badge { background: #3a2d16; color: #f6c761; }
    .result-values {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .45rem;
        margin-top: .7rem;
        padding-top: .6rem;
        border-top: 1px solid #222d3e;
    }
    .market-result-values {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .45rem;
        margin-top: .7rem;
        padding-top: .6rem;
        border-top: 1px solid #222d3e;
    }
    .result-label { color: #798596; font-size: .58rem; }
    .result-value { display: block; color: #eef3f8; font-weight: 800; margin-top: .12rem; }
    .injury-context {
        margin-top: .6rem;
        color: #aab4c2;
        font-size: .73rem;
        line-height: 1.45;
    }
    .market-result-card { min-height: 126px; }
    [data-testid="stDataFrame"] {
        border: 1px solid #202938;
        border-radius: 12px;
        overflow: hidden;
    }
    [data-testid="stForm"],
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #263143 !important;
        background: rgba(17,23,32,.74);
    }
    .stDownloadButton button, .stFormSubmitButton button {
        border-color: #b7ff3c;
        color: #b7ff3c;
        background: #101720;
    }
    @media (max-width: 850px) {
        .oracle-nav { display: none; }
        .oracle-hero { align-items: flex-start; flex-direction: column; }
        .sports-pick { min-height: auto; }
        .result-values { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


NOMBRES_MERCADOS = {
    "receptions": "Recepciones",
    "receiving_yards": "Yardas de recepción",
    "passing_yards": "Yardas por pase",
    "passing_tds": "Pases de touchdown",
    "rushing_yards": "Yardas terrestres",
    "anytime_td": "Anota touchdown",
}

# Ambos estados representan selecciones publicadas por el modelo. Las que
# requieren revisar una lesión se conservan en el historial con esa alerta,
# para no eliminar retrospectivamente ni sus victorias ni sus derrotas.
ESTADOS_APUESTA_EVALUABLE = ["CANDIDATO", "REVISAR LESION"]


def formatear_numero(valor, decimales=2):
    if pd.isna(valor):
        return "N/D"
    return f"{float(valor):.{decimales}f}"


def formatear_porcentaje(valor):
    if pd.isna(valor):
        return "N/D"
    return f"{float(valor):.1%}"


def formatear_momio(valor):
    if pd.isna(valor):
        return "N/D"
    valor = float(valor)
    return f"+{valor:.0f}" if valor > 0 else f"{valor:.0f}"


def texto_seguro(valor, defecto="N/D"):
    if valor is None or pd.isna(valor) or not str(valor).strip():
        return defecto
    return str(valor).strip()


def calcular_beneficio_unidades(fila):
    """Calcula una unidad arriesgada cuando MySQL no guardó el beneficio."""
    beneficio = pd.to_numeric(
        pd.Series([fila.get("beneficio_unidades")]), errors="coerce"
    ).iloc[0]
    if pd.notna(beneficio):
        return float(beneficio)

    resultado = texto_seguro(fila.get("resultado_pick")).upper()
    if resultado == "PERDIDA":
        return -1.0
    if resultado == "PUSH":
        return 0.0
    if resultado != "GANADA":
        return np.nan

    cuota = pd.to_numeric(
        pd.Series([fila.get("cuota_pick")]), errors="coerce"
    ).iloc[0]
    if pd.isna(cuota) or float(cuota) == 0:
        return np.nan
    cuota = float(cuota)
    return cuota / 100.0 if cuota > 0 else 100.0 / abs(cuota)


def html_seguro(valor, defecto="N/D"):
    return html.escape(texto_seguro(valor, defecto))


def obtener_secreto(*nombres):
    for nombre in nombres:
        if nombre in st.secrets:
            return st.secrets[nombre]

    if "mysql" in st.secrets:
        seccion = st.secrets["mysql"]
        for nombre in nombres:
            if nombre in seccion:
                return seccion[nombre]
    return None


def configuracion_mysql():
    config = {
        "host": obtener_secreto("host", "DB_HOST", "MYSQL_HOST"),
        "port": obtener_secreto("port", "DB_PORT", "MYSQL_PORT"),
        "user": obtener_secreto("user", "DB_USER", "MYSQL_USER"),
        "password": obtener_secreto(
            "password", "DB_PASSWORD", "MYSQL_PASSWORD"
        ),
        "database": obtener_secreto(
            "database", "DB_NAME", "MYSQL_DATABASE"
        ),
    }
    faltantes = [k for k, v in config.items() if v in (None, "")]
    if faltantes:
        raise ValueError("Faltan secretos MySQL: " + ", ".join(faltantes))

    config["port"] = int(config["port"])
    config["connection_timeout"] = 20
    config["ssl_disabled"] = False
    return config


def conectar_mysql():
    return mysql.connector.connect(**configuracion_mysql())


@st.cache_data(ttl=180, show_spinner=False)
def cargar_props_mysql():
    conexion = None
    cursor = None
    consulta = """
        SELECT
            p.id_proyeccion,
            p.id_juego,
            p.id_jugador,
            p.id_linea,
            p.modelo_version,
            j.temporada AS season,
            j.semana AS week,
            j.fecha AS gameday,
            j.equipo_visitante AS away_team,
            j.equipo_local AS home_team,
            ju.nombre AS player_name,
            ju.posicion AS position,
            ju.equipo_actual AS team,
            p.tipo_prop,
            p.linea,
            p.proyeccion,
            p.edge,
            p.seleccion,
            p.probabilidad_pick,
            p.probabilidad_over,
            p.probabilidad_under,
            p.cuota_pick,
            p.ev_estimado,
            p.estado_pick,
            p.estado_lesion,
            p.impacto_lesiones_companeros,
            p.contexto_lesiones,
            p.valor_real,
            p.resultado_pick,
            p.beneficio_unidades,
            p.evaluado_en,
            p.generado_en,
            p.actualizado_en,
            l.casa_apuestas,
            l.cuota_over,
            l.cuota_under,
            l.timestamp_captura
        FROM nfl_proyecciones_props AS p
        INNER JOIN nfl_juegos AS j
            ON j.id_juego = p.id_juego
        INNER JOIN nfl_jugadores AS ju
            ON ju.id_jugador = p.id_jugador
        LEFT JOIN nfl_lineas_props AS l
            ON l.id_linea = p.id_linea
        ORDER BY
            j.temporada DESC,
            j.semana DESC,
            p.actualizado_en DESC,
            p.id_proyeccion DESC
    """
    try:
        conexion = conectar_mysql()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(consulta)
        registros = cursor.fetchall()
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()

    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    fechas = [
        "gameday", "evaluado_en", "generado_en", "actualizado_en",
        "timestamp_captura",
    ]
    for columna in fechas:
        df[columna] = pd.to_datetime(df[columna], errors="coerce")

    numericas = [
        "season", "week", "linea", "proyeccion", "edge",
        "probabilidad_pick", "probabilidad_over", "probabilidad_under",
        "cuota_pick", "ev_estimado", "impacto_lesiones_companeros",
        "cuota_over", "cuota_under", "valor_real",
        "beneficio_unidades",
    ]
    for columna in numericas:
        df[columna] = pd.to_numeric(df[columna], errors="coerce")

    # Compatibilidad tanto con fracciones (0.72) como porcentajes (72).
    for columna in [
        "probabilidad_pick", "probabilidad_over",
        "probabilidad_under", "ev_estimado",
    ]:
        valores = df[columna].dropna().abs()
        if not valores.empty and valores.median() > 1:
            df[columna] = df[columna] / 100.0

    # Las proyecciones antiguas con alerta de lesión pueden tener resultado
    # oficial y beneficio NULL. Se reconstruye desde el momio americano para
    # que las tarjetas, las unidades acumuladas y el ROI sean consistentes.
    faltan_unidades = (
        df["beneficio_unidades"].isna()
        & df["resultado_pick"].isin(["GANADA", "PERDIDA", "PUSH"])
    )
    if faltan_unidades.any():
        df.loc[faltan_unidades, "beneficio_unidades"] = df.loc[
            faltan_unidades
        ].apply(calcular_beneficio_unidades, axis=1)

    df["edge_absoluto"] = df["edge"].abs()
    df["mercado"] = df["tipo_prop"].map(NOMBRES_MERCADOS).fillna(
        df["tipo_prop"]
    )

    # Conserva únicamente la versión más reciente de cada proyección.
    df = (
        df.sort_values(
            ["actualizado_en", "id_proyeccion"],
            ascending=[False, False],
        )
        .drop_duplicates(
            ["id_juego", "id_jugador", "tipo_prop", "modelo_version"],
            keep="first",
        )
        .reset_index(drop=True)
    )
    return df


def mostrar_badge(estado):
    if estado == "CANDIDATO":
        clase, texto = "badge-candidato", "CANDIDATO"
    elif estado == "SIN LINEA":
        clase, texto = "badge-sin-linea", "SIN LÍNEA"
    elif estado == "REVISAR LESION":
        clase, texto = "badge-revisar", "REVISAR LESIÓN"
    else:
        clase, texto = "badge-no-pick", "NO PICK"
    st.markdown(
        f'<span class="{clase}">{texto}</span>',
        unsafe_allow_html=True,
    )


def mostrar_prop(fila):
    with st.container(border=True):
        izquierda, derecha = st.columns([5, 1])
        with izquierda:
            st.subheader(
                f"{fila['player_name']} · {fila['mercado']}"
            )
            fecha = (
                fila["gameday"].strftime("%d/%m/%Y")
                if pd.notna(fila["gameday"])
                else "Fecha pendiente"
            )
            st.caption(
                f"{fila['position']} · {fila['team']} · "
                f"{fila['away_team']} @ {fila['home_team']} · {fecha}"
            )
        with derecha:
            mostrar_badge(fila["estado_pick"])

        metricas = st.columns(5)
        es_anota = fila["tipo_prop"] == "anytime_td"
        if es_anota:
            proyeccion_texto = formatear_porcentaje(fila["proyeccion"])
            linea_texto = "Sí/No" if pd.notna(fila["linea"]) else "N/D"
            edge_texto = formatear_porcentaje(fila["edge"])
        else:
            decimales = 1 if "yards" in fila["tipo_prop"] else 2
            proyeccion_texto = formatear_numero(
                fila["proyeccion"], decimales
            )
            linea_texto = formatear_numero(fila["linea"], 1)
            edge_texto = formatear_numero(fila["edge"], 2)
        metricas[0].metric("Proyección", proyeccion_texto)
        metricas[1].metric("Línea", linea_texto)
        metricas[2].metric("Edge", edge_texto)
        metricas[3].metric(
            "Probabilidad", formatear_porcentaje(fila["probabilidad_pick"])
        )
        metricas[4].metric("EV", formatear_porcentaje(fila["ev_estimado"]))

        linea = formatear_numero(fila["linea"], 1)
        if fila["seleccion"] == "OVER":
            st.markdown(
                f'<div class="pick-over">Selección: OVER {linea}</div>',
                unsafe_allow_html=True,
            )
        elif fila["seleccion"] == "UNDER":
            st.markdown(
                f'<div class="pick-under">Selección: UNDER {linea}</div>',
                unsafe_allow_html=True,
            )
        elif fila["seleccion"] == "ANOTA":
            st.markdown(
                '<div class="pick-anota">Selección: ANOTA TOUCHDOWN</div>',
                unsafe_allow_html=True,
            )
        else:
            state_message('Todavía no existe una línea para este jugador.',kind='empty')

        detalles = st.columns(4)
        detalles[0].write(
            "**Casa:** " + texto_seguro(fila.get("casa_apuestas"))
        )
        detalles[1].write(
            "**Momio:** " + formatear_momio(fila["cuota_pick"])
        )
        if es_anota:
            detalles[2].write(
                "**P(Anota):** "
                + formatear_porcentaje(fila["probabilidad_over"])
            )
            detalles[3].write(
                "**P(No anota):** "
                + formatear_porcentaje(fila["probabilidad_under"])
            )
        else:
            detalles[2].write(
                "**P(Over):** "
                + formatear_porcentaje(fila["probabilidad_over"])
            )
            detalles[3].write(
                "**P(Under):** "
                + formatear_porcentaje(fila["probabilidad_under"])
            )

        estado_lesion = texto_seguro(
            fila.get("estado_lesion"), "healthy_or_unlisted"
        )
        if estado_lesion not in {"healthy_or_unlisted", "healthy", "N/D"}:
            st.warning(
                f"Estado de lesión del jugador: {estado_lesion}. "
                "Confirma su disponibilidad antes de utilizar la selección."
            )

        contexto = texto_seguro(fila.get("contexto_lesiones"), "")
        if contexto:
            with st.expander("🏥 Contexto de lesiones del equipo"):
                st.write(contexto)


def mostrar_prop_compacto(fila):
    pick = nfl_pick(fila, prop=True)
    render_pick(pick, market=str(fila['mercado']), state=str(fila['estado_pick']),
        details=[('Proyección', formatear_porcentaje(fila['proyeccion']) if fila['tipo_prop']=='anytime_td' else formatear_numero(fila['proyeccion'], 2)),
                 ('Edge', formatear_numero(fila['edge'], 2)), ('EV estimado', formatear_porcentaje(fila['ev_estimado'])),
                 ('Lesión', texto_seguro(fila.get('estado_lesion'), 'Sin alerta'))],
        allow_register=fila['seleccion'] in ('OVER','UNDER','ANOTA'))



def mostrar_resultado_prop(fila):
    render_pick(nfl_pick(fila, prop=True), market=str(fila['mercado'])+' · Simulación 1 u', state=str(fila.get('resultado_pick','PENDIENTE')),
        details=[('Resultado real',formatear_numero(fila.get('valor_real'),1)),
                 ('Unidades', 'N/D' if pd.isna(fila.get('beneficio_unidades')) else f"{float(fila['beneficio_unidades']):+.2f} u"),
                 ('Publicación',str(fila.get('estado_pick','')))], allow_register=False)



def mostrar_lesion_compacta(fila):
    estado = texto_seguro(fila.get("estado_lesion"), "Por confirmar")
    contexto = texto_seguro(fila.get("contexto_lesiones"), "")
    if len(contexto) > 180:
        contexto = contexto[:177].rstrip() + "..."
    contexto_html = (
        f'<div class="injury-context">{html_seguro(contexto)}</div>'
        if contexto
        else ""
    )
    st.markdown(
        f"""
        <div class="injury-card">
            <div class="injury-head">
                <div>
                    <div class="injury-name">{html_seguro(fila['player_name'])}</div>
                    <div class="injury-meta">{html_seguro(fila['position'])} · {html_seguro(fila['team'])} · {html_seguro(fila['away_team'])} @ {html_seguro(fila['home_team'])}</div>
                </div>
                <span class="injury-badge">{html_seguro(estado)}</span>
            </div>
            {contexto_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def insertar_linea_draftea(
    id_juego, id_jugador, tipo_prop, linea, cuota_over, cuota_under
):
    conexion = None
    cursor = None
    try:
        conexion = conectar_mysql()
        cursor = conexion.cursor()
        cursor.execute(
            """
            INSERT INTO nfl_lineas_props (
                id_juego, id_jugador, casa_apuestas, tipo_prop,
                linea, cuota_over, cuota_under, timestamp_captura
            ) VALUES (%s, %s, 'Draftea', %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (
                id_juego, id_jugador, tipo_prop,
                float(linea), float(cuota_over),
                None if cuota_under is None else float(cuota_under),
            ),
        )
        conexion.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


# ---------------------------------------------------------------------------
# Carga y filtros
# ---------------------------------------------------------------------------

try:
    with st.spinner("Consultando props guardados…"):
        historico = cargar_props_mysql()
except Exception as error:
    state_message("No fue posible consultar las proyecciones de props. Reintenta cuando vuelva la conexión.",kind="offline")
    st.stop()

if historico.empty:
    state_message('Todavía no existen proyecciones NFL Props guardadas.',kind='empty')
    st.stop()

temporada = int(historico["season"].max())
semana = int(
    historico.loc[historico["season"] == temporada, "week"].max()
)
df = historico[
    (historico["season"] == temporada)
    & (historico["week"] == semana)
].copy()

st.sidebar.caption(f"NFL {temporada} · Semana {semana}")

filtrado = df.sort_values(
    ["ev_estimado", "probabilidad_pick"],
    ascending=[False, False],
    na_position="last",
).copy()

# Las oportunidades activas excluyen partidos de días anteriores. El
# histórico completo se conserva para calcular resultados, unidades y ROI.
pendientes = filtrar_partidos_pendientes(df)
candidatos = pendientes[
    pendientes["estado_pick"] == "CANDIDATO"
].copy()
revisar_lesion = pendientes[
    pendientes["estado_pick"] == "REVISAR LESION"
].copy()
con_linea = df[df["linea"].notna()].copy()
jugadores = df["id_jugador"].nunique()
prob_media = candidatos["probabilidad_pick"].mean()

# Resumen histórico para las tarjetas y el pulso de rendimiento.
resultados_resumen = historico[
    historico["estado_pick"].isin(ESTADOS_APUESTA_EVALUABLE)
    & historico["resultado_pick"].isin(["GANADA", "PERDIDA", "PUSH"])
].copy()
resultados_resumen = (
    resultados_resumen.sort_values(
        ["evaluado_en", "actualizado_en", "id_proyeccion"],
        ascending=[False, False, False],
    )
    .drop_duplicates(
        ["id_juego", "id_jugador", "tipo_prop"], keep="first"
    )
)
ganadas_resumen = int(
    (resultados_resumen["resultado_pick"] == "GANADA").sum()
)
perdidas_resumen = int(
    (resultados_resumen["resultado_pick"] == "PERDIDA").sum()
)
pushes_resumen = int(
    (resultados_resumen["resultado_pick"] == "PUSH").sum()
)
apuestas_roi_resumen = int(
    resultados_resumen["beneficio_unidades"].notna().sum()
)
unidades_resumen = float(
    resultados_resumen["beneficio_unidades"].fillna(0.0).sum()
)
roi_resumen = (
    unidades_resumen / apuestas_roi_resumen
    if apuestas_roi_resumen
    else np.nan
)

ultima = historico["actualizado_en"].max()
ultima_texto = (
    ultima.strftime("%d/%m/%Y · %H:%M")
    if pd.notna(ultima)
    else "Sin sincronización"
)
st.markdown(
    f"""
    <div class="oracle-hero">
        <div>
            <div class="oracle-eyebrow">MODELOS + MERCADO + CONTEXTO</div>
            <h1>Props NFL</h1>
            <div class="oracle-subtitle">Seis mercados, valor estimado y seguimiento real de resultados.</div>
        </div>
        <div class="oracle-live"><span class="oracle-live-dot"></span>Actualizado {ultima_texto}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

resumen = st.columns(3)
resumen[0].metric("Jugadores", jugadores)
resumen[1].metric("Con línea", len(con_linea), f"de {len(df)} props")
resumen[2].metric("Candidatos", len(candidatos))


# ---------------------------------------------------------------------------
# Navegación interna: solamente las tres vistas operativas.
# Capturar Draftea vive en la barra lateral; las proyecciones completas se
# consultan mediante los filtros y la metodología ya no ocupa una pestaña.
# ---------------------------------------------------------------------------
seccion_props = st.radio(
    "Sección de props",
    ["🔥 Candidatos", "📈 Rendimiento", "🏥 Lesiones"],
    horizontal=True,
    format_func=lambda value: value.lstrip("🔥📋📈⚾🏈📊⚽🔮💼 "),
    label_visibility="collapsed",
    key="nfl_props_seccion",
)

if seccion_props == "🔥 Candidatos":
    candidatos_mostrar = pendientes[
        pendientes["estado_pick"] == "CANDIDATO"
    ].sort_values(
        ["ev_estimado", "probabilidad_pick"],
        ascending=[False, False],
        na_position="last",
    )
    with st.container():
        st.subheader(f"Oportunidades · Semana {semana}")
        st.caption(
            "Solo partidos pendientes de hoy en adelante. Confirma "
            "participación, lesión y movimiento de la línea antes de "
            "utilizarlos."
        )
        selector_partido, selector_mercado = st.columns(2, gap="medium")
        with selector_partido:
            partidos_candidatos = opciones_partidos(candidatos_mostrar)
            partido_candidato = safe_select(
                "Partido",
                list(partidos_candidatos),
                key="props_partido_candidatos",
            )
        with selector_mercado:
            mercado_candidatos = safe_select(
                "Mercado",
                ["Todos los mercados"]
                + list(NOMBRES_MERCADOS.values()),
                key="props_mercado_candidatos",
            )

        if partidos_candidatos[partido_candidato] is not None:
            candidatos_mostrar = candidatos_mostrar[
                candidatos_mostrar["id_juego"] == partidos_candidatos[partido_candidato]
            ]
        if mercado_candidatos != "Todos los mercados":
            candidatos_mostrar = candidatos_mostrar[
                candidatos_mostrar["mercado"] == mercado_candidatos
            ]

        if candidatos_mostrar.empty:
            state_message('No quedan candidatos pendientes para ese partido y mercado en la semana actual.',kind='filters')
        else:
            filas_candidatos = list(render_order(candidatos_mostrar,'nfl_prop_picks',date_col='gameday',
                confidence_col='probabilidad_pick',ev_col='ev_estimado',upcoming=True).iterrows())
            for inicio in range(0, len(filas_candidatos), 2):
                columnas_picks = st.columns(2, gap="medium")
                for columna, (_, fila) in zip(
                    columnas_picks, filas_candidatos[inicio:inicio + 2]
                ):
                    with columna:
                        mostrar_prop_compacto(fila)

if seccion_props == "📈 Rendimiento":
    st.subheader("Rendimiento de picks publicados")
    st.caption(
        "Incluye candidatos y selecciones publicadas con alerta de lesión "
        "que ya tienen resultado oficial. Una unidad se arriesga por pick."
    )

    resultados = historico[
        historico["estado_pick"].isin(ESTADOS_APUESTA_EVALUABLE)
        & historico["resultado_pick"].isin(
            ["GANADA", "PERDIDA", "PUSH"]
        )
    ].copy()
    partidos_perf = opciones_partidos(resultados)
    partido_perf = safe_select('Partido', list(partidos_perf), key='props_perf_partido')
    if partidos_perf[partido_perf] is not None:
        resultados = resultados[resultados['id_juego'] == partidos_perf[partido_perf]]
    resultados = (
        resultados.sort_values(
            ["evaluado_en", "actualizado_en", "id_proyeccion"],
            ascending=[False, False, False],
        )
        .drop_duplicates(
            ["id_juego", "id_jugador", "tipo_prop"], keep="first"
        )
        .reset_index(drop=True)
    )

    resultados = performance_filters(resultados, 'gameday', 'nfl_prop_perf', season_col='season',
        probability_col='probabilidad_pick', probability_scale=100, market_col='mercado', result_col='resultado_pick',week_col='week',
        extra_keys={'partido':'props_perf_partido'})

    if resultados.empty:
        state_message('Todavía no hay candidatos evaluados. El panel se activará automáticamente cuando existan estadísticas oficiales.',kind='empty')
    else:
        resultados["es_ganada"] = (
            resultados["resultado_pick"] == "GANADA"
        ).astype(int)
        resultados["es_perdida"] = (
            resultados["resultado_pick"] == "PERDIDA"
        ).astype(int)
        resultados["es_push"] = (
            resultados["resultado_pick"] == "PUSH"
        ).astype(int)
        resultados["tiene_unidad"] = (
            resultados["beneficio_unidades"].notna()
        ).astype(int)

        ganadas = int(resultados["es_ganada"].sum())
        perdidas = int(resultados["es_perdida"].sum())
        pushes = int(resultados["es_push"].sum())
        decididas = ganadas + perdidas
        apuestas_roi = int(resultados["tiene_unidad"].sum())
        unidades = float(
            resultados["beneficio_unidades"].fillna(0.0).sum()
        )
        acierto = ganadas / decididas if decididas else np.nan
        roi = unidades / apuestas_roi if apuestas_roi else np.nan

        metricas_roi = st.columns(6)
        metricas_roi[0].metric("Picks evaluados", len(resultados))
        metricas_roi[1].metric("Ganadas", ganadas)
        metricas_roi[2].metric("Perdidas", perdidas)
        metricas_roi[3].metric("Pushes", pushes)
        metricas_roi[4].metric(
            "Unidades", f"{unidades:+.2f} u"
        )
        metricas_roi[5].metric("ROI", formatear_porcentaje(roi))
        roi_sample(apuestas_roi)
        st.caption(
            "Acierto sobre picks decididos: "
            + formatear_porcentaje(acierto)
        )

        render_model_equivalence(apuestas_roi, unidades)

        st.write("**Resultados por mercado**")
        por_mercado = (
            resultados.groupby("mercado", as_index=False)
            .agg(
                Picks=("id_proyeccion", "size"),
                Ganadas=("es_ganada", "sum"),
                Perdidas=("es_perdida", "sum"),
                Pushes=("es_push", "sum"),
                Apuestas_ROI=("tiene_unidad", "sum"),
                Unidades=("beneficio_unidades", "sum"),
            )
        )
        decididas_mercado = (
            por_mercado["Ganadas"] + por_mercado["Perdidas"]
        )
        por_mercado["Acierto"] = np.where(
            decididas_mercado > 0,
            por_mercado["Ganadas"] / decididas_mercado,
            np.nan,
        )
        por_mercado["ROI"] = np.where(
            por_mercado["Apuestas_ROI"] > 0,
            por_mercado["Unidades"] / por_mercado["Apuestas_ROI"],
            np.nan,
        )
        por_mercado = por_mercado.rename(
            columns={"mercado": "Mercado"}
        )[
            [
                "Mercado", "Picks", "Ganadas", "Perdidas", "Pushes",
                "Acierto", "Unidades", "ROI",
            ]
        ].sort_values("ROI", ascending=False)
        filas_mercado = list(por_mercado.iterrows())
        for inicio in range(0, len(filas_mercado), 3):
            columnas = st.columns(3, gap="medium")
            for columna, (_, fila) in zip(
                columnas, filas_mercado[inicio:inicio + 3]
            ):
                with columna:
                    st.markdown(
                        f"""
                        <div class="market-result-card">
                            <div class="market-result-title">{html_seguro(fila['Mercado'])}</div>
                            <div class="market-result-meta">{int(fila['Picks'])} picks · {int(fila['Ganadas'])}-{int(fila['Perdidas'])}-{int(fila['Pushes'])}</div>
                            <div class="market-result-values">
                                <div><span class="result-label">ACIERTOS</span><span class="result-value">{html_seguro(formatear_porcentaje(fila['Acierto']))}</span></div>
                                <div><span class="result-label">ROI</span><span class="result-value">{html_seguro(formatear_porcentaje(fila['ROI']))}</span></div>
                                <div><span class="result-label">UNIDADES</span><span class="result-value">{float(fila['Unidades']):+.2f} u</span></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        render_performance_charts(resultados,date_col='gameday',profit_col='beneficio_unidades',
            result_col='resultado_pick',group_cols=('mercado',))

        st.write("**Evolución por semana**")
        por_semana = (
            resultados.groupby(["season", "week"], as_index=False)
            .agg(
                Picks=("id_proyeccion", "size"),
                Ganadas=("es_ganada", "sum"),
                Perdidas=("es_perdida", "sum"),
                Pushes=("es_push", "sum"),
                Apuestas_ROI=("tiene_unidad", "sum"),
                Unidades=("beneficio_unidades", "sum"),
            )
            .sort_values(["season", "week"])
        )
        por_semana["Semana"] = (
            por_semana["season"].astype(int).astype(str)
            + "-S"
            + por_semana["week"].astype(int).astype(str)
        )
        por_semana["ROI"] = np.where(
            por_semana["Apuestas_ROI"] > 0,
            por_semana["Unidades"] / por_semana["Apuestas_ROI"],
            np.nan,
        )
        por_semana["Unidades acumuladas"] = (
            por_semana["Unidades"].fillna(0.0).cumsum()
        )
        semanas_recientes = por_semana.sort_values(
            ["season", "week"], ascending=False
        ).head(6)
        filas_semana = list(semanas_recientes.iterrows())
        for inicio in range(0, len(filas_semana), 3):
            columnas = st.columns(3, gap="medium")
            for columna, (_, fila) in zip(
                columnas, filas_semana[inicio:inicio + 3]
            ):
                with columna:
                    st.markdown(
                        f"""
                        <div class="market-result-card">
                            <div class="market-result-title">{html_seguro(fila['Semana'])}</div>
                            <div class="market-result-meta">{int(fila['Picks'])} picks · {int(fila['Ganadas'])}-{int(fila['Perdidas'])}-{int(fila['Pushes'])}</div>
                            <div class="market-result-values">
                                <div><span class="result-label">ROI</span><span class="result-value">{html_seguro(formatear_porcentaje(fila['ROI']))}</span></div>
                                <div><span class="result-label">UNIDADES</span><span class="result-value">{float(fila['Unidades']):+.2f} u</span></div>
                                <div><span class="result-label">ACUMULADO</span><span class="result-value">{float(fila['Unidades acumuladas']):+.2f} u</span></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        st.write("**Historial de picks evaluados**")

        st.download_button('Descargar rendimiento filtrado', resultados.to_csv(index=False), 'nfl_props_rendimiento.csv', 'text/csv', key='props_perf_csv')
        historial_filtrado = render_order(resultados,'nfl_prop_perf',date_col='gameday',
            confidence_col='probabilidad_pick',profit_col='beneficio_unidades')
        cantidad_historial = safe_select('Mostrar', ['20','50','100','Todos'], index=1, key='props_historial_cantidad')
        st.caption('El límite de tarjetas no modifica las métricas de la muestra.')

        total_filtrado = len(historial_filtrado)
        if cantidad_historial != "Todos":
            historial_filtrado = historial_filtrado.head(
                int(cantidad_historial)
            )

        st.caption(
            f"Mostrando {len(historial_filtrado)} de "
            f"{total_filtrado} picks que coinciden con los filtros."
        )

        if historial_filtrado.empty:
            state_message('No existen picks evaluados que coincidan con esos filtros.',kind='filters')
        else:
            filas_resultados = list(historial_filtrado.iterrows())
            for inicio in range(0, len(filas_resultados), 2):
                columnas = st.columns(2, gap="medium")
                for columna, (_, fila) in zip(
                    columnas, filas_resultados[inicio:inicio + 2]
                ):
                    with columna:
                        mostrar_resultado_prop(fila)

if seccion_props == "🏥 Lesiones":
    st.subheader("Lesiones y disponibilidad")
    st.caption(
        "Jugadores que requieren confirmación y contexto ofensivo que puede "
        "redistribuir volumen hacia sus compañeros."
    )
    selecciones_revisar = df[df["estado_pick"] == "REVISAR LESION"]
    if not selecciones_revisar.empty:
        st.write("**Selecciones que requieren confirmación de disponibilidad**")
        filas_revision = list(selecciones_revisar.iterrows())
        for inicio in range(0, len(filas_revision), 2):
            columnas = st.columns(2, gap="medium")
            for columna, (_, fila) in zip(
                columnas, filas_revision[inicio:inicio + 2]
            ):
                with columna:
                    mostrar_prop_compacto(fila)
        st.divider()

    lesionados = df[
        ~df["estado_lesion"].fillna("healthy_or_unlisted").isin(
            ["healthy", "healthy_or_unlisted"]
        )
    ].copy()
    lesionados = lesionados.drop_duplicates("id_jugador")
    if lesionados.empty:
        state_message('No hay jugadores elegibles con estatus de lesión activo.',kind='empty')
    else:
        st.write("**Reporte activo**")
        filas_lesionados = list(
            lesionados.sort_values(["team", "player_name"]).iterrows()
        )
        for inicio in range(0, len(filas_lesionados), 3):
            columnas = st.columns(3, gap="medium")
            for columna, (_, fila) in zip(
                columnas, filas_lesionados[inicio:inicio + 3]
            ):
                with columna:
                    mostrar_lesion_compacta(fila)

    st.divider()
    st.write("**Contexto ofensivo por equipo**")
    contextos = (
        df[["team", "contexto_lesiones"]]
        .dropna()
        .drop_duplicates()
        .sort_values("team")
    )
    for _, fila in contextos.iterrows():
        if str(fila["contexto_lesiones"]).strip():
            with st.expander(f"{fila['team']} · lesiones relevantes"):
                st.write(fila["contexto_lesiones"])

with st.sidebar.expander("✍️ Capturar Draftea", expanded=False):
    st.write("**Nueva línea manual**")
    st.caption(
        "La captura se guarda como una nueva observación histórica. "
        "Después debe ejecutarse el predictor para recalcular edge y EV."
    )

    password_configurado = obtener_secreto(
        "NFL_ADMIN_PASSWORD", "nfl_admin_password"
    )
    if not password_configurado:
        st.info(
            "Para habilitar este formulario agrega NFL_ADMIN_PASSWORD "
            "a los Secrets de Streamlit."
        )
    else:
        password = st.text_input(
            "Contraseña administrativa", type="password", key="props_admin"
        )
        autorizado = bool(password) and hmac.compare_digest(
            str(password), str(password_configurado)
        )
        if password and not autorizado:
            st.error("Contraseña incorrecta.")

        if autorizado:
            juegos = (
                df[["id_juego", "away_team", "home_team", "gameday"]]
                .drop_duplicates("id_juego")
                .sort_values(["gameday", "away_team"])
            )
            etiquetas_juegos = {
                f"{fila.away_team} @ {fila.home_team}": fila.id_juego
                for fila in juegos.itertuples(index=False)
            }
            etiqueta_juego = safe_select(
                "Partido", list(etiquetas_juegos.keys())
            )
            id_juego = etiquetas_juegos[etiqueta_juego]

            disponibles = (
                df[df["id_juego"] == id_juego][
                    ["id_jugador", "player_name", "position", "team"]
                ]
                .drop_duplicates("id_jugador")
                .sort_values("player_name")
            )
            etiquetas_jugadores = {
                f"{fila.player_name} · {fila.position} · {fila.team}": fila.id_jugador
                for fila in disponibles.itertuples(index=False)
            }
            etiqueta_jugador = safe_select(
                "Jugador", list(etiquetas_jugadores.keys())
            )
            id_jugador = etiquetas_jugadores[etiqueta_jugador]
            nombre_prop = safe_select(
                "Mercado", list(NOMBRES_MERCADOS.values())
            )
            tipo_prop = next(
                clave for clave, valor in NOMBRES_MERCADOS.items()
                if valor == nombre_prop
            )

            with st.form("captura_draftea", clear_on_submit=False):
                if tipo_prop == "anytime_td":
                    linea = 0.5
                    cuota_over = st.number_input(
                        "Momio Anota TD", value=150, step=1
                    )
                    cuota_under = None
                    st.caption(
                        "Para este mercado solo se necesita el momio de que "
                        "el jugador anota."
                    )
                else:
                    linea = st.number_input(
                        "Línea", min_value=0.0, step=0.5, format="%.1f"
                    )
                    cuota_over = st.number_input(
                        "Momio Over", value=-110, step=1
                    )
                    cuota_under = st.number_input(
                        "Momio Under", value=-110, step=1
                    )
                guardar = st.form_submit_button(
                    "Guardar línea de Draftea", use_container_width=True
                )

            if guardar:
                if linea <= 0:
                    st.error("La línea debe ser mayor que cero.")
                elif cuota_over == 0 or (
                    cuota_under is not None and cuota_under == 0
                ):
                    st.error("Los momios no pueden ser cero.")
                else:
                    try:
                        insertar_linea_draftea(
                            id_juego, id_jugador, tipo_prop,
                            linea, cuota_over, cuota_under,
                        )
                        st.cache_data.clear()
                        st.success(
                            "Línea guardada. Ejecuta "
                            "python nfl/predecir_props_semana_actual.py "
                            "para recalcular la selección."
                        )
                    except Exception as error:
                        st.error("No se pudo guardar la línea.")

st.divider()
columnas_csv = [
    "id_juego", "id_jugador", "season", "week", "gameday",
    "away_team", "home_team", "player_name", "position", "team",
    "tipo_prop", "proyeccion", "linea", "edge", "seleccion",
    "probabilidad_pick", "probabilidad_over", "probabilidad_under",
    "cuota_pick", "ev_estimado", "casa_apuestas", "estado_pick",
    "estado_lesion", "contexto_lesiones", "valor_real",
    "resultado_pick", "beneficio_unidades", "evaluado_en",
    "actualizado_en",
]
csv = df[columnas_csv].to_csv(index=False).encode("utf-8")
st.sidebar.download_button(
    "⬇️ Descargar props CSV",
    data=csv,
    file_name=f"nfl_props_{temporada}_semana_{semana}.csv",
    mime="text/csv",
)
