import mysql.connector
import numpy as np
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="NFL Oráculo",
    page_icon="🏈",
    layout="wide",
)

st.title("🏈 NFL Oráculo")
st.caption(
    "Modelo de totales Over/Under · "
    "Edge cuantitativo + probabilidad calibrada"
)

st.markdown(
    """
    <style>
    .pick-badge {
        display: inline-block;
        background-color: #0f9d58;
        color: white;
        font-weight: 700;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
    }
    .no-pick-badge {
        display: inline-block;
        background-color: #5f6368;
        color: white;
        font-weight: 700;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
    }
    .no-line-badge {
        display: inline-block;
        background-color: #d97706;
        color: white;
        font-weight: 700;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
    }
    .over-text {
        color: #ef4444;
        font-weight: 700;
    }
    .under-text {
        color: #3b82f6;
        font-weight: 700;
    }
    .small-note {
        color: #9ca3af;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def formatear_numero(valor, decimales=2):
    if pd.isna(valor):
        return "N/D"
    return f"{float(valor):.{decimales}f}"


def formatear_porcentaje(valor):
    if pd.isna(valor):
        return "N/D"
    return f"{float(valor) * 100:.2f}%"


def formatear_momio(valor):
    if pd.isna(valor):
        return "N/D"

    valor = float(valor)
    if valor > 0:
        return f"+{valor:.0f}"
    return f"{valor:.0f}"


def obtener_secreto(*nombres):
    """Busca secretos de nivel raíz y también dentro de [mysql]."""
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
            "password",
            "DB_PASSWORD",
            "MYSQL_PASSWORD",
        ),
        "database": obtener_secreto(
            "database",
            "DB_NAME",
            "MYSQL_DATABASE",
        ),
    }

    faltantes = [
        nombre
        for nombre, valor in config.items()
        if valor in (None, "")
    ]

    if faltantes:
        raise ValueError(
            "Faltan secretos de MySQL: "
            + ", ".join(faltantes)
        )

    config["port"] = int(config["port"])
    config["connection_timeout"] = 20
    config["ssl_disabled"] = False
    return config


@st.cache_data(ttl=300, show_spinner=False)
def cargar_predicciones_mysql():
    conexion = None
    cursor = None

    consulta = """
        SELECT
            p.id_prediccion,
            p.id_juego,
            p.modelo_version,
            j.temporada AS season,
            j.tipo_juego AS game_type,
            j.semana AS week,
            j.fecha AS gameday,
            j.equipo_visitante AS away_team,
            j.equipo_local AS home_team,
            j.marcador_visitante AS away_score,
            j.marcador_local AS home_score,
            p.linea_total AS total_line,
            p.total_proyectado AS pred_total,
            p.total_proyectado_base AS pred_total_base,
            p.edge,
            p.seleccion AS pick,
            p.probabilidad_pick AS prob_pick,
            p.probabilidad_over AS prob_over,
            p.probabilidad_under AS prob_under,
            p.cuota_pick AS odds_pick,
            p.ev_estimado AS ev,
            p.estado_pick AS estado,
            p.resultado_pick,
            p.beneficio_unidades,
            p.generado_en,
            p.actualizado_en
        FROM nfl_predicciones_totales AS p
        INNER JOIN nfl_juegos AS j
            ON j.id_juego = p.id_juego
        ORDER BY
            j.temporada DESC,
            j.semana DESC,
            p.actualizado_en DESC,
            p.id_prediccion DESC
    """

    try:
        conexion = mysql.connector.connect(
            **configuracion_mysql()
        )
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
    df["gameday"] = pd.to_datetime(
        df["gameday"],
        errors="coerce",
    )
    df["actualizado_en"] = pd.to_datetime(
        df["actualizado_en"],
        errors="coerce",
    )

    numericas = [
        "season",
        "week",
        "total_line",
        "pred_total",
        "pred_total_base",
        "edge",
        "prob_pick",
        "prob_over",
        "prob_under",
        "odds_pick",
        "ev",
    ]

    for columna in numericas:
        df[columna] = pd.to_numeric(
            df[columna],
            errors="coerce",
        )

    # En MySQL las probabilidades y el EV se almacenan como porcentaje.
    for columna in [
        "prob_pick",
        "prob_over",
        "prob_under",
        "ev",
    ]:
        df[columna] = df[columna] / 100.0

    df["edge_absoluto"] = df["edge"].abs()

    # Si existen varias versiones, conserva la actualización más reciente.
    df = (
        df.sort_values(
            ["actualizado_en", "id_prediccion"],
            ascending=[False, False],
        )
        .drop_duplicates(subset=["id_juego"], keep="first")
    )

    temporada = int(df["season"].max())
    semana = int(
        df.loc[df["season"] == temporada, "week"].max()
    )

    return df[
        (df["season"] == temporada)
        & (df["week"] == semana)
    ].reset_index(drop=True)


def mostrar_badge(estado):
    if estado == "PICK":
        clase = "pick-badge"
        texto = "PICK"
    elif estado == "SIN LÍNEA":
        clase = "no-line-badge"
        texto = "SIN LÍNEA"
    else:
        clase = "no-pick-badge"
        texto = "NO PICK"

    st.markdown(
        f'<span class="{clase}">{texto}</span>',
        unsafe_allow_html=True,
    )


def mostrar_partido(fila):
    with st.container(border=True):
        encabezado, estado_col = st.columns([5, 1])

        with encabezado:
            fecha = fila["gameday"]
            texto_fecha = (
                fecha.strftime("%d/%m/%Y")
                if pd.notna(fecha)
                else "Fecha pendiente"
            )

            st.subheader(
                f"{fila['away_team']} @ {fila['home_team']}"
            )
            st.caption(
                f"{texto_fecha} · Semana {int(fila['week'])}"
            )

        with estado_col:
            mostrar_badge(fila["estado"])

        col_linea, col_proyeccion, col_edge, col_ev = st.columns(4)

        col_linea.metric(
            "Línea O/U",
            formatear_numero(fila["total_line"], 1),
        )
        col_proyeccion.metric(
            "Total proyectado",
            formatear_numero(fila["pred_total"], 1),
        )
        col_edge.metric(
            "Edge",
            formatear_numero(fila["edge"], 2),
        )
        col_ev.metric(
            "EV estimado",
            formatear_porcentaje(fila["ev"]),
        )

        seleccion = fila["pick"]
        linea = formatear_numero(fila["total_line"], 1)

        if seleccion == "OVER":
            st.markdown(
                f'<div class="over-text">Selección: OVER {linea}</div>',
                unsafe_allow_html=True,
            )
        elif seleccion == "UNDER":
            st.markdown(
                f'<div class="under-text">Selección: UNDER {linea}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("La línea todavía no está disponible.")

        if pd.notna(fila["prob_pick"]):
            probabilidad = float(fila["prob_pick"])
            st.progress(
                min(max(probabilidad, 0.0), 1.0),
                text=(
                    "Probabilidad calibrada del pick: "
                    f"{probabilidad:.2%}"
                ),
            )

        detalles = st.columns(4)
        detalles[0].write(
            "**P(Over):** "
            + formatear_porcentaje(fila["prob_over"])
        )
        detalles[1].write(
            "**P(Under):** "
            + formatear_porcentaje(fila["prob_under"])
        )
        detalles[2].write(
            "**Momio:** "
            + formatear_momio(fila["odds_pick"])
        )
        detalles[3].write(
            "**Modelo base:** "
            + formatear_numero(fila["pred_total_base"], 1)
        )

        if fila["estado"] == "PICK":
            st.success(
                "Supera el edge mínimo de 3 puntos y "
                "presenta EV estimado positivo."
            )
        elif fila["estado"] == "NO PICK":
            st.caption(
                "No supera conjuntamente los filtros "
                "de edge y valor esperado."
            )


# ==========================================================
# CARGA DESDE MYSQL
# ==========================================================
st.sidebar.header("Configuración")

if st.sidebar.button(
    "🔄 Recargar desde MySQL",
    use_container_width=True,
):
    st.cache_data.clear()
    st.rerun()

try:
    with st.spinner("Consultando predicciones en Aiven..."):
        df = cargar_predicciones_mysql()
except Exception as error:
    st.error(
        "No fue posible consultar las predicciones en MySQL."
    )
    st.code(str(error), language="text")
    st.stop()

if df.empty:
    st.warning(
        "La base de datos todavía no contiene predicciones NFL."
    )
    st.stop()

temporada = int(df["season"].max())
semana = int(df["week"].max())

st.sidebar.write(f"**Temporada:** {temporada}")
st.sidebar.write(f"**Semana:** {semana}")

ultima_actualizacion = df["actualizado_en"].max()
if pd.notna(ultima_actualizacion):
    st.sidebar.caption(
        "Actualizado en MySQL: "
        + ultima_actualizacion.strftime("%d/%m/%Y %H:%M")
    )

filtro_estado = st.sidebar.selectbox(
    "Estado",
    ["Todos", "PICK", "NO PICK", "SIN LÍNEA"],
)

equipos = sorted(
    set(df["away_team"].dropna())
    | set(df["home_team"].dropna())
)
filtro_equipo = st.sidebar.selectbox(
    "Equipo",
    ["Todos"] + equipos,
)
orden = st.sidebar.selectbox(
    "Ordenar por",
    ["Mayor EV", "Mayor edge", "Fecha"],
)


# ==========================================================
# FILTROS Y RESUMEN
# ==========================================================
filtrado = df.copy()

if filtro_estado != "Todos":
    filtrado = filtrado[filtrado["estado"] == filtro_estado]

if filtro_equipo != "Todos":
    filtrado = filtrado[
        (filtrado["away_team"] == filtro_equipo)
        | (filtrado["home_team"] == filtro_equipo)
    ]

if orden == "Mayor EV":
    filtrado = filtrado.sort_values(
        "ev",
        ascending=False,
        na_position="last",
    )
elif orden == "Mayor edge":
    filtrado = filtrado.sort_values(
        "edge_absoluto",
        ascending=False,
        na_position="last",
    )
else:
    filtrado = filtrado.sort_values(
        ["gameday", "away_team"],
        ascending=True,
    )

picks = df[df["estado"] == "PICK"].copy()
probabilidad_media = (
    picks["prob_pick"].mean()
    if not picks.empty
    else np.nan
)
mayor_edge = (
    picks["edge_absoluto"].max()
    if not picks.empty
    else np.nan
)

resumen = st.columns(4)
resumen[0].metric("Partidos", len(df))
resumen[1].metric("Picks", len(picks))
resumen[2].metric(
    "Probabilidad media",
    formatear_porcentaje(probabilidad_media),
)
resumen[3].metric(
    "Mayor edge",
    formatear_numero(mayor_edge, 2),
)


# ==========================================================
# PESTAÑAS
# ==========================================================
tab_picks, tab_todos, tab_metodo = st.tabs(
    [
        "🔥 Picks filtrados",
        "📋 Todos los partidos",
        "🧠 Metodología",
    ]
)

with tab_picks:
    st.subheader(
        f"Semana {semana}: oportunidades detectadas"
    )

    if picks.empty:
        st.info(
            "No existen picks que superen los filtros actuales."
        )
    else:
        for _, fila in picks.sort_values(
            "ev",
            ascending=False,
        ).iterrows():
            mostrar_partido(fila)

with tab_todos:
    st.subheader("Calendario analizado")
    st.caption(f"Mostrando {len(filtrado)} partidos.")

    for _, fila in filtrado.iterrows():
        mostrar_partido(fila)

with tab_metodo:
    st.subheader("Configuración congelada")
    st.markdown(
        """
        - **Entrenamiento:** temporadas 2012–2023.
        - **Calibración:** temporada 2024.
        - **Confirmación:** temporada 2025.
        - **Evaluación OOS:** temporada 2026.
        - **Modelo:** HistGradientBoostingRegressor.
        - **Mercado:** total de puntos Over/Under.
        - **Edge mínimo:** 3 puntos.
        - **Filtro adicional:** EV estimado positivo.
        """
    )
    st.warning(
        "Las probabilidades son estimaciones, no garantías. "
        "Esta versión todavía no incorpora lesiones, "
        "EPA play-by-play ni confirmación de alineaciones."
    )
    st.write("**Fuente de datos:** MySQL/Aiven")


# ==========================================================
# DESCARGA
# ==========================================================
st.divider()

columnas_descarga = [
    "id_juego",
    "season",
    "week",
    "gameday",
    "away_team",
    "home_team",
    "total_line",
    "pred_total",
    "pred_total_base",
    "edge",
    "pick",
    "prob_pick",
    "prob_over",
    "prob_under",
    "odds_pick",
    "ev",
    "estado",
    "actualizado_en",
]

csv_descarga = df[columnas_descarga].to_csv(
    index=False
).encode("utf-8")

st.download_button(
    "⬇️ Descargar predicciones CSV",
    data=csv_descarga,
    file_name=(
        f"nfl_totales_{temporada}_semana_{semana}.csv"
    ),
    mime="text/csv",
)
