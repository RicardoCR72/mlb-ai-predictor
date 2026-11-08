"""Genera proyecciones semanales para los principales props NFL."""

import json
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
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
from nfl.settings import TEMPORADA_ACTUAL
from nfl.services.calendar_updates import (
    actualizar_calendario,
    actualizar_lesiones,
    actualizar_depth_charts,
    cargar_mapeo_depth_chart,
    obtener_proxima_semana,
)
from core.db import get_db_credentials as obtener_configuracion_mysql
from nfl.persistence.totals import valor_mysql


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))
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

MODELO_VERSION = "props_nfl_v3"
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

    print("Calculando features de carrera con Depth Chart oficial...")
    carrera = construir_dataset_carrera(combinadas, lesiones)
    carrera = carrera[carrera["game_id"].isin(ids_futuros)].copy()
    carrera = carrera[
        (carrera["player_games_before"] >= 3)
        & (carrera["player_carries_avg_5"] >= 2.0)
        & ~carrera["player_injury_status"].isin(["out", "doubtful"])
    ].copy()

    # Cargar y fusionar el depth chart oficial para determinar la jerarquía real
    try:
        dc_df = cargar_mapeo_depth_chart()
        # Mapear por (team, player_id)
        dc_id_map = (
            dc_df.dropna(subset=["player_id"])
            .drop_duplicates(subset=["team", "player_id"])
            .set_index(["team", "player_id"])["depth_rank"]
        )
        carrera["depth_rank"] = (
            carrera.set_index(["team", "player_id"]).index.map(dc_id_map)
        )

        # Fallback por (team, player_name)
        faltantes = carrera["depth_rank"].isna()
        if faltantes.any():
            dc_name_map = (
                dc_df.dropna(subset=["player_name"])
                .drop_duplicates(subset=["team", "player_name"])
                .set_index(["team", "player_name"])["depth_rank"]
            )
            carrera.loc[faltantes, "depth_rank"] = (
                carrera.loc[faltantes]
                .set_index(["team", "player_name"])
                .index.map(dc_name_map)
            )

        carrera["depth_rank"] = (
            pd.to_numeric(carrera["depth_rank"], errors="coerce")
            .fillna(99)
            .astype(int)
        )
    except Exception as e_dc:
        print(f"Aviso: No se pudo cargar depth chart oficial ({e_dc}). Se usará fallback.")
        carrera["depth_rank"] = 99

    # Identifica al corredor principal activo de cada equipo respetando el depth chart oficial.
    # El RB activo (no lesionado) con menor depth_rank (1 = titular) es el único is_primary_rusher = 1.
    # Si el titular está inactivo/descartado, el suplente #2 asciende a titular activo.
    carrera["is_primary_rusher"] = 0
    rbs_activos = carrera[carrera["position"].eq("RB")].copy()
    if not rbs_activos.empty:
        indices_principales = (
            rbs_activos.sort_values(
                ["game_id", "team", "depth_rank", "player_carries_avg_5"],
                ascending=[True, True, True, False],
            )
            .groupby(["game_id", "team"], sort=False)
            .head(1)
            .index
        )
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
        "player_carries_avg_5", "is_primary_rusher", "depth_rank",
        "player_targets_avg_5", "player_receiving_yards_avg_5",
        "player_target_share_avg_5", "player_receptions_avg_5",
        "player_passing_attempts_avg_5", "player_passing_yards_avg_5",
        "player_passing_tds_avg_5", "player_rushing_yards_avg_5",
    ]
    base = features[[c for c in columnas if c in features.columns]].copy()
    if "depth_rank" not in base:
        base["depth_rank"] = 99
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


def aplicar_inercia_volumen_elite(proyeccion, df, tipo_prop):
    """Ajusta las proyecciones para evitar el sesgo de subestimación (shrinkage) en superestrellas (WRs, QBs, RBs).
    
    Los modelos de árboles (Gradient Boosting) tienden a comprimir las proyecciones hacia la media
    de la liga (techo de ~75-80 yds en pase/recepción). Para jugadores con volumen dominante reciente
    (altos targets, acarreos o intentos de pase), pondera su inercia de volumen real para que el modelo
    pueda proyectar adecuadamente y recomendar OVER cuando esté justificado.
    """
    proj = np.asarray(proyeccion, dtype=float).copy()
    if tipo_prop == "receiving_yards":
        targets = pd.to_numeric(df.get("player_targets_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        yds_avg = pd.to_numeric(df.get("player_receiving_yards_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        mask = (targets >= 7.5) | (yds_avg >= 70.0)
        peso = np.clip((targets - 6.0) / 10.0, 0.0, 0.40)
        ajuste = np.where(mask & (yds_avg > proj), (1.0 - peso) * proj + peso * yds_avg, proj)
        return ajuste
    elif tipo_prop == "receptions":
        targets = pd.to_numeric(df.get("player_targets_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        rec_avg = pd.to_numeric(df.get("player_receptions_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        mask = (targets >= 7.5) | (rec_avg >= 6.0)
        peso = np.clip((targets - 6.0) / 10.0, 0.0, 0.40)
        ajuste = np.where(mask & (rec_avg > proj), (1.0 - peso) * proj + peso * rec_avg, proj)
        return ajuste
    elif tipo_prop == "rushing_yards":
        is_primary = pd.to_numeric(df.get("is_primary_rusher", pd.Series(0, index=df.index)), errors="coerce").fillna(0).to_numpy()
        carries = pd.to_numeric(df.get("player_carries_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        rush_avg = pd.to_numeric(df.get("player_rushing_yards_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        # La inercia de volumen SOLO aplica a corredores titulares confirmados
        mask = (is_primary == 1) & ((carries >= 15.0) | (rush_avg >= 70.0))
        peso = np.clip((carries - 13.0) / 12.0, 0.0, 0.35)
        ajuste = np.where(mask & (rush_avg > proj), (1.0 - peso) * proj + peso * rush_avg, proj)
        return ajuste
    elif tipo_prop == "passing_yards":
        att = pd.to_numeric(df.get("player_passing_attempts_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        pass_avg = pd.to_numeric(df.get("player_passing_yards_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        mask = (att >= 34.0) | (pass_avg >= 250.0)
        peso = np.clip((att - 30.0) / 15.0, 0.0, 0.30)
        ajuste = np.where(mask & (pass_avg > proj), (1.0 - peso) * proj + peso * pass_avg, proj)
        return ajuste
    elif tipo_prop == "passing_tds":
        td_avg = pd.to_numeric(df.get("player_passing_tds_avg_5", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0).to_numpy()
        mask = td_avg >= 1.8
        peso = 0.25
        ajuste = np.where(mask & (td_avg > proj), (1.0 - peso) * proj + peso * td_avg, proj)
        return ajuste
    return proj


def calibrar_team_share_rushing(bloque_rushing):
    """Aplica restricción de suma cero (Team Share) a las proyecciones terrestres del backfield.
    
    1. Si el corredor titular (#1) está activo:
       - Los corredores suplentes (#2) se ajustan a su rol real (máximo 35% del titular o 32 yardas).
       - Los corredores de tercer orden (#3+) se ajustan a un rol marginal (máximo 15% o 12 yardas).
    2. Restricción de capacidad máxima del backfield (Team Zero-Sum):
       - Ningún backfield colectivo de RBs puede sumar yardas irreales (> 120-130 yds).
       - Si la suma total excede el techo razonable, se calibra proporcionalmente asegurando
         que el titular mantenga su jerarquía principal (~70% del volumen).
    """
    res = bloque_rushing.copy()
    if res.empty or "game_id" not in res.columns:
        return res

    for (gid, tm), indices in res.groupby(["game_id", "team"]).groups.items():
        sub = res.loc[indices]
        mask_rb = sub["position"].eq("RB")
        if not mask_rb.any():
            continue

        idx_rbs = sub[mask_rb].index
        rbs = res.loc[idx_rbs]

        has_primary = (rbs["is_primary_rusher"] == 1).any()
        if not has_primary:
            continue

        prim_row = rbs[rbs["is_primary_rusher"] == 1].iloc[0]
        prim_proj = float(prim_row["proyeccion"])

        # 1. Calibrar suplentes cuando el titular está activo
        for idx in idx_rbs:
            if res.loc[idx, "is_primary_rusher"] == 0:
                dr = res.loc[idx].get("depth_rank", 99)
                try:
                    dr = int(dr)
                except (ValueError, TypeError):
                    dr = 99

                p_orig = float(res.loc[idx, "proyeccion"])
                if dr == 2:
                    # Suplente inmediato (#2): rol típico de 4-8 acarreos (~20-30 yardas)
                    techo_rb2 = min(32.0, max(12.0, prim_proj * 0.35))
                    res.loc[idx, "proyeccion"] = min(p_orig, techo_rb2)
                elif dr >= 3:
                    # Tercer corredor o profundidad: toques esporádicos
                    techo_rb3 = min(12.0, max(4.0, prim_proj * 0.15))
                    res.loc[idx, "proyeccion"] = min(p_orig, techo_rb3)

        # 2. Control de suma cero / capacidad total de carrera terrestre
        rbs_ajustados = res.loc[idx_rbs]
        suma_total = float(rbs_ajustados["proyeccion"].sum())
        TECHO_BACKFIELD = 120.0
        if suma_total > TECHO_BACKFIELD:
            factor = TECHO_BACKFIELD / suma_total
            res.loc[idx_rbs, "proyeccion"] = res.loc[idx_rbs, "proyeccion"] * factor

    return res


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
    pred_rec = predecir_modelo(modelo_recepciones, features)
    recepciones["proyeccion"] = aplicar_inercia_volumen_elite(pred_rec, features, "receptions")

    yardas = base.copy()
    yardas["tipo_prop"] = "receiving_yards"
    pred_yds = predecir_modelo(modelo_yardas, features)
    yardas["proyeccion"] = aplicar_inercia_volumen_elite(pred_yds, features, "receiving_yards")

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
        bloque["proyeccion"] = aplicar_inercia_volumen_elite(prediccion, conjunto, objetivo)
        if objetivo == "rushing_yards":
            bloque = calibrar_team_share_rushing(bloque)
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


from nfl.persistence.props import obtener_conexion, sincronizar_catalogos, cargar_lineas, guardar_proyecciones






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
    return seleccionar_candidatos(resultado)


def seleccionar_candidatos(resultado):
    decimal = resultado["cuota_pick"].apply(american_a_decimal)
    try:
        from core.calibracion_probabilidades import calibrar_probabilidad
        # Platt scaling aplica exclusivamente a líneas estándar 50/50 (yardas, recepciones, etc.), NUNCA a anytime_td
        mask_standard = ~resultado["tipo_prop"].eq("anytime_td")
        if mask_standard.any():
            resultado.loc[mask_standard, "probabilidad_pick"] = calibrar_probabilidad(
                resultado.loc[mask_standard, "probabilidad_pick"], decimal[mask_standard]
            )
    except Exception:
        pass
    resultado["ev_estimado"] = (
        resultado["probabilidad_pick"] * decimal - 1
    )
    resultado["estado_pick"] = "NO PICK"
    resultado.loc[resultado["linea"].isna(), "estado_pick"] = "SIN LINEA"
    umbrales_edge = {
        "receptions": 0.65,
        "receiving_yards": 8.0,
        "passing_yards": 25.0,
        "passing_tds": 0.35,
        "rushing_yards": 20.0,
        "anytime_td": 0.05,
    }
    umbral = resultado["tipo_prop"].map(umbrales_edge).fillna(np.inf)
    es_rushing = resultado["tipo_prop"].eq("rushing_yards")
    es_td = resultado["tipo_prop"].eq("anytime_td")

    # Para anytime_td el edge DEBE ser positivo (ventaja real a favor de anotar)
    edge_valido = np.where(
        es_td,
        resultado["edge"] >= umbral,
        resultado["edge"].abs() >= umbral,
    )

    umbral_probabilidad = np.select(
        [es_td, es_rushing],
        [0.25, 0.62],
        default=0.57,
    )
    umbral_ev = np.where(es_rushing, 0.05, 0.0)
    cuota_maxima = np.where(
        es_td, 1000, 2500
    )
    candidato = (
        resultado["linea"].notna()
        & edge_valido
        & (resultado["probabilidad_pick"] >= umbral_probabilidad)
        & (resultado["ev_estimado"] > umbral_ev)
        & (resultado["cuota_pick"].abs() >= 100)
        & (resultado["cuota_pick"].abs() <= cuota_maxima)
    )

    # Candado 1: Yardas terrestres: solamente el RB titular (#1) con volumen probado (mínimo 12 acarreos avg).
    # REGLA ESTRICTA DE JERARQUÍA / SUPLENTES:
    # 1. Un suplente (is_primary_rusher == 0 o depth_rank > 1 cuando el titular está activo)
    #    NUNCA puede ser candidato a un OVER en yardas terrestres (+EV trap).
    # 2. Bloquea UNDERs suicidas en corredores titulares élite (línea >= 75 yardas).
    # 3. Solo un RB con is_primary_rusher == 1 y carries_promedio >= 12.0 califica para OVER.
    linea_val = pd.to_numeric(resultado["linea"], errors="coerce").fillna(0.0)
    es_under_rush = es_rushing & resultado["seleccion"].eq("UNDER")
    es_over_rush = es_rushing & resultado["seleccion"].eq("OVER")

    carries_promedio = pd.to_numeric(
        resultado.get("player_carries_avg_5", pd.Series(0.0, index=resultado.index)), errors="coerce"
    ).fillna(0.0)
    principal = pd.to_numeric(
        resultado.get("is_primary_rusher", pd.Series(0, index=resultado.index)), errors="coerce"
    ).fillna(0).eq(1)
    depth_rank = pd.to_numeric(
        resultado.get("depth_rank", pd.Series(99, index=resultado.index)), errors="coerce"
    ).fillna(99)

    rushing_valido = (
        resultado["position"].eq("RB")
        & principal
        & ~(es_under_rush & (linea_val >= 75.0))
        & ~(es_over_rush & (~principal | (carries_promedio < 12.0) | (depth_rank > 1)))
    )
    candidato &= ~es_rushing | rushing_valido

    # Candado 2: Yardas de pase: PROHIBIR UNDER a mariscales de campo
    # (El juego moderno y el garbage time del 4to cuarto invalidan sistemáticamente los UNDERs)
    es_passing_under = resultado["tipo_prop"].eq("passing_yards") & resultado["seleccion"].eq("UNDER")
    candidato &= ~es_passing_under

    # Candado 3: Rushing: máximo 2 candidatos terrestres por partido
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

    # Candado 4: Anytime TD: máximo 1 anotador por equipo (máximo 2 por partido) con mayor EV
    # Evita canibalización de touchdowns y recomendaciones masivas de anotadores en el mismo juego
    indices_td = (
        resultado.loc[candidato & es_td]
        .sort_values(
            ["game_id", "team", "ev_estimado", "edge"],
            ascending=[True, True, False, False],
        )
        .groupby(["game_id", "team"], sort=False)
        .head(1)
        .index
    )
    candidato &= ~es_td | resultado.index.isin(indices_td)

    # Candado 5: Receptores Élite: PROHIBIR UNDERs en WRs/TEs estelares con líneas altas.
    # Los modelos de Gradient Boosting sufren de regresión hacia la media (shrinkage),
    # subestimando sistemáticamente a receptores élite (WR1) con volumen masivo de targets.
    # Nunca apostar UNDER si la línea es >= 80 yardas (o >= 7.0 recepciones) en jugadores
    # con promedio >= 7.5 targets o >= 75 yardas recientes.
    es_under_rec_yds = resultado["tipo_prop"].eq("receiving_yards") & resultado["seleccion"].eq("UNDER")
    es_under_recs = resultado["tipo_prop"].eq("receptions") & resultado["seleccion"].eq("UNDER")
    targets_promedio = pd.to_numeric(
        resultado.get("player_targets_avg_5", pd.Series(0.0, index=resultado.index)), errors="coerce"
    ).fillna(0.0)
    yds_promedio = pd.to_numeric(
        resultado.get("player_receiving_yards_avg_5", pd.Series(0.0, index=resultado.index)), errors="coerce"
    ).fillna(0.0)

    receptor_elite_yds = es_under_rec_yds & (linea_val >= 80.0) & ((targets_promedio >= 7.5) | (yds_promedio >= 75.0))
    receptor_elite_recs = es_under_recs & (linea_val >= 7.0) & (targets_promedio >= 7.5)
    candidato &= ~receptor_elite_yds
    candidato &= ~receptor_elite_recs

    # Candado 6: Mariscales de Campo Élite: PROHIBIR UNDER en pases de touchdown si promedia >= 2.0 TDs recientes
    es_under_pass_tds = resultado["tipo_prop"].eq("passing_tds") & resultado["seleccion"].eq("UNDER")
    pass_tds_promedio = pd.to_numeric(
        resultado.get("player_passing_tds_avg_5", pd.Series(0.0, index=resultado.index)), errors="coerce"
    ).fillna(0.0)
    candidato &= ~(es_under_pass_tds & (pass_tds_promedio >= 2.0))

    # Candado 7: Trampa de Líneas Bajas en WRs y TEs (Trap Lines)
    # En la NFL, cuando una casa de apuestas fija la línea de un WR o TE en <= 22.0 yardas (o <= 1.5 recepciones),
    # no se trata de un error de ineficiencia: indica que el QB titular está ausente, el jugador tiene conteo
    # severo de snaps o el esquema ofensivo es inoperante. Prohibir OVERs en estas líneas trampa.
    es_wr_te = resultado["position"].isin(["WR", "TE"])
    trampa_rec_yds = es_wr_te & resultado["tipo_prop"].eq("receiving_yards") & resultado["seleccion"].eq("OVER") & (linea_val <= 22.0)
    trampa_recs = es_wr_te & resultado["tipo_prop"].eq("receptions") & resultado["seleccion"].eq("OVER") & (linea_val <= 1.5)
    candidato &= ~trampa_rec_yds
    candidato &= ~trampa_recs

    # Candado 8: Killswitch de QB Ausente / Incertidumbre de Pasador
    # Si en un partido las casas publicaron líneas de pase para un equipo pero congelaron/retiraron las
    # líneas del equipo rival, indica ausencia confirmada o duda crítica del QB titular.
    # En ese escenario, se bloquean todos los OVERs del juego aéreo para la ofensiva sin línea de pase.
    partidos_con_pase = resultado.loc[
        resultado["tipo_prop"].isin(["passing_yards", "passing_tds"]) & resultado["linea"].notna()
    ]
    if not partidos_con_pase.empty and "game_id" in resultado.columns:
        equipos_con_pase_dict = (
            partidos_con_pase.groupby("game_id")["team"]
            .unique()
            .to_dict()
        )
        for gid, eq_con_pase in equipos_con_pase_dict.items():
            juego_mask = resultado["game_id"].eq(gid)
            todos_equipos = set(resultado.loc[juego_mask, "team"].dropna().unique())
            sin_linea_pase = todos_equipos - set(eq_con_pase)
            if sin_linea_pase:
                es_over_aereo = (
                    resultado["tipo_prop"].isin(["receiving_yards", "receptions", "passing_yards", "passing_tds"])
                    & resultado["seleccion"].eq("OVER")
                )
                candidato &= ~(juego_mask & resultado["team"].isin(sin_linea_pase) & es_over_aereo)

    # Candado 9: Diversificación y Anti-Canibalización en Receptores
    es_rec_prop = resultado["tipo_prop"].isin(["receiving_yards", "receptions"])

    # 9A. Máximo 1 pick por jugador individual (evita recomendar simultáneamente OVER recepciones + OVER yardas)
    if (candidato & es_rec_prop).any():
        indices_un_pick_jugador = (
            resultado.loc[candidato & es_rec_prop]
            .sort_values(
                ["game_id", "player_id", "ev_estimado", "probabilidad_pick"],
                ascending=[True, True, False, False],
            )
            .groupby(["game_id", "player_id"], sort=False)
            .head(1)
            .index
        )
        candidato &= ~es_rec_prop | resultado.index.isin(indices_un_pick_jugador)

    # 9B. Máximo 2 picks aéreos (OVER) por equipo (evita colapso en cascada si la ofensiva no camina)
    es_over_rec = es_rec_prop & resultado["seleccion"].eq("OVER")
    if (candidato & es_over_rec).any():
        indices_max_equipo_rec = (
            resultado.loc[candidato & es_over_rec]
            .sort_values(
                ["game_id", "team", "ev_estimado", "probabilidad_pick"],
                ascending=[True, True, False, False],
            )
            .groupby(["game_id", "team"], sort=False)
            .head(2)
            .index
        )
        candidato &= ~es_over_rec | resultado.index.isin(indices_max_equipo_rec)

    # 9C. Máximo 3 picks de receptores (OVER) por partido en total (garantiza diversificación entre juegos)
    if (candidato & es_over_rec).any():
        indices_max_partido_rec = (
            resultado.loc[candidato & es_over_rec]
            .sort_values(
                ["game_id", "ev_estimado", "probabilidad_pick"],
                ascending=[True, False, False],
            )
            .groupby("game_id", sort=False)
            .head(3)
            .index
        )
        candidato &= ~es_over_rec | resultado.index.isin(indices_max_partido_rec)

    resultado.loc[candidato, "estado_pick"] = "CANDIDATO"
    revisar_lesion = candidato & resultado["player_injury_status"].eq(
        "questionable"
    )
    resultado.loc[revisar_lesion, "estado_pick"] = "REVISAR LESION"
    return resultado


def evaluar_dependencia_recepcion(resultado, features, lineas):
    from nfl.dependencia_lesiones import escenarios_companeros, marcar_dependencia
    if features.empty or lineas.empty:
        return resultado
    juegan, ausentes, nombres = escenarios_companeros(features, cargar_lesiones())
    mask = nombres.ne('')
    if not mask.any():
        return resultado
    modelo = joblib.load(RUTA_MODELO_YARDAS)
    escenarios = []
    for frame in [juegan, ausentes]:
        bloque = base_proyeccion(frame.loc[mask])
        bloque['tipo_prop'] = 'receiving_yards'
        bloque['player_carries_avg_5'] = 0.0
        bloque['is_primary_rusher'] = 0
        bloque['proyeccion'] = predecir_modelo(modelo, frame.loc[mask])
        escenarios.append(agregar_lineas_y_probabilidades(bloque, lineas))
    names = features.loc[mask,['game_id','player_id']].copy()
    names['companeros_en_duda'] = nombres.loc[mask].values
    result = resultado.merge(names,on=['game_id','player_id'],how='left',validate='many_to_one')
    return marcar_dependencia(result,*escenarios)




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--solo-hoy', action='store_true')
    parser.add_argument('--proximas-horas', type=float, default=None)
    args = parser.parse_args()
    if args.proximas_horas is not None and (args.proximas_horas <= 0 or not args.solo_hoy):
        parser.error('--proximas-horas requiere --solo-hoy y un valor positivo')
    DIRECTORIO_SALIDA.mkdir(parents=True, exist_ok=True)
    calendario = actualizar_calendario()
    game_ids = None
    if args.solo_hoy:
        hoy = calendario_hoy(calendario[
            calendario['season'].eq(TEMPORADA_ACTUAL) & calendario['game_type'].eq('REG')
            & (calendario['home_score'].isna() | calendario['away_score'].isna())])
        if args.proximas_horas is not None:
            hoy = calendario_hoy(hoy, proximas_horas=args.proximas_horas)
        if hoy.empty:
            print('No hay partidos NFL de hoy sin iniciar; no se generan props.')
            return
        game_ids = hoy['game_id'].tolist()
        semana = int(hoy['week'].min())
    else:
        semana = obtener_proxima_semana(calendario)
    actualizar_lesiones()
    actualizar_depth_charts()
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
        resultado = evaluar_dependencia_recepcion(resultado, features, lineas)
        from nfl.publicaciones_props import save_publications
        guardar_proyecciones(conexion, resultado)
        save_publications(conexion, resultado, juegos, MODELO_VERSION)
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
        "ev_estimado", "estado_pick", "is_primary_rusher", "depth_rank", "player_injury_status",
    ]
    columnas = [c for c in columnas if c in resultado.columns]
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

