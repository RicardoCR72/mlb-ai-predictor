"""Descarga props NFL de The Odds API y guarda capturas en MySQL.

Mercados iniciales:
* player_receptions      -> receptions
* player_reception_yds   -> receiving_yards

El script conserva el historial: solo evita insertar una fila nueva cuando la
ultima captura de la misma casa tiene exactamente la misma linea y cuotas.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector
import requests

from predecir_semana_actual import TEMPORADA_ACTUAL, obtener_configuracion_mysql


API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"
REGION = "us"
MARKETS = {
    "player_receptions": "receptions",
    "player_reception_yds": "receiving_yards",
}

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


def emparejar_eventos(juegos, eventos):
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
                if inicio <= ahora:
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
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(c for c in valor if not unicodedata.combining(c)).lower()
    valor = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", valor)
    return re.sub(r"[^a-z0-9]+", " ", valor).strip()


def clave_nombre(valor: str):
    partes = texto_normalizado(valor).split()
    if not partes:
        return None
    return partes[0][0], "".join(partes[1:] or partes)


def cargar_jugadores_por_equipo(conexion, equipos):
    marcas = ",".join(["%s"] * len(equipos))
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(
        f"""
        SELECT id_jugador, nombre, posicion, equipo_actual
        FROM nfl_jugadores
        WHERE equipo_actual IN ({marcas})
        """,
        tuple(sorted(equipos)),
    )
    jugadores = cursor.fetchall()
    cursor.close()
    return jugadores


def indice_jugadores(jugadores):
    por_equipo = defaultdict(list)
    for jugador in jugadores:
        jugador = dict(jugador)
        jugador["nombre_normalizado"] = texto_normalizado(jugador["nombre"])
        jugador["clave_nombre"] = clave_nombre(jugador["nombre"])
        por_equipo[jugador["equipo_actual"]].append(jugador)
    return por_equipo


def resolver_jugador(nombre_api, equipos_juego, indice):
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

    # Último recurso: apellido único dentro de los dos equipos del partido.
    partes = normalizado.split()
    apellido = partes[-1] if partes else ""
    apellido_unico = [
        j for j in candidatos
        if j["nombre_normalizado"].split()
        and j["nombre_normalizado"].split()[-1] == apellido
    ]
    return apellido_unico[0] if len(apellido_unico) == 1 else None


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
                if nombre.lower() in {"over", "under"}:
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

    completas = [
        fila for fila in agrupadas.values()
        if fila["cuota_over"] is not None and fila["cuota_under"] is not None
    ]
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
    return all(
        abs(float(anterior[columna]) - float(nueva[columna])) < 1e-9
        for columna in ("linea", "cuota_over", "cuota_under")
    )


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
    args = parser.parse_args()

    api_key = obtener_api_key()
    conexion = conectar_mysql()
    try:
        juegos = cargar_juegos_pendientes(conexion)
        if not juegos:
            print("No hay juegos NFL pendientes para capturar.")
            return

        semana = juegos[0]["semana"]
        print(f"Juegos pendientes de la semana {semana}: {len(juegos)}")
        eventos, cuota = api_get(f"/sports/{SPORT}/events", api_key)
        parejas = emparejar_eventos(juegos, eventos)
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
            respuesta, cuota = api_get(
                f"/sports/{SPORT}/events/{evento['id']}/odds",
                api_key,
                regions=REGION,
                markets=",".join(MARKETS),
                oddsFormat="american",
                dateFormat="iso",
            )
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
