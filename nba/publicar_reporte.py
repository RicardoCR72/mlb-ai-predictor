"""Genera reporte_publico.html (página estática) a partir del ledger.

    python -m nba.publicar_reporte

Sube data/nba/audit/reporte_publico.html a cualquier hosting estático (GitHub Pages, Netlify, etc.).
No expone nada más que lo que está en el reporte. Publica también el hash de cabecera en otro canal.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nba.auditoria_publica import DIR_AUDIT, _ahora, _resumen, hash_cabecera, tabla_picks, verificar

PLANTILLA = Path(__file__).with_name("plantilla_reporte.html")
SALIDA = DIR_AUDIT / "reporte_publico.html"


def _limpio(o):
    if isinstance(o, dict):
        return {k: _limpio(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_limpio(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if (math.isnan(o) or math.isinf(o)) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def _por(liq: pd.DataFrame, col: str):
    return [{"grupo": str(k), **_resumen(g)} for k, g in liq.groupby(col, dropna=False)]


def construir_datos() -> dict:
    df = tabla_picks()
    d = {"generado": _ahora(), "hash": hash_cabecera(), "integro": bool(verificar()),
         "n_reg": int(len(df)), "n_liq": 0, "n_pend": int(len(df)), "n_corr": 0,
         "global": {"n": 0}, "publicados": {"n": 0}, "por_lado": [], "por_mercado": [],
         "clv": None, "brier": None, "calibracion": [], "curva": [], "ultimos": []}
    if df.empty or "resultado" not in df.columns:
        return d

    liq = df[df.resultado.isin(["GANADA", "PERDIDA", "PUSH"])].copy()
    liq["gano"] = (liq.resultado == "GANADA").astype(int)
    d.update(n_liq=int(len(liq)), n_pend=int(len(df) - len(liq)), n_corr=int(df.corregido.sum()))
    d["global"] = _resumen(liq)
    d["publicados"] = _resumen(liq[liq.publicado == True])  # noqa: E712
    d["por_lado"] = _por(liq, "pick_type")
    d["por_mercado"] = _por(liq, "market")

    nop = liq[liq.resultado != "PUSH"].sort_values(["fecha", "registrado_en"])
    d["curva"] = [{"i": i + 1, "u": round(float(u), 3)} for i, u in enumerate(nop.unidades.astype(float).cumsum())]

    if "cuota_cierre" in liq.columns:
        c = liq.dropna(subset=["cuota_cierre"])
        c = c[c.linea_cierre.astype(float) == c.line.astype(float)]
        if len(c):
            clv = c.cuota_tomada.astype(float) / c.cuota_cierre.astype(float) - 1
            d["clv"] = {"n": int(len(c)), "medio": float(clv.mean() * 100), "pct_pos": float((clv > 0).mean() * 100)}

    sp = nop.dropna(subset=["model_prob", "fair_implied_prob"])
    if len(sp) >= 30:
        d["brier"] = {"n": int(len(sp)),
                      "modelo": float(((sp.model_prob.astype(float) - sp.gano) ** 2).mean()),
                      "mercado": float(((sp.fair_implied_prob.astype(float) - sp.gano) ** 2).mean())}
        b = sp.assign(bucket=pd.qcut(sp.model_prob.astype(float), 5, duplicates="drop"))
        d["calibracion"] = [{"n": int(len(g)), "modelo": float(g.model_prob.astype(float).mean()),
                             "real": float(g.gano.mean())} for _, g in b.groupby("bucket", observed=True)]

    ult = liq.sort_values("registrado_en", ascending=False).head(40)
    d["ultimos"] = [{"fecha": str(r.fecha)[:10], "jugador": r.player_name, "mercado": r.market,
                     "lado": r.pick_type, "linea": r.line, "cuota": r.cuota_tomada,
                     "resultado": r.resultado, "real": r.valor_real, "u": r.unidades,
                     "pub": bool(r.publicado), "corr": bool(r.corregido)} for r in ult.itertuples()]
    return _limpio(d)


def main() -> None:
    datos = json.dumps(construir_datos(), ensure_ascii=False).replace("</", "<\\/")
    SALIDA.write_text(PLANTILLA.read_text(encoding="utf-8").replace("__DATA__", datos), encoding="utf-8")
    print(f"✅ {SALIDA}")


if __name__ == "__main__":
    main()
