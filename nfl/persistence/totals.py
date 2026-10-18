"""Servicio extraído del predictor NFL; conserva sus cálculos originales."""
from pathlib import Path
import mysql.connector
import numpy as np
import pandas as pd
from core.db import get_db_credentials as obtener_configuracion_mysql
MODELO_VERSION = 'totales_v2_seleccion_automatica'

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

        from nfl.publicaciones_totales import save as save_original_totals
        save_original_totals(conexion,filas_validas,MODELO_VERSION,Path(__file__).resolve().parents[2])

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
