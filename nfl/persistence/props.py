"""Responsabilidad extraída del flujo CLI NFL."""
import mysql.connector
import numpy as np
import pandas as pd
from core.db import get_db_credentials as obtener_configuracion_mysql
from nfl.persistence.totals import valor_mysql
from nfl.settings import PROPS_MODEL_VERSION as MODELO_VERSION

def obtener_conexion():
    configuracion = obtener_configuracion_mysql()
    if configuracion is None:
        return None
    return mysql.connector.connect(**configuracion)

def sincronizar_catalogos(conexion, features, juegos):
    cursor = conexion.cursor()
    sql_jugador = """
        INSERT INTO nfl_jugadores (id_jugador, nombre, posicion, equipo_actual)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            nombre = VALUES(nombre),
            posicion = VALUES(posicion),
            equipo_actual = VALUES(equipo_actual)
    """
    datos_jugadores = [
        (
            valor_mysql(fila.player_id), valor_mysql(fila.player_name),
            valor_mysql(fila.position), valor_mysql(fila.team),
        )
        for fila in features[
            ["player_id", "player_name", "position", "team"]
        ].drop_duplicates("player_id").itertuples(index=False)
    ]
    cursor.executemany(sql_jugador, datos_jugadores)

    sql_juego = """
        INSERT INTO nfl_juegos (
            id_juego, temporada, tipo_juego, semana, fecha,
            equipo_local, equipo_visitante, marcador_local,
            marcador_visitante, estado
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, 'PROGRAMADO')
        ON DUPLICATE KEY UPDATE
            fecha = VALUES(fecha),
            equipo_local = VALUES(equipo_local),
            equipo_visitante = VALUES(equipo_visitante),
            estado = VALUES(estado)
    """
    datos_juegos = [
        (
            valor_mysql(fila.game_id), int(fila.season),
            valor_mysql(fila.game_type), int(fila.week),
            valor_mysql(fila.gameday), valor_mysql(fila.home_team),
            valor_mysql(fila.away_team),
        )
        for fila in juegos.itertuples(index=False)
    ]
    cursor.executemany(sql_juego, datos_juegos)
    conexion.commit()
    cursor.close()

def cargar_lineas(conexion, game_ids):
    if conexion is None or not game_ids:
        return pd.DataFrame()
    marcadores = ",".join(["%s"] * len(game_ids))
    consulta = f"""
        SELECT id_linea, id_juego, id_jugador, casa_apuestas, tipo_prop,
               linea, cuota_over, cuota_under, timestamp_captura
        FROM nfl_lineas_props
        WHERE id_juego IN ({marcadores})
          AND LOWER(TRIM(casa_apuestas)) = 'draftkings'
    """
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(consulta, tuple(game_ids))
    lineas = pd.DataFrame(cursor.fetchall())
    cursor.close()
    if lineas.empty:
        return lineas
    lineas["timestamp_captura"] = pd.to_datetime(lineas["timestamp_captura"])
    from core.domain.quotes import fresh_quotes
    lineas = fresh_quotes(lineas)
    if lineas.empty:
        return lineas
    # MySQL devuelve las columnas DECIMAL como decimal.Decimal. Convertirlas
    # aquí evita operaciones incompatibles con las predicciones float de
    # numpy/pandas al calcular edge, cuotas decimales y EV.
    for columna in ["linea", "cuota_over", "cuota_under"]:
        lineas[columna] = pd.to_numeric(lineas[columna], errors="coerce").astype(float)
    claves_prop = ["id_juego", "id_jugador", "tipo_prop"]
    # Conserva la captura mas reciente de cada linea alternativa por casa.
    lineas = (
        lineas.sort_values("timestamp_captura")
        .drop_duplicates(
            claves_prop + ["casa_apuestas", "linea"], keep="last"
        )
    )

    # Descarta puntos incompatibles con el tipo de mercado. Es una defensa
    # adicional ante feeds que mezclan variantes o datos defectuosos.
    limites = {
        "receptions": (0.5, 15.5),
        "receiving_yards": (4.5, 175.5),
        "passing_yards": (100.5, 425.5),
        "passing_tds": (0.5, 4.5),
        "rushing_yards": (0.5, 175.5),
        "anytime_td": (0.5, 0.5),
    }
    valida = pd.Series(False, index=lineas.index)
    for tipo, (minimo, maximo) in limites.items():
        valida |= (
            lineas["tipo_prop"].eq(tipo)
            & lineas["linea"].between(minimo, maximo)
        )
    lineas = lineas[valida].copy()

    def probabilidad_implicita(serie):
        serie = pd.to_numeric(serie, errors="coerce")
        return np.where(
            serie > 0,
            100 / (serie + 100),
            (-serie) / ((-serie) + 100),
        )

    p_over = probabilidad_implicita(lineas["cuota_over"])
    p_under = probabilidad_implicita(lineas["cuota_under"])
    # La linea principal suele tener precios cercanos entre si. Las lineas
    # alternativas muy altas/bajas reciben una penalizacion grande.
    lineas["_balance_linea"] = np.abs(p_over - p_under)
    lineas.loc[lineas["tipo_prop"].eq("anytime_td"), "_balance_linea"] = 0.0
    lineas["_balance_linea"] = lineas["_balance_linea"].fillna(99.0)
    lineas = (
        lineas.sort_values(
            claves_prop + ["casa_apuestas", "_balance_linea", "timestamp_captura"],
            ascending=[True, True, True, True, True, False],
        )
        .drop_duplicates(claves_prop + ["casa_apuestas"], keep="first")
    )

    # La casa base es exclusiva: una cuota ausente no se sustituye por otra casa.
    lineas = lineas.drop_duplicates(claves_prop, keep="first")
    return lineas.rename(
        columns={"id_juego": "game_id", "id_jugador": "player_id"}
    )

def guardar_proyecciones(conexion, df):
    if conexion is None:
        print("Sin credenciales MySQL: se guardará únicamente CSV.")
        return
    cursor = conexion.cursor()
    ids_juegos = sorted(df["game_id"].dropna().astype(str).unique())
    if ids_juegos:
        marcadores = ",".join(["%s"] * len(ids_juegos))
        cursor.execute(
            f"""
            DELETE FROM nfl_proyecciones_props
            WHERE modelo_version = %s
              AND id_juego IN ({marcadores})
            """,
            tuple([MODELO_VERSION] + ids_juegos),
        )

    sql = """
        INSERT INTO nfl_proyecciones_props (
            id_juego, id_jugador, id_linea, modelo_version, tipo_prop,
            linea, proyeccion, edge, seleccion, probabilidad_pick,
            probabilidad_over, probabilidad_under, cuota_pick, ev_estimado,
            estado_pick, estado_lesion, impacto_lesiones_companeros,
            contexto_lesiones
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            id_linea = VALUES(id_linea),
            modelo_version = VALUES(modelo_version),
            linea = VALUES(linea),
            proyeccion = VALUES(proyeccion), edge = VALUES(edge),
            seleccion = VALUES(seleccion),
            probabilidad_pick = VALUES(probabilidad_pick),
            probabilidad_over = VALUES(probabilidad_over),
            probabilidad_under = VALUES(probabilidad_under),
            cuota_pick = VALUES(cuota_pick), ev_estimado = VALUES(ev_estimado),
            estado_pick = VALUES(estado_pick),
            estado_lesion = VALUES(estado_lesion),
            impacto_lesiones_companeros = VALUES(impacto_lesiones_companeros),
            contexto_lesiones = VALUES(contexto_lesiones),
            actualizado_en = CURRENT_TIMESTAMP
    """
    datos = []
    for fila in df.itertuples(index=False):
        datos.append(
            tuple(
                valor_mysql(valor)
                for valor in [
                    fila.game_id, fila.player_id, fila.id_linea,
                    MODELO_VERSION, fila.tipo_prop, fila.linea,
                    fila.proyeccion, fila.edge, fila.seleccion,
                    fila.probabilidad_pick, fila.probabilidad_over,
                    fila.probabilidad_under, fila.cuota_pick,
                    fila.ev_estimado, fila.estado_pick,
                    fila.player_injury_status,
                    fila.teammate_skill_injury_score,
                    fila.contexto_lesiones,
                ]
            )
        )
    cursor.executemany(sql, datos)
    conexion.commit()
    cursor.close()
    print(f"MySQL actualizado: {len(df):,} proyecciones de props.")
