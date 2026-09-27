from pathlib import Path

import nflreadpy as nfl
import pandas as pd


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_SALIDA = (
    RAIZ_PROYECTO
    / "data"
    / "nfl"
    / "raw"
    / "nfl_injuries_2012_2026.parquet"
)
TEMPORADAS = list(range(2012, 2027))


def descargar_lesiones():
    bloques = []
    errores = []

    for temporada in TEMPORADAS:
        print(f"Descargando lesiones {temporada}...")
        try:
            datos = nfl.load_injuries([temporada]).to_pandas()
            if datos.empty:
                errores.append((temporada, "sin registros"))
                continue

            bloques.append(datos)
            print(f"  Registros: {len(datos):,}")
        except Exception as error:
            errores.append((temporada, str(error)))
            print(f"  No disponible: {error}")

    if not bloques:
        raise RuntimeError(
            "No fue posible descargar ninguna temporada de lesiones."
        )

    return pd.concat(bloques, ignore_index=True), errores


def main():
    lesiones, errores = descargar_lesiones()

    columnas_requeridas = {
        "season",
        "season_type",
        "team",
        "week",
        "gsis_id",
        "position",
        "full_name",
        "report_primary_injury",
        "report_status",
        "practice_status",
        "date_modified",
    }
    faltantes = sorted(columnas_requeridas - set(lesiones.columns))
    if faltantes:
        raise ValueError(
            "Faltan columnas requeridas: " + ", ".join(faltantes)
        )

    lesiones["season"] = pd.to_numeric(
        lesiones["season"], errors="coerce"
    ).astype("Int64")
    lesiones["week"] = pd.to_numeric(
        lesiones["week"], errors="coerce"
    ).astype("Int64")
    lesiones["date_modified"] = pd.to_datetime(
        lesiones["date_modified"], errors="coerce", utc=True
    )

    lesiones = lesiones.sort_values(
        ["season", "week", "team", "gsis_id", "date_modified"]
    ).reset_index(drop=True)

    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    lesiones.to_parquet(RUTA_SALIDA, index=False)

    print("\n" + "=" * 72)
    print("AUDITORÍA DE LESIONES NFL")
    print("=" * 72)
    print(f"Filas totales: {len(lesiones):,}")
    print(f"Columnas: {len(lesiones.columns)}")
    print("\nRegistros por temporada:")
    print(lesiones.groupby("season").size().to_string())

    duplicados = lesiones.duplicated(
        subset=["season", "week", "team", "gsis_id"],
        keep=False,
    ).sum()
    print(
        "\nFilas en jugador-semana repetidas "
        f"(antes de elegir el reporte final): {duplicados:,}"
    )

    print("\nEstados finales del reporte:")
    print(
        lesiones["report_status"]
        .fillna("SIN ESTADO")
        .value_counts()
        .head(20)
        .to_string()
    )

    print("\nEstados de práctica:")
    print(
        lesiones["practice_status"]
        .fillna("SIN ESTADO")
        .value_counts()
        .head(20)
        .to_string()
    )

    actual = lesiones[lesiones["season"] == 2026].copy()
    print("\n" + "=" * 72)
    print("TEMPORADA 2026")
    print("=" * 72)
    print(f"Registros: {len(actual):,}")

    if not actual.empty:
        print("Semanas disponibles:")
        print(actual.groupby("week").size().to_string())

        semana_actual = int(actual["week"].max())
        reporte = actual[
            (actual["week"] == semana_actual)
            & actual["position"].isin(
                ["QB", "RB", "WR", "TE", "T", "G", "C", "OT"]
            )
        ][
            [
                "team",
                "week",
                "position",
                "full_name",
                "report_primary_injury",
                "report_status",
                "practice_status",
                "date_modified",
            ]
        ].sort_values(["team", "position", "full_name"])

        print(
            f"\nJugadores ofensivos reportados en Semana {semana_actual}:"
        )
        print(reporte.to_string(index=False))

    if errores:
        print("\nTemporadas no disponibles:")
        for temporada, detalle in errores:
            print(f"  {temporada}: {detalle}")

    print(f"\nArchivo guardado en:\n{RUTA_SALIDA}")


if __name__ == "__main__":
    main()
