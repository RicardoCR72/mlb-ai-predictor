"""Genera reporte_publico.html (página estática) a partir del ledger de NFL props.

    python -m nfl.publicar_reporte

Sube data/nfl/audit/reporte_publico.html a cualquier hosting estático (GitHub Pages, etc.).
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

from nfl.auditoria_publica import DIR_AUDIT, _ahora, _resumen, hash_cabecera, tabla_picks, verificar

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
    d.update(n_liq=int(len(liq)), n_pend=int(len(df) - len(liq)), n_corr=int(df.corregido.sum() if "corregido" in df.columns else 0))
    d["global"] = _resumen(liq)
    d["publicados"] = _resumen(liq[liq.publicado == True]) if "publicado" in liq.columns else {"n": 0}  # noqa: E712
    d["por_lado"] = _por(liq, "seleccion") if "seleccion" in liq.columns else []
    d["por_mercado"] = _por(liq, "tipo_prop") if "tipo_prop" in liq.columns else []

    nop = liq[liq.resultado != "PUSH"].sort_values(["fecha", "registrado_en"]) if "registrado_en" in liq.columns else liq[liq.resultado != "PUSH"]
    if not nop.empty and "unidades" in nop.columns:
        d["curva"] = [{"i": i + 1, "u": round(float(u), 3)} for i, u in enumerate(nop.unidades.astype(float).cumsum())]

    if "cuota_cierre" in liq.columns:
        c = liq.dropna(subset=["cuota_cierre"])
        if len(c):
            c_cuota = c.cuota.astype(float)
            c_cierre = c.cuota_cierre.astype(float)
            clv = c_cuota / c_cierre - 1.0
            d["clv"] = {"n": int(len(c)), "medio": float(clv.mean() * 100), "pct_pos": float((clv > 0).mean() * 100)}

    if "probabilidad_pick" in nop.columns:
        sp = nop.dropna(subset=["probabilidad_pick"])
        if len(sp) >= 30:
            d["brier"] = {"n": int(len(sp)),
                          "modelo": float(((sp.probabilidad_pick.astype(float) - sp.gano) ** 2).mean()),
                          "mercado": float(((0.5238 - sp.gano) ** 2).mean())}
            b = sp.assign(bucket=pd.qcut(sp.probabilidad_pick.astype(float), 5, duplicates="drop"))
            d["calibracion"] = [{"n": int(len(g)), "modelo": float(g.probabilidad_pick.astype(float).mean()),
                                 "real": float(g.gano.mean())} for _, g in b.groupby("bucket", observed=True)]

    ult = liq.sort_values("fecha", ascending=False).head(40) if not liq.empty else df.sort_values("fecha", ascending=False).head(40)
    for _, r in ult.iterrows():
        d["ultimos"].append({
            "fecha": str(r.get("fecha", ""))[:10],
            "jugador": r.get("player_name"),
            "mercado": r.get("tipo_prop"),
            "lado": r.get("seleccion", "OVER"),
            "linea": r.get("linea"),
            "cuota": r.get("cuota"),
            "real": r.get("valor_real"),
            "resultado": r.get("resultado", "PENDIENTE"),
            "corr": bool(r.get("corregido", False)),
            "u": r.get("unidades"),
            "pub": bool(r.get("publicado", False)),
        })
    return _limpio(d)


def main() -> None:
    DIR_AUDIT.mkdir(parents=True, exist_ok=True)
    datos = json.dumps(construir_datos(), ensure_ascii=False).replace("</", "<\\/")
    SALIDA.write_text(PLANTILLA.read_text(encoding="utf-8").replace("__DATA__", datos), encoding="utf-8")
    print(f"✅ {SALIDA}")


if __name__ == "__main__":
    main()
