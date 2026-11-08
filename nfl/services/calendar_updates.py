"""Responsabilidad extraída del flujo CLI NFL."""
from pathlib import Path
import pandas as pd
import nflreadpy as nfl
from nfl.settings import TEMPORADA_ACTUAL, RUTA_CALENDARIO, RUTA_DEPTH_CHARTS
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

    # Enriquecer líneas de Totales y Spread de la temporada actual desde ESPN / Bovada (0 Créditos)
    try:
        from nfl.proveedor_cuotas import obtener_jornada_nfl_espn
        partidos_en_vivo = obtener_jornada_nfl_espn()
        for p_live in partidos_en_vivo:
            vis = p_live.get("equipo_visita")
            loc = p_live.get("equipo_local")
            tot = p_live.get("linea_total")
            spd = p_live.get("spread_line")
            if not vis or not loc:
                continue
            mask = (
                (calendario["season"] == TEMPORADA_ACTUAL)
                & (calendario["away_team"] == vis)
                & (calendario["home_team"] == loc)
                & (calendario["home_score"].isna())
            )
            if mask.any():
                if tot is not None:
                    calendario.loc[mask, "total_line"] = float(tot)
                if spd is not None:
                    calendario.loc[mask, "spread_line"] = float(spd)
    except Exception as e_live:
        print(f"Aviso: No se pudieron sincronizar líneas en vivo en calendario: {e_live}")

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


def actualizar_depth_charts():
    """Descarga o actualiza el depth chart oficial de la temporada actual usando nflreadpy."""
    print(f"Actualizando depth charts de {TEMPORADA_ACTUAL}...")
    RUTA_DEPTH_CHARTS.parent.mkdir(parents=True, exist_ok=True)
    try:
        df = nfl.load_depth_charts([TEMPORADA_ACTUAL]).to_pandas()
        df.to_parquet(RUTA_DEPTH_CHARTS, index=False)
        print(f"Depth charts actualizados: {len(df):,} registros.")
        return df
    except Exception as error:
        if RUTA_DEPTH_CHARTS.exists():
            print(
                f"ADVERTENCIA: no se pudo descargar depth charts ({error}); "
                "se usará la copia local."
            )
            return pd.read_parquet(RUTA_DEPTH_CHARTS)
        raise RuntimeError(
            f"No fue posible descargar depth charts de {TEMPORADA_ACTUAL} y no hay copia local: {error}"
        ) from error


def cargar_mapeo_depth_chart():
    """Retorna un DataFrame con el orden jerárquico (depth_rank) oficial más reciente por jugador y equipo.
    
    Incluye mapeo por player_id (gsis_id) y nombres normalizados para resolver jerarquías
    de RB, QB, WR y TE.
    """
    if not RUTA_DEPTH_CHARTS.exists():
        actualizar_depth_charts()

    df = pd.read_parquet(RUTA_DEPTH_CHARTS)
    if "dt" in df.columns:
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
        df = df.sort_values("dt")
    
    posiciones = ["RB", "QB", "WR", "TE"]
    if "pos_abb" in df.columns:
        df = df[df["pos_abb"].isin(posiciones)].copy()

    # Conserva la entrada más reciente por (equipo, jugador)
    if "gsis_id" in df.columns:
        latest = df.dropna(subset=["gsis_id"]).drop_duplicates(subset=["team", "gsis_id"], keep="last").copy()
    else:
        latest = df.drop_duplicates(subset=["team", "player_name"], keep="last").copy()

    latest["depth_rank"] = pd.to_numeric(latest["pos_rank"], errors="coerce").fillna(99).astype(int)
    
    mapeo = latest[["team", "player_name", "gsis_id", "pos_abb", "depth_rank"]].rename(
        columns={"gsis_id": "player_id", "pos_abb": "position"}
    )
    return mapeo
