import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
from jornada import calendario_hoy

from pathlib import Path

import joblib

import mysql.connector

import nflreadpy as nfl

import numpy as np

import pandas as pd

from construir_dataset_partidos import (

    convertir_formato_equipo,

    construir_features_equipos,

    unir_features_partidos,

)

from nfl.feature_spec import (

    FEATURES_BASE,

    FEATURES_CATEGORICAS,

    FEATURES_MERCADO,

)

from features_lesiones import (
    RUTA_LESIONES,
    agregar_contexto_lesiones,
    agregar_features_lesiones,
    cargar_lesiones,
)

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]

RUTA_CALENDARIO = (

    RAIZ_PROYECTO

    / "data"

    / "nfl"

    / "raw"

    / "nfl_schedules_2012_2026.parquet"

)

RUTA_MODELO_MERCADO = (

    RAIZ_PROYECTO

    / "modelos_nfl"

    / "total_con_mercado.joblib"

)

RUTA_MODELO_BASE = (

    RAIZ_PROYECTO

    / "modelos_nfl"

    / "total_sin_mercado.joblib"

)

RUTA_CALIBRADOR = (

    RAIZ_PROYECTO

    / "modelos_nfl"

    / "calibrador_pick_totales.joblib"

)

DIRECTORIO_PREDICCIONES = (

    RAIZ_PROYECTO

    / "data"

    / "nfl"

    / "predictions"

)

TEMPORADA_ACTUAL = 2026

EDGE_MINIMO = 3.0

MODELO_VERSION = "totales_v2_seleccion_automatica"

def obtener_variable_entorno(*nombres, obligatoria=False):

    """Obtiene la primera variable de entorno disponible."""

    for nombre in nombres:

        valor = os.getenv(nombre)

        if valor not in (None, ""):

            return valor

    if obligatoria:

        raise ValueError(

            "Falta configurar una de estas variables: "

            + ", ".join(nombres)

        )

    return None

def obtener_configuracion_mysql():
    from core.db import get_db_credentials
    return get_db_credentials()

from nfl.persistence.totals import valor_mysql, guardar_predicciones_mysql

from nfl.services.totals_engine import american_a_decimal, obtener_columnas_modelo, generar_predicciones

from nfl.services.calendar_updates import actualizar_calendario, actualizar_lesiones, obtener_proxima_semana



def preparar_features(calendario, proxima_semana, game_ids=None):

    regulares = calendario[

        calendario["game_type"] == "REG"

    ].copy()

    terminados = regulares[

        regulares["home_score"].notna()

        & regulares["away_score"].notna()

    ].copy()

    proximos = regulares[

        (regulares["season"] == TEMPORADA_ACTUAL)

        & (regulares["week"] == proxima_semana)

        & (

            regulares["home_score"].isna()

            | regulares["away_score"].isna()

        )

    ].copy()

    if game_ids is not None:
        proximos = proximos[proximos['game_id'].isin(game_ids)].copy()

    if proximos.empty:

        raise ValueError(

            f"No hay partidos pendientes en Semana "

            f"{proxima_semana}."

        )

    # Únicamente agregamos la siguiente semana.

    # Así, ningún partido futuro intermedio contamina

    # las medias móviles de otro encuentro.

    base = pd.concat(

        [terminados, proximos],

        ignore_index=True,

    )

    base = base.sort_values(

        ["season", "week", "gameday", "game_id"]

    ).reset_index(drop=True)

    equipos = convertir_formato_equipo(base)

    equipos = construir_features_equipos(equipos)

    dataset = unir_features_partidos(

        base,

        equipos,

    )

    lesiones = cargar_lesiones()
    lesiones_semana = lesiones[
        (pd.to_numeric(lesiones["season"], errors="coerce") == TEMPORADA_ACTUAL)
        & (pd.to_numeric(lesiones["week"], errors="coerce") == proxima_semana)
    ]
    if lesiones_semana.empty:
        raise ValueError(
            f"No hay reportes de lesiones para {TEMPORADA_ACTUAL}, "
            f"Semana {proxima_semana}. Se detiene para no predecir con ceros."
        )

    print(
        f"Reportes de lesiones de la semana: {len(lesiones_semana):,}"
    )
    dataset = agregar_features_lesiones(
        dataset,
        base,
        lesiones,
    )
    dataset = agregar_contexto_lesiones(
        dataset,
        base,
        lesiones,
    )

    prediccion = dataset[

        (dataset["season"] == TEMPORADA_ACTUAL)

        & (dataset["week"] == proxima_semana)

        & (

            dataset["home_score"].isna()

            | dataset["away_score"].isna()

        )

    ].copy()

    if game_ids is not None:
        prediccion = prediccion[prediccion['game_id'].isin(game_ids)].copy()
    return prediccion

def cargar_modelos():

    rutas = [

        RUTA_MODELO_MERCADO,

        RUTA_MODELO_BASE,

        RUTA_CALIBRADOR,

    ]

    for ruta in rutas:

        if not ruta.exists():

            raise FileNotFoundError(

                f"No se encontró: {ruta}"

            )

    modelo_mercado = joblib.load(

        RUTA_MODELO_MERCADO

    )

    modelo_base = joblib.load(

        RUTA_MODELO_BASE

    )

    calibrador = joblib.load(

        RUTA_CALIBRADOR

    )

    return (

        modelo_mercado,

        modelo_base,

        calibrador,

    )

def mostrar_resultados(df, semana):

    columnas = [

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

    ]

    tabla = df[columnas].copy()

    redondear = [

        "total_line",

        "pred_total",

        "pred_total_base",

        "edge",

        "odds_pick",

    ]

    for columna in redondear:

        tabla[columna] = (

            tabla[columna].round(2)

        )

    porcentajes = [

        "prob_pick",

        "prob_over",

        "prob_under",

        "ev",

    ]

    for columna in porcentajes:

        tabla[columna] = (

            tabla[columna] * 100

        ).round(2)

    tabla = tabla.sort_values(

        ["estado", "prob_pick"],

        ascending=[True, False],

    )

    print("\n" + "=" * 100)

    print(

        f"PREDICCIONES NFL - "

        f"TEMPORADA {TEMPORADA_ACTUAL} "

        f"SEMANA {semana}"

    )

    print("=" * 100)

    print(tabla.to_string(index=False))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--solo-hoy', action='store_true')
    parser.add_argument('--proximas-horas', type=float, default=None)
    args = parser.parse_args()
    if args.proximas_horas is not None and (args.proximas_horas <= 0 or not args.solo_hoy):
        parser.error('--proximas-horas requiere --solo-hoy y un valor positivo')

    DIRECTORIO_PREDICCIONES.mkdir(

        parents=True,

        exist_ok=True,

    )

    calendario = actualizar_calendario()

    game_ids = None
    if args.solo_hoy:
        hoy = calendario_hoy(calendario[
            calendario['season'].eq(TEMPORADA_ACTUAL) & calendario['game_type'].eq('REG')
            & (calendario['home_score'].isna() | calendario['away_score'].isna())])
        if args.proximas_horas is not None:
            hoy = calendario_hoy(hoy, proximas_horas=args.proximas_horas)
        if hoy.empty:
            print('No hay partidos NFL de hoy sin iniciar; no se generan predicciones.')
            return
        game_ids = hoy['game_id'].tolist()
        proxima_semana = int(hoy['week'].min())
    else:
        proxima_semana = obtener_proxima_semana(calendario)
    actualizar_lesiones()

    print(

        f"Próxima semana detectada: "

        f"{proxima_semana}"

    )

    print("Construyendo variables previas...")

    proximos = preparar_features(

        calendario,

        proxima_semana,
        game_ids=game_ids,
    )

    (

        modelo_mercado,

        modelo_base,

        calibrador,

    ) = cargar_modelos()

    print("Generando predicciones...")

    predicciones = generar_predicciones(

        proximos,

        modelo_mercado,

        modelo_base,

        calibrador,

    )

    if args.solo_hoy:
        predicciones = calendario_hoy(predicciones)
        if predicciones.empty:
            print('Los partidos ya comenzaron; no se guardan nuevas predicciones prepartido.')
            return

    ruta_salida = (

        DIRECTORIO_PREDICCIONES

        / (

            f"nfl_totales_"

            f"{TEMPORADA_ACTUAL}_"

            f"semana_{proxima_semana}" + ("_hoy" if args.solo_hoy else "") + ".csv"

        )

    )

    predicciones.to_csv(

        ruta_salida,

        index=False,

    )

    print("Sincronizando predicciones con MySQL...")

    if not guardar_predicciones_mysql(predicciones):
        raise RuntimeError('No se guardaron las predicciones en MySQL.')

    mostrar_resultados(

        predicciones,

        proxima_semana,

    )

    print("\nArchivo guardado:")

    print(ruta_salida)

if __name__ == "__main__":

    main()
