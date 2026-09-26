import os
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

from entrenar_totales import (
    FEATURES_BASE,
    FEATURES_CATEGORICAS,
    FEATURES_MERCADO,
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
MODELO_VERSION = "totales_v1"


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
    """
    Construye la configuración de Aiven/MySQL.

    Acepta tanto los nombres DB_* recomendados para GitHub Actions
    como los nombres cortos que ya usa la aplicación Streamlit.
    Si no hay credenciales, devuelve None y permite conservar el CSV.
    """
    host = obtener_variable_entorno(
        "DB_HOST",
        "MYSQL_HOST",
        "host",
    )
    usuario = obtener_variable_entorno(
        "DB_USER",
        "MYSQL_USER",
        "user",
    )
    password = obtener_variable_entorno(
        "DB_PASSWORD",
        "MYSQL_PASSWORD",
        "password",
    )
    base_datos = obtener_variable_entorno(
        "DB_NAME",
        "MYSQL_DATABASE",
        "database",
    )

    if not all([host, usuario, password, base_datos]):
        return None

    puerto = obtener_variable_entorno(
        "DB_PORT",
        "MYSQL_PORT",
        "port",
    ) or "3306"

    configuracion = {
        "host": host,
        "port": int(puerto),
        "user": usuario,
        "password": password,
        "database": base_datos,
        "connection_timeout": 20,
        "ssl_disabled": False,
    }

    ruta_ca = obtener_variable_entorno(
        "DB_SSL_CA",
        "MYSQL_SSL_CA",
        "ssl_ca",
    )

    if ruta_ca:
        configuracion["ssl_ca"] = ruta_ca
        configuracion["ssl_verify_cert"] = True

    return configuracion


def valor_mysql(valor):
    """Convierte tipos de pandas/numpy a valores compatibles con MySQL."""
    if pd.isna(valor):
        return None

    if isinstance(valor, np.generic):
        return valor.item()

    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()

    return valor


def guardar_predicciones_mysql(predicciones):
    """
    Inserta o actualiza el calendario y las predicciones de totales.

    Un fallo de base de datos no elimina el CSV ni detiene el predictor.
    """
    configuracion = obtener_configuracion_mysql()

    if configuracion is None:
        print(
            "ADVERTENCIA: no se configuraron las variables de MySQL. "
            "Se conservará únicamente el archivo CSV."
        )
        return False

    conexion = None
    cursor = None

    try:
        conexion = mysql.connector.connect(**configuracion)
        cursor = conexion.cursor()

        sql_juego = """
            INSERT INTO nfl_juegos (
                id_juego,
                temporada,
                tipo_juego,
                semana,
                fecha,
                equipo_local,
                equipo_visitante,
                marcador_local,
                marcador_visitante,
                estado
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                temporada = VALUES(temporada),
                tipo_juego = VALUES(tipo_juego),
                semana = VALUES(semana),
                fecha = VALUES(fecha),
                equipo_local = VALUES(equipo_local),
                equipo_visitante = VALUES(equipo_visitante),
                marcador_local = VALUES(marcador_local),
                marcador_visitante = VALUES(marcador_visitante),
                estado = VALUES(estado)
        """

        juegos = []

        for _, fila in predicciones.iterrows():
            terminado = (
                pd.notna(fila.get("home_score"))
                and pd.notna(fila.get("away_score"))
            )

            juegos.append(
                (
                    str(fila["game_id"]),
                    int(fila["season"]),
                    str(fila.get("game_type", "REG")),
                    int(fila["week"]),
                    valor_mysql(fila["gameday"]),
                    str(fila["home_team"]),
                    str(fila["away_team"]),
                    valor_mysql(fila.get("home_score")),
                    valor_mysql(fila.get("away_score")),
                    "finalizado" if terminado else "programado",
                )
            )

        cursor.executemany(sql_juego, juegos)

        sql_prediccion = """
            INSERT INTO nfl_predicciones_totales (
                id_juego,
                modelo_version,
                linea_total,
                total_proyectado,
                total_proyectado_base,
                edge,
                seleccion,
                probabilidad_pick,
                probabilidad_over,
                probabilidad_under,
                cuota_pick,
                ev_estimado,
                estado_pick
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                linea_total = VALUES(linea_total),
                total_proyectado = VALUES(total_proyectado),
                total_proyectado_base = VALUES(total_proyectado_base),
                edge = VALUES(edge),
                seleccion = VALUES(seleccion),
                probabilidad_pick = VALUES(probabilidad_pick),
                probabilidad_over = VALUES(probabilidad_over),
                probabilidad_under = VALUES(probabilidad_under),
                cuota_pick = VALUES(cuota_pick),
                ev_estimado = VALUES(ev_estimado),
                estado_pick = VALUES(estado_pick)
        """

        filas_validas = predicciones[
            predicciones["total_line"].notna()
            & predicciones["pred_total"].notna()
            & predicciones["edge"].notna()
        ]

        registros = []

        for _, fila in filas_validas.iterrows():
            registros.append(
                (
                    str(fila["game_id"]),
                    MODELO_VERSION,
                    valor_mysql(fila["total_line"]),
                    valor_mysql(fila["pred_total"]),
                    valor_mysql(fila["pred_total_base"]),
                    valor_mysql(fila["edge"]),
                    str(fila["pick"]),
                    valor_mysql(fila["prob_pick"] * 100),
                    valor_mysql(fila["prob_over"] * 100),
                    valor_mysql(fila["prob_under"] * 100),
                    valor_mysql(fila["odds_pick"]),
                    valor_mysql(fila["ev"] * 100),
                    str(fila["estado"]),
                )
            )

        if registros:
            cursor.executemany(sql_prediccion, registros)

        conexion.commit()

        print(
            "MySQL actualizado: "
            f"{len(juegos)} juegos y "
            f"{len(registros)} predicciones."
        )
        return True

    except Exception as error:
        if conexion is not None:
            conexion.rollback()

        print(
            "ADVERTENCIA: no fue posible actualizar MySQL. "
            f"El CSV se conservó correctamente. Detalle: {error}"
        )
        return False

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


def american_a_decimal(odds):
    if pd.isna(odds):
        return np.nan

    odds = float(odds)

    if odds >= 100:
        return 1 + odds / 100

    if odds <= -100:
        return 1 + 100 / abs(odds)

    if odds > 1:
        return odds

    return np.nan


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


def preparar_features(calendario, proxima_semana):
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

    prediccion = dataset[
        (dataset["season"] == TEMPORADA_ACTUAL)
        & (dataset["week"] == proxima_semana)
        & (
            dataset["home_score"].isna()
            | dataset["away_score"].isna()
        )
    ].copy()

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


def generar_predicciones(
    df,
    modelo_mercado,
    modelo_base,
    calibrador,
):
    resultado = df.copy()

    columnas_mercado = (
        FEATURES_MERCADO
        + FEATURES_CATEGORICAS
    )

    columnas_base = (
        FEATURES_BASE
        + FEATURES_CATEGORICAS
    )

    resultado["pred_total_base"] = (
        modelo_base.predict(
            resultado[columnas_base]
        )
    )

    resultado["pred_total"] = np.nan
    resultado["edge"] = np.nan
    resultado["edge_absoluto"] = np.nan
    resultado["pick"] = "SIN LÍNEA"
    resultado["prob_pick"] = np.nan
    resultado["prob_over"] = np.nan
    resultado["prob_under"] = np.nan
    resultado["odds_pick"] = np.nan
    resultado["decimal_pick"] = np.nan
    resultado["prob_break_even"] = np.nan
    resultado["ev"] = np.nan
    resultado["estado"] = "SIN LÍNEA"

    con_linea = resultado[
        resultado["total_line"].notna()
    ].index

    if len(con_linea) == 0:
        return resultado

    X_mercado = resultado.loc[
        con_linea,
        columnas_mercado,
    ]

    predicciones = modelo_mercado.predict(
        X_mercado
    )

    resultado.loc[
        con_linea,
        "pred_total"
    ] = predicciones

    resultado.loc[
        con_linea,
        "edge"
    ] = (
        resultado.loc[
            con_linea,
            "pred_total"
        ]
        - resultado.loc[
            con_linea,
            "total_line"
        ]
    )

    resultado.loc[
        con_linea,
        "edge_absoluto"
    ] = (
        resultado.loc[
            con_linea,
            "edge"
        ].abs()
    )

    resultado.loc[
        con_linea,
        "pick"
    ] = np.where(
        resultado.loc[con_linea, "edge"] > 0,
        "OVER",
        "UNDER",
    )

    probabilidades = calibrador.predict_proba(
        resultado.loc[
            con_linea,
            ["edge_absoluto"]
        ]
    )[:, 1]

    resultado.loc[
        con_linea,
        "prob_pick"
    ] = probabilidades

    resultado.loc[
        con_linea,
        "prob_over"
    ] = np.where(
        resultado.loc[con_linea, "pick"] == "OVER",
        probabilidades,
        1 - probabilidades,
    )

    resultado.loc[
        con_linea,
        "prob_under"
    ] = (
        1
        - resultado.loc[
            con_linea,
            "prob_over"
        ]
    )

    resultado.loc[
        con_linea,
        "odds_pick"
    ] = np.where(
        resultado.loc[con_linea, "pick"] == "OVER",
        resultado.loc[con_linea, "over_odds"],
        resultado.loc[con_linea, "under_odds"],
    )

    resultado.loc[
        con_linea,
        "decimal_pick"
    ] = resultado.loc[
        con_linea,
        "odds_pick"
    ].apply(american_a_decimal)

    resultado.loc[
        con_linea,
        "prob_break_even"
    ] = (
        1
        / resultado.loc[
            con_linea,
            "decimal_pick"
        ]
    )

    resultado.loc[
        con_linea,
        "ev"
    ] = (
        resultado.loc[
            con_linea,
            "prob_pick"
        ]
        * resultado.loc[
            con_linea,
            "decimal_pick"
        ]
        - 1
    )

    cumple_edge = (
        resultado["edge_absoluto"] >= EDGE_MINIMO
    )

    cumple_ev = (
        resultado["ev"] > 0
    )

    resultado.loc[
        con_linea,
        "estado"
    ] = "NO PICK"

    resultado.loc[
        cumple_edge & cumple_ev,
        "estado"
    ] = "PICK"

    return resultado


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
    DIRECTORIO_PREDICCIONES.mkdir(
        parents=True,
        exist_ok=True,
    )

    calendario = actualizar_calendario()

    proxima_semana = obtener_proxima_semana(
        calendario
    )

    print(
        f"Próxima semana detectada: "
        f"{proxima_semana}"
    )

    print("Construyendo variables previas...")
    proximos = preparar_features(
        calendario,
        proxima_semana,
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

    ruta_salida = (
        DIRECTORIO_PREDICCIONES
        / (
            f"nfl_totales_"
            f"{TEMPORADA_ACTUAL}_"
            f"semana_{proxima_semana}.csv"
        )
    )

    predicciones.to_csv(
        ruta_salida,
        index=False,
    )

    print("Sincronizando predicciones con MySQL...")
    guardar_predicciones_mysql(predicciones)

    mostrar_resultados(
        predicciones,
        proxima_semana,
    )

    print("\nArchivo guardado:")
    print(ruta_salida)


if __name__ == "__main__":
    main()
