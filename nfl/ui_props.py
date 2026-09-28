import hmac
import html

import mysql.connector
import numpy as np
import pandas as pd
import streamlit as st


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
    .result-values, .market-result-values {
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
            st.info("Todavía no existe una línea para este jugador.")

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
    """Tarjeta compacta estilo sportsbook para la vista principal."""
    es_anota = fila["tipo_prop"] == "anytime_td"
    es_revision = fila["estado_pick"] == "REVISAR LESION"
    estado = "REVISAR" if es_revision else "CANDIDATO"
    clase_revision = " review" if es_revision else ""

    if es_anota:
        seleccion = "ANOTA TOUCHDOWN"
        proyeccion = formatear_porcentaje(fila["proyeccion"])
        edge = formatear_porcentaje(fila["edge"])
    else:
        linea = formatear_numero(fila["linea"], 1)
        seleccion = f"{texto_seguro(fila['seleccion'], 'SIN LÍNEA')} {linea}"
        decimales = 1 if "yards" in fila["tipo_prop"] else 2
        proyeccion = formatear_numero(fila["proyeccion"], decimales)
        edge = formatear_numero(fila["edge"], 2)

    probabilidad = fila["probabilidad_pick"]
    probabilidad_texto = formatear_porcentaje(probabilidad)
    confianza = 0.0 if pd.isna(probabilidad) else float(probabilidad) * 100
    confianza = min(max(confianza, 0.0), 100.0)
    ev = formatear_porcentaje(fila["ev_estimado"])
    momio = formatear_momio(fila["cuota_pick"])
    casa = texto_seguro(fila.get("casa_apuestas"))
    contexto = (
        f"{texto_seguro(fila['position'])} · {texto_seguro(fila['team'])} · "
        f"{texto_seguro(fila['away_team'])} @ {texto_seguro(fila['home_team'])}"
    )

    estado_lesion = texto_seguro(
        fila.get("estado_lesion"), "healthy_or_unlisted"
    )
    lesion_html = ""
    if estado_lesion not in {"healthy_or_unlisted", "healthy", "N/D"}:
        lesion_html = (
            '<div class="sports-context" style="color:#f6c761;margin-top:.55rem">'
            f'🏥 Confirmar disponibilidad: {html_seguro(estado_lesion)}</div>'
        )

    st.markdown(
        f"""
        <div class="sports-pick{clase_revision}">
            <div class="sports-pick-head">
                <div>
                    <div class="sports-player">{html_seguro(fila['player_name'])}</div>
                    <div class="sports-context">{html_seguro(contexto)}</div>
                    <div class="sports-context">{html_seguro(fila['mercado'])} · {html_seguro(casa)}</div>
                </div>
                <span class="sports-badge{clase_revision}">{estado}</span>
            </div>
            <div class="sports-selection">
                <span class="sports-pick-name">{html_seguro(seleccion)}</span>
                <span class="sports-odds">{html_seguro(momio)}</span>
            </div>
            <div class="sports-values">
                <div><span class="sports-value-label">PROYECCIÓN</span><span class="sports-value">{html_seguro(proyeccion)}</span></div>
                <div><span class="sports-value-label">EDGE</span><span class="sports-value sports-positive">{html_seguro(edge)}</span></div>
                <div><span class="sports-value-label">PROB. / EV</span><span class="sports-value">{html_seguro(probabilidad_texto)} / {html_seguro(ev)}</span></div>
            </div>
            <div class="sports-confidence"><span style="width:{confianza:.1f}%"></span></div>
            {lesion_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_resultado_prop(fila):
    resultado = texto_seguro(fila.get("resultado_pick"), "PENDIENTE")
    clase = {
        "GANADA": "",
        "PERDIDA": " lost",
        "PUSH": " push",
    }.get(resultado, " push")
    fecha = (
        fila["gameday"].strftime("%d/%m/%Y")
        if pd.notna(fila.get("gameday"))
        else "Fecha pendiente"
    )
    seleccion = texto_seguro(fila.get("seleccion"))
    if fila.get("tipo_prop") != "anytime_td":
        seleccion += " " + formatear_numero(fila.get("linea"), 1)
    unidades = fila.get("beneficio_unidades")
    unidades_texto = (
        "N/D" if pd.isna(unidades) else f"{float(unidades):+.2f} u"
    )
    st.markdown(
        f"""
        <div class="result-card{clase}">
            <div class="result-head">
                <div>
                    <div class="result-title">{html_seguro(fila['player_name'])}</div>
                    <div class="result-meta">{html_seguro(fila['mercado'])} · {html_seguro(fila['away_team'])} @ {html_seguro(fila['home_team'])} · {fecha}</div>
                </div>
                <span class="result-badge{clase}">{html_seguro(resultado)}</span>
            </div>
            <div class="result-values">
                <div><span class="result-label">SELECCIÓN</span><span class="result-value">{html_seguro(seleccion)}</span></div>
                <div><span class="result-label">RESULTADO REAL</span><span class="result-value">{html_seguro(formatear_numero(fila.get('valor_real'), 1))}</span></div>
                <div><span class="result-label">UNIDADES</span><span class="result-value">{html_seguro(unidades_texto)}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
if st.sidebar.button("🔄 Recargar desde MySQL", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

try:
    with st.spinner("Consultando props NFL en Aiven..."):
        historico = cargar_props_mysql()
except Exception as error:
    st.error("No fue posible consultar las proyecciones de props.")
    st.code(str(error), language="text")
    st.stop()

if historico.empty:
    st.warning(
        "Todavía no existen proyecciones en nfl_proyecciones_props."
    )
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

candidatos = df[df["estado_pick"] == "CANDIDATO"].copy()
revisar_lesion = df[df["estado_pick"] == "REVISAR LESION"].copy()
con_linea = df[df["linea"].notna()].copy()
jugadores = df["id_jugador"].nunique()
prob_media = candidatos["probabilidad_pick"].mean()

# Resumen histórico para las tarjetas y el pulso de rendimiento.
resultados_resumen = historico[
    (historico["estado_pick"] == "CANDIDATO")
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

resumen = st.columns(5)
resumen[0].metric("Jugadores", jugadores)
resumen[1].metric("Con línea", len(con_linea), f"de {len(df)} props")
resumen[2].metric("Candidatos", len(candidatos))
resumen[3].metric("Prob. media", formatear_porcentaje(prob_media))
resumen[4].metric("ROI histórico", formatear_porcentaje(roi_resumen))


# ---------------------------------------------------------------------------
# Navegación interna: solamente las tres vistas operativas.
# Capturar Draftea vive en la barra lateral; las proyecciones completas se
# consultan mediante los filtros y la metodología ya no ocupa una pestaña.
# ---------------------------------------------------------------------------
seccion_props = st.radio(
    "Sección de props",
    ["🔥 Candidatos", "📈 Rendimiento", "🏥 Lesiones"],
    horizontal=True,
    label_visibility="collapsed",
    key="nfl_props_seccion",
)

if seccion_props == "🔥 Candidatos":
    candidatos_mostrar = filtrado[
        filtrado["estado_pick"] == "CANDIDATO"
    ]
    zona_picks, zona_pulso = st.columns([3.25, 1], gap="large")
    with zona_picks:
        encabezado_picks, selector_mercado = st.columns(
            [2.15, 1], gap="medium"
        )
        with encabezado_picks:
            st.subheader(f"Oportunidades · Semana {semana}")
            st.caption(
                "Candidatos cuantitativos. Confirma participación, "
                "lesión y movimiento de la línea antes de utilizarlos."
            )
        with selector_mercado:
            mercado_candidatos = st.selectbox(
                "Mercado",
                ["Todos los mercados"]
                + list(NOMBRES_MERCADOS.values()),
                key="props_mercado_candidatos",
            )

        if mercado_candidatos != "Todos los mercados":
            candidatos_mostrar = candidatos_mostrar[
                candidatos_mostrar["mercado"] == mercado_candidatos
            ]

        if candidatos_mostrar.empty:
            st.markdown(
                '<div class="empty-state">No hay candidatos para ese '
                'mercado en la semana actual.</div>',
                unsafe_allow_html=True,
            )
        else:
            filas_candidatos = list(candidatos_mostrar.iterrows())
            for inicio in range(0, len(filas_candidatos), 2):
                columnas_picks = st.columns(2, gap="medium")
                for columna, (_, fila) in zip(
                    columnas_picks, filas_candidatos[inicio:inicio + 2]
                ):
                    with columna:
                        mostrar_prop_compacto(fila)

    with zona_pulso:
        st.subheader("Pulso")
        pulso = 0.0 if pd.isna(prob_media) else float(prob_media) * 100
        pulso = min(max(pulso, 0.0), 100.0)
        probabilidad_pulso = formatear_porcentaje(prob_media)
        roi_pulso = formatear_porcentaje(roi_resumen)
        unidades_pulso = f"{unidades_resumen:+.2f} u"
        record_pulso = (
            f"{ganadas_resumen}-{perdidas_resumen}-{pushes_resumen}"
            if not resultados_resumen.empty
            else "Sin resultados"
        )
        st.markdown(
            f"""
            <div class="pulse-panel">
                <div class="pulse-title">Confianza media</div>
                <div class="pulse-ring" style="--pulse:{pulso:.1f}%">
                    <strong>{html_seguro(probabilidad_pulso)}</strong>
                </div>
                <div class="pulse-row"><span>Récord</span><strong>{html_seguro(record_pulso)}</strong></div>
                <div class="pulse-row"><span>ROI histórico</span><strong>{html_seguro(roi_pulso)}</strong></div>
                <div class="pulse-row"><span>Unidades</span><strong>{html_seguro(unidades_pulso)}</strong></div>
                <div class="pulse-row"><span>Revisar lesión</span><strong>{len(revisar_lesion)}</strong></div>
                <div class="pulse-note">El valor real se confirma al comparar proyección, momio y contexto de última hora.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

if seccion_props == "📈 Rendimiento":
    st.subheader("Rendimiento de picks oficiales")
    st.caption(
        "Solo incluye selecciones que fueron marcadas como CANDIDATO y "
        "que ya tienen resultado oficial. Una unidad se arriesga por pick."
    )

    resultados = historico[
        (historico["estado_pick"] == "CANDIDATO")
        & historico["resultado_pick"].isin(
            ["GANADA", "PERDIDA", "PUSH"]
        )
    ].copy()
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

    if resultados.empty:
        st.markdown(
            '<div class="empty-state">Todavía no hay candidatos '
            'evaluados. El panel se activará automáticamente cuando '
            'existan estadísticas oficiales.</div>',
            unsafe_allow_html=True,
        )
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
        st.caption(
            "Acierto sobre picks decididos: "
            + formatear_porcentaje(acierto)
        )

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
        st.line_chart(
            por_semana.set_index("Semana")[["Unidades acumuladas"]],
            use_container_width=True,
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
        filas_resultados = list(resultados.head(20).iterrows())
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
        st.markdown(
            '<div class="empty-state">No hay jugadores elegibles con '
            'estatus de lesión activo.</div>',
            unsafe_allow_html=True,
        )
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
            etiqueta_juego = st.selectbox(
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
            etiqueta_jugador = st.selectbox(
                "Jugador", list(etiquetas_jugadores.keys())
            )
            id_jugador = etiquetas_jugadores[etiqueta_jugador]
            nombre_prop = st.selectbox(
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
                        st.code(str(error), language="text")

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
