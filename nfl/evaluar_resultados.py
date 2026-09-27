import os
from datetime import datetime

import mysql.connector
import nflreadpy as nfl
import pandas as pd


def variable_entorno(*nombres, obligatoria=False):
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


def configuracion_mysql():
    config = {
        "host": variable_entorno(
            "DB_HOST", "MYSQL_HOST", "host", obligatoria=True
        ),
        "port": int(
            variable_entorno(
                "DB_PORT", "MYSQL_PORT", "port"
            ) or "3306"
        ),
        "user": variable_entorno(
            "DB_USER", "MYSQL_USER", "user", obligatoria=True
        ),
        "password": variable_entorno(
            "DB_PASSWORD",
            "MYSQL_PASSWORD",
            "password",
            obligatoria=True,
        ),
        "database": variable_entorno(
            "DB_NAME",
            "MYSQL_DATABASE",
            "database",
            obligatoria=True,
        ),
        "connection_timeout": 20,
        "ssl_disabled": False,
    }

    ruta_ca = variable_entorno(
        "DB_SSL_CA", "MYSQL_SSL_CA", "ssl_ca"
    )
    if ruta_ca:
        config["ssl_ca"] = ruta_ca
        config["ssl_verify_cert"] = True

    return config


def beneficio_por_momio(momio):
    if momio is None or pd.isna(momio):
        return None

    momio = float(momio)
    if momio >= 100:
        return momio / 100.0
    if momio <= -100:
        return 100.0 / abs(momio)
    return None


def resolver_pick(seleccion, linea, total_real):
    seleccion = str(seleccion).upper()
    linea = float(linea)
    total_real = float(total_real)

    if total_real == linea:
        return "PUSH"

    if seleccion == "OVER":
        return "GANADA" if total_real > linea else "PERDIDA"

    if seleccion == "UNDER":
        return "GANADA" if total_real < linea else "PERDIDA"

    return None


def obtener_pendientes(cursor):
    cursor.execute(
        """
        SELECT
            p.id_prediccion,
            p.id_juego,
            p.linea_total,
            p.seleccion,
            p.cuota_pick,
            p.estado_pick,
            j.temporada
        FROM nfl_predicciones_totales AS p
        INNER JOIN nfl_juegos AS j
            ON j.id_juego = p.id_juego
        WHERE p.resultado_pick = 'PENDIENTE'
        ORDER BY j.temporada, j.semana, p.id_juego
        """
    )
    return cursor.fetchall()


def main():
    conexion = mysql.connector.connect(**configuracion_mysql())
    cursor = conexion.cursor(dictionary=True)

    try:
        pendientes = obtener_pendientes(cursor)
        if not pendientes:
            print("No existen predicciones pendientes de evaluar.")
            return

        temporadas = sorted(
            {int(fila["temporada"]) for fila in pendientes}
        )
        print(
            "Descargando resultados NFL para temporadas: "
            + ", ".join(map(str, temporadas))
        )

        calendario = nfl.load_schedules(temporadas).to_pandas()
        calendario = calendario[
            calendario["home_score"].notna()
            & calendario["away_score"].notna()
        ].copy()
        calendario = calendario.drop_duplicates(
            subset=["game_id"], keep="last"
        ).set_index("game_id")

        sql_juego = """
            UPDATE nfl_juegos
            SET
                marcador_local = %s,
                marcador_visitante = %s,
                estado = 'finalizado'
            WHERE id_juego = %s
        """
        sql_prediccion = """
            UPDATE nfl_predicciones_totales
            SET
                total_real = %s,
                resultado_pick = %s,
                beneficio_unidades = %s,
                evaluado_en = %s
            WHERE id_prediccion = %s
              AND resultado_pick = 'PENDIENTE'
        """

        evaluadas = 0
        oficiales = 0
        ganadas = 0
        perdidas = 0
        pushes = 0
        beneficio_total = 0.0

        for prediccion in pendientes:
            game_id = prediccion["id_juego"]
            if game_id not in calendario.index:
                continue

            partido = calendario.loc[game_id]
            marcador_local = int(partido["home_score"])
            marcador_visitante = int(partido["away_score"])
            total_real = marcador_local + marcador_visitante

            resultado = resolver_pick(
                prediccion["seleccion"],
                prediccion["linea_total"],
                total_real,
            )
            if resultado is None:
                continue

            beneficio = None
            if prediccion["estado_pick"] == "PICK":
                oficiales += 1
                if resultado == "GANADA":
                    beneficio = beneficio_por_momio(
                        prediccion["cuota_pick"]
                    )
                    ganadas += 1
                elif resultado == "PERDIDA":
                    beneficio = -1.0
                    perdidas += 1
                else:
                    beneficio = 0.0
                    pushes += 1

                if beneficio is not None:
                    beneficio_total += beneficio

            cursor.execute(
                sql_juego,
                (
                    marcador_local,
                    marcador_visitante,
                    game_id,
                ),
            )
            cursor.execute(
                sql_prediccion,
                (
                    total_real,
                    resultado,
                    beneficio,
                    datetime.now(),
                    prediccion["id_prediccion"],
                ),
            )
            evaluadas += cursor.rowcount

        conexion.commit()

        print(f"Predicciones evaluadas: {evaluadas}")
        print(f"Picks oficiales terminados: {oficiales}")
        print(
            f"Balance: {ganadas} ganadas, "
            f"{perdidas} perdidas, {pushes} push"
        )
        print(f"Beneficio acumulado: {beneficio_total:+.4f} unidades")

    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()
        if conexion.is_connected():
            conexion.close()


if __name__ == "__main__":
    main()
