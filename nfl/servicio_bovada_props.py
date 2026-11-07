"""Servicio extractor de líneas y momios de Player Props de la NFL desde Bovada (0 Créditos).

Extrae en tiempo real las líneas de:
* Yardas de Pase (passing_yards)
* Pases de Touchdown (passing_tds)
* Yardas por Carrera (rushing_yards)
* Yardas por Recepción (receiving_yards)
* Recepciones Totales (receptions)
* Anotador de Touchdown en cualquier momento (anytime_td)

Totalmente gratuito: 0 créditos consumidos, consultas ilimitadas.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX
from core.db import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nfl_servicio_bovada")

URL_BOVADA_NFL = "https://www.bovada.lv/services/sports/event/v2/events/A/description/football/nfl"
DIR_CACHE = RAIZ / "data" / "nfl" / "cache"
RUTA_CACHE_PROPS = DIR_CACHE / "bovada_nfl_props.json"
RUTA_PARQUET_PROPS = DIR_CACHE / "bovada_nfl_props.parquet"

# Mapeo de nombres completos de equipos Bovada a siglas oficiales NFL
EQUIPOS_BOVADA_A_SIGLA = {
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


def _limpiar_nombre(texto: str) -> str:
    """Normaliza cadenas quitando puntuación y sufijos de nombres."""
    import unicodedata
    s = str(texto or "").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")
    s = re.sub(r"\s+(Jr\.?|Sr\.?|II|III|IV|V)$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.split()).lower()


def _american_a_decimal(american: Any) -> float:
    """Convierte momio americano a cuota decimal."""
    try:
        s = str(american).strip().upper()
        if s == "EVEN":
            return 2.0
        val = float(s)
        if val > 0:
            return round((val / 100.0) + 1.0, 4)
        else:
            return round((100.0 / abs(val)) + 1.0, 4)
    except Exception:
        return 1.909


def descargar_mercados_bovada_nfl() -> List[Dict[str, Any]]:
    """Descarga los eventos y mercados de la NFL directamente de la API pública de Bovada."""
    req = urllib.request.Request(
        URL_BOVADA_NFL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list) and len(data) > 0:
                return data[0].get("events", [])
    except Exception as e:
        logger.error(f"Error descargando NFL de Bovada: {e}")
    return []


def _construir_indice_jugadores() -> Dict[str, Any]:
    """Carga los jugadores de la base de datos de la NFL para emparejamiento rápido."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id_jugador, nombre, equipo_actual, posicion FROM nfl_jugadores")
        filas = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f"No se pudo cargar nfl_jugadores de BD: {e}")
        filas = []

    indice_norm = {}
    indice_por_equipo = {}
    for f in filas:
        norm = _limpiar_nombre(f["nombre"])
        indice_norm[norm] = f
        eq = f.get("equipo_actual")
        if eq:
            if eq not in indice_por_equipo:
                indice_por_equipo[eq] = {}
            indice_por_equipo[eq][norm] = f

    return {
        "global": indice_norm,
        "por_equipo": indice_por_equipo,
    }


def _resolver_jugador_nfl(nombre: str, equipo_sug: str, indice: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Busca al jugador por nombre y equipo sugerido."""
    norm = _limpiar_nombre(nombre)
    if not norm:
        return None

    # 1. Búsqueda directa por equipo
    if equipo_sug and equipo_sug in indice["por_equipo"]:
        if norm in indice["por_equipo"][equipo_sug]:
            return indice["por_equipo"][equipo_sug][norm]

    # 2. Búsqueda directa global
    if norm in indice["global"]:
        return indice["global"][norm]

    # 3. Coincidencia por apellido único en el equipo
    partes = norm.split()
    if partes and equipo_sug and equipo_sug in indice["por_equipo"]:
        apellido = partes[-1]
        matches = [j for n, j in indice["por_equipo"][equipo_sug].items() if n.split() and n.split()[-1] == apellido]
        if len(matches) == 1:
            return matches[0]

    # 4. Coincidencia por inicial y apellido
    if len(partes) >= 2:
        ini_ape = f"{partes[0][0]} {partes[-1]}"
        matches_global = [j for n, j in indice["global"].items() if len(n.split()) >= 2 and f"{n.split()[0][0]} {n.split()[-1]}" == ini_ape]
        if len(matches_global) == 1:
            return matches_global[0]

    return None


def _asegurar_juegos_registrados(conn) -> int:
    """Verifica y asegura que los juegos de la temporada 2026 del calendario estén en nfl_juegos."""
    ruta_sched = RAIZ / "data" / "nfl" / "raw" / "nfl_schedules_2012_2026.parquet"
    if not ruta_sched.exists():
        return 0
    try:
        df_sched = pd.read_parquet(ruta_sched)
        sched_2026 = df_sched[df_sched["season"] >= 2026]
        if sched_2026.empty:
            return 0
        cur = conn.cursor()
        sql = """
            INSERT INTO nfl_juegos (
                id_juego, temporada, tipo_juego, semana, fecha,
                equipo_local, equipo_visitante, marcador_local,
                marcador_visitante, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, 'PROGRAMADO')
            ON DUPLICATE KEY UPDATE
                fecha = VALUES(fecha),
                equipo_local = VALUES(equipo_local),
                equipo_visitante = VALUES(equipo_visitante)
        """
        rows = [
            (
                str(r["game_id"]),
                int(r["season"]),
                str(r.get("game_type", "REG")),
                int(r["week"]),
                str(r["gameday"]),
                str(r["home_team"]),
                str(r["away_team"]),
            )
            for _, r in sched_2026.iterrows()
        ]
        cur.executemany(sql, rows)
        conn.commit()
        count = cur.rowcount
        cur.close()
        return count
    except Exception as e:
        logger.warning(f"Error asegurando juegos en nfl_juegos: {e}")
        return 0


def extraer_props_nfl(usar_cache: bool = True) -> pd.DataFrame:
    """Extrae y estructura todos los player props de la NFL disponibles en Bovada."""
    DIR_CACHE.mkdir(parents=True, exist_ok=True)

    if usar_cache and RUTA_CACHE_PROPS.exists():
        try:
            mtime = RUTA_CACHE_PROPS.stat().st_mtime
            edad_h = (time.time() - mtime) / 3600.0
            if edad_h < 1.0: # Menos de 1 hora de antigüedad
                df_cache = pd.read_parquet(RUTA_PARQUET_PROPS)
                logger.info(f"⚡ Cargados {len(df_cache)} props NFL de Bovada desde caché local ({edad_h:.1f}h).")
                return df_cache
        except Exception:
            pass

    eventos = descargar_mercados_bovada_nfl()
    if not eventos:
        if RUTA_PARQUET_PROPS.exists():
            return pd.read_parquet(RUTA_PARQUET_PROPS)
        return pd.DataFrame()

    indice_jug = _construir_indice_jugadores()

    # Cargar juegos registrados para asociar id_juego
    juegos_dict = {}
    try:
        conn = get_db_connection()
        _asegurar_juegos_registrados(conn)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id_juego, temporada, semana, equipo_visitante, equipo_local, fecha FROM nfl_juegos WHERE temporada >= 2026")
        for jg in cur.fetchall():
            clave = (jg["equipo_visitante"], jg["equipo_local"])
            juegos_dict[clave] = jg
        conn.close()
    except Exception as e:
        logger.warning(f"No se pudieron consultar nfl_juegos: {e}")

    pat_prop = re.compile(
        r"^(?:Total|Alternate)\s+(Passing\s+Yards|Passing\s+Touchdowns|Rushing\s+Yards|Receiving\s+Yards|Receptions)\s*-\s*(.+?)(?:\s*\(([A-Z]{2,3})\))?$",
        re.I
    )

    mapa_tipos = {
        "passing yards": "passing_yards",
        "passing touchdowns": "passing_tds",
        "rushing yards": "rushing_yards",
        "receiving yards": "receiving_yards",
        "receptions": "receptions",
    }

    props_extraidos = []
    timestamp_ahora = datetime.now(timezone.utc).isoformat()

    for ev in eventos:
        desc_evento = ev.get("description", "") # Ej: "Cincinnati Bengals @ Atlanta Falcons"
        competitors = ev.get("competitors", [])
        if len(competitors) < 2:
            continue

        # En Bovada, el primer competidor suele ser el Local o se deduce de desc_evento
        # desc_evento: "Visitante @ Local"
        if "@" in desc_evento:
            partes_ev = desc_evento.split("@")
            vis_nom = partes_ev[0].strip()
            loc_nom = partes_ev[1].strip()
        else:
            vis_nom = competitors[1].get("name", "")
            loc_nom = competitors[0].get("name", "")

        vis_sigla = EQUIPOS_BOVADA_A_SIGLA.get(vis_nom, "")
        loc_sigla = EQUIPOS_BOVADA_A_SIGLA.get(loc_nom, "")

        if not vis_sigla or not loc_sigla:
            continue

        info_juego = juegos_dict.get((vis_sigla, loc_sigla))
        id_juego = info_juego["id_juego"] if info_juego else f"2026_{vis_sigla}_{loc_sigla}"

        display_groups = ev.get("displayGroups", [])

        for dg in display_groups:
            dg_desc = dg.get("description", "")
            markets = dg.get("markets", [])

            # Caso A: Mercados Over/Under individuales
            for m in markets:
                m_desc = m.get("description", "")

                # 1. Anytime Touchdown Scorer
                if "Anytime Touchdown Scorer" in m_desc:
                    for o in m.get("outcomes", []):
                        jug_desc = o.get("description", "") # Ej: "Ja'Marr Chase (CIN)"
                        m_team = re.search(r"\(([A-Z]{2,3})\)", jug_desc)
                        team_sug = m_team.group(1) if m_team else ""
                        jug_nom_limpio = re.sub(r"\s*\([A-Z]{2,3}\)", "", jug_desc).strip()

                        jug_info = _resolver_jugador_nfl(jug_nom_limpio, team_sug, indice_jug)
                        id_jugador = jug_info["id_jugador"] if jug_info else None
                        nombre_oficial = jug_info["nombre"] if jug_info else jug_nom_limpio
                        pos = jug_info.get("posicion", "OF") if jug_info else "OF"
                        equipo_real = jug_info.get("equipo_actual", team_sug or vis_sigla) if jug_info else team_sug

                        am_odds = o.get("price", {}).get("american")
                        if am_odds is not None:
                            dec_odds = _american_a_decimal(am_odds)
                            props_extraidos.append({
                                "id_juego": id_juego,
                                "id_jugador": id_jugador,
                                "player_name": nombre_oficial,
                                "team": equipo_real,
                                "posicion": pos,
                                "tipo_prop": "anytime_td",
                                "market_name": "Anytime Touchdown",
                                "linea": 0.5,
                                "cuota_over": dec_odds,
                                "cuota_under": None,
                                "momio_over_am": str(am_odds),
                                "momio_under_am": None,
                                "casa_apuestas": "bovada",
                                "timestamp_captura": timestamp_ahora,
                            })
                    continue

                # 2. Mercados Over / Under (Passing, Rushing, Receiving, Receptions)
                mat = pat_prop.match(m_desc)
                if not mat:
                    continue

                stat_tipo_raw = mat.group(1).lower()
                tipo_prop = mapa_tipos.get(stat_tipo_raw)
                if not tipo_prop:
                    continue

                jug_nom = mat.group(2).strip()
                team_sug = mat.group(3) or ""

                jug_info = _resolver_jugador_nfl(jug_nom, team_sug, indice_jug)
                id_jugador = jug_info["id_jugador"] if jug_info else None
                nombre_oficial = jug_info["nombre"] if jug_info else jug_nom
                pos = jug_info.get("posicion", "OF") if jug_info else "OF"
                equipo_real = jug_info.get("equipo_actual", team_sug or vis_sigla) if jug_info else team_sug

                # Agrupar outcomes por handicap para hallar la línea balanceada principal
                outcomes_por_handicap: Dict[float, Dict[str, Any]] = {}
                for o in m.get("outcomes", []):
                    desc_o = o.get("description", "").lower() # "over" o "under"
                    price = o.get("price", {})
                    h_val = price.get("handicap")
                    if h_val is None:
                        continue
                    try:
                        h_float = float(h_val)
                    except ValueError:
                        continue

                    if h_float not in outcomes_por_handicap:
                        outcomes_por_handicap[h_float] = {}
                    outcomes_por_handicap[h_float][desc_o] = price

                # Buscar la línea con over y under cuyas cuotas estén más balanceadas (cercanas a 1.91 o diff mínima)
                mejor_linea = None
                menor_diff = 999999.0
                mejor_datos = None

                for h_float, lados in outcomes_por_handicap.items():
                    if "over" in lados and "under" in lados:
                        am_o = lados["over"].get("american", "-115")
                        am_u = lados["under"].get("american", "-115")
                        dec_o = _american_a_decimal(am_o)
                        dec_u = _american_a_decimal(am_u)
                        diff = abs(dec_o - dec_u)
                        if diff < menor_diff:
                            menor_diff = diff
                            mejor_linea = h_float
                            mejor_datos = (am_o, dec_o, am_u, dec_u)

                if mejor_linea is not None and mejor_datos is not None:
                    am_o, dec_o, am_u, dec_u = mejor_datos
                    props_extraidos.append({
                        "id_juego": id_juego,
                        "id_jugador": id_jugador,
                        "player_name": nombre_oficial,
                        "team": equipo_real,
                        "posicion": pos,
                        "tipo_prop": tipo_prop,
                        "market_name": stat_tipo_raw.title(),
                        "linea": mejor_linea,
                        "cuota_over": dec_o,
                        "cuota_under": dec_u,
                        "momio_over_am": str(am_o),
                        "momio_under_am": str(am_u),
                        "casa_apuestas": "bovada",
                        "timestamp_captura": timestamp_ahora,
                    })

    if not props_extraidos:
        logger.warning("No se pudieron extraer props de la NFL desde Bovada.")
        return pd.DataFrame()

    df = pd.DataFrame(props_extraidos)
    # Deduplicar quedándonos con la línea principal por jugador y tipo de prop
    df = df.drop_duplicates(subset=["id_juego", "player_name", "tipo_prop"], keep="first")

    # Guardar en caché local
    try:
        df.to_parquet(RUTA_PARQUET_PROPS, index=False)
        with open(RUTA_CACHE_PROPS, "w", encoding="utf-8") as f:
            json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Guardados {len(df)} props de NFL en caché ({RUTA_CACHE_PROPS.name}).")
    except Exception as e:
        logger.warning(f"Error guardando caché: {e}")

    return df


def sincronizar_lineas_bovada_a_mysql() -> int:
    """Inserta las líneas recién extraídas de Bovada en la tabla `nfl_lineas_props` de MySQL."""
    df = extraer_props_nfl(usar_cache=False)
    if df.empty:
        return 0

    validos = df[df["id_jugador"].notna() & df["id_juego"].notna()].copy()
    if validos.empty:
        logger.warning("No se encontraron jugadores vinculados a id_jugador en MySQL.")
        return 0

    conn = get_db_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO nfl_lineas_props (
            id_juego, id_jugador, casa_apuestas, tipo_prop, linea,
            cuota_over, cuota_under, timestamp_captura
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            linea = VALUES(linea),
            cuota_over = VALUES(cuota_over),
            cuota_under = VALUES(cuota_under),
            timestamp_captura = VALUES(timestamp_captura)
    """

    registros = []
    for _, r in validos.iterrows():
        # En nfl_lineas_props las cuotas se almacenan como momio americano float (ej. -115.0, 150.0)
        am_o = None
        if pd.notna(r.get("momio_over_am")):
            try:
                s_am = str(r["momio_over_am"]).strip().replace("+", "")
                am_o = float(s_am) if s_am != "EVEN" else 100.0
            except Exception:
                pass
        am_u = None
        if pd.notna(r.get("momio_under_am")):
            try:
                s_am_u = str(r["momio_under_am"]).strip().replace("+", "")
                am_u = float(s_am_u) if s_am_u != "EVEN" else 100.0
            except Exception:
                pass

        registros.append((
            str(r["id_juego"]),
            str(r["id_jugador"]),
            "bovada",
            str(r["tipo_prop"]),
            float(r["linea"]),
            am_o,
            am_u,
            datetime.now(timezone.utc),
        ))

    cur.executemany(sql, registros)
    conn.commit()
    filas_afectadas = cur.rowcount
    cur.close()
    conn.close()

    logger.info(f"🚀 Sincronizadas {filas_afectadas} líneas de props en MySQL (casa: bovada).")
    return len(registros)


def extraer_lineas_partido_bovada() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Extrae las líneas de Moneyline, Spread y Totales de Bovada para todos los partidos."""
    eventos = descargar_mercados_bovada_nfl()
    if not eventos:
        return {}

    partidos = {}
    for ev in eventos:
        desc = ev.get("description", "")
        if "@" not in desc:
            continue
        partes = desc.split("@")
        vis_nom = partes[0].strip()
        loc_nom = partes[1].strip()
        vis_sigla = EQUIPOS_BOVADA_A_SIGLA.get(vis_nom)
        loc_sigla = EQUIPOS_BOVADA_A_SIGLA.get(loc_nom)
        if not vis_sigla or not loc_sigla:
            continue

        ml_vis, ml_loc = None, None
        spread_val = None
        tot_line, tot_over, tot_under = None, None, None

        for dg in ev.get("displayGroups", []):
            if dg.get("description") != "Game Lines":
                continue
            for m in dg.get("markets", []):
                # Filtrar únicamente mercado de partido completo (period == 'Game')
                if m.get("period", {}).get("description") != "Game":
                    continue
                desc_m = m.get("description", "")
                if desc_m == "Moneyline":
                    for o in m.get("outcomes", []):
                        if o.get("description") == loc_nom:
                            ml_loc = o.get("price", {}).get("american")
                        elif o.get("description") == vis_nom:
                            ml_vis = o.get("price", {}).get("american")
                elif desc_m == "Point Spread":
                    for o in m.get("outcomes", []):
                        if o.get("description") == loc_nom:
                            h = o.get("price", {}).get("handicap")
                            if h is not None:
                                spread_val = float(h)
                elif desc_m == "Total":
                    for o in m.get("outcomes", []):
                        desc_o = o.get("description", "")
                        p_o = o.get("price", {})
                        if "Over" in desc_o:
                            h = p_o.get("handicap")
                            if h is not None:
                                tot_line = float(h)
                            tot_over = p_o.get("american")
                        elif "Under" in desc_o:
                            tot_under = p_o.get("american")
            break

        partidos[(vis_sigla, loc_sigla)] = {
            "moneyline_local": str(ml_loc) if ml_loc is not None else None,
            "moneyline_visita": str(ml_vis) if ml_vis is not None else None,
            "ml_local_dec": _american_a_decimal(ml_loc) if ml_loc is not None else None,
            "ml_visita_dec": _american_a_decimal(ml_vis) if ml_vis is not None else None,
            "spread_line": spread_val,
            "linea_total": tot_line,
            "over_momio": str(tot_over) if tot_over is not None else None,
            "under_momio": str(tot_under) if tot_under is not None else None,
            "over_momio_dec": _american_a_decimal(tot_over) if tot_over is not None else None,
            "under_momio_dec": _american_a_decimal(tot_under) if tot_under is not None else None,
        }

    return partidos


if __name__ == "__main__":
    df = extraer_props_nfl(usar_cache=False)
    print(f"\n📊 Total props NFL extraídos de Bovada (0 créditos): {len(df)}")
    if not df.empty:
        print("\nDistribución por tipo de prop:")
        print(df["tipo_prop"].value_counts())
        print("\nPrimeras 5 líneas:")
        print(df[["player_name", "team", "tipo_prop", "linea", "momio_over_am", "momio_under_am"]].head(10))
        n = sincronizar_lineas_bovada_a_mysql()
        print(f"\n✅ Sincronizados con MySQL: {n} líneas.")
