"""Construye datasets jugador-partido para props NFL de pase y carrera.

Salidas:
* nfl_props_pase_features_2012_2026.parquet
* nfl_props_carrera_features_2012_2026.parquet

Todas las variables historicas se desplazan un partido con shift(1) para
evitar que el resultado del partido objetivo entre en sus propias features.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from features_lesiones import normalizar_lesiones


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RAW = RAIZ_PROYECTO / "data" / "nfl" / "raw"
PROCESSED = RAIZ_PROYECTO / "data" / "nfl" / "processed"

RUTA_JUGADORES = RAW / "nfl_player_stats_2012_2026.parquet"
RUTA_PARTIDOS = RAW / "nfl_schedules_2012_2026.parquet"
RUTA_LESIONES = RAW / "nfl_injuries_2012_2026.parquet"
RUTA_PASE = PROCESSED / "nfl_props_pase_features_2012_2026.parquet"
RUTA_CARRERA = PROCESSED / "nfl_props_carrera_features_2012_2026.parquet"

VENTANAS = [3, 5, 8]
POSICIONES_PASE = ["QB"]
POSICIONES_CARRERA = ["QB", "RB", "FB", "WR", "TE"]

METRICAS_PASE = [
    "passing_attempts",
    "passing_completions",
    "passing_yards",
    "passing_tds",
    "interceptions",
    "sacks",
    "passing_air_yards",
    "passing_yards_after_catch",
    "passing_first_downs",
    "passing_epa",
]

METRICAS_CARRERA = [
    "carries",
    "rushing_yards",
    "rushing_tds",
    "rushing_first_downs",
    "rushing_epa",
    "rushing_fumbles",
    "rushing_fumbles_lost",
]

POSICIONES_SKILL = {"RB", "FB", "WR", "TE"}
POSICIONES_OL = {"C", "G", "OG", "T", "OT", "OL"}
POSICIONES_DEFENSA = {
    "CB", "DB", "DE", "DL", "DT", "EDGE", "FS", "ILB", "LB",
    "MLB", "NT", "OLB", "S", "SAF", "SS",
}


def asegurar_columna(df, nombre, aliases=(), valor=0.0):
    """Crea una columna canonica usando el primer alias disponible."""
    if nombre in df.columns:
        return
    for alias in aliases:
        if alias in df.columns:
            df[nombre] = df[alias]
            return
    df[nombre] = valor


def normalizar_columnas_estadisticas(jugadores):
    df = jugadores.copy()
    asegurar_columna(df, "passing_attempts", ["attempts"])
    asegurar_columna(df, "passing_completions", ["completions"])
    asegurar_columna(df, "interceptions", ["passing_interceptions"])
    asegurar_columna(df, "sacks", ["sacks_suffered"])

    for columna in METRICAS_PASE + METRICAS_CARRERA:
        asegurar_columna(df, columna)
        df[columna] = pd.to_numeric(df[columna], errors="coerce").fillna(0.0)

    for columna in ["season", "week"]:
        df[columna] = pd.to_numeric(df[columna], errors="coerce")

    for columna in [
        "player_id", "player_name", "position", "team", "opponent_team",
        "game_id",
    ]:
        if columna not in df.columns:
            raise KeyError(f"Falta la columna obligatoria: {columna}")
        df[columna] = df[columna].fillna("").astype(str).str.strip()

    df["position"] = df["position"].str.upper()
    df["team"] = df["team"].str.upper()
    df["opponent_team"] = df["opponent_team"].str.upper()
    return df


def cargar_datos():
    for ruta in [RUTA_JUGADORES, RUTA_PARTIDOS, RUTA_LESIONES]:
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontro: {ruta}")

    jugadores = normalizar_columnas_estadisticas(pd.read_parquet(RUTA_JUGADORES))
    partidos = pd.read_parquet(RUTA_PARTIDOS)
    lesiones = pd.read_parquet(RUTA_LESIONES)

    partidos["gameday"] = pd.to_datetime(partidos["gameday"], errors="coerce")
    partidos = partidos[
        (partidos["game_type"] == "REG")
        & partidos["home_score"].notna()
        & partidos["away_score"].notna()
    ].copy()

    columnas_partido = [
        "game_id", "gameday", "home_team", "away_team",
        "home_qb_id", "away_qb_id", "home_rest", "away_rest",
        "roof", "surface", "temp", "wind", "spread_line", "total_line",
        "home_moneyline", "away_moneyline", "div_game",
    ]
    columnas_partido = [c for c in columnas_partido if c in partidos.columns]
    jugadores = jugadores.merge(
        partidos[columnas_partido],
        on="game_id",
        how="inner",
        validate="many_to_one",
    )

    jugadores["is_home"] = jugadores["team"].eq(
        jugadores["home_team"].astype(str).str.upper()
    ).astype(int)
    jugadores["rest"] = np.where(
        jugadores["is_home"].eq(1),
        jugadores.get("home_rest", np.nan),
        jugadores.get("away_rest", np.nan),
    )
    jugadores["starting_qb_id"] = np.where(
        jugadores["is_home"].eq(1),
        jugadores.get("home_qb_id", ""),
        jugadores.get("away_qb_id", ""),
    )
    jugadores["is_starting_qb"] = (
        jugadores["player_id"].astype(str)
        == jugadores["starting_qb_id"].fillna("").astype(str)
    ).astype(int)

    for columna in [
        "rest", "temp", "wind", "spread_line", "total_line",
        "home_moneyline", "away_moneyline", "div_game",
    ]:
        if columna not in jugadores.columns:
            jugadores[columna] = np.nan
        jugadores[columna] = pd.to_numeric(jugadores[columna], errors="coerce")

    jugadores = jugadores.sort_values(
        ["player_id", "gameday", "game_id"]
    ).reset_index(drop=True)
    return jugadores, lesiones


def media_previa(serie, ventana):
    return serie.shift(1).rolling(ventana, min_periods=1).mean()


def desviacion_previa(serie, ventana):
    return serie.shift(1).rolling(ventana, min_periods=2).std()


def agregar_forma_jugador(df, metricas, prefijo_objetivo):
    resultado = df.copy()
    grupo = resultado.groupby("player_id", group_keys=False)
    grupo_temporada = resultado.groupby(
        ["player_id", "season"], group_keys=False
    )

    resultado["player_games_before"] = grupo.cumcount()
    resultado["player_games_before_season"] = grupo_temporada.cumcount()

    for metrica in metricas:
        for ventana in VENTANAS:
            resultado[f"player_{metrica}_avg_{ventana}"] = (
                grupo[metrica].transform(
                    lambda serie, w=ventana: media_previa(serie, w)
                )
            )
        resultado[f"player_{metrica}_avg_season"] = (
            grupo_temporada[metrica].transform(
                lambda serie: serie.shift(1).expanding(min_periods=1).mean()
            )
        )

    for ventana in [5, 8]:
        resultado[f"player_{prefijo_objetivo}_std_{ventana}"] = (
            grupo[prefijo_objetivo].transform(
                lambda serie, w=ventana: desviacion_previa(serie, w)
            )
        )
    return resultado


def agregar_rates_pase(df):
    intentos = df["player_passing_attempts_avg_5"].replace(0, np.nan)
    df["player_completion_rate_5"] = (
        df["player_passing_completions_avg_5"] / intentos
    )
    df["player_passing_yards_per_attempt_5"] = (
        df["player_passing_yards_avg_5"] / intentos
    )
    df["player_passing_td_rate_5"] = (
        df["player_passing_tds_avg_5"] / intentos
    )
    df["player_interception_rate_5"] = (
        df["player_interceptions_avg_5"] / intentos
    )
    return df


def agregar_rates_carrera(df):
    acarreos = df["player_carries_avg_5"].replace(0, np.nan)
    df["player_rushing_yards_per_carry_5"] = (
        df["player_rushing_yards_avg_5"] / acarreos
    )
    df["player_rushing_td_rate_5"] = (
        df["player_rushing_tds_avg_5"] / acarreos
    )
    return df


def agregar_contexto_equipo(df, metricas, nombre):
    agregaciones = {f"team_{m}": (m, "sum") for m in metricas}
    totales = (
        df.groupby(
            ["game_id", "gameday", "season", "week", "team"],
            as_index=False,
        )
        .agg(**agregaciones)
        .sort_values(["team", "gameday", "game_id"])
    )
    grupo = totales.groupby("team", group_keys=False)
    for metrica in agregaciones:
        for ventana in VENTANAS:
            totales[f"{metrica}_avg_{ventana}"] = grupo[metrica].transform(
                lambda serie, w=ventana: media_previa(serie, w)
            )

    columnas = [
        c for c in totales.columns
        if c in ["game_id", "team"] or c.startswith("team_") and "_avg_" in c
    ]
    resultado = df.merge(
        totales[columnas],
        on=["game_id", "team"],
        how="left",
        validate="many_to_one",
    )
    print(f"  Contexto de equipo {nombre}: {len(columnas) - 2} features")
    return resultado


def agregar_defensa_rival(df, metricas, nombre):
    agregaciones = {f"allowed_{m}": (m, "sum") for m in metricas}
    permitidos = (
        df.groupby(
            ["game_id", "gameday", "season", "week", "opponent_team"],
            as_index=False,
        )
        .agg(**agregaciones)
        .sort_values(["opponent_team", "gameday", "game_id"])
    )
    grupo = permitidos.groupby("opponent_team", group_keys=False)
    for metrica in agregaciones:
        for ventana in VENTANAS:
            permitidos[f"opp_{metrica}_avg_{ventana}"] = (
                grupo[metrica].transform(
                    lambda serie, w=ventana: media_previa(serie, w)
                )
            )

    columnas = [
        c for c in permitidos.columns
        if c in ["game_id", "opponent_team"]
        or c.startswith("opp_allowed_")
    ]
    resultado = df.merge(
        permitidos[columnas],
        on=["game_id", "opponent_team"],
        how="left",
        validate="many_to_one",
    )
    print(f"  Defensa rival {nombre}: {len(columnas) - 2} features")
    return resultado


def agregar_lesiones(df, lesiones):
    reportes = normalizar_lesiones(lesiones)
    reportes["is_qb"] = reportes["position"].eq("QB").astype(float)
    reportes["is_skill"] = reportes["position"].isin(POSICIONES_SKILL).astype(float)
    reportes["is_ol"] = reportes["position"].isin(POSICIONES_OL).astype(float)
    reportes["is_defense"] = reportes["position"].isin(POSICIONES_DEFENSA).astype(float)

    for grupo in ["qb", "skill", "ol", "defense"]:
        reportes[f"{grupo}_injury_score"] = (
            reportes["injury_weight"] * reportes[f"is_{grupo}"]
        )
        reportes[f"{grupo}_injury_count"] = reportes[f"is_{grupo}"]

    columnas_resumen = [
        f"{grupo}_injury_{metrica}"
        for grupo in ["qb", "skill", "ol", "defense"]
        for metrica in ["score", "count"]
    ]
    resumen = (
        reportes.groupby(["season", "week", "team"], as_index=False)[
            columnas_resumen
        ].sum()
    )

    propias = reportes[
        [
            "season", "week", "team", "gsis_id", "injury_weight",
            "report_status_norm",
        ]
    ].rename(
        columns={
            "gsis_id": "player_id",
            "injury_weight": "player_injury_score",
            "report_status_norm": "player_injury_status",
        }
    )
    propias["player_id"] = propias["player_id"].fillna("").astype(str)

    propias_equipo = resumen.add_prefix("team_").rename(
        columns={
            "team_season": "season",
            "team_week": "week",
            "team_team": "team",
        }
    )
    rivales = resumen.add_prefix("opp_").rename(
        columns={
            "opp_season": "season",
            "opp_week": "week",
            "opp_team": "opponent_team",
        }
    )

    resultado = (
        df.merge(
            propias_equipo,
            on=["season", "week", "team"],
            how="left",
            validate="many_to_one",
        )
        .merge(
            rivales,
            on=["season", "week", "opponent_team"],
            how="left",
            validate="many_to_one",
        )
        .merge(
            propias,
            on=["season", "week", "team", "player_id"],
            how="left",
            validate="many_to_one",
        )
    )
    columnas_lesiones = [
        c for c in resultado.columns
        if c.startswith("team_") and "injury_" in c
        or c.startswith("opp_") and "injury_" in c
    ]
    resultado[columnas_lesiones + ["player_injury_score"]] = resultado[
        columnas_lesiones + ["player_injury_score"]
    ].fillna(0.0)
    resultado["player_injury_status"] = resultado[
        "player_injury_status"
    ].fillna("healthy_or_unlisted")
    return resultado


def columnas_comunes(df):
    columnas = [
        "game_id", "gameday", "season", "week", "player_id", "player_name",
        "position", "team", "opponent_team", "is_home", "rest",
        "is_starting_qb", "starting_qb_id", "roof", "surface", "temp", "wind",
        "spread_line", "total_line", "home_moneyline", "away_moneyline",
        "div_game",
    ]
    return [c for c in columnas if c in df.columns]


def construir_dataset_pase(jugadores, lesiones):
    base = jugadores[jugadores["position"].isin(POSICIONES_PASE)].copy()
    base = base[columnas_comunes(base) + METRICAS_PASE]
    base = base.sort_values(["player_id", "gameday", "game_id"]).reset_index(drop=True)

    resultado = agregar_forma_jugador(base, METRICAS_PASE, "passing_yards")
    resultado = agregar_rates_pase(resultado)
    resultado = agregar_contexto_equipo(resultado, METRICAS_PASE[:6], "pase")
    resultado = agregar_defensa_rival(resultado, METRICAS_PASE[:6], "pase")
    resultado = agregar_lesiones(resultado, lesiones)
    return resultado


def construir_dataset_carrera(jugadores, lesiones):
    base = jugadores[jugadores["position"].isin(POSICIONES_CARRERA)].copy()
    base = base[columnas_comunes(base) + METRICAS_CARRERA]
    base = base.sort_values(["player_id", "gameday", "game_id"]).reset_index(drop=True)

    resultado = agregar_forma_jugador(base, METRICAS_CARRERA, "rushing_yards")
    resultado = agregar_rates_carrera(resultado)
    resultado = agregar_contexto_equipo(resultado, METRICAS_CARRERA[:4], "carrera")
    resultado = agregar_defensa_rival(resultado, METRICAS_CARRERA[:4], "carrera")
    resultado = agregar_lesiones(resultado, lesiones)
    return resultado


def validar_dataset(df, nombre, volumen, objetivos, umbral):
    print("\n" + "=" * 76)
    print(f"VALIDACION DATASET PROPS DE {nombre.upper()}")
    print("=" * 76)
    print(f"Filas totales: {len(df):,}")
    print(f"Columnas: {len(df.columns):,}")
    print(
        "Duplicados jugador-partido: "
        f"{df.duplicated(['player_id', 'game_id']).sum():,}"
    )

    columna_volumen = f"player_{volumen}_avg_5"
    elegibles = df[
        (df["player_games_before"] >= 3)
        & (df[columna_volumen] >= umbral)
    ].copy()
    print(
        f"Filas elegibles (3 juegos previos, {volumen} avg >= {umbral}): "
        f"{len(elegibles):,}"
    )
    print("\nFilas elegibles por temporada:")
    print(elegibles.groupby("season").size().to_string())
    print("\nObjetivos en muestra elegible:")
    for objetivo in objetivos:
        print(f"{objetivo}: media {elegibles[objetivo].mean():.3f}")

    control = [
        columna_volumen,
        f"player_{objetivos[0]}_avg_5",
        f"opp_allowed_{objetivos[0]}_avg_5",
        "player_injury_score",
    ]
    control = [c for c in control if c in elegibles.columns]
    print("\nNulos en features principales (%):")
    print(elegibles[control].isna().mean().mul(100).round(2).to_string())


def main():
    print("Cargando estadisticas, calendario y lesiones...")
    jugadores, lesiones = cargar_datos()

    print("\nConstruyendo dataset de pase...")
    pase = construir_dataset_pase(jugadores, lesiones)
    pase = pase.sort_values(
        ["season", "week", "gameday", "game_id", "player_id"]
    ).reset_index(drop=True)

    print("\nConstruyendo dataset de carrera...")
    carrera = construir_dataset_carrera(jugadores, lesiones)
    carrera = carrera.sort_values(
        ["season", "week", "gameday", "game_id", "player_id"]
    ).reset_index(drop=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    pase.to_parquet(RUTA_PASE, index=False)
    carrera.to_parquet(RUTA_CARRERA, index=False)

    validar_dataset(
        pase,
        "pase",
        "passing_attempts",
        ["passing_yards", "passing_tds"],
        10.0,
    )
    validar_dataset(
        carrera,
        "carrera",
        "carries",
        ["rushing_yards", "rushing_tds"],
        2.0,
    )

    print("\nArchivos guardados en:")
    print(RUTA_PASE)
    print(RUTA_CARRERA)
    print("\nConstruccion terminada correctamente.")


if __name__ == "__main__":
    main()
