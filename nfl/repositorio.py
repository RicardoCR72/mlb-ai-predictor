"""Consultas NFL y normalización: sin navegación, formularios ni escritura."""
from pathlib import Path
import logging
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from core.domain.contracts import probabilities, require_columns
from core.db import get_db_connection

logger = logging.getLogger("repositorio_nfl")

RAIZ = Path(__file__).resolve().parents[1]
RUTA_CACHE_NFL = RAIZ / "data" / "nfl" / "cache"
RUTA_PRED_NFL = RAIZ / "data" / "nfl" / "predictions"

NOMBRES_MERCADOS = {'receptions': 'Recepciones', 'receiving_yards': 'Yardas de recepción', 'passing_yards': 'Yardas por pase', 'passing_tds': 'Pases de touchdown', 'rushing_yards': 'Yardas terrestres', 'anytime_td': 'Anota touchdown'}

def calcular_beneficio_unidades(fila):
    """Calcula una unidad arriesgada cuando MySQL no guardó el beneficio."""
    beneficio = pd.to_numeric(pd.Series([fila.get('beneficio_unidades')]), errors='coerce').iloc[0]
    if pd.notna(beneficio):
        return float(beneficio)
    raw = fila.get('resultado_pick')
    resultado = '' if raw is None or pd.isna(raw) else str(raw).strip().upper()
    if resultado == 'PERDIDA':
        return -1.0
    if resultado == 'PUSH':
        return 0.0
    if resultado != 'GANADA':
        return np.nan
    cuota = pd.to_numeric(pd.Series([fila.get('cuota_pick')]), errors='coerce').iloc[0]
    if pd.isna(cuota) or float(cuota) == 0:
        return np.nan
    cuota = float(cuota)
    return cuota / 100.0 if cuota > 0 else 100.0 / abs(cuota)


def _procesar_props_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza columnas, tipos de datos y beneficios de props NFL."""
    if df.empty:
        return df
    require_columns(df, ['id_juego', 'modelo_version', 'resultado_pick'], source='Repositorio NFL')
    fechas = ['gameday', 'evaluado_en', 'generado_en', 'actualizado_en', 'timestamp_captura']
    for columna in fechas:
        if columna in df.columns:
            df[columna] = pd.to_datetime(df[columna], errors='coerce')
    numericas = [
        'season', 'week', 'linea', 'proyeccion', 'edge', 'probabilidad_pick',
        'probabilidad_over', 'probabilidad_under', 'cuota_pick', 'ev_estimado',
        'impacto_lesiones_companeros', 'cuota_over', 'cuota_under', 'valor_real', 'beneficio_unidades'
    ]
    for columna in numericas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors='coerce')
    for columna in ['probabilidad_pick', 'probabilidad_over', 'probabilidad_under', 'ev_estimado']:
        if columna in df.columns and columna != 'ev_estimado':
            df[columna] = probabilities(df[columna], scale=1)
    if 'beneficio_unidades' in df.columns and 'resultado_pick' in df.columns:
        faltan_unidades = df['beneficio_unidades'].isna() & df['resultado_pick'].isin(['GANADA', 'PERDIDA', 'PUSH'])
        if faltan_unidades.any():
            df.loc[faltan_unidades, 'beneficio_unidades'] = df.loc[faltan_unidades].apply(calcular_beneficio_unidades, axis=1)
    if 'edge' in df.columns:
        df['edge_absoluto'] = df['edge'].abs()
    if 'tipo_prop' in df.columns:
        df['mercado'] = df['tipo_prop'].map(NOMBRES_MERCADOS).fillna(df['tipo_prop'])
    dedup = [c for c in ['id_juego', 'id_jugador', 'tipo_prop', 'modelo_version'] if c in df.columns]
    sort_c = [c for c in ['actualizado_en', 'id_proyeccion'] if c in df.columns]
    if sort_c:
        df = df.sort_values(sort_c, ascending=[False] * len(sort_c))
    if dedup:
        df = df.drop_duplicates(dedup, keep='first')
    return df.reset_index(drop=True)


def _guardar_cache_props_disco(df: pd.DataFrame, season: int) -> None:
    """Guarda copia de respaldo en parquet para fallback ultrarrápido."""
    if df.empty:
        return
    try:
        RUTA_CACHE_NFL.mkdir(parents=True, exist_ok=True)
        if season:
            df.to_parquet(RUTA_CACHE_NFL / f"cache_props_nfl_{season}.parquet", index=False)
        df.to_parquet(RUTA_CACHE_NFL / "cache_props_nfl.parquet", index=False)
    except Exception as exc:
        logger.debug(f"No se pudo guardar caché parquet de NFL props: {exc}")


def _cargar_cache_props_disco(season: int = None) -> pd.DataFrame:
    """Intenta cargar props de la NFL desde el respaldo en disco (parquet o csv)."""
    try:
        # 1. Intentar parquet específico de temporada
        if season:
            archivo_temp = RUTA_CACHE_NFL / f"cache_props_nfl_{season}.parquet"
            if archivo_temp.exists():
                return pd.read_parquet(archivo_temp)

        # 2. Intentar parquet consolidado más reciente
        archivo_reciente = RUTA_CACHE_NFL / "cache_props_nfl.parquet"
        if archivo_reciente.exists():
            return pd.read_parquet(archivo_reciente)

        # 3. Intentar los CSV generados por el pipeline semanal de predicciones
        if RUTA_PRED_NFL.exists():
            archivos_csv = sorted(RUTA_PRED_NFL.glob("nfl_props_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
            for f_csv in archivos_csv:
                try:
                    df_csv = pd.read_csv(f_csv)
                    if not df_csv.empty and "player_name" in df_csv.columns:
                        return _procesar_props_dataframe(df_csv)
                except Exception:
                    continue
    except Exception as exc:
        logger.warning(f"Error cargando fallback de props NFL desde disco: {exc}")

    return pd.DataFrame()


def _procesar_totales_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza columnas, tipos de datos y probabilidades de totales NFL."""
    if df.empty:
        return df
    require_columns(df, ['id_juego', 'modelo_version', 'resultado_pick'], source='Repositorio NFL')
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce')
    df['actualizado_en'] = pd.to_datetime(df['actualizado_en'], errors='coerce')
    numericas = ['season', 'week', 'total_line', 'pred_total', 'pred_total_base', 'edge', 'prob_pick', 'prob_over', 'prob_under', 'odds_pick', 'ev']
    for columna in numericas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors='coerce')
    for columna in ['prob_pick', 'prob_over', 'prob_under']:
        if columna in df.columns:
            df[columna] = probabilities(df[columna], scale=100)
    if 'ev' in df.columns:
        df['ev'] = df['ev'] / 100.0
    if 'edge' in df.columns:
        df['edge_absoluto'] = df['edge'].abs()
    sort_c = [c for c in ['actualizado_en', 'id_prediccion'] if c in df.columns]
    if sort_c:
        df = df.sort_values(sort_c, ascending=[False] * len(sort_c))
    if 'id_juego' in df.columns:
        df = df.drop_duplicates(subset=['id_juego'], keep='first')
    return df.reset_index(drop=True)


def _guardar_cache_totales_disco(df: pd.DataFrame, season: int) -> None:
    """Guarda copia de respaldo de totales NFL en parquet."""
    if df.empty:
        return
    try:
        RUTA_CACHE_NFL.mkdir(parents=True, exist_ok=True)
        if season:
            df.to_parquet(RUTA_CACHE_NFL / f"cache_totales_nfl_{season}.parquet", index=False)
        df.to_parquet(RUTA_CACHE_NFL / "cache_totales_nfl.parquet", index=False)
    except Exception as exc:
        logger.debug(f"No se pudo guardar caché parquet de totales NFL: {exc}")


def _cargar_cache_totales_disco(season: int = None) -> pd.DataFrame:
    """Carga respaldo en disco de totales NFL en caso de fallo o timeout de BD."""
    try:
        if season:
            f_temp = RUTA_CACHE_NFL / f"cache_totales_nfl_{season}.parquet"
            if f_temp.exists():
                return pd.read_parquet(f_temp)

        f_rec = RUTA_CACHE_NFL / "cache_totales_nfl.parquet"
        if f_rec.exists():
            return pd.read_parquet(f_rec)

        if RUTA_PRED_NFL.exists():
            archivos_csv = sorted(RUTA_PRED_NFL.glob("nfl_totales_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
            for f_csv in archivos_csv:
                try:
                    df_csv = pd.read_csv(f_csv)
                    if not df_csv.empty and "id_juego" in df_csv.columns:
                        return _procesar_totales_dataframe(df_csv)
                except Exception:
                    continue
    except Exception as exc:
        logger.warning(f"Error cargando fallback de totales NFL: {exc}")

    return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def cargar_props_mysql(season=None):
    now = datetime.now(timezone.utc)
    season = season or (now.year if now.month >= 3 else now.year - 1)
    conexion = None
    cursor = None
    consulta = '\n        SELECT\n            p.id_proyeccion,\n            p.id_juego,\n            p.id_jugador,\n            p.id_linea,\n            p.modelo_version,\n            j.temporada AS season,\n            j.semana AS week,\n            j.fecha AS gameday,\n            j.equipo_visitante AS away_team,\n            j.equipo_local AS home_team,\n            j.estado AS game_status,\n            j.marcador_local AS home_score,\n            j.marcador_visitante AS away_score,\n            ju.nombre AS player_name,\n            ju.posicion AS position,\n            ju.equipo_actual AS team,\n            p.tipo_prop,\n            p.linea,\n            p.proyeccion,\n            p.edge,\n            p.seleccion,\n            p.probabilidad_pick,\n            p.probabilidad_over,\n            p.probabilidad_under,\n            p.cuota_pick,\n            p.ev_estimado,\n            p.estado_pick,\n            p.estado_lesion,\n            p.impacto_lesiones_companeros,\n            p.contexto_lesiones,\n            p.valor_real,\n            p.resultado_pick,\n            p.beneficio_unidades,\n            p.evaluado_en,\n            p.generado_en,\n            p.actualizado_en,\n            l.casa_apuestas,\n            l.cuota_over,\n            l.cuota_under,\n            l.timestamp_captura\n        FROM nfl_proyecciones_props AS p\n        INNER JOIN nfl_juegos AS j\n            ON j.id_juego = p.id_juego\n        INNER JOIN nfl_jugadores AS ju\n            ON ju.id_jugador = p.id_jugador\n        LEFT JOIN nfl_lineas_props AS l\n            ON l.id_linea = p.id_linea\n        WHERE j.temporada = %s\n        ORDER BY\n            j.temporada DESC,\n            j.semana DESC,\n            p.actualizado_en DESC,\n            p.id_proyeccion DESC\n    '
    registros = None
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(consulta, (int(season),))
        registros = cursor.fetchall()
        from nfl.publicaciones_props import attach_publications
        registros = attach_publications(conexion, registros)
    except Exception as exc:
        logger.warning(f"⚠️ Aviso conexión MySQL NFL Props ({exc}). Activando fallback de caché local...")
        registros = None
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conexion is not None:
            try:
                if hasattr(conexion, 'is_connected') and conexion.is_connected():
                    conexion.close()
            except Exception:
                pass

    if not registros:
        return _cargar_cache_props_disco(season)

    df = pd.DataFrame(registros)
    df = _procesar_props_dataframe(df)
    _guardar_cache_props_disco(df, season)
    return df


@st.cache_data(ttl=120, show_spinner=False)
def cargar_predicciones_mysql(season=None):
    now = datetime.now(timezone.utc)
    season = season or (now.year if now.month >= 3 else now.year - 1)
    conexion = None
    cursor = None
    consulta = '\n        SELECT\n            p.id_prediccion,\n            p.id_juego,\n            p.modelo_version,\n            j.temporada AS season,\n            j.tipo_juego AS game_type,\n            j.semana AS week,\n            j.fecha AS gameday,\n            j.equipo_visitante AS away_team,\n            j.equipo_local AS home_team,\n            j.marcador_visitante AS away_score,\n            j.marcador_local AS home_score,\n            p.linea_total AS total_line,\n            p.total_proyectado AS pred_total,\n            p.total_proyectado_base AS pred_total_base,\n            p.edge,\n            p.seleccion AS pick,\n            p.probabilidad_pick AS prob_pick,\n            p.probabilidad_over AS prob_over,\n            p.probabilidad_under AS prob_under,\n            p.cuota_pick AS odds_pick,\n            p.ev_estimado AS ev,\n            p.estado_pick AS estado,\n            p.total_real,\n            p.resultado_pick,\n            p.beneficio_unidades,\n            p.generado_en,\n            p.actualizado_en\n        FROM nfl_predicciones_totales AS p\n        INNER JOIN nfl_juegos AS j\n            ON j.id_juego = p.id_juego\n        WHERE j.temporada = %s\n        ORDER BY\n            j.temporada DESC,\n            j.semana DESC,\n            p.actualizado_en DESC,\n            p.id_prediccion DESC\n    '
    registros = None
    try:
        conexion = get_db_connection()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(consulta, (int(season),))
        registros = cursor.fetchall()
    except Exception as exc:
        logger.warning(f"⚠️ Aviso conexión MySQL NFL Totales ({exc}). Activando fallback de caché local...")
        registros = None
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conexion is not None:
            try:
                if hasattr(conexion, 'is_connected') and conexion.is_connected():
                    conexion.close()
            except Exception:
                pass

    if not registros:
        return _cargar_cache_totales_disco(season)

    df = pd.DataFrame(registros)
    df = _procesar_totales_dataframe(df)
    _guardar_cache_totales_disco(df, season)
    return df

