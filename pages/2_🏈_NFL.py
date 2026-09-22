import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]

DIRECTORIO_PREDICCIONES = (
    RAIZ_PROYECTO
    / "data"
    / "nfl"
    / "predictions"
)

SCRIPT_ACTUALIZACION = (
    RAIZ_PROYECTO
    / "nfl"
    / "predecir_semana_actual.py"
)


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


def obtener_archivo_mas_reciente():
    archivos = list(
        DIRECTORIO_PREDICCIONES.glob(
            "nfl_totales_*.csv"
        )
    )

    if not archivos:
        return None

    return max(
        archivos,
        key=lambda ruta: ruta.stat().st_mtime,
    )


@st.cache_data(ttl=60)
def cargar_predicciones(ruta_archivo):
    df = pd.read_csv(ruta_archivo)

    df["gameday"] = pd.to_datetime(
        df["gameday"],
        errors="coerce",
    )

    numericas = [
        "season",
        "week",
        "total_line",
        "pred_total",
        "pred_total_base",
        "edge",
        "edge_absoluto",
        "prob_pick",
        "prob_over",
        "prob_under",
        "odds_pick",
        "ev",
    ]

    for columna in numericas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(
                df[columna],
                errors="coerce",
            )

    return df


def ejecutar_actualizacion():
    if not SCRIPT_ACTUALIZACION.exists():
        st.error(
            "No se encontró "
            "nfl/predecir_semana_actual.py"
        )
        return

    with st.spinner(
        "Actualizando calendario, líneas y predicciones..."
    ):
        try:
            resultado = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_ACTUALIZACION),
                ],
                cwd=str(RAIZ_PROYECTO),
                capture_output=True,
                text=True,
                timeout=300,
            )

            if resultado.returncode != 0:
                st.error(
                    "No fue posible actualizar "
                    "las predicciones."
                )

                st.code(
                    resultado.stderr,
                    language="text",
                )

                return

            st.success(
                "Predicciones actualizadas correctamente."
            )

            with st.expander(
                "Ver resultado de la actualización"
            ):
                st.code(
                    resultado.stdout,
                    language="text",
                )

            st.cache_data.clear()
            st.rerun()

        except subprocess.TimeoutExpired:
            st.error(
                "La actualización excedió "
                "los cinco minutos."
            )

        except Exception as error:
            st.error(
                f"Error actualizando: {error}"
            )


def mostrar_badge(estado):
    if estado == "PICK":
        st.markdown(
            '<span class="pick-badge">PICK</span>',
            unsafe_allow_html=True,
        )

    elif estado == "SIN LÍNEA":
        st.markdown(
            '<span class="no-line-badge">'
            'SIN LÍNEA</span>',
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            '<span class="no-pick-badge">'
            'NO PICK</span>',
            unsafe_allow_html=True,
        )


def mostrar_partido(fila):
    with st.container(border=True):
        encabezado, estado_col = st.columns(
            [5, 1]
        )

        with encabezado:
            fecha = fila["gameday"]

            if pd.notna(fecha):
                texto_fecha = fecha.strftime(
                    "%d/%m/%Y"
                )
            else:
                texto_fecha = "Fecha pendiente"

            st.subheader(
                f"{fila['away_team']} @ "
                f"{fila['home_team']}"
            )

            st.caption(
                f"{texto_fecha} · "
                f"Semana {int(fila['week'])}"
            )

        with estado_col:
            mostrar_badge(fila["estado"])

        (
            columna_linea,
            columna_proyeccion,
            columna_edge,
            columna_ev,
        ) = st.columns(4)

        columna_linea.metric(
            "Línea O/U",
            formatear_numero(
                fila["total_line"],
                1,
            ),
        )

        proyeccion = (
            fila["pred_total"]
            if pd.notna(fila["pred_total"])
            else fila["pred_total_base"]
        )

        columna_proyeccion.metric(
            "Total proyectado",
            formatear_numero(
                proyeccion,
                1,
            ),
        )

        columna_edge.metric(
            "Edge",
            formatear_numero(
                fila["edge"],
                2,
            ),
        )

        columna_ev.metric(
            "EV estimado",
            formatear_porcentaje(
                fila["ev"]
            ),
        )

        if fila["pick"] == "OVER":
            st.markdown(
                f"""
                <div class="over-text">
                    Selección: OVER {
                        formatear_numero(
                            fila["total_line"],
                            1
                        )
                    }
                </div>
                """,
                unsafe_allow_html=True,
            )

        elif fila["pick"] == "UNDER":
            st.markdown(
                f"""
                <div class="under-text">
                    Selección: UNDER {
                        formatear_numero(
                            fila["total_line"],
                            1
                        )
                    }
                </div>
                """,
                unsafe_allow_html=True,
            )

        else:
            st.info(
                "La línea todavía no está disponible."
            )

        if pd.notna(fila["prob_pick"]):
            probabilidad = float(
                fila["prob_pick"]
            )

            st.progress(
                min(max(probabilidad, 0), 1),
                text=(
                    "Probabilidad calibrada del pick: "
                    f"{probabilidad:.2%}"
                ),
            )

        detalles = st.columns(4)

        detalles[0].write(
            "**P(Over):** "
            + formatear_porcentaje(
                fila["prob_over"]
            )
        )

        detalles[1].write(
            "**P(Under):** "
            + formatear_porcentaje(
                fila["prob_under"]
            )
        )

        detalles[2].write(
            "**Momio:** "
            + formatear_momio(
                fila["odds_pick"]
            )
        )

        detalles[3].write(
            "**Modelo base:** "
            + formatear_numero(
                fila["pred_total_base"],
                1,
            )
        )

        if fila["estado"] == "PICK":
            st.success(
                "Supera el edge mínimo de 3 puntos "
                "y presenta EV estimado positivo."
            )

        elif fila["estado"] == "NO PICK":
            st.caption(
                "No supera conjuntamente los filtros "
                "de edge y valor esperado."
            )


# ==========================================================
# BARRA LATERAL
# ==========================================================
st.sidebar.header("Configuración")

if st.sidebar.button(
    "🔄 Actualizar predicciones",
    use_container_width=True,
):
    ejecutar_actualizacion()


ruta_archivo = obtener_archivo_mas_reciente()

if ruta_archivo is None:
    st.warning(
        "Todavía no existen predicciones. "
        "Presiona «Actualizar predicciones»."
    )
    st.stop()


df = cargar_predicciones(
    str(ruta_archivo)
)

temporada = int(df["season"].max())
semana = int(df["week"].max())

st.sidebar.write(
    f"**Temporada:** {temporada}"
)

st.sidebar.write(
    f"**Semana:** {semana}"
)

estados_disponibles = [
    "Todos",
    "PICK",
    "NO PICK",
    "SIN LÍNEA",
]

filtro_estado = st.sidebar.selectbox(
    "Estado",
    estados_disponibles,
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
    [
        "Mayor EV",
        "Mayor edge",
        "Fecha",
    ],
)


# ==========================================================
# FILTROS
# ==========================================================
filtrado = df.copy()

if filtro_estado != "Todos":
    filtrado = filtrado[
        filtrado["estado"] == filtro_estado
    ]

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


# ==========================================================
# RESUMEN
# ==========================================================
cantidad_partidos = len(df)

picks = df[
    df["estado"] == "PICK"
].copy()

probabilidad_media = (
    picks["prob_pick"].mean()
    if not picks.empty
    else np.nan
)

ev_medio = (
    picks["ev"].mean()
    if not picks.empty
    else np.nan
)

mayor_edge = (
    picks["edge_absoluto"].max()
    if not picks.empty
    else np.nan
)

resumen = st.columns(4)

resumen[0].metric(
    "Partidos",
    cantidad_partidos,
)

resumen[1].metric(
    "Picks",
    len(picks),
)

resumen[2].metric(
    "Probabilidad media",
    formatear_porcentaje(
        probabilidad_media
    ),
)

resumen[3].metric(
    "Mayor edge",
    formatear_numero(
        mayor_edge,
        2,
    ),
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
            "No existen picks que superen "
            "los filtros actuales."
        )

    else:
        picks_ordenados = picks.sort_values(
            "ev",
            ascending=False,
        )

        for _, fila in picks_ordenados.iterrows():
            mostrar_partido(fila)


with tab_todos:
    st.subheader("Calendario analizado")

    st.caption(
        f"Mostrando {len(filtrado)} partidos."
    )

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

    st.write(
        f"Archivo utilizado: `{ruta_archivo.name}`"
    )


# ==========================================================
# DESCARGA
# ==========================================================
st.divider()

csv_descarga = df.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    "⬇️ Descargar predicciones CSV",
    data=csv_descarga,
    file_name=ruta_archivo.name,
    mime="text/csv",
)