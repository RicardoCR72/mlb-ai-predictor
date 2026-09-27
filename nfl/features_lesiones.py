"""Variables de lesiones compartidas por entrenamiento y prediccion NFL."""

from pathlib import Path

import numpy as np
import pandas as pd


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]

RUTA_LESIONES = (
    RAIZ_PROYECTO
    / "data"
    / "nfl"
    / "raw"
    / "nfl_injuries_2012_2026.parquet"
)


# El peso representa disponibilidad esperada, no severidad medica.
PESO_ESTADO = {
    "out": 1.00,
    "doubtful": 0.80,
    "questionable": 0.35,
    "probable": 0.10,
}

POSICIONES_SKILL = {"RB", "FB", "WR", "TE"}
POSICIONES_OL = {"C", "G", "OG", "T", "OT", "OL"}
POSICIONES_DEFENSA = {
    "CB", "DB", "DE", "DL", "DT", "EDGE", "FS", "ILB", "LB",
    "MLB", "NT", "OLB", "S", "SAF", "SS",
}


FEATURES_LESIONES_EQUIPO = [
    "injury_severity",
    "injury_out_count",
    "injury_doubtful_count",
    "injury_questionable_count",
    "injury_dnp_count",
    "injury_qb_score",
    "injury_qb_out",
    "injury_starting_qb_score",
    "injury_starting_qb_out",
    "injury_skill_score",
    "injury_skill_out",
    "injury_ol_score",
    "injury_ol_out",
    "injury_defense_score",
    "injury_defense_out",
]

FEATURES_LESIONES_SUMA = [
    "injury_severity",
    "injury_out_count",
    "injury_dnp_count",
    "injury_qb_score",
    "injury_starting_qb_score",
    "injury_skill_score",
    "injury_ol_score",
    "injury_defense_score",
]

FEATURES_LESIONES_DIFERENCIA = [
    "injury_severity",
    "injury_out_count",
    "injury_starting_qb_score",
    "injury_skill_score",
    "injury_ol_score",
    "injury_defense_score",
]

FEATURES_LESIONES_PARTIDO = (
    [
        f"{lado}_{feature}"
        for lado in ("home", "away")
        for feature in FEATURES_LESIONES_EQUIPO
    ]
    + [f"sum_{feature}" for feature in FEATURES_LESIONES_SUMA]
    + [f"diff_{feature}" for feature in FEATURES_LESIONES_DIFERENCIA]
    + [
        "sum_injury_offense_score",
        "net_injury_total_pressure",
    ]
)

# Conjunto compacto usado por el modelo. Las demas columnas se conservan
# en el parquet para auditoria y analisis, pero no entran al estimador.
FEATURES_LESIONES_MODELO = [
    "sum_injury_starting_qb_score",
    "sum_injury_skill_score",
    "sum_injury_ol_score",
    "sum_injury_defense_score",
    "sum_injury_out_count",
    "net_injury_total_pressure",
]


def cargar_lesiones(ruta=RUTA_LESIONES):
    """Carga el historico auditado de lesiones."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encontro el archivo de lesiones: {ruta}. "
            "Ejecuta primero nfl/auditar_lesiones.py."
        )
    return pd.read_parquet(ruta)


def _texto_normalizado(serie):
    return serie.fillna("").astype(str).str.strip().str.lower()


def normalizar_lesiones(lesiones):
    """Limpia estados y conserva un reporte por jugador/equipo/semana."""
    requeridas = {
        "season", "week", "team", "position", "report_status",
        "practice_status",
    }
    faltantes = sorted(requeridas - set(lesiones.columns))
    if faltantes:
        raise KeyError(
            "Faltan columnas en lesiones: " + ", ".join(faltantes)
        )

    df = lesiones.copy()
    df["season"] = pd.to_numeric(df["season"], errors="coerce")
    df["week"] = pd.to_numeric(df["week"], errors="coerce")
    df["team"] = df["team"].fillna("").astype(str).str.strip().str.upper()
    df["position"] = (
        df["position"].fillna("").astype(str).str.strip().str.upper()
    )
    df["report_status_norm"] = _texto_normalizado(df["report_status"])
    df["practice_status_norm"] = _texto_normalizado(df["practice_status"])
    df["injury_weight"] = (
        df["report_status_norm"].map(PESO_ESTADO).fillna(0.0)
    )

    # Un reporte vacio o de participacion completa no representa una baja.
    df = df[df["injury_weight"] > 0].copy()

    if "gsis_id" in df.columns:
        id_jugador = df["gsis_id"].fillna("").astype(str).str.strip()
    else:
        id_jugador = pd.Series("", index=df.index, dtype="object")

    if "full_name" in df.columns:
        nombre = _texto_normalizado(df["full_name"])
    else:
        nombre = pd.Series("", index=df.index, dtype="object")

    df["player_key"] = np.where(
        id_jugador.ne(""),
        "id:" + id_jugador,
        "name:" + nombre,
    )

    df["practice_priority"] = np.select(
        [
            df["practice_status_norm"].str.contains(
                "did not participate|definitely will not play",
                regex=True,
            ),
            df["practice_status_norm"].str.contains("limited", regex=False),
        ],
        [2, 1],
        default=0,
    )

    # Los duplicados son escasos. Se conserva la designacion mas restrictiva.
    df = (
        df.sort_values(
            [
                "season", "week", "team", "player_key",
                "injury_weight", "practice_priority",
            ]
        )
        .drop_duplicates(
            subset=["season", "week", "team", "player_key"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


def construir_features_lesiones(lesiones, partidos):
    """Resume lesiones por equipo/temporada/semana y reconoce al QB titular."""
    df = normalizar_lesiones(lesiones)

    columnas_qb = {
        "home_qb_id", "away_qb_id", "home_team", "away_team",
        "season", "week",
    }
    if columnas_qb.issubset(partidos.columns):
        home_qb = partidos[
            ["season", "week", "home_team", "home_qb_id"]
        ].rename(columns={"home_team": "team", "home_qb_id": "starter_qb_id"})
        away_qb = partidos[
            ["season", "week", "away_team", "away_qb_id"]
        ].rename(columns={"away_team": "team", "away_qb_id": "starter_qb_id"})
        titulares = pd.concat([home_qb, away_qb], ignore_index=True)
        titulares["team"] = titulares["team"].astype(str).str.upper()
        titulares["starter_qb_id"] = (
            titulares["starter_qb_id"].fillna("").astype(str).str.strip()
        )
        titulares = titulares.drop_duplicates(["season", "week", "team"])
        df = df.merge(
            titulares,
            on=["season", "week", "team"],
            how="left",
            validate="many_to_one",
        )
    else:
        df["starter_qb_id"] = ""

    if "gsis_id" in df.columns:
        player_id = df["gsis_id"].fillna("").astype(str).str.strip()
    else:
        player_id = pd.Series("", index=df.index, dtype="object")

    es_out = df["report_status_norm"].eq("out")
    es_doubtful = df["report_status_norm"].eq("doubtful")
    es_questionable = df["report_status_norm"].eq("questionable")
    es_qb = df["position"].eq("QB")
    es_skill = df["position"].isin(POSICIONES_SKILL)
    es_ol = df["position"].isin(POSICIONES_OL)
    es_defensa = df["position"].isin(POSICIONES_DEFENSA)
    es_titular = (
        es_qb
        & player_id.ne("")
        & player_id.eq(df["starter_qb_id"].fillna("").astype(str).str.strip())
    )
    es_dnp = df["practice_status_norm"].str.contains(
        "did not participate|definitely will not play",
        regex=True,
    )

    df["injury_severity"] = df["injury_weight"]
    df["injury_out_count"] = es_out.astype(float)
    df["injury_doubtful_count"] = es_doubtful.astype(float)
    df["injury_questionable_count"] = es_questionable.astype(float)
    df["injury_dnp_count"] = es_dnp.astype(float)
    df["injury_qb_score"] = df["injury_weight"] * es_qb
    df["injury_qb_out"] = (es_qb & es_out).astype(float)
    df["injury_starting_qb_score"] = df["injury_weight"] * es_titular
    df["injury_starting_qb_out"] = (es_titular & es_out).astype(float)
    df["injury_skill_score"] = df["injury_weight"] * es_skill
    df["injury_skill_out"] = (es_skill & es_out).astype(float)
    df["injury_ol_score"] = df["injury_weight"] * es_ol
    df["injury_ol_out"] = (es_ol & es_out).astype(float)
    df["injury_defense_score"] = df["injury_weight"] * es_defensa
    df["injury_defense_out"] = (es_defensa & es_out).astype(float)

    resumen = (
        df.groupby(["season", "week", "team"], as_index=False)[
            FEATURES_LESIONES_EQUIPO
        ]
        .sum()
    )

    # Incluye equipos sin lesionados reportados para distinguirlos de un merge fallido.
    equipos = pd.concat(
        [
            partidos[["season", "week", "home_team"]].rename(
                columns={"home_team": "team"}
            ),
            partidos[["season", "week", "away_team"]].rename(
                columns={"away_team": "team"}
            ),
        ],
        ignore_index=True,
    ).drop_duplicates()
    equipos["team"] = equipos["team"].astype(str).str.upper()

    resumen = equipos.merge(
        resumen,
        on=["season", "week", "team"],
        how="left",
        validate="one_to_one",
    )
    resumen[FEATURES_LESIONES_EQUIPO] = (
        resumen[FEATURES_LESIONES_EQUIPO].fillna(0.0)
    )
    return resumen


def agregar_features_lesiones(dataset, partidos, lesiones):
    """Agrega variables locales, visitantes, sumas y diferencias."""
    features = construir_features_lesiones(lesiones, partidos)

    home = features.rename(
        columns={
            "team": "home_team",
            **{
                feature: f"home_{feature}"
                for feature in FEATURES_LESIONES_EQUIPO
            },
        }
    )
    away = features.rename(
        columns={
            "team": "away_team",
            **{
                feature: f"away_{feature}"
                for feature in FEATURES_LESIONES_EQUIPO
            },
        }
    )

    resultado = dataset.merge(
        home,
        on=["season", "week", "home_team"],
        how="left",
        validate="many_to_one",
    ).merge(
        away,
        on=["season", "week", "away_team"],
        how="left",
        validate="many_to_one",
    )

    for feature in FEATURES_LESIONES_EQUIPO:
        columnas = [f"home_{feature}", f"away_{feature}"]
        resultado[columnas] = resultado[columnas].fillna(0.0)

    for feature in FEATURES_LESIONES_SUMA:
        resultado[f"sum_{feature}"] = (
            resultado[f"home_{feature}"] + resultado[f"away_{feature}"]
        )

    for feature in FEATURES_LESIONES_DIFERENCIA:
        resultado[f"diff_{feature}"] = (
            resultado[f"home_{feature}"] - resultado[f"away_{feature}"]
        )

    # Un QB titular recibe peso doble porque una ausencia en esa posicion
    # suele alterar mas la produccion ofensiva que una baja individual.
    resultado["sum_injury_offense_score"] = (
        2.0 * resultado["sum_injury_starting_qb_score"]
        + resultado["sum_injury_skill_score"]
        + resultado["sum_injury_ol_score"]
    )
    resultado["net_injury_total_pressure"] = (
        resultado["sum_injury_defense_score"]
        - resultado["sum_injury_offense_score"]
    )

    return resultado


def agregar_contexto_lesiones(dataset, partidos, lesiones):
    """Agrega nombres y notas interpretables sin alterar la prediccion."""
    df = normalizar_lesiones(lesiones)

    home_qb = partidos[
        ["season", "week", "home_team", "home_qb_id"]
    ].rename(columns={"home_team": "team", "home_qb_id": "starter_qb_id"})
    away_qb = partidos[
        ["season", "week", "away_team", "away_qb_id"]
    ].rename(columns={"away_team": "team", "away_qb_id": "starter_qb_id"})
    titulares = pd.concat([home_qb, away_qb], ignore_index=True)
    titulares["team"] = titulares["team"].astype(str).str.upper()
    titulares["starter_qb_id"] = (
        titulares["starter_qb_id"].fillna("").astype(str).str.strip()
    )
    titulares = titulares.drop_duplicates(["season", "week", "team"])
    df = df.merge(
        titulares,
        on=["season", "week", "team"],
        how="left",
        validate="many_to_one",
    )

    player_id = (
        df.get("gsis_id", pd.Series("", index=df.index))
        .fillna("").astype(str).str.strip()
    )
    es_qb_titular = (
        df["position"].eq("QB")
        & player_id.ne("")
        & player_id.eq(df["starter_qb_id"].fillna("").astype(str).str.strip())
    )
    estado_fuerte = df["report_status_norm"].isin(["out", "doubtful"])
    skill_relevante = (
        df["position"].isin(POSICIONES_SKILL)
        & df["report_status_norm"].isin(["out", "doubtful", "questionable"])
    )
    ol_relevante = df["position"].isin(POSICIONES_OL) & estado_fuerte
    defensa_relevante = df["position"].isin(POSICIONES_DEFENSA) & estado_fuerte
    df = df[es_qb_titular | skill_relevante | ol_relevante | defensa_relevante].copy()

    if df.empty:
        return dataset.assign(
            home_key_injuries="",
            away_key_injuries="",
            home_prop_injury_note="",
            away_prop_injury_note="",
        )

    df["is_starter_qb"] = es_qb_titular.loc[df.index]
    nombres = df.get("full_name", pd.Series("Jugador", index=df.index))
    nombres = nombres.fillna("Jugador").astype(str).str.strip()
    estado = df["report_status_norm"].str.upper()
    df["injury_label"] = (
        nombres + " (" + df["position"] + ", " + estado + ")"
    )
    df["sort_priority"] = (
        10 * df["is_starter_qb"].astype(int)
        + df["injury_weight"]
    )

    registros = []
    for claves, grupo in df.groupby(["season", "week", "team"], sort=False):
        grupo = grupo.sort_values("sort_priority", ascending=False)
        etiquetas = grupo["injury_label"].drop_duplicates().head(8).tolist()
        notas = []
        if grupo["is_starter_qb"].any():
            notas.append("QB titular afectado: revisar pases, receptores y total")
        if grupo["position"].isin({"WR", "TE"}).any():
            notas.append("Posible redistribución de targets y recepciones")
        if grupo["position"].isin({"RB", "FB"}).any():
            notas.append("Posible redistribución de acarreos y targets")
        if grupo["position"].isin(POSICIONES_OL).any():
            notas.append("Bajas en línea ofensiva: revisar presión y eficiencia")
        if grupo["position"].isin(POSICIONES_DEFENSA).any():
            notas.append("Bajas defensivas relevantes para props del rival")

        registros.append(
            {
                "season": claves[0],
                "week": claves[1],
                "team": claves[2],
                "key_injuries": "; ".join(etiquetas),
                "prop_injury_note": "; ".join(dict.fromkeys(notas)),
            }
        )

    contexto = pd.DataFrame(registros)
    home = contexto.rename(
        columns={
            "team": "home_team",
            "key_injuries": "home_key_injuries",
            "prop_injury_note": "home_prop_injury_note",
        }
    )
    away = contexto.rename(
        columns={
            "team": "away_team",
            "key_injuries": "away_key_injuries",
            "prop_injury_note": "away_prop_injury_note",
        }
    )
    resultado = dataset.merge(
        home,
        on=["season", "week", "home_team"],
        how="left",
        validate="many_to_one",
    ).merge(
        away,
        on=["season", "week", "away_team"],
        how="left",
        validate="many_to_one",
    )
    columnas = [
        "home_key_injuries", "away_key_injuries",
        "home_prop_injury_note", "away_prop_injury_note",
    ]
    resultado[columnas] = resultado[columnas].fillna("")
    return resultado
