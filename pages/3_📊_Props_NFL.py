import hmac

import mysql.connector
import numpy as np
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Props NFL",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Props NFL")
st.caption(
    "Proyecciones de recepción, pase, carrera y anotación · "
    "líneas de mercado, edge, probabilidad y contexto de lesiones"
)

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

st.sidebar.header("Filtros")
st.sidebar.write(f"**Temporada:** {temporada}")
st.sidebar.write(f"**Semana:** {semana}")

estado = st.sidebar.selectbox(
    "Estado",
    ["Todos", "CANDIDATO", "REVISAR LESION", "NO PICK", "SIN LINEA"],
)
mercado = st.sidebar.selectbox(
    "Mercado", ["Todos"] + list(NOMBRES_MERCADOS.values())
)
posicion = st.sidebar.selectbox(
    "Posición", ["Todas"] + sorted(df["position"].dropna().unique().tolist())
)
equipos = sorted(df["team"].dropna().unique().tolist())
equipo = st.sidebar.selectbox("Equipo", ["Todos"] + equipos)
jugador = st.sidebar.text_input("Buscar jugador")
orden = st.sidebar.selectbox(
    "Ordenar por", ["Mayor EV", "Mayor probabilidad", "Mayor edge"]
)

filtrado = df.copy()
if estado != "Todos":
    filtrado = filtrado[filtrado["estado_pick"] == estado]
if mercado != "Todos":
    filtrado = filtrado[filtrado["mercado"] == mercado]
if posicion != "Todas":
    filtrado = filtrado[filtrado["position"] == posicion]
if equipo != "Todos":
    filtrado = filtrado[filtrado["team"] == equipo]
if jugador.strip():
    filtrado = filtrado[
        filtrado["player_name"].str.contains(
            jugador.strip(), case=False, na=False, regex=False
        )
    ]

if orden == "Mayor EV":
    filtrado = filtrado.sort_values("ev_estimado", ascending=False)
elif orden == "Mayor probabilidad":
    filtrado = filtrado.sort_values("probabilidad_pick", ascending=False)
else:
    filtrado = filtrado.sort_values("edge_absoluto", ascending=False)

candidatos = df[df["estado_pick"] == "CANDIDATO"].copy()
revisar_lesion = df[df["estado_pick"] == "REVISAR LESION"].copy()
con_linea = df[df["linea"].notna()].copy()
jugadores = df["id_jugador"].nunique()
prob_media = candidatos["probabilidad_pick"].mean()

resumen = st.columns(6)
resumen[0].metric("Jugadores", jugadores)
resumen[1].metric("Props", len(df))
resumen[2].metric("Con línea", len(con_linea))
resumen[3].metric("Candidatos", len(candidatos))
resumen[4].metric("Revisar lesión", len(revisar_lesion))
resumen[5].metric("Prob. media", formatear_porcentaje(prob_media))

ultima = historico["actualizado_en"].max()
if pd.notna(ultima):
    st.caption("Última actualización: " + ultima.strftime("%d/%m/%Y %H:%M"))


# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------
(
    tab_candidatos,
    tab_todos,
    tab_rendimiento,
    tab_lesiones,
    tab_draftea,
    tab_metodo,
) = st.tabs(
    [
        "🔥 Candidatos",
        "📋 Todas las proyecciones",
        "📈 Rendimiento",
        "🏥 Lesiones",
        "✍️ Capturar Draftea",
        "🧠 Metodología",
    ]
)

with tab_candidatos:
    st.subheader(f"Semana {semana}: oportunidades detectadas")
    st.warning(
        "Son candidatos cuantitativos, no picks oficiales. "
        "Confirma lesión, participación y línea antes de utilizarlos."
    )
    candidatos_mostrar = filtrado[
        filtrado["estado_pick"] == "CANDIDATO"
    ]
    if candidatos_mostrar.empty:
        st.info("No hay candidatos con los filtros seleccionados.")
    else:
        for _, fila in candidatos_mostrar.iterrows():
            mostrar_prop(fila)

with tab_todos:
    st.subheader("Proyecciones disponibles")
    st.caption(f"Mostrando {len(filtrado)} de {len(df)} props.")
    tabla = filtrado[
        [
            "player_name", "position", "team", "mercado", "proyeccion",
            "linea", "edge", "seleccion", "probabilidad_pick",
            "ev_estimado", "casa_apuestas", "estado_pick", "estado_lesion",
        ]
    ].rename(
        columns={
            "player_name": "Jugador",
            "position": "Pos.",
            "team": "Equipo",
            "mercado": "Mercado",
            "proyeccion": "Proyección",
            "linea": "Línea",
            "edge": "Edge",
            "seleccion": "Selección",
            "probabilidad_pick": "Probabilidad",
            "ev_estimado": "EV",
            "casa_apuestas": "Casa",
            "estado_pick": "Estado",
            "estado_lesion": "Lesión",
        }
    )
    st.dataframe(
        tabla,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Probabilidad": st.column_config.NumberColumn(format="percent"),
            "EV": st.column_config.NumberColumn(format="percent"),
            "Proyección": st.column_config.NumberColumn(format="%.2f"),
            "Línea": st.column_config.NumberColumn(format="%.1f"),
            "Edge": st.column_config.NumberColumn(format="%+.2f"),
        },
    )

with tab_rendimiento:
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
        st.info(
            "Todavía no hay candidatos evaluados. Esta sección se "
            "llenará después de ejecutar evaluar_resultados_props.py "
            "cuando existan estadísticas oficiales."
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
        st.dataframe(
            por_mercado,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Acierto": st.column_config.NumberColumn(format="percent"),
                "ROI": st.column_config.NumberColumn(format="percent"),
                "Unidades": st.column_config.NumberColumn(format="%+.2f"),
            },
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
        st.dataframe(
            por_semana[
                [
                    "Semana", "Picks", "Ganadas", "Perdidas", "Pushes",
                    "Unidades", "ROI", "Unidades acumuladas",
                ]
            ].sort_values("Semana", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "ROI": st.column_config.NumberColumn(format="percent"),
                "Unidades": st.column_config.NumberColumn(format="%+.2f"),
                "Unidades acumuladas": st.column_config.NumberColumn(
                    format="%+.2f"
                ),
            },
        )

        st.write("**Historial de picks evaluados**")
        historial_resultados = resultados.assign(
            Partido=(
                resultados["away_team"].astype(str)
                + " @ "
                + resultados["home_team"].astype(str)
            )
        )[
            [
                "gameday", "Partido", "player_name", "mercado",
                "seleccion", "linea", "valor_real", "cuota_pick",
                "resultado_pick", "beneficio_unidades",
            ]
        ].rename(
            columns={
                "gameday": "Fecha",
                "player_name": "Jugador",
                "mercado": "Mercado",
                "seleccion": "Selección",
                "linea": "Línea",
                "valor_real": "Resultado real",
                "cuota_pick": "Momio",
                "resultado_pick": "Resultado",
                "beneficio_unidades": "Unidades",
            }
        )
        st.dataframe(
            historial_resultados,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Línea": st.column_config.NumberColumn(format="%.1f"),
                "Resultado real": st.column_config.NumberColumn(
                    format="%.1f"
                ),
                "Momio": st.column_config.NumberColumn(format="%+.0f"),
                "Unidades": st.column_config.NumberColumn(format="%+.2f"),
            },
        )

with tab_lesiones:
    st.subheader("Jugadores y contexto de lesiones")
    selecciones_revisar = df[df["estado_pick"] == "REVISAR LESION"]
    if not selecciones_revisar.empty:
        st.write("**Selecciones que requieren confirmación de disponibilidad**")
        for _, fila in selecciones_revisar.iterrows():
            mostrar_prop(fila)
        st.divider()

    lesionados = df[
        ~df["estado_lesion"].fillna("healthy_or_unlisted").isin(
            ["healthy", "healthy_or_unlisted"]
        )
    ].copy()
    lesionados = lesionados.drop_duplicates("id_jugador")
    if lesionados.empty:
        st.info("No hay jugadores elegibles con estatus de lesión activo.")
    else:
        for _, fila in lesionados.sort_values(["team", "player_name"]).iterrows():
            st.warning(
                f"{fila['player_name']} · {fila['team']} · "
                f"{texto_seguro(fila['estado_lesion'])}"
            )

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

with tab_draftea:
    st.subheader("Capturar una línea de Draftea")
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
                    c1, c2, c3 = st.columns(3)
                    linea = c1.number_input(
                        "Línea", min_value=0.0, step=0.5, format="%.1f"
                    )
                    cuota_over = c2.number_input(
                        "Momio Over", value=-110, step=1
                    )
                    cuota_under = c3.number_input(
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

with tab_metodo:
    st.subheader("Configuración del modelo")
    st.markdown(
        """
        - **Entrenamiento:** temporadas 2012–2023.
        - **Selección:** temporada 2024.
        - **Confirmación:** temporada 2025.
        - **Evaluación OOS:** temporada 2026.
        - **Mercados:** recepciones, yardas de recepción, yardas por pase, pases de TD, yardas terrestres y anota touchdown.
        - **Elegibilidad recepción:** mínimo 3 juegos previos y 3 targets promedio.
        - **Elegibilidad pase:** mínimo 3 juegos previos y 10 intentos de pase promedio.
        - **Elegibilidad carrera:** mínimo 3 juegos previos y 2 acarreos promedio.
        - **Anota TD:** clasificador binario para RB, FB, WR y TE con al menos 2 oportunidades promedio.
        - **Probabilidades de yardas:** distribución empírica de errores de 2024.
        - **Pases de TD:** calibración específica para líneas 0.5, 1.5 y 2.5.
        - **Lesiones:** contexto, estatus individual y advertencia para jugadores cuestionables.
        - **Candidato recepciones:** edge absoluto ≥ 0.75, probabilidad ≥ 57% y EV positivo.
        - **Candidato yardas recibidas/terrestres:** edge absoluto ≥ 10, probabilidad ≥ 57% y EV positivo.
        - **Candidato yardas por pase:** edge absoluto ≥ 25, probabilidad ≥ 57% y EV positivo.
        - **Candidato pases de TD:** edge absoluto ≥ 0.35, probabilidad ≥ 57% y EV positivo.
        - **Candidato anota TD:** probabilidad ≥ 25%, ventaja ≥ 5 puntos porcentuales, EV positivo y momio máximo +1000.
        """
    )
    st.warning(
        "Las probabilidades son estimaciones, no garantías. "
        "CANDIDATO no significa pick oficialmente validado."
    )


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
st.download_button(
    "⬇️ Descargar props CSV",
    data=csv,
    file_name=f"nfl_props_{temporada}_semana_{semana}.csv",
    mime="text/csv",
)
