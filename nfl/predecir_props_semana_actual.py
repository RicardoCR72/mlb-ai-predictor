"""Genera proyecciones semanales NFL de recepciones y yardas recibidas."""

from pathlib import Path

import joblib
import mysql.connector
import nflreadpy as nfl
import numpy as np
import pandas as pd

from construir_dataset_props_recepcion import (
    METRICAS_JUGADOR,
    POSICIONES,
    RUTA_JUGADORES,
    agregar_contexto_equipo,
    agregar_defensa_rival,
    agregar_forma_jugador,
    agregar_lesiones_companeros,
    cargar_datos,
)
from features_lesiones import agregar_contexto_lesiones, cargar_lesiones
from predecir_semana_actual import (
    TEMPORADA_ACTUAL,
    actualizar_calendario,
    actualizar_lesiones,
    obtener_configuracion_mysql,
    obtener_proxima_semana,
    valor_mysql,
)


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
DIRECTORIO_MODELOS = RAIZ_PROYECTO / "modelos_nfl" / "props"
DIRECTORIO_SALIDA = RAIZ_PROYECTO / "data" / "nfl" / "predictions"

RUTA_MODELO_RECEPCIONES = DIRECTORIO_MODELOS / "props_receptions.joblib"
RUTA_MODELO_YARDAS = DIRECTORIO_MODELOS / "props_receiving_yards.joblib"
RUTA_VALIDACION = DIRECTORIO_MODELOS / "predicciones_validacion_recepcion.csv"

MODELO_VERSION = "props_recepcion_v1"
POSICIONES_ELEGIBLES = ["WR", "TE", "RB"]
TARGETS_PROMEDIO_MINIMO = 3.0


def actualizar_estadisticas_jugadores():
    print(f"Actualizando estadísticas de jugadores {TEMPORADA_ACTUAL}...")
    if not RUTA_JUGADORES.exists():
        raise FileNotFoundError(f"No se encontró: {RUTA_JUGADORES}")

    historico = pd.read_parquet(RUTA_JUGADORES)
    try:
        actual = nfl.load_player_stats([TEMPORADA_ACTUAL]).to_pandas()
    except Exception as error:
        disponible = historico[historico["season"] == TEMPORADA_ACTUAL]
        if disponible.empty:
            raise RuntimeError(
                "No se pudieron descargar estadísticas de jugadores."
            ) from error
        print("ADVERTENCIA: se utilizarán estadísticas locales.")
        return historico

    jugadores = pd.concat(
        [historico[historico["season"] != TEMPORADA_ACTUAL], actual],
        ignore_index=True,
    )
    claves = ["player_id", "game_id"]
    jugadores = jugadores.drop_duplicates(claves, keep="last")
    jugadores.to_parquet(RUTA_JUGADORES, index=False)
    print(f"Estadísticas disponibles: {len(jugadores):,} registros.")
    return jugadores


def crear_filas_futuras(raw, proximos):
    ofensivos = raw[
        (raw["season"] == TEMPORADA_ACTUAL)
        & raw["position"].isin(POSICIONES)
    ].copy()
    ofensivos = ofensivos.sort_values(["player_id", "week", "game_id"])
    roster = ofensivos.drop_duplicates("player_id", keep="last")

    equipos = pd.concat(
        [
            proximos[
                ["game_id", "season", "week", "home_team", "away_team"]
            ].rename(columns={"home_team": "team", "away_team": "opponent_team"}),
            proximos[
                ["game_id", "season", "week", "home_team", "away_team"]
            ].rename(columns={"away_team": "team", "home_team": "opponent_team"}),
        ],
        ignore_index=True,
    )
    filas = roster.merge(equipos, on="team", how="inner", suffixes=("", "_next"))
    filas["game_id"] = filas["game_id_next"]
    filas["season"] = filas["season_next"]
    filas["week"] = filas["week_next"]
    filas["opponent_team"] = filas["opponent_team_next"]

    columnas_borrar = [
        columna for columna in filas.columns
        if columna.endswith("_next")
    ]
    filas = filas.drop(columns=columnas_borrar)

    for columna in set(METRICAS_JUGADOR + ["receiving_tds"]):
        if columna in filas.columns:
            filas[columna] = np.nan
    return filas


def agregar_contexto_partido(df, calendario):
    contexto = calendario[
        [
            "game_id", "gameday", "home_team", "away_team",
            "home_qb_id", "away_qb_id", "home_rest", "away_rest",
            "roof", "surface", "temp", "wind",
        ]
    ].drop_duplicates("game_id")
    columnas_contexto_existentes = [
        columna for columna in contexto.columns
        if columna != "game_id" and columna in df.columns
    ]
    resultado = df.drop(columns=columnas_contexto_existentes).merge(
        contexto,
        on="game_id",
        how="left",
        validate="many_to_one",
    )
    resultado["gameday"] = pd.to_datetime(resultado["gameday"], errors="coerce")
    resultado["is_home"] = resultado["team"].eq(resultado["home_team"]).astype(int)
    resultado["rest"] = np.where(
        resultado["is_home"].eq(1),
        resultado["home_rest"],
        resultado["away_rest"],
    )
    resultado["starting_qb_id"] = np.where(
        resultado["is_home"].eq(1),
        resultado["home_qb_id"],
        resultado["away_qb_id"],
    )
    return resultado


def preparar_features(calendario, semana):
    raw = pd.read_parquet(RUTA_JUGADORES)
    historico, _, lesiones = cargar_datos()
    proximos = calendario[
        (calendario["season"] == TEMPORADA_ACTUAL)
        & (calendario["week"] == semana)
        & (calendario["game_type"] == "REG")
        & (calendario["home_score"].isna() | calendario["away_score"].isna())
    ].copy()

    futuras_raw = crear_filas_futuras(raw, proximos)
    futuras = agregar_contexto_partido(futuras_raw, proximos)
    combinadas = pd.concat([historico, futuras], ignore_index=True, sort=False)
    combinadas = combinadas.sort_values(
        ["player_id", "gameday", "game_id"]
    ).reset_index(drop=True)

    print("Calculando forma previa de jugadores...")
    dataset = agregar_forma_jugador(combinadas)
    dataset = agregar_contexto_equipo(dataset)
    dataset = agregar_defensa_rival(dataset)
    dataset = agregar_lesiones_companeros(dataset, lesiones)

    futuros = dataset[
        (dataset["season"] == TEMPORADA_ACTUAL)
        & (dataset["week"] == semana)
        & dataset["game_id"].isin(proximos["game_id"])
    ].copy()
    futuros = futuros[
        futuros["position"].isin(POSICIONES_ELEGIBLES)
        & (futuros["player_games_before"] >= 3)
        & (futuros["player_targets_avg_5"] >= TARGETS_PROMEDIO_MINIMO)
        & ~futuros["player_injury_status"].isin(["out", "doubtful"])
    ].copy()

    contexto = agregar_contexto_lesiones(
        proximos.copy(),
        proximos,
        cargar_lesiones(),
    )[
        [
            "game_id", "home_key_injuries", "away_key_injuries",
            "home_prop_injury_note", "away_prop_injury_note",
        ]
    ]
    futuros = futuros.merge(contexto, on="game_id", how="left", validate="many_to_one")
    futuros["contexto_lesiones"] = np.where(
        futuros["is_home"].eq(1),
        futuros["home_key_injuries"],
        futuros["away_key_injuries"],
    )
    return futuros, proximos


def predecir_modelo(modelo, df):
    columnas = list(modelo.feature_names_in_)
    faltantes = sorted(set(columnas) - set(df.columns))
    if faltantes:
        raise KeyError("Faltan features: " + ", ".join(faltantes))
    return np.maximum(modelo.predict(df[columnas]), 0)


def construir_proyecciones(features):
    for ruta in [RUTA_MODELO_RECEPCIONES, RUTA_MODELO_YARDAS, RUTA_VALIDACION]:
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontró: {ruta}")
    modelo_recepciones = joblib.load(RUTA_MODELO_RECEPCIONES)
    modelo_yardas = joblib.load(RUTA_MODELO_YARDAS)

    base = features[
        [
            "game_id", "season", "week", "gameday", "player_id",
            "player_name", "position", "team", "opponent_team",
            "player_targets_avg_5", "player_receptions_avg_5",
            "player_receiving_yards_avg_5", "player_injury_status",
            "teammate_skill_injury_score", "contexto_lesiones",
        ]
    ].copy()
    recepciones = base.copy()
    recepciones["tipo_prop"] = "receptions"
    recepciones["proyeccion"] = predecir_modelo(modelo_recepciones, features)
    yardas = base.copy()
    yardas["tipo_prop"] = "receiving_yards"
    yardas["proyeccion"] = predecir_modelo(modelo_yardas, features)
    return pd.concat([recepciones, yardas], ignore_index=True)


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
    """
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(consulta, tuple(game_ids))
    lineas = pd.DataFrame(cursor.fetchall())
    cursor.close()
    if lineas.empty:
        return lineas
    lineas["timestamp_captura"] = pd.to_datetime(lineas["timestamp_captura"])
    return (
        lineas.sort_values("timestamp_captura")
        .drop_duplicates(
            ["id_juego", "id_jugador", "tipo_prop", "casa_apuestas"],
            keep="last",
        )
        .rename(columns={"id_juego": "game_id", "id_jugador": "player_id"})
    )


def american_a_decimal(odds):
    if pd.isna(odds) or odds == 0:
        return np.nan
    return 1 + (odds / 100 if odds > 0 else 100 / abs(odds))


def agregar_lineas_y_probabilidades(proyecciones, lineas):
    resultado = proyecciones.copy()
    if lineas.empty:
        for columna in [
            "id_linea", "casa_apuestas", "linea", "cuota_over", "cuota_under"
        ]:
            resultado[columna] = np.nan
    else:
        resultado = resultado.merge(
            lineas,
            on=["game_id", "player_id", "tipo_prop"],
            how="left",
        )

    resultado["edge"] = resultado["proyeccion"] - resultado["linea"]
    resultado["seleccion"] = np.where(resultado["edge"] >= 0, "OVER", "UNDER")
    resultado.loc[resultado["linea"].isna(), "seleccion"] = None

    validacion = pd.read_csv(RUTA_VALIDACION)
    calibracion = validacion[validacion["season"] == 2024].copy()
    probabilidades_over = []
    for fila in resultado.itertuples(index=False):
        if pd.isna(fila.linea):
            probabilidades_over.append(np.nan)
            continue
        residuos = calibracion[
            (calibracion["objetivo"] == fila.tipo_prop)
            & (calibracion["position"] == fila.position)
        ]["error"].dropna()
        if len(residuos) < 100:
            residuos = calibracion[
                calibracion["objetivo"] == fila.tipo_prop
            ]["error"].dropna()
        probabilidades_over.append(float((residuos < fila.edge).mean()))

    resultado["probabilidad_over"] = probabilidades_over
    resultado["probabilidad_under"] = 1 - resultado["probabilidad_over"]
    resultado["probabilidad_pick"] = np.where(
        resultado["seleccion"].eq("OVER"),
        resultado["probabilidad_over"],
        resultado["probabilidad_under"],
    )
    resultado["cuota_pick"] = np.where(
        resultado["seleccion"].eq("OVER"),
        resultado["cuota_over"],
        resultado["cuota_under"],
    )
    decimal = resultado["cuota_pick"].apply(american_a_decimal)
    resultado["ev_estimado"] = (
        resultado["probabilidad_pick"] * decimal - 1
    )
    umbral_edge = np.where(resultado["tipo_prop"].eq("receptions"), 0.75, 10.0)
    resultado["estado_pick"] = "NO PICK"
    resultado.loc[resultado["linea"].isna(), "estado_pick"] = "SIN LINEA"
    candidato = (
        resultado["linea"].notna()
        & (resultado["edge"].abs() >= umbral_edge)
        & (resultado["probabilidad_pick"] >= 0.57)
        & (resultado["ev_estimado"] > 0)
    )
    resultado.loc[candidato, "estado_pick"] = "CANDIDATO"
    return resultado


def guardar_proyecciones(conexion, df):
    if conexion is None:
        print("Sin credenciales MySQL: se guardará únicamente CSV.")
        return
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
            id_linea = VALUES(id_linea), linea = VALUES(linea),
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
    cursor = conexion.cursor()
    cursor.executemany(sql, datos)
    conexion.commit()
    cursor.close()
    print(f"MySQL actualizado: {len(df):,} proyecciones de props.")


def main():
    DIRECTORIO_SALIDA.mkdir(parents=True, exist_ok=True)
    calendario = actualizar_calendario()
    actualizar_lesiones()
    actualizar_estadisticas_jugadores()
    semana = obtener_proxima_semana(calendario)
    print(f"Semana detectada: {semana}")

    features, juegos = preparar_features(calendario, semana)
    print(f"Jugadores elegibles: {len(features):,}")
    proyecciones = construir_proyecciones(features)

    conexion = obtener_conexion()
    try:
        if conexion is not None:
            sincronizar_catalogos(conexion, features, juegos)
        lineas = cargar_lineas(conexion, juegos["game_id"].tolist())
        resultado = agregar_lineas_y_probabilidades(proyecciones, lineas)
        guardar_proyecciones(conexion, resultado)
    finally:
        if conexion is not None and conexion.is_connected():
            conexion.close()

    ruta = DIRECTORIO_SALIDA / (
        f"nfl_props_recepcion_{TEMPORADA_ACTUAL}_semana_{semana}.csv"
    )
    resultado.to_csv(ruta, index=False)

    columnas = [
        "player_name", "position", "team", "opponent_team", "tipo_prop",
        "proyeccion", "linea", "edge", "seleccion", "probabilidad_pick",
        "ev_estimado", "estado_pick", "player_injury_status",
    ]
    print("\n" + "=" * 120)
    print(f"PROYECCIONES PROPS NFL {TEMPORADA_ACTUAL} - SEMANA {semana}")
    print("=" * 120)
    print(
        resultado[columnas]
        .sort_values(["estado_pick", "tipo_prop", "proyeccion"], ascending=[True, True, False])
        .round(3)
        .to_string(index=False)
    )
    print(f"\nArchivo guardado en:\n{ruta}")


if __name__ == "__main__":
    main()
