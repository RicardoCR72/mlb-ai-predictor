"""Descarga props NFL de The Odds API y guarda capturas en MySQL.

Mercados:
* player_receptions      -> receptions
* player_reception_yds   -> receiving_yards
* player_pass_yds        -> passing_yards
* player_pass_tds        -> passing_tds
* player_rush_yds        -> rushing_yards
* player_anytime_td      -> anytime_td

El script conserva el historial: solo evita insertar una fila nueva cuando la
ultima captura de la misma casa tiene exactamente la misma linea y cuotas.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector
import pandas as pd
import requests

from predecir_semana_actual import TEMPORADA_ACTUAL, obtener_configuracion_mysql


API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"
REGION = "us"
MARKETS = {
    "player_receptions": "receptions",
    "player_reception_yds": "receiving_yards",
    "player_pass_yds": "passing_yards",
    "player_pass_tds": "passing_tds",
    "player_rush_yds": "rushing_yards",
    "player_anytime_td": "anytime_td",
}

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_JUGADORES = (
    RAIZ_PROYECTO / "data" / "nfl" / "raw"
    / "nfl_player_stats_2012_2026.parquet"
)
DIRECTORIO_CACHE = RAIZ_PROYECTO / "data" / "nfl" / "cache" / "odds_props"

# Casas que normalmente tienen buena cobertura de props NFL. Si ninguna de
# estas aparece para un partido, se conserva la primera casa disponible.
CASAS_PREFERIDAS = {
    "draftkings",
    "fanduel",
    "betmgm",
    "williamhill_us",
    "espnbet",
}

EQUIPO_API_A_SIGLA = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


def leer_secrets_streamlit() -> dict:
    """Lee secrets.toml local sin depender de Streamlit."""
    try:
        import tomllib
    except ImportError:  # pragma: no cover - el proyecto usa Python 3.12
        return {}

    raiz = Path(__file__).resolve().parents[1]
    rutas = [
        raiz / ".streamlit" / "secrets.toml",
        Path.cwd() / ".streamlit" / "secrets.toml",
    ]
    for ruta in rutas:
        if ruta.exists():
            with ruta.open("rb") as archivo:
                return tomllib.load(archivo)
    return {}


def obtener_api_key() -> str:
    for nombre in ("ODDS_API_KEY", "THE_ODDS_API_KEY", "odds_api_key"):
        valor = os.getenv(nombre)
        if valor:
            return valor.strip()

    secrets = leer_secrets_streamlit()
    for nombre in ("odds_api_key", "ODDS_API_KEY", "THE_ODDS_API_KEY"):
        valor = secrets.get(nombre)
        if valor:
            return str(valor).strip()

    raise RuntimeError(
        "No se encontro la API key. Configura ODDS_API_KEY o "
        ".streamlit/secrets.toml con odds_api_key."
    )


def conectar_mysql():
    configuracion = obtener_configuracion_mysql()
    if configuracion is None:
        raise RuntimeError(
            "Faltan las variables DB_HOST, DB_PORT, DB_USER, DB_PASSWORD y DB_NAME."
        )
    return mysql.connector.connect(**configuracion)


def api_get(ruta: str, api_key: str, **parametros):
    params = {"apiKey": api_key, **parametros}
    respuesta = requests.get(f"{API_BASE}{ruta}", params=params, timeout=30)
    if respuesta.status_code != 200:
        detalle = respuesta.text[:500]
        raise RuntimeError(
            f"The Odds API respondio {respuesta.status_code}: {detalle}"
        )
    cuota = {
        "usados": respuesta.headers.get("x-requests-used"),
        "restantes": respuesta.headers.get("x-requests-remaining"),
        "costo": respuesta.headers.get("x-requests-last"),
    }
    return respuesta.json(), cuota


def cargar_juegos_pendientes(conexion):
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id_juego, temporada, semana, fecha,
               equipo_local, equipo_visitante
        FROM nfl_juegos
        WHERE temporada = %s
          AND estado = 'PROGRAMADO'
          AND fecha >= DATE_SUB(CURDATE(), INTERVAL 1 DAY)
        ORDER BY semana, fecha, id_juego
        """,
        (TEMPORADA_ACTUAL,),
    )
    juegos = cursor.fetchall()
    cursor.close()
    if not juegos:
        return []

    # Evita gastar créditos consultando semanas futuras que ya estén cargadas.
    semana = min(int(juego["semana"]) for juego in juegos)
    return [juego for juego in juegos if int(juego["semana"]) == semana]


def emparejar_eventos(juegos, eventos, permitir_iniciados=False):
    por_equipos = {
        (juego["equipo_visitante"], juego["equipo_local"]): juego
        for juego in juegos
    }
    parejas = []
    ahora = datetime.now(timezone.utc)
    for evento in eventos:
        inicio_texto = evento.get("commence_time")
        if inicio_texto:
            try:
                inicio = datetime.fromisoformat(
                    inicio_texto.replace("Z", "+00:00")
                )
                # Nunca guardar líneas live como si fueran prepartido.
                if inicio <= ahora and not permitir_iniciados:
                    continue
            except (TypeError, ValueError):
                pass
        visitante = EQUIPO_API_A_SIGLA.get(evento.get("away_team"))
        local = EQUIPO_API_A_SIGLA.get(evento.get("home_team"))
        juego = por_equipos.get((visitante, local))
        if juego:
            parejas.append((juego, evento))
    return parejas


def texto_normalizado(valor: str) -> str:
    # Algunas casas devuelven nombres unidos: CaseKeenum, CeeDeeLamb.
    valor = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(valor or ""))
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(c for c in valor if not unicodedata.combining(c)).lower()
    valor = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", valor)
    return re.sub(r"[^a-z0-9]+", " ", valor).strip()


def clave_nombre(valor: str):
    partes = texto_normalizado(valor).split()
    if not partes:
        return None
    # Primer inicial + ultimo apellido relaciona Alvin Kamara con A.Kamara,
    # CJ Daniels con C.J.Daniels y Amon-Ra St. Brown con A.St. Brown.
    return partes[0][0], partes[-1]


def cargar_catalogo_estadisticas():
    """Lee IDs y usa el nombre completo cuando el parquet lo incluye."""
    columnas_disponibles = set()
    try:
        import pyarrow.parquet as pq
        columnas_disponibles = set(
            pq.ParquetFile(RUTA_JUGADORES).schema.names
        )
    except Exception:
        pass

    candidatos_nombre = [
        "player_display_name", "display_name", "football_name", "player_name"
    ]
    nombre_fuente = next(
        (c for c in candidatos_nombre if c in columnas_disponibles),
        "player_name",
    )
    columnas = [
        "player_id", nombre_fuente, "position", "team", "season", "week"
    ]
    df = pd.read_parquet(RUTA_JUGADORES, columns=list(dict.fromkeys(columnas)))
    if nombre_fuente != "player_name":
        df = df.rename(columns={nombre_fuente: "player_name"})
    return df


def sincronizar_catalogo_jugadores(conexion):
    """Actualiza el catalogo con el registro mas reciente de cada jugador.

    Incluir el historial permite relacionar jugadores activos que todavia no
    registran estadisticas en la temporada actual (lesionados, suplentes y
    novatos con datos de una temporada anterior).
    """
    if not RUTA_JUGADORES.exists():
        print(f"ADVERTENCIA: no existe el catalogo local {RUTA_JUGADORES}")
        return 0

    df = cargar_catalogo_estadisticas()
    df = df.copy()
    for columna in ["player_id", "player_name", "position", "team"]:
        df[columna] = df[columna].fillna("").astype(str).str.strip()
    df = df[
        df["player_id"].ne("")
        & df["player_name"].ne("")
        & df["position"].ne("")
        & df["team"].ne("")
    ]
    df = (
        df.sort_values(["player_id", "season", "week"])
        .drop_duplicates("player_id", keep="last")
    )
    if df.empty:
        return 0

    cursor = conexion.cursor()
    cursor.executemany(
        """
        INSERT INTO nfl_jugadores (id_jugador, nombre, posicion, equipo_actual)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            nombre = VALUES(nombre),
            posicion = VALUES(posicion),
            equipo_actual = VALUES(equipo_actual)
        """,
        list(
            df[["player_id", "player_name", "position", "team"]]
            .itertuples(index=False, name=None)
        ),
    )
    conexion.commit()
    cursor.close()
    return len(df)


def cargar_jugadores_por_equipo(conexion, equipos):
    # Se usa el ultimo registro conocido de cada ID. Esto conserva jugadores
    # activos que aun no aparecen en las estadisticas de la temporada actual.
    if RUTA_JUGADORES.exists():
        df = cargar_catalogo_estadisticas()
        df = df.copy()
        for columna in ["player_id", "player_name", "position", "team"]:
            df[columna] = df[columna].fillna("").astype(str).str.strip()
        df = df[
            df["player_id"].ne("")
            & df["player_name"].ne("")
            & df["position"].ne("")
            & df["team"].ne("")
        ]
        df = (
            df.sort_values(["player_id", "season", "week"])
            .drop_duplicates("player_id", keep="last")
            .rename(columns={
                "player_id": "id_jugador",
                "player_name": "nombre",
                "position": "posicion",
                "team": "equipo_actual",
            })
        )
        return df[
            [
                "id_jugador", "nombre", "posicion", "equipo_actual",
                "season", "week",
            ]
        ].to_dict("records")

    cursor = conexion.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id_jugador, nombre, posicion, equipo_actual
        FROM nfl_jugadores
        """
    )
    jugadores = cursor.fetchall()
    cursor.close()
    for jugador in jugadores:
        jugador["season"] = 0
        jugador["week"] = 0
    return jugadores


def indice_jugadores(jugadores):
    por_equipo = defaultdict(list)
    for jugador in jugadores:
        jugador = dict(jugador)
        jugador["nombre_normalizado"] = texto_normalizado(jugador["nombre"])
        jugador["clave_nombre"] = clave_nombre(jugador["nombre"])
        jugador["ultima_temporada"] = int(jugador.get("season") or 0)
        jugador["ultima_semana"] = int(jugador.get("week") or 0)
        por_equipo[jugador["equipo_actual"]].append(jugador)
        por_equipo["__todos__"].append(jugador)
    return por_equipo


def resolver_jugador(nombre_api, equipos_juego, indice):
    def mas_reciente(opciones):
        if not opciones:
            return None
        ordenadas = sorted(
            opciones,
            key=lambda j: (j["ultima_temporada"], j["ultima_semana"]),
            reverse=True,
        )
        mejor_fecha = (
            ordenadas[0]["ultima_temporada"], ordenadas[0]["ultima_semana"]
        )
        mejores = [
            j for j in ordenadas
            if (j["ultima_temporada"], j["ultima_semana"]) == mejor_fecha
        ]
        return mejores[0] if len(mejores) == 1 else None

    candidatos = []
    for equipo in equipos_juego:
        candidatos.extend(indice.get(equipo, []))

    normalizado = texto_normalizado(nombre_api)
    exactos = [j for j in candidatos if j["nombre_normalizado"] == normalizado]
    if len(exactos) == 1:
        return exactos[0]

    clave = clave_nombre(nombre_api)
    similares = [j for j in candidatos if j["clave_nombre"] == clave]
    if len(similares) == 1:
        return similares[0]
    reciente = mas_reciente(similares)
    if reciente is not None:
        return reciente

    # Un nombre completo exacto es seguro incluso si el ultimo equipo guardado
    # ya no coincide con el roster actual.
    exactos_globales = [
        j for j in indice.get("__todos__", [])
        if j["nombre_normalizado"] == normalizado
    ]
    if len(exactos_globales) == 1:
        return exactos_globales[0]

    # Si el equipo en el feed estadistico esta desactualizado, se permite un
    # match global solamente cuando inicial+apellido identifica a una persona.
    globales = [
        j for j in indice.get("__todos__", [])
        if j["clave_nombre"] == clave
    ]
    if len(globales) == 1:
        return globales[0]
    reciente = mas_reciente(globales)
    if reciente is not None:
        return reciente

    # Último recurso: apellido único dentro de los dos equipos del partido.
    partes = normalizado.split()
    apellido = partes[-1] if partes else ""
    apellido_unico = [
        j for j in candidatos
        if j["nombre_normalizado"].split()
        and j["nombre_normalizado"].split()[-1] == apellido
    ]
    return apellido_unico[0] if len(apellido_unico) == 1 else None


def ruta_cache_evento(evento_id):
    return DIRECTORIO_CACHE / f"{evento_id}.json"


def guardar_cache_evento(evento_id, respuesta):
    DIRECTORIO_CACHE.mkdir(parents=True, exist_ok=True)
    ruta_cache_evento(evento_id).write_text(
        json.dumps(respuesta, ensure_ascii=False), encoding="utf-8"
    )


def cargar_cache_evento(evento_id):
    ruta = ruta_cache_evento(evento_id)
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def cargar_eventos_desde_cache():
    """Recupera eventos completos cacheados, incluso si ya comenzaron."""
    eventos = []
    if not DIRECTORIO_CACHE.exists():
        return eventos
    for ruta in DIRECTORIO_CACHE.glob("*.json"):
        try:
            evento = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(evento, dict) and evento.get("id"):
            eventos.append(evento)
    return eventos


def seleccionar_casas(bookmakers):
    preferidas = [b for b in bookmakers if b.get("key") in CASAS_PREFERIDAS]
    return preferidas or bookmakers[:1]


def extraer_lineas(respuesta, juego, indice):
    agrupadas = {}
    no_resueltos = set()
    equipos = {juego["equipo_local"], juego["equipo_visitante"]}

    for casa in seleccionar_casas(respuesta.get("bookmakers", [])):
        casa_nombre = str(casa.get("title") or casa.get("key") or "Desconocida")[:50]
        for mercado in casa.get("markets", []):
            tipo_prop = MARKETS.get(mercado.get("key"))
            if not tipo_prop:
                continue
            captura = mercado.get("last_update") or casa.get("last_update")
            for resultado in mercado.get("outcomes", []):
                nombre = str(resultado.get("name", ""))
                descripcion = str(resultado.get("description", ""))
                if tipo_prop == "anytime_td" and nombre.lower() in {"yes", "no"}:
                    lado = "over" if nombre.lower() == "yes" else "under"
                    nombre_jugador = descripcion
                elif tipo_prop == "anytime_td" and descripcion.lower() in {"yes", "no"}:
                    lado = "over" if descripcion.lower() == "yes" else "under"
                    nombre_jugador = nombre
                elif nombre.lower() in {"over", "under"}:
                    lado, nombre_jugador = nombre.lower(), descripcion
                elif descripcion.lower() in {"over", "under"}:
                    lado, nombre_jugador = descripcion.lower(), nombre
                else:
                    continue

                jugador = resolver_jugador(nombre_jugador, equipos, indice)
                if jugador is None:
                    no_resueltos.add(nombre_jugador)
                    continue

                punto = resultado.get("point")
                if tipo_prop == "anytime_td" and punto is None:
                    punto = 0.5
                cuota = resultado.get("price")
                if punto is None or cuota is None:
                    continue
                clave = (
                    juego["id_juego"], jugador["id_jugador"], casa_nombre,
                    tipo_prop, float(punto), captura,
                )
                fila = agrupadas.setdefault(
                    clave,
                    {
                        "id_juego": juego["id_juego"],
                        "id_jugador": jugador["id_jugador"],
                        "jugador": jugador["nombre"],
                        "casa_apuestas": casa_nombre,
                        "tipo_prop": tipo_prop,
                        "linea": float(punto),
                        "cuota_over": None,
                        "cuota_under": None,
                        "timestamp_captura": captura,
                    },
                )
                fila[f"cuota_{lado}"] = float(cuota)

    completas = []
    for fila in agrupadas.values():
        if fila["tipo_prop"] == "anytime_td":
            if fila["cuota_over"] is not None:
                completas.append(fila)
        elif fila["cuota_over"] is not None and fila["cuota_under"] is not None:
            completas.append(fila)
    return completas, no_resueltos


def convertir_timestamp(valor):
    if not valor:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).astimezone(
            timezone.utc
        ).replace(tzinfo=None)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).replace(tzinfo=None)


def cargar_ultimas_lineas(conexion, ids_juegos):
    if not ids_juegos:
        return {}
    marcas = ",".join(["%s"] * len(ids_juegos))
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(
        f"""
        SELECT id_linea, id_juego, id_jugador, casa_apuestas, tipo_prop,
               linea, cuota_over, cuota_under, timestamp_captura
        FROM nfl_lineas_props
        WHERE id_juego IN ({marcas})
        ORDER BY timestamp_captura DESC, id_linea DESC
        """,
        tuple(ids_juegos),
    )
    ultimas = {}
    for fila in cursor.fetchall():
        clave = (
            fila["id_juego"], fila["id_jugador"],
            fila["casa_apuestas"], fila["tipo_prop"],
        )
        ultimas.setdefault(clave, fila)
    cursor.close()
    return ultimas


def misma_linea(anterior, nueva):
    for columna in ("linea", "cuota_over", "cuota_under"):
        valor_anterior = anterior[columna]
        valor_nuevo = nueva[columna]
        if valor_anterior is None or valor_nuevo is None:
            if valor_anterior is not None or valor_nuevo is not None:
                return False
        elif abs(float(valor_anterior) - float(valor_nuevo)) >= 1e-9:
            return False
    return True


def guardar_lineas(conexion, lineas):
    ultimas = cargar_ultimas_lineas(
        conexion, sorted({fila["id_juego"] for fila in lineas})
    )
    nuevas = []
    for fila in lineas:
        clave = (
            fila["id_juego"], fila["id_jugador"],
            fila["casa_apuestas"], fila["tipo_prop"],
        )
        anterior = ultimas.get(clave)
        if anterior is None or not misma_linea(anterior, fila):
            nuevas.append(fila)

    if not nuevas:
        return 0

    cursor = conexion.cursor()
    cursor.executemany(
        """
        INSERT INTO nfl_lineas_props (
            id_juego, id_jugador, casa_apuestas, tipo_prop,
            linea, cuota_over, cuota_under, timestamp_captura
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                fila["id_juego"], fila["id_jugador"],
                fila["casa_apuestas"], fila["tipo_prop"],
                fila["linea"], fila["cuota_over"], fila["cuota_under"],
                convertir_timestamp(fila["timestamp_captura"]),
            )
            for fila in nuevas
        ],
    )
    conexion.commit()
    cursor.close()
    return len(nuevas)


def respaldar_y_limpiar_semana(conexion, juegos, temporada, semana):
    """Respalda y elimina proyecciones/lineas respetando sus llaves foraneas."""
    ids = sorted({str(juego["id_juego"]) for juego in juegos})
    if not ids:
        return {
            "tabla_lineas": "", "tabla_proyecciones": "",
            "lineas_respaldadas": 0, "proyecciones_respaldadas": 0,
            "lineas_eliminadas": 0, "proyecciones_eliminadas": 0,
        }
    temporada = int(temporada)
    semana = int(semana)
    tabla_lineas = f"nfl_lineas_props_respaldo_{temporada}_s{semana}"
    tabla_proyecciones = (
        f"nfl_proyecciones_props_respaldo_{temporada}_s{semana}"
    )
    marcadores = ",".join(["%s"] * len(ids))
    cursor = conexion.cursor()
    cursor.execute(
        f"CREATE TABLE IF NOT EXISTS {tabla_lineas} LIKE nfl_lineas_props"
    )
    cursor.execute(
        f"""
        INSERT IGNORE INTO {tabla_lineas}
        SELECT * FROM nfl_lineas_props
        WHERE id_juego IN ({marcadores})
        """,
        tuple(ids),
    )
    lineas_respaldadas = max(int(cursor.rowcount), 0)

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {tabla_proyecciones}
        LIKE nfl_proyecciones_props
        """
    )
    cursor.execute(
        f"""
        INSERT IGNORE INTO {tabla_proyecciones}
        SELECT * FROM nfl_proyecciones_props
        WHERE id_juego IN ({marcadores})
        """,
        tuple(ids),
    )
    proyecciones_respaldadas = max(int(cursor.rowcount), 0)
    cursor.execute(
        f"DELETE FROM nfl_proyecciones_props WHERE id_juego IN ({marcadores})",
        tuple(ids),
    )
    proyecciones_eliminadas = max(int(cursor.rowcount), 0)
    cursor.execute(
        f"DELETE FROM nfl_lineas_props WHERE id_juego IN ({marcadores})",
        tuple(ids),
    )
    lineas_eliminadas = max(int(cursor.rowcount), 0)
    conexion.commit()
    cursor.close()
    return {
        "tabla_lineas": tabla_lineas,
        "tabla_proyecciones": tabla_proyecciones,
        "lineas_respaldadas": lineas_respaldadas,
        "proyecciones_respaldadas": proyecciones_respaldadas,
        "lineas_eliminadas": lineas_eliminadas,
        "proyecciones_eliminadas": proyecciones_eliminadas,
    }


def imprimir_cuota(cuota):
    partes = []
    if cuota.get("costo") is not None:
        partes.append(f"costo ultima consulta: {cuota['costo']}")
    if cuota.get("usados") is not None:
        partes.append(f"usados: {cuota['usados']}")
    if cuota.get("restantes") is not None:
        partes.append(f"restantes: {cuota['restantes']}")
    if partes:
        print("Créditos API | " + " | ".join(partes))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--solo-eventos",
        action="store_true",
        help="Valida partidos sin solicitar props ni consumir sus créditos.",
    )
    parser.add_argument(
        "--solo-catalogo",
        action="store_true",
        help="Sincroniza nfl_jugadores sin consultar eventos ni props.",
    )
    parser.add_argument(
        "--usar-cache",
        action="store_true",
        help="Reprocesa la ultima respuesta guardada sin consumir creditos.",
    )
    parser.add_argument(
        "--reconstruir-semana",
        action="store_true",
        help=(
            "Respalda y reemplaza las lineas de la semana. "
            "Debe utilizarse junto con --usar-cache."
        ),
    )
    args = parser.parse_args()

    if args.reconstruir_semana and not args.usar_cache:
        parser.error("--reconstruir-semana requiere --usar-cache")

    api_key = obtener_api_key()
    conexion = conectar_mysql()
    try:
        sincronizados = sincronizar_catalogo_jugadores(conexion)
        print(f"Catalogo NFL sincronizado: {sincronizados:,} jugadores.")
        if args.solo_catalogo:
            print("Catalogo actualizado. No se consulto The Odds API.")
            return
        juegos = cargar_juegos_pendientes(conexion)
        if not juegos:
            print("No hay juegos NFL pendientes para capturar.")
            return

        semana = juegos[0]["semana"]
        print(f"Juegos pendientes de la semana {semana}: {len(juegos)}")
        if args.reconstruir_semana:
            reconstruccion = respaldar_y_limpiar_semana(
                conexion, juegos, TEMPORADA_ACTUAL, semana
            )
            print(
                f"Respaldos: {reconstruccion['tabla_lineas']} y "
                f"{reconstruccion['tabla_proyecciones']}"
            )
            print(
                "Lineas | nuevas respaldadas: "
                f"{reconstruccion['lineas_respaldadas']:,} | retiradas: "
                f"{reconstruccion['lineas_eliminadas']:,}"
            )
            print(
                "Proyecciones | nuevas respaldadas: "
                f"{reconstruccion['proyecciones_respaldadas']:,} | retiradas: "
                f"{reconstruccion['proyecciones_eliminadas']:,}"
            )
        eventos, cuota = api_get(f"/sports/{SPORT}/events", api_key)
        if args.usar_cache:
            por_id = {evento.get("id"): evento for evento in eventos}
            for evento in cargar_eventos_desde_cache():
                por_id[evento.get("id")] = evento
            eventos = list(por_id.values())
        parejas = emparejar_eventos(
            juegos, eventos, permitir_iniciados=args.usar_cache
        )
        print(f"Partidos emparejados con The Odds API: {len(parejas)}")
        imprimir_cuota(cuota)

        faltantes = {
            juego["id_juego"] for juego in juegos
        } - {juego["id_juego"] for juego, _ in parejas}
        if faltantes:
            print("Sin evento API: " + ", ".join(sorted(faltantes)))

        if args.solo_eventos:
            print("Validacion terminada. No se solicitaron ni guardaron props.")
            return

        equipos = {
            equipo
            for juego, _ in parejas
            for equipo in (juego["equipo_local"], juego["equipo_visitante"])
        }
        jugadores = cargar_jugadores_por_equipo(conexion, equipos)
        indice = indice_jugadores(jugadores)

        todas = []
        no_resueltos = set()
        for numero, (juego, evento) in enumerate(parejas, start=1):
            print(
                f"[{numero}/{len(parejas)}] {juego['equipo_visitante']} @ "
                f"{juego['equipo_local']}..."
            )
            respuesta = cargar_cache_evento(evento["id"])
            if args.usar_cache and respuesta is None:
                print("  Sin respuesta cacheada; se omite sin consultar la API.")
                continue
            if not args.usar_cache:
                respuesta, cuota = api_get(
                    f"/sports/{SPORT}/events/{evento['id']}/odds",
                    api_key,
                    regions=REGION,
                    markets=",".join(MARKETS),
                    oddsFormat="american",
                    dateFormat="iso",
                )
                guardar_cache_evento(evento["id"], respuesta)
            else:
                cuota = {"usados": None, "restantes": None, "costo": 0}
                print("  Usando respuesta cacheada.")
            lineas, sin_match = extraer_lineas(respuesta, juego, indice)
            todas.extend(lineas)
            no_resueltos.update(sin_match)
            print(f"  Lineas completas encontradas: {len(lineas)}")
            imprimir_cuota(cuota)

        insertadas = guardar_lineas(conexion, todas)
        print("\n" + "=" * 72)
        print(f"Lineas completas descargadas: {len(todas):,}")
        print(f"Capturas nuevas insertadas en MySQL: {insertadas:,}")
        print(f"Capturas sin cambios omitidas: {len(todas) - insertadas:,}")
        if no_resueltos:
            muestra = ", ".join(sorted(no_resueltos)[:20])
            print(f"Jugadores no relacionados ({len(no_resueltos)}): {muestra}")
        print("=" * 72)
    finally:
        if conexion.is_connected():
            conexion.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
