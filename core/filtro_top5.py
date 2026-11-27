"""Filtro centralizado Top 5 de máxima confianza y valor esperado (+EV).

Unifica la selección automática en todos los deportes y mercados para mostrar
únicamente los picks más seguros y con valor esperado positivo, eliminando
selecciones neutrales, sin valor o ruido de estrellas de baja confianza.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Iterable, Optional, Sequence

import pandas as pd

TOP_N_PICKS: int = 5

MERCADOS_PROPS_NBA_EXCLUIDOS_TOP5 = frozenset({"Total Assists"})

CONFIANZAS_EXCLUIDAS = frozenset({
    "NEUTRAL",
    "SIN VALOR",
    "NO PICK",
    "PASS",
    "ZONA MUERTA",
    "LONGSHOT",
    "BAJA",
    "⚪",
    "",
})

CONFIANZAS_VALIDAS = frozenset({
    "ALTA",
    "MEDIA",
    "CANDIDATO",
    "PICK",
    "ELITE",
})


def etiqueta_top(rank: int) -> str:
    """Devuelve la insignia oficial de ranking Top N sin estrellas ruidosas."""
    pos = max(1, int(rank))
    return f"🏆 TOP #{pos}"


def _normalizar_prob(val: Any) -> Optional[float]:
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    if num > 1.0:
        num = num / 100.0
    return num


def _a_float_finito(val: Any) -> Optional[float]:
    try:
        num = float(val)
        return num if math.isfinite(num) else None
    except (TypeError, ValueError):
        return None


def filtrar_top5_picks_dict(
    items: Iterable[dict],
    get_conf: Callable[[dict], Any],
    get_prob: Callable[[dict], Any],
    get_ev: Callable[[dict], Any],
    get_id_unico: Optional[Callable[[dict], Any]] = None,
    limite: int = TOP_N_PICKS,
    min_prob: float = 0.53,
    min_ev_pct: Optional[float] = None,
    confianzas_validas: Optional[Sequence[str]] = ("ALTA", "MEDIA"),
    min_ev: float = 0.0,
) -> list[dict]:
    """Filtra una colección de picks (dicts) al Top N más seguro con EV positivo."""
    if limite <= 0:
        return []

    umbral_ev = float(min_ev if min_ev_pct is None else min_ev_pct)
    permitidas = (
        {str(c).strip().upper() for c in confianzas_validas if str(c).strip()}
        if confianzas_validas is not None
        else None
    )
    candidatos: list[tuple[tuple[int, float, float], dict]] = []

    for item in items:
        conf_norm = str(get_conf(item) or "").strip().upper()
        if conf_norm in CONFIANZAS_EXCLUIDAS:
            continue
        if permitidas is not None and conf_norm not in permitidas:
            continue

        prob = _normalizar_prob(get_prob(item))
        ev = _a_float_finito(get_ev(item))
        if prob is None or ev is None:
            continue
        if prob < min_prob or ev <= umbral_ev:
            continue

        score = (1 if conf_norm in ("ALTA", "ELITE") else 0, prob, ev)
        candidatos.append((score, item))

    candidatos.sort(key=lambda par: par[0], reverse=True)

    if get_id_unico is None:
        return [item for _, item in candidatos[:limite]]

    vistos: set[str] = set()
    resultado: list[dict] = []
    for _, item in candidatos:
        raw_id = get_id_unico(item)
        clave = str(raw_id or "").strip().lower()
        if clave:
            if clave in vistos:
                continue
            vistos.add(clave)
        resultado.append(item)
        if len(resultado) >= limite:
            break

    return resultado


def filtrar_top5_dataframe(
    df: pd.DataFrame,
    prob_col: str,
    ev_col: str,
    valid_mask: Optional[pd.Series] = None,
    conf_col: Optional[str] = None,
    dedupe_cols: Optional[Sequence[str] | str] = None,
    limite: int = TOP_N_PICKS,
    min_prob: float = 0.53,
    min_ev: float = 0.0,
    confianzas_validas: Optional[Sequence[str]] = ("ALTA", "MEDIA"),
    dedupe_col: Optional[str] = None,
) -> pd.DataFrame:
    """Filtra un DataFrame al Top N más seguro con probabilidad mínima y EV positivo."""
    if df is None or df.empty or limite <= 0:
        return df.iloc[0:0].copy() if df is not None else pd.DataFrame()
    if prob_col not in df.columns or ev_col not in df.columns:
        return df.iloc[0:0].copy()

    effective_dedupe = dedupe_cols if dedupe_cols is not None else dedupe_col

    work = df.copy()
    if valid_mask is not None:
        mask_aligned = pd.Series(valid_mask, index=work.index).fillna(False).astype(bool)
        work = work.loc[mask_aligned].copy()
        if work.empty:
            return work

    if conf_col and conf_col in work.columns:
        confs = work[conf_col].astype(str).str.strip().str.upper()
        mask_conf = ~confs.isin(CONFIANZAS_EXCLUIDAS)
        if confianzas_validas is not None:
            permitidas = {str(c).strip().upper() for c in confianzas_validas if str(c).strip()}
            mask_conf = mask_conf & confs.isin(permitidas)
        work = work.loc[mask_conf].copy()
        if work.empty:
            return work
        work["_top5_prio"] = work[conf_col].astype(str).str.strip().str.upper().isin(("ALTA", "ELITE")).astype(int)
    else:
        work["_top5_prio"] = 0

    prob_num = pd.to_numeric(work[prob_col], errors="coerce")
    prob_num = prob_num.where(prob_num <= 1.0, prob_num / 100.0)
    ev_num = pd.to_numeric(work[ev_col], errors="coerce")

    work["_top5_prob"] = prob_num
    work["_top5_ev"] = ev_num

    work = work[
        work["_top5_prob"].notna()
        & work["_top5_ev"].notna()
        & (work["_top5_prob"] >= float(min_prob))
        & (work["_top5_ev"] > float(min_ev))
    ].copy()

    if work.empty:
        return work.drop(columns=["_top5_prio", "_top5_prob", "_top5_ev"], errors="ignore")

    work = work.sort_values(
        by=["_top5_prio", "_top5_prob", "_top5_ev"],
        ascending=[False, False, False],
        kind="mergesort",
    )

    if effective_dedupe:
        cols_list = [effective_dedupe] if isinstance(effective_dedupe, str) else list(effective_dedupe)
        cols_presentes = [c for c in cols_list if c in work.columns]
        if cols_presentes:
            temp_keys = []
            for c in cols_presentes:
                tk = f"_top5_key_{c}"
                work[tk] = work[c].astype(str).str.strip().str.lower()
                temp_keys.append(tk)
            work = work.drop_duplicates(subset=temp_keys, keep="first")
            work = work.drop(columns=temp_keys, errors="ignore")

    work = work.head(int(limite)).drop(
        columns=["_top5_prio", "_top5_prob", "_top5_ev"],
        errors="ignore",
    )
    return work.reset_index(drop=True)
