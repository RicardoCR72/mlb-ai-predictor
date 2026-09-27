"""Audita las fuentes necesarias para props NFL de recepcion."""

from pathlib import Path

import pandas as pd


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
DIRECTORIO_RAW = RAIZ_PROYECTO / "data" / "nfl" / "raw"
DIRECTORIO_PROCESADO = RAIZ_PROYECTO / "data" / "nfl" / "processed"
RUTA_LESIONES = DIRECTORIO_RAW / "nfl_injuries_2012_2026.parquet"

RUTAS_JUGADORES = [
    DIRECTORIO_RAW / "nfl_player_stats_2012_2026.parquet",
    DIRECTORIO_RAW / "nfl_player_stats.parquet",
    DIRECTORIO_RAW / "player_stats_2012_2026.parquet",
]

COLUMNAS_CLAVE = [
    "player_id", "player_name", "position", "team", "opponent_team",
    "game_id", "season", "week", "targets", "receptions",
    "receiving_yards", "receiving_tds", "receiving_air_yards",
    "receiving_yards_after_catch", "target_share", "air_yards_share",
    "carries", "rushing_yards", "rushing_tds", "passing_attempts",
    "passing_yards", "passing_tds", "fantasy_points",
]


def encontrar_archivo_jugadores():
    for ruta in RUTAS_JUGADORES:
        if ruta.exists():
            return ruta

    candidatos = sorted(DIRECTORIO_RAW.glob("*player*stat*.parquet"))
    if candidatos:
        return candidatos[0]

    raise FileNotFoundError(
        "No se encontro el parquet de estadisticas de jugadores en "
        f"{DIRECTORIO_RAW}"
    )


def porcentaje_nulos(df, columnas):
    disponibles = [columna for columna in columnas if columna in df.columns]
    return (
        df[disponibles]
        .isna()
        .mean()
        .mul(100)
        .round(2)
        .rename("porcentaje_nulos")
    )


def auditar_enlace_lesiones(jugadores):
    print("\n" + "=" * 72)
    print("ENLACE CON LESIONES")
    print("=" * 72)

    if not RUTA_LESIONES.exists():
        print(f"No existe: {RUTA_LESIONES}")
        return

    lesiones = pd.read_parquet(RUTA_LESIONES)
    if "gsis_id" not in lesiones.columns or "player_id" not in jugadores.columns:
        print("No estan disponibles gsis_id/player_id para enlazar.")
        return

    ofensivas = lesiones[
        lesiones["position"].isin(["WR", "TE", "RB", "FB"])
    ].copy()
    ofensivas = ofensivas[ofensivas["report_status"].notna()]

    ids_stats = set(
        jugadores["player_id"].dropna().astype(str).unique()
    )
    ofensivas["encontrado_stats"] = (
        ofensivas["gsis_id"].astype(str).isin(ids_stats)
    )

    print(f"Lesiones ofensivas con estado: {len(ofensivas):,}")
    print(
        "Coincidencia por ID: "
        f"{ofensivas['encontrado_stats'].mean() * 100:.2f}%"
    )


def main():
    ruta = encontrar_archivo_jugadores()
    print(f"Cargando: {ruta}")
    df = pd.read_parquet(ruta)

    print("\n" + "=" * 72)
    print("AUDITORIA DE DATOS PARA PROPS DE RECEPCION")
    print("=" * 72)
    print(f"Filas: {len(df):,}")
    print(f"Columnas: {len(df.columns):,}")

    print("\nColumnas clave disponibles:")
    for columna in COLUMNAS_CLAVE:
        estado = "SI" if columna in df.columns else "NO"
        print(f"  [{estado}] {columna}")

    requeridas = {
        "player_id", "position", "team", "season", "week",
        "targets", "receptions", "receiving_yards",
    }
    faltantes = sorted(requeridas - set(df.columns))
    if faltantes:
        raise KeyError(
            "No se puede construir el modelo. Faltan: "
            + ", ".join(faltantes)
        )

    numericas = [
        "season", "week", "targets", "receptions", "receiving_yards",
        "receiving_tds", "receiving_air_yards",
        "receiving_yards_after_catch", "carries", "rushing_yards",
    ]
    for columna in numericas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")

    claves = ["player_id", "season", "week"]
    if "game_id" in df.columns:
        claves = ["player_id", "game_id"]
    print(
        "\nDuplicados jugador-partido: "
        f"{df.duplicated(claves).sum():,}"
    )

    ofensivos = df[df["position"].isin(["WR", "TE", "RB", "FB"])].copy()
    print(f"Registros WR/TE/RB/FB: {len(ofensivos):,}")

    print("\nNulos en variables principales:")
    print(porcentaje_nulos(ofensivos, COLUMNAS_CLAVE).to_string())

    resumen_temporada = (
        ofensivos.groupby("season", as_index=False)
        .agg(
            registros=("player_id", "size"),
            jugadores=("player_id", "nunique"),
            targets=("targets", "sum"),
            recepciones=("receptions", "sum"),
            yardas_recepcion=("receiving_yards", "sum"),
        )
        .sort_values("season")
    )
    print("\nCobertura por temporada:")
    print(resumen_temporada.to_string(index=False))

    elegibles = ofensivos[ofensivos["targets"] >= 1]
    print("\nMuestra candidata con al menos un target:")
    print(f"Filas: {len(elegibles):,}")
    print(f"Jugadores: {elegibles['player_id'].nunique():,}")
    print(f"Recepciones promedio: {elegibles['receptions'].mean():.2f}")
    print(f"Yardas promedio: {elegibles['receiving_yards'].mean():.2f}")

    actual = ofensivos[ofensivos["season"] == ofensivos["season"].max()].copy()
    print("\nTemporada mas reciente:")
    print(f"Temporada: {int(ofensivos['season'].max())}")
    print(f"Registros: {len(actual):,}")
    print("Registros por semana:")
    print(actual.groupby("week").size().to_string())

    columnas_muestra = [
        columna for columna in [
            "player_id", "player_name", "position", "team", "week",
            "targets", "receptions", "receiving_yards", "receiving_tds",
        ] if columna in actual.columns
    ]
    muestra = actual.sort_values(
        ["week", "targets", "receiving_yards"],
        ascending=[False, False, False],
    )[columnas_muestra].head(30)
    print("\nMuestra reciente:")
    print(muestra.to_string(index=False))

    auditar_enlace_lesiones(df)

    DIRECTORIO_PROCESADO.mkdir(parents=True, exist_ok=True)
    ruta_salida = DIRECTORIO_PROCESADO / "auditoria_props_recepcion.csv"
    resumen_temporada.to_csv(ruta_salida, index=False)
    print(f"\nResumen guardado en:\n{ruta_salida}")
    print("\nAuditoria terminada correctamente.")


if __name__ == "__main__":
    main()
