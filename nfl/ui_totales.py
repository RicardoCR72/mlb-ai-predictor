from core.ui_rendimiento_resumen import history_window
from core.ui_controles import state_message, roi_sample, render_order
from core.ui_tarjetas import render_pick, nfl_pick
from core.ui_rendimiento_diseno import performance_filters, safe_select
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


def html_seguro(valor, defecto="N/D"):
    if valor is None or pd.isna(valor) or not str(valor).strip():
        return html.escape(defecto)
    return html.escape(str(valor).strip())


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
    from core.db import get_db_credentials
    return get_db_credentials()


def cargar_predicciones_mysql():
    from nfl.repositorio import cargar_predicciones_mysql as read
    return read()


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
    pick = nfl_pick(fila)
    render_pick(pick, market='Total del partido', state=str(fila['estado']),
        details=[('Proyección', formatear_numero(fila['pred_total'], 1)),
                 ('Edge', formatear_numero(fila['edge'], 2)), ('EV estimado', formatear_porcentaje(fila['ev'])),
                 ('P(Over) / P(Under)', formatear_porcentaje(fila['prob_over'])+' / '+formatear_porcentaje(fila['prob_under'])),
                 ('Proyección base', formatear_numero(fila['pred_total_base'], 1))],
        allow_register=fila['pick'] in ('OVER', 'UNDER') and pd.notna(fila['total_line']))



def mostrar_resultado_total(fila):
    result=str(fila.get('resultado_pick','PENDIENTE'))
    label={'GANADA':'✅ Ganada','PERDIDA':'❌ Perdida'}.get(result.upper(),result)
    render_pick(nfl_pick(fila), market='Total del partido · Simulación 1 u', state=label,
        details=[('Total real',formatear_numero(fila.get('total_real'),1)),
                 ('Unidades', 'N/D' if pd.isna(fila.get('beneficio_unidades')) else f"{float(fila['beneficio_unidades']):+.2f} u")],
        allow_register=False)



# ==========================================================
# CARGA DESDE MYSQL
# ==========================================================


def render():
    try:
        with st.spinner("Consultando predicciones guardadas…"):
            historico = cargar_predicciones_mysql()
    except Exception as error:
        state_message("No fue posible consultar las predicciones NFL. Reintenta cuando vuelva la conexión.",kind="offline")
        st.stop()

    if historico.empty:
        state_message('La base de datos todavía no contiene predicciones NFL.',kind='empty')
        st.stop()
    temporada = int(historico["season"].max())
    semana = int(
        historico.loc[
            historico["season"] == temporada,
            "week",
        ].max()
    )
    df = historico[
        (historico["season"] == temporada)
        & (historico["week"] == semana)
    ].copy()

    st.sidebar.caption(f"NFL {temporada} · Semana {semana}")

    ultima_actualizacion = historico["actualizado_en"].max()
    if pd.notna(ultima_actualizacion):
        st.sidebar.caption(
            "Último registro: "
            + ultima_actualizacion.strftime("%d/%m/%Y %H:%M")
        )

    # ==========================================================
    # FILTROS Y RESUMEN
    # ==========================================================
    filtrado = df.sort_values(
        ["ev", "edge_absoluto"],
        ascending=[False, False],
        na_position="last",
    ).copy()

    # La tarjeta de oportunidades solo muestra encuentros que aún no se juegan.
    # Los picks anteriores permanecen disponibles en Rendimiento.
    pendientes = filtrar_partidos_pendientes(df)
    picks = pendientes[pendientes["estado"] == "PICK"].copy()
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

    liquidados_resumen = historico[
        (historico["estado"] == "PICK")
        & historico["resultado_pick"].isin(["GANADA", "PERDIDA", "PUSH"])
    ].copy()
    ganadas_resumen = int(
        (liquidados_resumen["resultado_pick"] == "GANADA").sum()
    )
    perdidas_resumen = int(
        (liquidados_resumen["resultado_pick"] == "PERDIDA").sum()
    )
    pushes_resumen = int(
        (liquidados_resumen["resultado_pick"] == "PUSH").sum()
    )
    apuestas_roi_resumen = int(
        liquidados_resumen["beneficio_unidades"].notna().sum()
    )
    unidades_resumen = float(
        pd.to_numeric(
            liquidados_resumen["beneficio_unidades"], errors="coerce"
        ).fillna(0.0).sum()
    )
    roi_resumen = (
        unidades_resumen / apuestas_roi_resumen
        if apuestas_roi_resumen
        else np.nan
    )

    seccion_totales = st.radio(
        "Sección de totales",
        ["🔥 Picks filtrados", "📋 Todos los partidos", "📈 Rendimiento"],
        horizontal=True,
        format_func=lambda value: value.lstrip("🔥📋📈⚾🏈📊⚽🔮💼 "),
        label_visibility="collapsed",
        key="nfl_totales_seccion",
    )

    if seccion_totales != "📈 Rendimiento":
        resumen = st.columns(3)
        resumen[0].metric("Partidos", len(df))
        resumen[1].metric("Con línea", int(df["total_line"].notna().sum()))
        resumen[2].metric("Picks", len(picks))



    # ==========================================================
    # NAVEGACIÓN INTERNA: sin pestaña independiente de metodología.
    # ==========================================================

    if seccion_totales == "🔥 Picks filtrados":
        with st.container():
            st.subheader(f"Oportunidades · Semana {semana}")
            st.caption(
                "Solo partidos pendientes de hoy en adelante que superan los "
                "filtros de edge y valor esperado. Confirma la línea antes de "
                "utilizarlos."
            )
            partidos_candidatos = opciones_partidos(picks)
            partido_candidato = safe_select(
                "Partido",
                list(partidos_candidatos),
                key="totales_partido_candidatos",
            )
            picks_mostrar = picks
            if partidos_candidatos[partido_candidato] is not None:
                picks_mostrar = picks_mostrar[
                    picks_mostrar["id_juego"] == partidos_candidatos[partido_candidato]
                ]
            if picks_mostrar.empty:
                state_message('No quedan picks pendientes para ese partido en la semana actual.',kind='filters')
            else:
                filas_picks = list(
                    render_order(picks_mostrar, 'nfl_total_picks',date_col='gameday',confidence_col='prob_pick',ev_col='ev',upcoming=True).iterrows()
                )
                for inicio in range(0, len(filas_picks), 2):
                    columnas = st.columns(2, gap="medium")
                    for columna, (_, fila) in zip(
                        columnas, filas_picks[inicio:inicio + 2]
                    ):
                        with columna:
                            mostrar_partido(fila)

    if seccion_totales == "📋 Todos los partidos":
        st.subheader("Calendario analizado")
        st.caption(f"Mostrando {len(filtrado)} partidos.")
        filas_partidos = list(filtrado.iterrows())
        for inicio in range(0, len(filas_partidos), 2):
            columnas = st.columns(2, gap="medium")
            for columna, (_, fila) in zip(
                columnas, filas_partidos[inicio:inicio + 2]
            ):
                with columna:
                    mostrar_partido(fila)

    if seccion_totales == "📈 Rendimiento":
        from core.ui_historial_publicado import render_history
        render_history("NFL",'Totales',key='nfl_totales_perf')

    if seccion_totales != "📈 Rendimiento":
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

        st.sidebar.download_button(
            "⬇️ Descargar predicciones CSV",
            data=csv_descarga,
            file_name=(
                f"nfl_totales_{temporada}_semana_{semana}.csv"
            ),
            mime="text/csv",
        )
