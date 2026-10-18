"""Responsabilidad extraída del flujo CLI NFL."""
from pathlib import Path
import pandas as pd
import nflreadpy as nfl
from nfl.settings import TEMPORADA_ACTUAL, RUTA_CALENDARIO
from nfl.features_lesiones import RUTA_LESIONES

def actualizar_calendario():

    print(

        f"Actualizando calendario de "

        f"{TEMPORADA_ACTUAL}..."

    )

    RUTA_CALENDARIO.parent.mkdir(

        parents=True,

        exist_ok=True,

    )

    if RUTA_CALENDARIO.exists():

        print("Cargando calendario local...")

        historico = pd.read_parquet(

            RUTA_CALENDARIO

        )

    else:

        print(

            "No existe calendario local. "

            "Descargando histórico 2012-2026..."

        )

        historico = nfl.load_schedules(

            list(

                range(

                    2012,

                    TEMPORADA_ACTUAL + 1

                )

            )

        ).to_pandas()

    # Volvemos a descargar 2026 para obtener

    # resultados y líneas actualizadas.

    actual = nfl.load_schedules(

        [TEMPORADA_ACTUAL]

    ).to_pandas()

    historico_anterior = historico[

        historico["season"] != TEMPORADA_ACTUAL

    ].copy()

    calendario = pd.concat(

        [historico_anterior, actual],

        ignore_index=True,

    )

    calendario["gameday"] = pd.to_datetime(

        calendario["gameday"],

        errors="coerce",

    )

    calendario = (

        calendario

        .sort_values(

            [

                "season",

                "week",

                "gameday",

                "game_id",

            ]

        )

        .drop_duplicates(

            subset=["game_id"],

            keep="last",

        )

        .reset_index(drop=True)

    )

    calendario.to_parquet(

        RUTA_CALENDARIO,

        index=False,

    )

    print(

        f"Calendario disponible: "

        f"{len(calendario):,} partidos."

    )

    return calendario

def actualizar_lesiones():
    """Actualiza la temporada vigente sin perder el historico local."""
    print(f"Actualizando lesiones de {TEMPORADA_ACTUAL}...")
    RUTA_LESIONES.parent.mkdir(parents=True, exist_ok=True)

    if RUTA_LESIONES.exists():
        historico = pd.read_parquet(RUTA_LESIONES)
    else:
        print("No existe histórico local. Descargando lesiones 2012-2026...")
        historico = nfl.load_injuries(
            list(range(2012, TEMPORADA_ACTUAL + 1))
        ).to_pandas()

    try:
        actual = nfl.load_injuries([TEMPORADA_ACTUAL]).to_pandas()
    except Exception as error:
        disponible = historico[
            historico["season"] == TEMPORADA_ACTUAL
        ]
        if disponible.empty:
            raise RuntimeError(
                "No fue posible descargar lesiones y no hay datos locales "
                f"de {TEMPORADA_ACTUAL}."
            ) from error
        print(
            "ADVERTENCIA: no se pudo actualizar lesiones; "
            "se usará la copia local."
        )
        return historico

    anteriores = historico[
        historico["season"] != TEMPORADA_ACTUAL
    ].copy()
    lesiones = pd.concat([anteriores, actual], ignore_index=True)

    # Solo elimina filas totalmente identicas. La seleccion entre reportes
    # repetidos se hace despues por severidad en features_lesiones.py.
    lesiones = lesiones.drop_duplicates().reset_index(drop=True)
    lesiones.to_parquet(RUTA_LESIONES, index=False)

    print(f"Lesiones disponibles: {len(lesiones):,} registros.")
    return lesiones

def obtener_proxima_semana(calendario):

    pendientes = calendario[

        (calendario["season"] == TEMPORADA_ACTUAL)

        & (calendario["game_type"] == "REG")

        & (

            calendario["home_score"].isna()

            | calendario["away_score"].isna()

        )

    ].copy()

    if pendientes.empty:

        raise ValueError(

            "No se encontraron partidos pendientes."

        )

    proxima_semana = int(

        pendientes["week"].min()

    )

    return proxima_semana
