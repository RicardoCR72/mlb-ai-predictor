"""Liquida proyecciones NFL de recepciones y yardas de recepción."""

from collections import defaultdict
from datetime import datetime, timezone

import mysql.connector
import nflreadpy as nfl
import pandas as pd

from predecir_semana_actual import obtener_configuracion_mysql


MERCADOS = {
    "receptions": "receptions",
    "receiving_yards": "receiving_yards",
}


def conectar_mysql():
    configuracion = obtener_configuracion_mysql()
    if configuracion is None:
        raise RuntimeError(
            "Faltan DB_HOST, DB_PORT, DB_USER, DB_PASSWORD y DB_NAME."
        )
    return mysql.connector.connect(**configuracion)


def verificar_columnas(cursor):
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'nfl_proyecciones_props'
        """
    )
    existentes = {fila["COLUMN_NAME"] for fila in cursor.fetchall()}
    requeridas = {
        "valor_real", "resultado_pick",
        "beneficio_unidades", "evaluado_en",
    }
    faltantes = sorted(requeridas - existentes)
    if faltantes:
        raise RuntimeError(
            "Faltan columnas en nfl_proyecciones_props: "
            + ", ".join(faltantes)
            + ". Ejecuta primero nfl/migracion_resultados_props.sql."
        )


def cargar_pendientes(cursor):
    cursor.execute(
        """
        SELECT
            p.id_proyeccion,
            p.id_juego,
            p.id_jugador,
            p.tipo_prop,
            p.linea,
            p.seleccion,
            p.cuota_pick,
            p.estado_pick,
            j.temporada,
            j.semana
        FROM nfl_proyecciones_props AS p
        INNER JOIN nfl_juegos AS j
            ON j.id_juego = p.id_juego
        WHERE p.resultado_pick = 'PENDIENTE'
          AND p.linea IS NOT NULL
          AND p.seleccion IN ('OVER', 'UNDER')
          AND p.tipo_prop IN ('receptions', 'receiving_yards')
        ORDER BY j.temporada, j.semana, p.id_juego, p.id_jugador
        """
    )
    return cursor.fetchall()


def resultado_seleccion(seleccion, linea, valor_real):
    seleccion = str(seleccion).upper()
    linea = float(linea)
    valor_real = float(valor_real)

    if abs(valor_real - linea) < 1e-9:
        return "PUSH"
    if seleccion == "OVER":
        return "GANADA" if valor_real > linea else "PERDIDA"
    if seleccion == "UNDER":
        return "GANADA" if valor_real < linea else "PERDIDA"
    return None


def ganancia_momio_americano(momio):
    if momio is None or pd.isna(momio):
        return None
    momio = float(momio)
    if momio >= 100:
        return momio / 100.0
    if momio <= -100:
        return 100.0 / abs(momio)
    return None


def beneficio(resultado, momio, es_candidato):
    if not es_candidato:
        return None
    if resultado == "GANADA":
        return ganancia_momio_americano(momio)
    if resultado == "PERDIDA":
        return -1.0
    if resultado == "PUSH":
        return 0.0
    return None


def cargar_resultados(temporadas):
    print(
        "Descargando calendarios y estadísticas: "
        + ", ".join(map(str, temporadas))
    )
    calendario = nfl.load_schedules(temporadas).to_pandas()
    finales = calendario[
        calendario["home_score"].notna()
        & calendario["away_score"].notna()
    ]["game_id"].dropna().astype(str)
    ids_finales = set(finales)

    estadisticas = nfl.load_player_stats(temporadas).to_pandas()
    columnas = [
        "game_id", "player_id", "receptions", "receiving_yards"
    ]
    faltantes = sorted(set(columnas) - set(estadisticas.columns))
    if faltantes:
        raise KeyError(
            "Faltan columnas en player stats: " + ", ".join(faltantes)
        )

    estadisticas = estadisticas[columnas].copy()
    estadisticas["game_id"] = estadisticas["game_id"].astype(str)
    estadisticas["player_id"] = estadisticas["player_id"].astype(str)
    for columna in ["receptions", "receiving_yards"]:
        estadisticas[columna] = pd.to_numeric(
            estadisticas[columna], errors="coerce"
        )
    estadisticas = (
        estadisticas.drop_duplicates(
            ["game_id", "player_id"], keep="last"
        )
        .set_index(["game_id", "player_id"])
    )
    return ids_finales, estadisticas


def main():
    conexion = conectar_mysql()
    cursor = conexion.cursor(dictionary=True)
    try:
        verificar_columnas(cursor)
        pendientes = cargar_pendientes(cursor)
        if not pendientes:
            print("No hay proyecciones de props pendientes de evaluar.")
            return

        temporadas = sorted({int(fila["temporada"]) for fila in pendientes})
        ids_finales, estadisticas = cargar_resultados(temporadas)

        sql = """
            UPDATE nfl_proyecciones_props
            SET
                valor_real = %s,
                resultado_pick = %s,
                beneficio_unidades = %s,
                evaluado_en = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id_proyeccion = %s
              AND resultado_pick = 'PENDIENTE'
        """

        resumen = defaultdict(
            lambda: {
                "evaluadas": 0, "candidatos": 0,
                "ganadas": 0, "perdidas": 0,
                "pushes": 0, "unidades": 0.0,
            }
        )
        omitidos_sin_registro = 0
        pendientes_partido = 0
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)

        for fila in pendientes:
            game_id = str(fila["id_juego"])
            player_id = str(fila["id_jugador"])
            if game_id not in ids_finales:
                pendientes_partido += 1
                continue

            clave = (game_id, player_id)
            if clave not in estadisticas.index:
                # No asignamos cero a un jugador ausente: la apuesta pudo ser void.
                omitidos_sin_registro += 1
                continue

            columna_real = MERCADOS[fila["tipo_prop"]]
            valor_real = estadisticas.loc[clave, columna_real]
            if pd.isna(valor_real):
                omitidos_sin_registro += 1
                continue

            resultado = resultado_seleccion(
                fila["seleccion"], fila["linea"], valor_real
            )
            if resultado is None:
                continue

            es_candidato = fila["estado_pick"] == "CANDIDATO"
            utilidad = beneficio(
                resultado, fila["cuota_pick"], es_candidato
            )
            cursor.execute(
                sql,
                (
                    float(valor_real), resultado, utilidad,
                    ahora, int(fila["id_proyeccion"]),
                ),
            )
            if cursor.rowcount != 1:
                continue

            datos = resumen[fila["tipo_prop"]]
            datos["evaluadas"] += 1
            if es_candidato:
                datos["candidatos"] += 1
                if resultado == "GANADA":
                    datos["ganadas"] += 1
                elif resultado == "PERDIDA":
                    datos["perdidas"] += 1
                else:
                    datos["pushes"] += 1
                if utilidad is not None:
                    datos["unidades"] += utilidad

        conexion.commit()

        total_evaluadas = sum(x["evaluadas"] for x in resumen.values())
        print("\n" + "=" * 72)
        print(f"Proyecciones evaluadas: {total_evaluadas}")
        print(f"Partidos aún no finalizados: {pendientes_partido}")
        print(f"Jugadores sin registro oficial: {omitidos_sin_registro}")
        for mercado, datos in sorted(resumen.items()):
            decididas = datos["ganadas"] + datos["perdidas"]
            acierto = datos["ganadas"] / decididas if decididas else None
            roi = (
                datos["unidades"] / datos["candidatos"]
                if datos["candidatos"] else None
            )
            acierto_txt = f"{acierto:.2%}" if acierto is not None else "N/D"
            roi_txt = f"{roi:.2%}" if roi is not None else "N/D"
            print(
                f"{mercado}: {datos['evaluadas']} evaluadas | "
                f"candidatos {datos['candidatos']} | "
                f"{datos['ganadas']}-{datos['perdidas']}-{datos['pushes']} | "
                f"acierto {acierto_txt} | "
                f"unidades {datos['unidades']:+.3f} | ROI {roi_txt}"
            )
        print("=" * 72)
    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()
        if conexion.is_connected():
            conexion.close()


if __name__ == "__main__":
    main()
