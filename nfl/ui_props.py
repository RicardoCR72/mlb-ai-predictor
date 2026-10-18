from core.ui_rendimiento_resumen import history_window
from core.ui_controles import state_message, roi_sample, render_order
from core.ui_tarjetas import render_pick, nfl_pick
from core.ui_rendimiento_diseno import performance_filters, safe_select
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
    from nfl.services.eligibility import upcoming
    return upcoming(datos)


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
    from core.db import get_db_credentials
    return get_db_credentials()


def conectar_mysql():
    return mysql.connector.connect(**configuracion_mysql())


def cargar_props_mysql():
    from nfl.repositorio import cargar_props_mysql as read
    return read()


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
                 ('Lesión', texto_seguro(fila.get('estado_lesion'), 'Sin alerta')),
                 ('Contexto y escenarios', texto_seguro(fila.get('contexto_lesiones'), 'Sin alerta'))],
        allow_register=fila['seleccion'] in ('OVER','UNDER','ANOTA'))



def mostrar_resultado_prop(fila):
    result=str(fila.get('resultado_pick','PENDIENTE'))
    label={'GANADA':'✅ Ganada','PERDIDA':'❌ Perdida'}.get(result.upper(),result)
    render_pick(nfl_pick(fila, prop=True), market=str(fila['mercado'])+' · Simulación 1 u', state=label,
        details=[('Resultado real',formatear_numero(fila.get('valor_real'),1)),
                 ('Unidades', 'N/D' if pd.isna(fila.get('beneficio_unidades')) else f"{float(fila['beneficio_unidades']):+.2f} u"),
                 ('Publicación',str(fila.get('estado_pick','')))], allow_register=False)



def mostrar_lesion_compacta(fila):
    estado = texto_seguro(fila.get("estado_lesion"), "Por confirmar")
    contexto = texto_seguro(fila.get("contexto_lesiones"), "")
    if "Dependencia de lesión:" in contexto:
        estado = "Depende de compañeros en duda"
    if len(contexto) > 180 and "Dependencia de lesión:" not in contexto:
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


def render():
    seccion_props = st.radio(
        "Sección de props",
        ["🔥 Candidatos", "📈 Rendimiento", "🏥 Lesiones"],
        horizontal=True,
        format_func=lambda value: value.lstrip("🔥📋📈⚾🏈📊⚽🔮💼 "),
        label_visibility="collapsed",
        key="nfl_props_seccion",
    )
    if seccion_props == "📈 Rendimiento":
        from core.ui_historial_publicado import render_history
        render_history("NFL", None, key='nfl_prop_perf')
        return

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


    st.subheader('Props de jugadores')
    st.caption('Último registro: '+ultima_texto)

    if seccion_props != "📈 Rendimiento":st.metric("Candidatos", len(candidatos))


    # ---------------------------------------------------------------------------
    # Navegación interna: solamente las tres vistas operativas.
    # Capturar Draftea vive en la barra lateral; las proyecciones completas se
    # consultan mediante los filtros y la metodología ya no ocupa una pestaña.
    # ---------------------------------------------------------------------------

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

    if seccion_props != "📈 Rendimiento":
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
    if seccion_props != "📈 Rendimiento":
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
