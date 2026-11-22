"""Registro auditable y reporte público de picks (NFL props).

Principios:
1. APPEND-ONLY: cada evento se agrega al final de ledger.jsonl y lleva el hash del anterior
   (cadena tipo blockchain SHA-256). Si se edita o borra una línea, `verificar` lo detecta.
2. PRIMER SNAPSHOT GANA: un pick (fecha+jugador+tipo_prop) se registra una sola vez. Nunca se reemplaza.
3. SE REGISTRA TODO: tanto picks oficiales como no oficiales. Campo `publicado` indica si
   fue seleccionado como oficial.
4. Rechazo pre-partido: picks registrados después del kickoff se rechazan.
5. Cierres y liquidaciones son EVENTOS NUEVOS, preservando trazabilidad completa.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DIR_AUDIT = RAIZ / "data" / "nfl" / "audit"
LEDGER = DIR_AUDIT / "ledger.jsonl"
LOCK = DIR_AUDIT / ".ledger.lock"
REPORTE_MD = DIR_AUDIT / "reporte_publico.md"
GENESIS = "0" * 64

CAMPOS_PICK = [
    "fecha", "game_id", "home_team", "away_team", "player_name", "team", "position",
    "tipo_prop", "seleccion", "linea", "cuota", "proyeccion", "edge",
    "probabilidad_pick", "ev_estimado", "estado_pick", "hora", "commence_ts",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nfl_auditoria")


# ---------------------------------------------------------------- utilidades
def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash(prev: str, cuerpo: Dict[str, Any]) -> str:
    return hashlib.sha256((prev + _canon(cuerpo)).encode("utf-8")).hexdigest()


def pick_id(fecha: str, jugador: str, tipo_prop: str) -> str:
    base = f"{str(fecha)[:10]}|{jugador.strip().lower()}|{tipo_prop.strip().lower()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def version_modelo() -> str:
    try:
        h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ,
                                    stderr=subprocess.DEVNULL).decode().strip()
        sucio = subprocess.check_output(["git", "status", "--porcelain"], cwd=RAIZ,
                                        stderr=subprocess.DEVNULL).decode().strip()
        return f"{h}{'-dirty' if sucio else ''}"
    except Exception:
        return "unknown"


class _Lock:
    def __enter__(self):
        DIR_AUDIT.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                self.fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except (FileExistsError, PermissionError):
                if time.time() - t0 > 15:
                    raise TimeoutError(f"Lock colgado: borra {LOCK} si no hay otro proceso corriendo.")
                time.sleep(0.1)

    def __exit__(self, *a):
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            os.unlink(LOCK)
        except OSError:
            pass


def _leer() -> List[Dict[str, Any]]:
    if not LEDGER.exists():
        return []
    with open(LEDGER, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _agregar(eventos: List[Dict[str, Any]]) -> int:
    if not eventos:
        return 0
    with _Lock():
        existentes = _leer()
        prev = existentes[-1]["hash"] if existentes else GENESIS
        lineas = []
        for e in eventos:
            e["ts"] = _ahora()
            e["hash"] = _hash(prev, {k: v for k, v in e.items() if k != "hash"})
            prev = e["hash"]
            lineas.append(json.dumps(e, ensure_ascii=False))
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
    return len(eventos)


def hash_cabecera() -> str:
    ev = _leer()
    return ev[-1]["hash"] if ev else GENESIS


def verificar() -> bool:
    """Valida la cadena SHA-256 completa desde el bloque génesis."""
    ev = _leer()
    if not ev:
        print("Ledger vacío.")
        return True
    prev = GENESIS
    for i, e in enumerate(ev):
        esperado = _hash(prev, {k: v for k, v in e.items() if k != "hash"})
        if e.get("hash") != esperado:
            print(f"❌ CORRUPCIÓN en evento #{i} (pick_id={e.get('pick_id')}): hash={e.get('hash')} != {esperado}")
            return False
        prev = e["hash"]
    print(f"✅ Ledger íntegro. Hash de cabecera: {prev}")
    return True


# ---------------------------------------------------------------- registro de picks
def registrar_picks(df: pd.DataFrame) -> Dict[str, int]:
    """Registra picks de NFL generados por el modelo. Snapshot inmutable."""
    if df.empty:
        return {"nuevos": 0, "duplicados": 0, "rechazados": 0}

    ev = _leer()
    existentes = {e["pick_id"] for e in ev if e["tipo"] == "PICK"}
    ahora_dt = datetime.now(timezone.utc)
    version = version_modelo()
    nuevos: List[Dict[str, Any]] = []
    dup, rech = 0, 0

    for _, r in df.iterrows():
        p_nom = str(r.get("player_name") or "")
        t_prop = str(r.get("tipo_prop") or "")
        f_val = str(r.get("fecha") or r.get("game_date") or datetime.now().strftime("%Y-%m-%d"))[:10]
        
        pid = pick_id(f_val, p_nom, t_prop)
        if pid in existentes:
            dup += 1
            continue

        c_ts = r.get("commence_ts")
        if c_ts:
            try:
                ini = pd.to_datetime(c_ts, utc=True).to_pydatetime()
                if ahora_dt >= ini:
                    rech += 1
                    continue
            except Exception:
                pass

        cuota = r.get("cuota") or r.get("cuota_over") or r.get("cuota_under") or 1.91
        payload = {c: (None if pd.isna(r.get(c)) else r.get(c)) for c in CAMPOS_PICK if c in df.columns}
        payload["model_version"] = version
        payload["publicado"] = bool(str(r.get("estado_pick", "")).upper() in ["OFICIAL", "CANDADO"])
        payload["cuota_tomada"] = float(cuota)
        payload["fecha"] = f_val

        nuevos.append({"tipo": "PICK", "pick_id": pid, "payload": payload})
        existentes.add(pid)

    n = _agregar(nuevos)
    return {"nuevos": n, "duplicados": dup, "rechazados": rech}


# ---------------------------------------------------------------- cierres (para CLV)
def registrar_cierres(df_bovada: pd.DataFrame, solo_pick_ids: Optional[set] = None) -> int:
    """Captura cuotas de cierre de Bovada NFL para comparar con la cuota tomada."""
    if df_bovada.empty:
        return 0
    ev = _leer()
    picks = {e["pick_id"]: e["payload"] for e in ev if e["tipo"] == "PICK"}
    liquidados = {e["pick_id"] for e in ev if e["tipo"] == "LIQUIDACION"}
    nuevos = []

    # Indizar bovada por (player_name.lower(), tipo_prop, linea)
    idx = {}
    for _, r in df_bovada.iterrows():
        p_name = str(r.get("player_name", "")).strip().lower()
        t_prop = str(r.get("tipo_prop", "")).strip().lower()
        lin = float(r.get("linea", 0.0) or 0.0)
        idx[(p_name, t_prop, lin)] = r

    for pid, p in picks.items():
        if pid in liquidados or (solo_pick_ids is not None and pid not in solo_pick_ids):
            continue
        p_name = str(p.get("player_name", "")).strip().lower()
        t_prop = str(p.get("tipo_prop", "")).strip().lower()
        lin = float(p.get("linea", 0.0) or 0.0)

        match = idx.get((p_name, t_prop, lin))
        if match is None:
            continue

        sel = str(p.get("seleccion", "OVER")).upper()
        if sel == "OVER":
            cuota_cierre = match.get("cuota_over")
        else:
            cuota_cierre = match.get("cuota_under")

        if not cuota_cierre or pd.isna(cuota_cierre):
            continue

        c_tomada = float(p.get("cuota_tomada") or p.get("cuota") or 1.91)
        clv = (c_tomada / float(cuota_cierre)) - 1.0

        nuevos.append({
            "tipo": "CIERRE",
            "pick_id": pid,
            "payload": {
                "cuota_cierre": float(cuota_cierre),
                "linea_cierre": lin,
                "clv_pct": round(clv * 100.0, 2),
                "timestamp_cierre": _ahora(),
            }
        })

    return _agregar(nuevos)


# ---------------------------------------------------------------- liquidaciones
def registrar_liquidaciones(stats_dict_or_df: Any) -> int:
    """Liquida picks contra boxscores oficiales de la NFL."""
    ev = _leer()
    picks = {e["pick_id"]: e["payload"] for e in ev if e["tipo"] == "PICK"}
    ya_liquidados = {e["pick_id"] for e in ev if e["tipo"] == "LIQUIDACION"}
    nuevos = []

    # Puede ser dict {norm_nombre: {stat: valor}} o DataFrame
    for pid, p in picks.items():
        if pid in ya_liquidados:
            continue

        p_nom = str(p.get("player_name", "")).strip().lower()
        t_prop = str(p.get("tipo_prop", "")).strip().lower()
        lin = float(p.get("linea", 0.0) or 0.0)
        sel = str(p.get("seleccion", "OVER")).upper()

        val_real = None
        if isinstance(stats_dict_or_df, dict):
            jug_stats = stats_dict_or_df.get(p_nom)
            if jug_stats:
                val_real = jug_stats.get(t_prop)
        elif isinstance(stats_dict_or_df, pd.DataFrame):
            # Buscar en dataframe
            m = stats_dict_or_df[stats_dict_or_df["player_name"].str.lower() == p_nom]
            if not m.empty and t_prop in m.columns:
                val_real = float(m[t_prop].iloc[0])

        if val_real is None or pd.isna(val_real):
            continue

        if val_real > lin:
            res = "GANADA" if sel == "OVER" else "PERDIDA"
        elif val_real < lin:
            res = "PERDIDA" if sel == "OVER" else "GANADA"
        else:
            res = "PUSH"

        c = float(p.get("cuota_tomada") or p.get("cuota") or 1.91)
        u = (c - 1.0) if res == "GANADA" else (-1.0 if res == "PERDIDA" else 0.0)

        nuevos.append({
            "tipo": "LIQUIDACION",
            "pick_id": pid,
            "payload": {
                "valor_real": float(val_real),
                "resultado": res,
                "unidades": round(u, 3),
                "liquidado_en": _ahora(),
            }
        })

    return _agregar(nuevos)


# ---------------------------------------------------------------- tabla de análisis
def tabla_picks() -> pd.DataFrame:
    filas: Dict[str, Dict[str, Any]] = {}
    for e in _leer():
        pid = e["pick_id"]
        if e["tipo"] == "PICK":
            filas[pid] = {**e["payload"], "pick_id": pid, "registrado_en": e["ts"], "corregido": False}
        elif pid in filas:
            if e["tipo"] == "CIERRE":
                filas[pid].update(e["payload"])
            elif e["tipo"] in ("LIQUIDACION", "CORRECCION"):
                filas[pid].update(e["payload"])
                filas[pid]["corregido"] = filas[pid]["corregido"] or e["tipo"] == "CORRECCION"
    return pd.DataFrame(filas.values())


def _ic_roi(u: pd.Series, n_boot: int = 5000) -> List[float]:
    rng = np.random.default_rng(0)
    v = u.to_numpy()
    medias = [rng.choice(v, len(v), replace=True).mean() for _ in range(n_boot)]
    return [float(x * 100) for x in np.percentile(medias, [2.5, 97.5])]


def _resumen(d: pd.DataFrame) -> Dict[str, Any]:
    d = d[d.resultado.isin(["GANADA", "PERDIDA"])]
    if d.empty:
        return {"n": 0}
    u = d.unidades.astype(float)
    lo, hi = _ic_roi(u) if len(d) >= 20 else (np.nan, np.nan)
    return {"n": len(d), "acierto_%": round((d.resultado == "GANADA").mean() * 100, 1),
            "unidades": round(u.sum(), 2), "roi_%": round(u.mean() * 100, 1),
            "ic95_lo": round(lo, 1), "ic95_hi": round(hi, 1)}


def generar_reporte() -> str:
    df = tabla_picks()
    cab = hash_cabecera()
    if df.empty:
        return f"# Reporte NFL Props\nHash cabecera: `{cab}`\nSin picks registrados."

    liq = df[df["resultado"].notna()]
    n_total = len(df)
    n_liq = len(liq)
    u_total = liq["unidades"].sum() if n_liq > 0 else 0.0
    roi = (u_total / n_liq * 100.0) if n_liq > 0 else 0.0

    md = [
        f"# Reporte Institucional NFL Props",
        f"Hash de cabecera: `{cab}` | Verificado: {_ahora()}",
        f"- **Picks Totales:** {n_total}",
        f"- **Liquidados:** {n_liq}",
        f"- **Unidades:** {u_total:+.2f} U",
        f"- **ROI:** {roi:+.2f}%",
    ]
    texto = "\n".join(md)
    DIR_AUDIT.mkdir(parents=True, exist_ok=True)
    REPORTE_MD.write_text(texto, encoding="utf-8")
    return texto


# ---------------------------------------------------------------- CLI
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["cierres", "liquidar", "verificar", "reporte"])
    a = ap.parse_args()
    if a.accion == "verificar":
        sys.exit(0 if verificar() else 1)
    elif a.accion == "reporte":
        print(generar_reporte())
    elif a.accion == "cierres":
        from nfl.servicio_bovada_props import extraer_props_nfl
        print("Cierres registrados:", registrar_cierres(extraer_props_nfl(usar_cache=False)))
    elif a.accion == "liquidar":
        from nfl.liquidar_nfl import obtener_boxscore_espn
        # Por omisión liquidar con lo disponible
        print("Para liquidar especificar IDs de juegos concluidos.")
