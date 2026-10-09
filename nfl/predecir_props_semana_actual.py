"""Genera proyecciones semanales para los principales props NFL."""

import json
import argparse
from jornada import calendario_hoy
from pathlib import Path

import joblib
import mysql.connector
import nflreadpy as nfl
import numpy as np
import pandas as pd
from scipy.stats import poisson

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
from construir_dataset_props_pase_carrera import (
    METRICAS_CARRERA,
    METRICAS_PASE,
    POSICIONES_CARRERA,
    agregar_lesiones as agregar_lesiones_pc,
    cargar_datos as cargar_datos_pc,
    construir_dataset_carrera,
    construir_dataset_pase,
    normalizar_columnas_estadisticas,
)
from construir_dataset_prop_touchdown import (
    METRICAS as METRICAS_TOUCHDOWN,
    POSICIONES as POSICIONES_TOUCHDOWN,
    agregar_contexto_equipo as agregar_contexto_equipo_td,
    agregar_defensa_rival as agregar_defensa_rival_td,
    agregar_forma_jugador as agregar_forma_jugador_td,
    agregar_participacion as agregar_participacion_td,
    preparar_base as preparar_base_td,
)
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
RUTA_MODELO_PASS_YDS = DIRECTORIO_MODELOS / "props_passing_yards.joblib"
RUTA_MODELO_PASS_TDS = DIRECTORIO_MODELOS / "props_passing_tds.joblib"
RUTA_MODELO_RUSH_YDS = DIRECTORIO_MODELOS / "props_rushing_yards.joblib"
RUTA_MODELO_ANYTIME_TD = DIRECTORIO_MODELOS / "props_anytime_td.joblib"
RUTA_CALIBRACION_PC = DIRECTORIO_MODELOS / "calibracion_props_pase_carrera.json"
RUTA_RESIDUOS_PC = DIRECTORIO_MODELOS / "residuos_props_pase_carrera.npz"

MODELO_VERSION = "props_nfl_v2"
POSICIONES_ELEGIBLES = ["WR", "TE", "RB"]
TARGETS_PROMEDIO_MINIMO = 3.0


def actualizar_estadisticas_jugadores():
    print(f"Actualizando estadísticas de jugadores {TEMPORADA_ACTUAL}...")
    if not RUTA_JUGADORES.exists():
        print(
            "No existe histórico local. Descargando estadísticas "
            f"2012-{TEMPORADA_ACTUAL}..."
        )
        RUTA_JUGADORES.parent.mkdir(parents=True, exist_ok=True)
        try:
            jugadores = nfl.load_player_stats(
                list(range(2012, TEMPORADA_ACTUAL + 1))
            ).to_pandas()
        except Exception as error:
            raise RuntimeError(
                "No se pudo descargar el histórico de estadísticas de jugadores."
            ) from error

        if jugadores.empty:
            raise RuntimeError(
                "La descarga del histórico de jugadores no devolvió registros."
            )

        jugadores = jugadores.drop_duplicates(
            ["player_id", "game_id"], keep="last"
        )
        jugadores.to_parquet(RUTA_JUGADORES, index=False)
        print(f"Estadísticas disponibles: {len(jugadores):,} registros.")
        return jugadores

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
    columnas = [
        "game_id", "gameday", "home_team", "away_team",
        "home_qb_id", "away_qb_id", "home_rest", "away_rest",
        "roof", "surface", "temp", "wind", "spread_line", "total_line",
        "home_moneyline", "away_moneyline", "div_game",
    ]
    contexto = calendario[
        [columna for columna in columnas if columna in calendario.columns]
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
    resultado["is_starting_qb"] = (
        resultado["player_id"].astype(str)
        == pd.Series(resultado["starting_qb_id"]).fillna("").astype(str)
    ).astype(int)
    return resultado


def preparar_features(calendario, semana, game_ids=None):
    raw = pd.read_parquet(RUTA_JUGADORES)
    historico, _, lesiones = cargar_datos()
    proximos = calendario[
        (calendario["season"] == TEMPORADA_ACTUAL)
        & (calendario["week"] == semana)
        & (calendario["game_type"] == "REG")
        & (calendario["home_score"].isna() | calendario["away_score"].isna())
    ].copy()

    if game_ids is not None:
        proximos = proximos[proximos['game_id'].isin(game_ids)].copy()
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


def crear_filas_futuras_generales(raw, proximos):
    """Crea filas futuras para pase, carrera y anota TD sin fuga de datos."""
    jugadores = normalizar_columnas_estadisticas(raw)
    posiciones = sorted(set(
        POSICIONES_CARRERA + POSICIONES_TOUCHDOWN + ["QB"]
    ))
    actuales = jugadores[
        (jugadores["season"] == TEMPORADA_ACTUAL)
        & jugadores["position"].isin(posiciones)
    ].copy()
    roster = (
        actuales.sort_values(["player_id", "week", "game_id"])
        .drop_duplicates("player_id", keep="last")
    )

    equipos = pd.concat(
        [
            proximos[["game_id", "season", "week", "home_team", "away_team"]]
            .rename(columns={"home_team": "team", "away_team": "opponent_team"}),
            proximos[["game_id", "season", "week", "home_team", "away_team"]]
            .rename(columns={"away_team": "team", "home_team": "opponent_team"}),
        ],
        ignore_index=True,
    )
    filas = roster.merge(equipos, on="team", how="inner", suffixes=("", "_next"))
    filas["game_id"] = filas["game_id_next"]
    filas["season"] = filas["season_next"]
    filas["week"] = filas["week_next"]
    filas["opponent_team"] = filas["opponent_team_next"]
    filas = filas.drop(columns=[c for c in filas if c.endswith("_next")])
    filas = agregar_contexto_partido(filas, proximos)

    metricas = set(METRICAS_PASE + METRICAS_CARRERA + METRICAS_TOUCHDOWN)
    for metrica in metricas:
        if metrica not in filas.columns:
            filas[metrica] = np.nan
        else:
            filas[metrica] = np.nan
    return filas


def agregar_notas_lesiones(df, proximos):
    contexto = agregar_contexto_lesiones(
        proximos.copy(), proximos, cargar_lesiones()
    )[
        [
            "game_id", "home_key_injuries", "away_key_injuries",
            "home_prop_injury_note", "away_prop_injury_note",
        ]
    ].drop_duplicates("game_id")
    resultado = df.merge(contexto, on="game_id", how="left", validate="many_to_one")
    resultado["contexto_lesiones"] = np.where(
        resultado["is_home"].eq(1),
        resultado["home_key_injuries"],
        resultado["away_key_injuries"],
    )
    return resultado


def preparar_features_adicionales(calendario, semana, game_ids=None):
    proximos = calendario[
        (calendario["season"] == TEMPORADA_ACTUAL)
        & (calendario["week"] == semana)
        & (calendario["game_type"] == "REG")
        & (calendario["home_score"].isna() | calendario["away_score"].isna())
    ].copy()
    if game_ids is not None:
        proximos = proximos[proximos['game_id'].isin(game_ids)].copy()
    historico, lesiones = cargar_datos_pc()
    raw = pd.read_parquet(RUTA_JUGADORES)
    futuras = crear_filas_futuras_generales(raw, proximos)
    combinadas = pd.concat([historico, futuras], ignore_index=True, sort=False)
    ids_futuros = set(proximos["game_id"])

    print("Calculando features de pase...")
    pase = construir_dataset_pase(combinadas, lesiones)
    pase = pase[pase["game_id"].isin(ids_futuros)].copy()
    pase = pase[
        (pase["player_games_before"] >= 3)
        & (pase["player_passing_attempts_avg_5"] >= 10.0)
        & ~pase["player_injury_status"].isin(["out", "doubtful"])
    ].copy()
    # Un solo QB por equipo. El mayor volumen reciente resulta mas robusto
    # que el identificador preliminar del calendario cuando hay una lesion o
    # cambio de titular durante la semana.
    if not pase.empty:
        titulares = pase.groupby(["game_id", "team"])[
            "player_passing_attempts_avg_5"
        ].idxmax()
        pase["is_starting_qb"] = 0
        pase.loc[titulares, "is_starting_qb"] = 1
        pase = pase.loc[titulares].copy()

    print("Calculando features de carrera...")
    carrera = construir_dataset_carrera(combinadas, lesiones)
    carrera = carrera[carrera["game_id"].isin(ids_futuros)].copy()
    carrera = carrera[
        (carrera["player_games_before"] >= 3)
        & (carrera["player_carries_avg_5"] >= 2.0)
        & ~carrera["player_injury_status"].isin(["out", "doubtful"])
    ].copy()

    # Identifica al corredor principal activo de cada equipo. Conservamos las
    # proyecciones de todos los jugadores para análisis, pero únicamente un RB
    # con volumen estable podrá convertirse posteriormente en candidato.
    carrera["is_primary_rusher"] = 0
    principales_elegibles = carrera[
        carrera["position"].eq("RB")
        & (carrera["player_carries_avg_5"] >= 10.0)
    ]
    if not principales_elegibles.empty:
        indices_principales = principales_elegibles.groupby(
            ["game_id", "team"]
        )["player_carries_avg_5"].idxmax()
        carrera.loc[indices_principales, "is_primary_rusher"] = 1

    print("Calculando features de anota touchdown...")
    touchdown = agregar_forma_jugador_td(preparar_base_td(combinadas))
    touchdown = agregar_contexto_equipo_td(touchdown)
    touchdown = agregar_defensa_rival_td(touchdown)
    touchdown = agregar_participacion_td(touchdown)
    touchdown = agregar_lesiones_pc(touchdown, lesiones)
    touchdown = touchdown[touchdown["game_id"].isin(ids_futuros)].copy()
    touchdown = touchdown[
        (touchdown["player_games_before"] >= 3)
        & (touchdown["player_opportunities_avg_5"] >= 2.0)
        & ~touchdown["player_injury_status"].isin(["out", "doubtful"])
    ].copy()

    return (
        agregar_notas_lesiones(pase, proximos),
        agregar_notas_lesiones(carrera, proximos),
        agregar_notas_lesiones(touchdown, proximos),
    )


def predecir_modelo(modelo, df):
    columnas = list(modelo.feature_names_in_)
    faltantes = sorted(set(columnas) - set(df.columns))
    if faltantes:
        raise KeyError("Faltan features: " + ", ".join(faltantes))
    return np.maximum(modelo.predict(df[columnas]), 0)


def base_proyeccion(features):
    columnas = [
        "game_id", "season", "week", "gameday", "player_id",
        "player_name", "position", "team", "opponent_team",
        "player_injury_status", "contexto_lesiones",
        "player_carries_avg_5", "is_primary_rusher",
    ]
    base = features[[c for c in columnas if c in features.columns]].copy()
    if "player_injury_status" not in base:
        base["player_injury_status"] = "healthy_or_unlisted"
    if "contexto_lesiones" not in base:
        base["contexto_lesiones"] = ""
    if "teammate_skill_injury_score" in features:
        base["teammate_skill_injury_score"] = features[
            "teammate_skill_injury_score"
        ].to_numpy()
    elif "team_skill_injury_score" in features:
        base["teammate_skill_injury_score"] = features[
            "team_skill_injury_score"
        ].to_numpy()
    else:
        base["teammate_skill_injury_score"] = 0.0
    return base


def construir_proyecciones(features, pase, carrera, touchdown):
    for ruta in [RUTA_MODELO_RECEPCIONES, RUTA_MODELO_YARDAS, RUTA_VALIDACION]:
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontró: {ruta}")
    requeridos = [
        RUTA_MODELO_PASS_YDS, RUTA_MODELO_PASS_TDS, RUTA_MODELO_RUSH_YDS,
        RUTA_MODELO_ANYTIME_TD, RUTA_CALIBRACION_PC, RUTA_RESIDUOS_PC,
    ]
    for ruta in requeridos:
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontró: {ruta}")
    modelo_recepciones = joblib.load(RUTA_MODELO_RECEPCIONES)
    modelo_yardas = joblib.load(RUTA_MODELO_YARDAS)

    base = base_proyeccion(features)
    recepciones = base.copy()
    recepciones["tipo_prop"] = "receptions"
    recepciones["proyeccion"] = predecir_modelo(modelo_recepciones, features)
    yardas = base.copy()
    yardas["tipo_prop"] = "receiving_yards"
    yardas["proyeccion"] = predecir_modelo(modelo_yardas, features)

    config = json.loads(RUTA_CALIBRACION_PC.read_text(encoding="utf-8"))
    adicionales = []
    modelos = [
        ("passing_yards", RUTA_MODELO_PASS_YDS, pase),
        ("passing_tds", RUTA_MODELO_PASS_TDS, pase),
        ("rushing_yards", RUTA_MODELO_RUSH_YDS, carrera),
    ]
    for objetivo, ruta, conjunto in modelos:
        modelo = joblib.load(ruta)
        bloque = base_proyeccion(conjunto)
        bloque["tipo_prop"] = objetivo
        prediccion = predecir_modelo(modelo, conjunto)
        if objetivo in config.get("yardas", {}):
            ajuste = config["yardas"][objetivo]
            prediccion = np.maximum(
                ajuste.get("intercepto", 0.0)
                + ajuste.get("pendiente", 1.0) * prediccion,
                0.0,
            )
        bloque["proyeccion"] = prediccion
        adicionales.append(bloque)

    modelo_td = joblib.load(RUTA_MODELO_ANYTIME_TD)
    columnas_td = list(modelo_td.feature_names_in_)
    faltantes = sorted(set(columnas_td) - set(touchdown.columns))
    if faltantes:
        raise KeyError("Faltan features de anytime TD: " + ", ".join(faltantes))
    bloque_td = base_proyeccion(touchdown)
    bloque_td["tipo_prop"] = "anytime_td"
    bloque_td["proyeccion"] = modelo_td.predict_proba(
        touchdown[columnas_td]
    )[:, 1]
    adicionales.append(bloque_td)

    return pd.concat(
        [recepciones, yardas] + adicionales,
        ignore_index=True,
    )


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
    calibracion_recepcion = validacion[validacion["season"] == 2024].copy()
    config = json.loads(RUTA_CALIBRACION_PC.read_text(encoding="utf-8"))
    archivo_residuos = np.load(RUTA_RESIDUOS_PC)
    residuos_pc = {nombre: archivo_residuos[nombre] for nombre in archivo_residuos.files}

    probabilidades_over = []
    edges = []
    selecciones = []
    for fila in resultado.itertuples(index=False):
        if pd.isna(fila.linea):
            probabilidades_over.append(np.nan)
            edges.append(np.nan)
            selecciones.append(None)
            continue

        edge_punto = float(fila.proyeccion - fila.linea)
        if fila.tipo_prop in {"receptions", "receiving_yards"}:
            residuos = calibracion_recepcion[
                (calibracion_recepcion["objetivo"] == fila.tipo_prop)
                & (calibracion_recepcion["position"] == fila.position)
            ]["error"].dropna()
            if len(residuos) < 100:
                residuos = calibracion_recepcion[
                    calibracion_recepcion["objetivo"] == fila.tipo_prop
                ]["error"].dropna()
            probabilidad = float((residuos < edge_punto).mean())
            seleccion = "OVER" if edge_punto >= 0 else "UNDER"
            edge = edge_punto
        elif fila.tipo_prop in {"passing_yards", "rushing_yards"}:
            residuos = np.asarray(residuos_pc[fila.tipo_prop], dtype=float)
            probabilidad = float(np.mean(residuos < edge_punto))
            seleccion = "OVER" if edge_punto >= 0 else "UNDER"
            edge = edge_punto
        elif fila.tipo_prop == "passing_tds":
            clave = str(float(fila.linea))
            calibrador = config.get("passing_tds", {}).get("lineas", {}).get(clave)
            if calibrador and calibrador.get("metodo") == "logistico":
                z = (
                    float(calibrador["intercepto"])
                    + float(calibrador["coeficiente"]) * float(fila.proyeccion)
                )
                probabilidad = float(1 / (1 + np.exp(-np.clip(z, -35, 35))))
            else:
                probabilidad = float(
                    1 - poisson.cdf(np.floor(float(fila.linea)), max(float(fila.proyeccion), 1e-6))
                )
            seleccion = "OVER" if probabilidad >= 0.5 else "UNDER"
            edge = edge_punto
        elif fila.tipo_prop == "anytime_td":
            probabilidad = float(np.clip(fila.proyeccion, 0, 1))
            seleccion = "ANOTA"
            decimal_over = american_a_decimal(fila.cuota_over)
            implicita = 1 / decimal_over if pd.notna(decimal_over) else np.nan
            edge = probabilidad - implicita if pd.notna(implicita) else np.nan
        else:
            probabilidad = np.nan
            seleccion = None
            edge = np.nan

        probabilidades_over.append(probabilidad)
        edges.append(edge)
        selecciones.append(seleccion)

    resultado["edge"] = edges
    resultado["seleccion"] = selecciones
    resultado["probabilidad_over"] = probabilidades_over
    resultado["probabilidad_under"] = 1 - resultado["probabilidad_over"]
    resultado["probabilidad_pick"] = np.where(
        resultado["seleccion"].isin(["OVER", "ANOTA"]),
        resultado["probabilidad_over"],
        resultado["probabilidad_under"],
    )
    resultado["cuota_pick"] = np.where(
        resultado["seleccion"].isin(["OVER", "ANOTA"]),
        resultado["cuota_over"],
        resultado["cuota_under"],
    )
    decimal = resultado["cuota_pick"].apply(american_a_decimal)
    resultado["ev_estimado"] = (
        resultado["probabilidad_pick"] * decimal - 1
    )
    resultado["estado_pick"] = "NO PICK"
    resultado.loc[resultado["linea"].isna(), "estado_pick"] = "SIN LINEA"
    umbrales_edge = {
        "receptions": 0.75,
        "receiving_yards": 10.0,
        "passing_yards": 25.0,
        "passing_tds": 0.35,
        "rushing_yards": 20.0,
        "anytime_td": 0.05,
    }
    umbral = resultado["tipo_prop"].map(umbrales_edge).fillna(np.inf)
    es_rushing = resultado["tipo_prop"].eq("rushing_yards")
    umbral_probabilidad = np.select(
        [resultado["tipo_prop"].eq("anytime_td"), es_rushing],
        [0.25, 0.62],
        default=0.57,
    )
    umbral_ev = np.where(es_rushing, 0.05, 0.0)
    cuota_maxima = np.where(
        resultado["tipo_prop"].eq("anytime_td"), 1000, 2500
    )
    candidato = (
        resultado["linea"].notna()
        & (resultado["edge"].abs() >= umbral)
        & (resultado["probabilidad_pick"] >= umbral_probabilidad)
        & (resultado["ev_estimado"] > umbral_ev)
        & (resultado["cuota_pick"].abs() >= 100)
        & (resultado["cuota_pick"].abs() <= cuota_maxima)
    )

    # Yardas terrestres: solamente el RB principal, con volumen reciente
    # suficiente. Esto limita naturalmente a uno por equipo y dos por juego.
    carries_promedio = pd.to_numeric(
        resultado.get("player_carries_avg_5"), errors="coerce"
    ).fillna(0.0)
    principal = pd.to_numeric(
        resultado.get("is_primary_rusher"), errors="coerce"
    ).fillna(0).eq(1)
    rushing_valido = (
        resultado["position"].eq("RB")
        & (carries_promedio >= 10.0)
        & principal
    )
    candidato &= ~es_rushing | rushing_valido

    # Candado adicional: aun con datos duplicados nunca publicar más de dos
    # candidatos terrestres por partido.
    indices_rushing = (
        resultado.loc[candidato & es_rushing]
        .sort_values(
            ["game_id", "ev_estimado", "probabilidad_pick"],
            ascending=[True, False, False],
        )
        .groupby("game_id", sort=False)
        .head(2)
        .index
    )
    candidato &= ~es_rushing | resultado.index.isin(indices_rushing)
    resultado.loc[candidato, "estado_pick"] = "CANDIDATO"
    revisar_lesion = candidato & resultado["player_injury_status"].eq(
        "questionable"
    )
    resultado.loc[revisar_lesion, "estado_pick"] = "REVISAR LESION"
    return resultado


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--solo-hoy', action='store_true')
    args = parser.parse_args()
    DIRECTORIO_SALIDA.mkdir(parents=True, exist_ok=True)
    calendario = actualizar_calendario()
    game_ids = None
    if args.solo_hoy:
        hoy = calendario_hoy(calendario[
            calendario['season'].eq(TEMPORADA_ACTUAL) & calendario['game_type'].eq('REG')
            & (calendario['home_score'].isna() | calendario['away_score'].isna())])
        if hoy.empty:
            print('No hay partidos NFL de hoy sin iniciar; no se generan props.')
            return
        game_ids = hoy['game_id'].tolist()
        semana = int(hoy['week'].min())
    else:
        semana = obtener_proxima_semana(calendario)
    actualizar_lesiones()
    actualizar_estadisticas_jugadores()
    print(f"Semana detectada: {semana}")

    features, juegos = preparar_features(calendario, semana, game_ids=game_ids)
    pase, carrera, touchdown = preparar_features_adicionales(calendario, semana, game_ids=game_ids)
    print(
        "Jugadores elegibles | "
        f"recepcion: {len(features):,} | pase: {len(pase):,} | "
        f"carrera: {len(carrera):,} | anota TD: {len(touchdown):,}"
    )
    proyecciones = construir_proyecciones(
        features, pase, carrera, touchdown
    )

    catalogo = pd.concat(
        [
            conjunto[["player_id", "player_name", "position", "team"]]
            for conjunto in [features, pase, carrera, touchdown]
        ],
        ignore_index=True,
    ).drop_duplicates("player_id")

    if args.solo_hoy:
        juegos = calendario_hoy(juegos)
        proyecciones = proyecciones[proyecciones['game_id'].isin(juegos['game_id'])].copy()
        if juegos.empty:
            print('Los partidos ya comenzaron; no se guardan nuevas predicciones prepartido.')
            return

    conexion = obtener_conexion()
    if conexion is None:
        raise RuntimeError('No hay conexión MySQL para guardar props.')
    try:
        if conexion is not None:
            sincronizar_catalogos(conexion, catalogo, juegos)
        lineas = cargar_lineas(conexion, juegos["game_id"].tolist())
        resultado = agregar_lineas_y_probabilidades(proyecciones, lineas)
        guardar_proyecciones(conexion, resultado)
    finally:
        if conexion is not None and conexion.is_connected():
            conexion.close()

    ruta = DIRECTORIO_SALIDA / (
        f"nfl_props_{TEMPORADA_ACTUAL}_semana_{semana}" + ("_hoy" if args.solo_hoy else "") + ".csv"
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

