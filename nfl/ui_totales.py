from core.ui_controles import state_message, roi_sample, render_order
from core.ui_unidades import render_model_equivalence
from core.ui_picks import render_pick, nfl_pick
from core.ui_rendimiento import performance_filters, safe_select
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import mysql.connector
import numpy as np
import pandas as pd
import streamlit as st


ZONA_MEXICO = ZoneInfo("America/Mexico_City")


def filtrar_partidos_pendientes(datos):
    """Conserva juegos de hoy o posteriores que todavía no tienen resultado."""
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
    .total-pick-card {
        position: relative;
        overflow: hidden;
        min-height: 226px;
        padding: 1rem 1rem .9rem 1.15rem;
        margin-bottom: .8rem;
        border: 1px solid #263143;
        border-radius: 13px;
        background: linear-gradient(145deg, #121924, #0e141d);
    }
    .total-pick-card::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: #b7ff3c;
    }
    .total-pick-card.no-pick::before { background: #596579; }
    .total-card-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: .7rem;
    }
    .total-game { color: #f5f8fb; font-size: 1.08rem; font-weight: 850; }
    .total-context { color: #8994a5; font-size: .73rem; margin-top: .18rem; }
    .total-badge {
        color: #b7ff3c;
        background: #1b3518;
        border-radius: 999px;
        padding: .3rem .52rem;
        font-size: .65rem;
        font-weight: 850;
        white-space: nowrap;
    }
    .total-badge.no-pick { color: #aab3c0; background: #222b38; }
    .total-selection {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: .6rem;
        margin: .9rem 0;
    }
    .total-pick-name { color: #fff; font-size: 1.08rem; font-weight: 900; }
    .total-odds {
        padding: .27rem .45rem;
        border-radius: 7px;
        background: #1b2431;
        color: #f2f5f8;
        font-weight: 800;
    }
    .total-values {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .45rem;
        padding-top: .7rem;
        border-top: 1px solid #222d3e;
    }
    .total-value-label { color: #798596; font-size: .6rem; }
    .total-value {
        display: block;
        margin-top: .16rem;
        color: #eef3f8;
        font-weight: 800;
    }
    .total-positive { color: #b7ff3c; }
    .total-confidence {
        height: 4px;
        margin-top: .75rem;
        border-radius: 999px;
        background: #273141;
        overflow: hidden;
    }
    .total-confidence > span { display: block; height: 100%; background: #b7ff3c; }
    .total-footer {
        display: flex;
        justify-content: space-between;
        gap: .5rem;
        margin-top: .55rem;
        color: #8994a5;
        font-size: .68rem;
    }
    .total-pulse {
        padding: 1rem;
        border: 1px solid #202938;
        border-radius: 12px;
        background: #111720;
    }
    .total-pulse-title { color: #f5f8fb; font-weight: 800; }
    .total-pulse-ring {
        width: 116px;
        height: 116px;
        display: grid;
        place-items: center;
        position: relative;
        margin: .9rem auto 1rem;
        border-radius: 50%;
        background: conic-gradient(#b7ff3c 0 var(--pulse), #273141 var(--pulse) 100%);
    }
    .total-pulse-ring::before {
        content: "";
        position: absolute;
        width: 84px;
        height: 84px;
        border-radius: 50%;
        background: #111720;
    }
    .total-pulse-ring strong { position: relative; z-index: 1; font-size: 1.35rem; }
    .total-pulse-row {
        display: flex;
        justify-content: space-between;
        gap: .6rem;
        padding: .55rem 0;
        border-bottom: 1px solid #202938;
        font-size: .8rem;
    }
    .total-pulse-row span { color: #8994a5; }
    .total-pulse-note {
        margin-top: .8rem;
        padding: .65rem;
        border-radius: 8px;
        background: #19220f;
        color: #c9fb77;
        font-size: .72rem;
    }
    .total-empty-state {
        padding: 1rem;
        border: 1px dashed #334155;
        border-radius: 11px;
        background: #111720;
        color: #9aa6b6;
        font-size: .84rem;
    }
    .total-result-card, .total-week-card {
        position: relative;
        padding: .9rem 1rem;
        margin-bottom: .7rem;
        border: 1px solid #263143;
        border-radius: 12px;
        background: linear-gradient(145deg, #121924, #0e141d);
    }
    .total-result-card::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        border-radius: 12px 0 0 12px;
        background: #b7ff3c;
    }
    .total-result-card.lost::before { background: #ff5d68; }
    .total-result-card.push::before { background: #f2b84b; }
    .total-result-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: .6rem;
    }
    .total-result-title, .total-week-title { color: #f5f8fb; font-weight: 850; }
    .total-result-meta, .total-week-meta { color: #8994a5; font-size: .7rem; margin-top: .18rem; }
    .total-result-badge {
        padding: .26rem .46rem;
        border-radius: 999px;
        background: #1b3518;
        color: #b7ff3c;
        font-size: .62rem;
        font-weight: 850;
    }
    .total-result-badge.lost { background: #3b1d25; color: #ff7881; }
    .total-result-badge.push { background: #3a2d16; color: #f6c761; }
    .total-result-values {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .45rem;
        margin-top: .7rem;
        padding-top: .6rem;
        border-top: 1px solid #222d3e;
    }
    .total-history-values {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .45rem;
        margin-top: .7rem;
        padding-top: .6rem;
        border-top: 1px solid #222d3e;
    }
    .total-result-label { color: #798596; font-size: .58rem; }
    .total-result-value { display: block; color: #eef3f8; font-weight: 800; margin-top: .12rem; }
    @media (max-width: 850px) {
        .total-pick-card { min-height: auto; }
        .total-values { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .total-history-values { grid-template-columns: repeat(2, minmax(0, 1fr)); }
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
            p.total_real,
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

    return df.reset_index(drop=True)


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
    render_pick(nfl_pick(fila), market='Total del partido · Simulación 1 u', state=str(fila.get('resultado_pick','PENDIENTE')),
        details=[('Total real',formatear_numero(fila.get('total_real'),1)),
                 ('Unidades', 'N/D' if pd.isna(fila.get('beneficio_unidades')) else f"{float(fila['beneficio_unidades']):+.2f} u")],
        allow_register=False)



# ==========================================================
# CARGA DESDE MYSQL
# ==========================================================
if st.sidebar.button(
    "🔄 Recargar desde MySQL",
    use_container_width=True,
):
    st.cache_data.clear()
    st.rerun()

try:
    with st.spinner("Consultando predicciones en Aiven..."):
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
        "Actualizado en MySQL: "
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

resumen = st.columns(5)
resumen[0].metric("Partidos", len(df))
resumen[1].metric("Con línea", int(df["total_line"].notna().sum()))
resumen[2].metric("Picks", len(picks))
resumen[3].metric(
    "Probabilidad media",
    formatear_porcentaje(probabilidad_media),
)
resumen[4].metric("ROI histórico", formatear_porcentaje(roi_resumen))
roi_sample(apuestas_roi_resumen)


# ==========================================================
# NAVEGACIÓN INTERNA: sin pestaña independiente de metodología.
# ==========================================================
seccion_totales = st.radio(
    "Sección de totales",
    ["🔥 Picks filtrados", "📋 Todos los partidos", "📈 Rendimiento"],
    horizontal=True,
    label_visibility="collapsed",
    key="nfl_totales_seccion",
)

if seccion_totales == "🔥 Picks filtrados":
    zona_picks, zona_pulso = st.columns([3.25, 1], gap="large")
    with zona_picks:
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

    with zona_pulso:
        st.subheader("Pulso")
        pulso = (
            0.0
            if pd.isna(probabilidad_media)
            else float(probabilidad_media) * 100
        )
        pulso = min(max(pulso, 0.0), 100.0)
        record = (
            f"{ganadas_resumen}-{perdidas_resumen}-{pushes_resumen}"
            if not liquidados_resumen.empty
            else "Sin resultados"
        )
        st.markdown(
            f"""
            <div class="total-pulse">
                <div class="total-pulse-title">Confianza media</div>
                <div class="total-pulse-ring" style="--pulse:{pulso:.1f}%">
                    <strong>{html_seguro(formatear_porcentaje(probabilidad_media))}</strong>
                </div>
                <div class="total-pulse-row"><span>Récord</span><strong>{html_seguro(record)}</strong></div>
                <div class="total-pulse-row"><span>ROI histórico</span><strong>{html_seguro(formatear_porcentaje(roi_resumen))}</strong></div>
                <div class="total-pulse-row"><span>Unidades</span><strong>{unidades_resumen:+.2f} u</strong></div>
                <div class="total-pulse-row"><span>Mayor edge</span><strong>{html_seguro(formatear_numero(mayor_edge, 2))}</strong></div>
                <div class="total-pulse-note">El modelo exige al menos 3 puntos de edge y EV positivo para marcar un PICK.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
    st.subheader("Rendimiento de picks oficiales")

    liquidados = historico[
        (historico["estado"] == "PICK")
        & historico["resultado_pick"].isin(
            ["GANADA", "PERDIDA", "PUSH"]
        )
    ].copy()
    liquidados = performance_filters(liquidados, 'gameday', 'nfl_total_perf', season_col='season',
        probability_col='prob_pick', probability_scale=100, market_col='pick',
        result_col='resultado_pick', week_col='week', expanded=True,
        extra_keys={'partido':'totales_partido_rendimiento'})
    partidos_rendimiento = opciones_partidos(liquidados)
    partido_rendimiento = safe_select(
        "Partido",
        list(partidos_rendimiento),
        key="totales_partido_rendimiento",
    )
    if partidos_rendimiento[partido_rendimiento] is not None:
        liquidados = liquidados[
            liquidados["id_juego"] == partidos_rendimiento[partido_rendimiento]
        ]

    if liquidados.empty:
        state_message('No hay picks oficiales liquidados para los filtros seleccionados.',kind='filters')
    else:
        st.download_button('Descargar rendimiento filtrado', liquidados.to_csv(index=False), 'nfl_totales_rendimiento.csv', 'text/csv', key='totals_perf_csv')
        ganadas = int(
            (liquidados["resultado_pick"] == "GANADA").sum()
        )
        perdidas = int(
            (liquidados["resultado_pick"] == "PERDIDA").sum()
        )
        pushes = int(
            (liquidados["resultado_pick"] == "PUSH").sum()
        )
        decididas = ganadas + perdidas
        accuracy = (
            ganadas / decididas if decididas else np.nan
        )
        beneficio = pd.to_numeric(
            liquidados["beneficio_unidades"],
            errors="coerce",
        ).fillna(0).sum()
        muestra_roi=int(pd.to_numeric(liquidados['beneficio_unidades'],errors='coerce').notna().sum())
        roi = beneficio / muestra_roi if muestra_roi else np.nan

        metricas = st.columns(4)
        metricas[0].metric(
            "Balance",
            f"{ganadas}-{perdidas}-{pushes}",
        )
        metricas[1].metric(
            "Acierto",
            formatear_porcentaje(accuracy),
        )
        metricas[2].metric(
            "Beneficio",
            f"{beneficio:+.2f} u",
        )
        metricas[3].metric(
            "ROI",
            formatear_porcentaje(roi),
        )

        roi_sample(muestra_roi)
        render_model_equivalence(muestra_roi, beneficio)

        comparacion = (liquidados.assign(
            unidades=pd.to_numeric(liquidados['beneficio_unidades'], errors='coerce'))
            .groupby('pick', as_index=False)
            .agg(Picks=('id_prediccion','count'), Muestra_ROI=('unidades','count'), Beneficio=('unidades','sum')))
        comparacion['ROI (%)'] = comparacion['Beneficio'] / comparacion['Muestra_ROI'].replace(0,np.nan) * 100
        comparacion = comparacion.rename(columns={'pick':'Mercado','Beneficio':'Beneficio (u)'})
        st.write('**Rentabilidad por mercado**')
        st.dataframe(comparacion.sort_values('ROI (%)',ascending=False), hide_index=True, use_container_width=True)
        st.caption('OVER y UNDER: simulación de 1 unidad por pick. La comparación usa todos los filtros activos, incluido Resultado.')

        semanal = (
            liquidados.assign(
                ganada=(
                    liquidados["resultado_pick"] == "GANADA"
                ).astype(int),
                perdida=(
                    liquidados["resultado_pick"] == "PERDIDA"
                ).astype(int),
                push=(
                    liquidados["resultado_pick"] == "PUSH"
                ).astype(int),
                unidades=pd.to_numeric(
                    liquidados["beneficio_unidades"],
                    errors="coerce",
                ),
            )
            .groupby(["season", "week"], as_index=False)
            .agg(
                picks=("id_prediccion", "count"),
                ganadas=("ganada", "sum"),
                perdidas=("perdida", "sum"),
                pushes=("push", "sum"),
                unidades=("unidades", "sum"),
                muestra_roi=("unidades", "count"),
            )
        )
        semanal["acierto_pct"] = (
            semanal["ganadas"]
            / (semanal["ganadas"] + semanal["perdidas"])
            * 100
        )
        semanal["roi_pct"] = (
            semanal["unidades"] / semanal["muestra_roi"].replace(0,np.nan) * 100
        )
        semanal = semanal.rename(
            columns={
                "season": "Temporada",
                "week": "Semana",
                "picks": "Picks",
                "muestra_roi": "Muestra ROI",
                "ganadas": "Ganadas",
                "perdidas": "Perdidas",
                "pushes": "Push",
                "unidades": "Unidades",
                "acierto_pct": "Acierto %",
                "roi_pct": "ROI %",
            }
        )
        st.write("**Rendimiento semanal**")
        semanas_recientes = semanal.sort_values(
            ["Temporada", "Semana"], ascending=False
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
                        <div class="total-week-card">
                            <div class="total-week-title">{int(fila['Temporada'])} · Semana {int(fila['Semana'])}</div>
                            <div class="total-week-meta">{int(fila['Picks'])} picks · {int(fila['Ganadas'])}-{int(fila['Perdidas'])}-{int(fila['Push'])}</div>
                            <div class="total-result-values">
                                <div><span class="total-result-label">ACIERTOS</span><span class="total-result-value">{float(fila['Acierto %']):.1f}%</span></div>
                                <div><span class="total-result-label">ROI</span><span class="total-result-value">{float(fila['ROI %']):+.1f}%</span></div>
                                <div><span class="total-result-label">UNIDADES</span><span class="total-result-value">{float(fila['Unidades']):+.2f} u</span></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        st.subheader("Historial liquidado")
        filas_resultados = list(
            render_order(liquidados, 'nfl_total_perf',date_col='gameday',confidence_col='prob_pick',profit_col='beneficio_unidades')
            .head(20)
            .iterrows()
        )
        for inicio in range(0, len(filas_resultados), 2):
            columnas = st.columns(2, gap="medium")
            for columna, (_, fila) in zip(
                columnas, filas_resultados[inicio:inicio + 2]
            ):
                with columna:
                    mostrar_resultado_total(fila)

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

st.sidebar.download_button(
    "⬇️ Descargar predicciones CSV",
    data=csv_descarga,
    file_name=(
        f"nfl_totales_{temporada}_semana_{semana}.csv"
    ),
    mime="text/csv",
)
