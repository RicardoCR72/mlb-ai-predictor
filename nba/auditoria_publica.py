"""Registro auditable y reporte público de picks (NBA props).

Principios:
1. APPEND-ONLY: cada evento se agrega al final de ledger.jsonl y lleva el hash del anterior
   (cadena tipo blockchain). Si alguien edita o borra una línea vieja, `verificar` lo detecta.
2. PRIMER SNAPSHOT GANA: un pick (fecha+jugador+mercado) se registra una sola vez. Nunca se reemplaza.
3. SE REGISTRA TODO lo que el modelo señala (>= ⭐), se publique o no. Campo `publicado` indica si
   entró al Top 20. Así el reporte no sufre sesgo de selección.
4. Un pick que llega después del inicio del partido (si se conoce `commence_ts`) se rechaza.
5. Las liquidaciones y cierres son EVENTOS NUEVOS, no ediciones. Las correcciones quedan visibles.
6. Cada día se publica el hash de cabecera (`hash_cabecera`) en un lugar externo (canal público,
   tweet, commit de git). Eso prueba que el historial existía en esa fecha.

Integración (en predecir_props.py, justo después de construir df_res):
    from nba.auditoria_publica import registrar_picks
    registrar_picks(df_res)

Uso por CLI (programar con cron / Task Scheduler):
    python -m nba.auditoria_publica cierres      # 5-10 min antes de cada bloque de partidos
    python -m nba.auditoria_publica liquidar     # al día siguiente
    python -m nba.auditoria_publica verificar
    python -m nba.auditoria_publica reporte
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DIR_AUDIT = RAIZ / "data" / "nba" / "audit"
LEDGER = DIR_AUDIT / "ledger.jsonl"
LOCK = DIR_AUDIT / ".ledger.lock"
REPORTE_MD = DIR_AUDIT / "reporte_publico.md"
GENESIS = "0" * 64

CAMPOS_PICK = [
    "fecha", "game", "player_name", "team", "market", "pick_type", "line", "line_modelo",
    "is_milestone", "pick_odds_decimal", "pick_odds_american", "timestamp_cuota",
    "model_prob", "fair_implied_prob", "ev_pct", "ev_raw", "projection", "stars",
    "home_team", "away_team", "hora", "commence_ts", "minutos_proyectados", "tasa_por_minuto", "factor_defensa_rival",
]


# ---------------------------------------------------------------- utilidades
def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash(prev: str, cuerpo: Dict[str, Any]) -> str:
    return hashlib.sha256((prev + _canon(cuerpo)).encode("utf-8")).hexdigest()


def pick_id(fecha: str, jugador: str, mercado: str) -> str:
    base = f"{str(fecha)[:10]}|{jugador.strip().lower()}|{mercado.strip().lower()}"
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
        os.close(self.fd)
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
    """Agrega eventos [{tipo, pick_id, payload}] al ledger con cadena de hashes."""
    if not eventos:
        return 0
    with _Lock():
        previos = _leer()
        seq = previos[-1]["seq"] + 1 if previos else 0
        prev = previos[-1]["hash"] if previos else GENESIS
        with open(LEDGER, "a", encoding="utf-8") as f:
            for ev in eventos:
                cuerpo = {"seq": seq, "tipo": ev["tipo"], "pick_id": ev.get("pick_id"),
                          "ts": _ahora(), "payload": ev["payload"]}
                h = _hash(prev, cuerpo)
                f.write(_canon({**cuerpo, "prev_hash": prev, "hash": h}) + "\n")
                prev, seq = h, seq + 1
            f.flush()
            os.fsync(f.fileno())
    return len(eventos)


def hash_cabecera() -> str:
    ev = _leer()
    return ev[-1]["hash"] if ev else GENESIS


def verificar() -> bool:
    """Recalcula toda la cadena. False si alguien alteró, borró o reordenó algo."""
    prev, ok = GENESIS, True
    for i, e in enumerate(_leer()):
        cuerpo = {k: e[k] for k in ("seq", "tipo", "pick_id", "ts", "payload")}
        if e["seq"] != i or e["prev_hash"] != prev or _hash(prev, cuerpo) != e["hash"]:
            print(f"❌ Cadena rota en seq={i}")
            ok = False
            break
        prev = e["hash"]
    if ok:
        print(f"✅ Ledger íntegro. Hash de cabecera (publícalo): {prev}")
    return ok


# ---------------------------------------------------------------- registro de picks
def registrar_picks(df: pd.DataFrame, solo_con_senal: bool = True,
                    commence_col: str = "commence_ts") -> Dict[str, int]:
    """Registra picks nuevos. Regla fija: todo pick con >= ⭐ se registra, se publique o no."""
    if df is None or df.empty:
        return {"nuevos": 0, "duplicados": 0, "rechazados": 0}

    existentes = {e["pick_id"] for e in _leer() if e["tipo"] == "PICK"}
    version = version_modelo()
    ahora = datetime.now(timezone.utc)
    nuevos, dup, rech = [], 0, 0

    for _, r in df.iterrows():
        if solo_con_senal and r.get("stars") in ("⚪", "", None):
            continue
        pid = pick_id(r.get("fecha"), str(r.get("player_name", "")), str(r.get("market", "")))
        if pid in existentes:
            dup += 1
            continue
        cuota, prob = r.get("pick_odds_decimal"), r.get("model_prob")
        # validaciones básicas de cordura
        if cuota is None or not (1.01 < float(cuota) < 15) or prob is None or not (0 < float(prob) < 1):
            rech += 1
            continue
        if commence_col in df.columns and pd.notna(r.get(commence_col)):
            try:
                if ahora >= pd.to_datetime(r[commence_col], utc=True):
                    rech += 1  # el partido ya empezó: no cuenta como pick pre-partido
                    continue
            except Exception:
                pass
        payload = {c: (None if pd.isna(r.get(c)) else r.get(c)) for c in CAMPOS_PICK if c in df.columns}
        payload["model_version"] = version
        payload["publicado"] = bool(r.get("es_top20_oficial", False))
        payload["cuota_tomada"] = float(cuota)
        nuevos.append({"tipo": "PICK", "pick_id": pid, "payload": payload})
        existentes.add(pid)

    n = _agregar(nuevos)
    return {"nuevos": n, "duplicados": dup, "rechazados": rech}


# ---------------------------------------------------------------- cierres (para CLV)
def registrar_cierres(df_bovada: pd.DataFrame, solo_pick_ids: Optional[set] = None) -> int:
    """Captura la cuota vigente (ejecutar 5-10 min antes del tip-off). Sin cierre no hay CLV."""
    ev = _leer()
    picks = {e["pick_id"]: e["payload"] for e in ev if e["tipo"] == "PICK"}
    liquidados = {e["pick_id"] for e in ev if e["tipo"] == "LIQUIDACION"}
    nuevos = []
    idx = {(str(r["player_clean"]).lower(), r["market"], float(r["line"])): r
           for _, r in df_bovada.iterrows()}
    for pid, p in picks.items():
        if pid in liquidados or (solo_pick_ids is not None and pid not in solo_pick_ids):
            continue
        clave = (str(p["player_name"]).lower(), p["market"], float(p["line"]))
        fila = idx.get(clave)
        if fila is None:
            continue  # la línea se movió o ya no existe: sin cierre comparable
        col = "over_decimal" if p["pick_type"] == "OVER" else "under_decimal"
        cierre = fila.get(col)
        if cierre and float(cierre) > 1.0:
            nuevos.append({"tipo": "CIERRE", "pick_id": pid,
                           "payload": {"cuota_cierre": float(cierre), "linea_cierre": float(fila["line"])}})
    return _agregar(nuevos)


# ---------------------------------------------------------------- liquidación
def registrar_liquidaciones(df_box: pd.DataFrame) -> int:
    """Liquida picks pendientes con boxscores finales. Una vez liquidado, NO se toca (salvo corrección)."""
    from nba.evaluar_props import liquidar_prop_nba, normalizar_nombre_atleta

    if df_box is None or df_box.empty:
        return 0
    df_box = df_box.copy()
    if "minutos" not in df_box.columns and "min" in df_box.columns:
        df_box["minutos"] = df_box["min"]
    df_box["norm_name"] = df_box["player_name"].apply(normalizar_nombre_atleta)

    ev = _leer()
    liquidados = {e["pick_id"] for e in ev if e["tipo"] == "LIQUIDACION"}
    nuevos = []
    for e in ev:
        if e["tipo"] != "PICK" or e["pick_id"] in liquidados:
            continue
        p = e["payload"]
        sub = df_box[df_box["fecha"].astype(str) == str(p["fecha"])[:10]]
        if sub.empty:
            continue  # sin boxscores de ese día: no liquidar (evita falsos PUSH)
        res = liquidar_prop_nba({
            "player_name": p["player_name"], "player_clean": p["player_name"], "team": p.get("team"),
            "market": p["market"], "line": p["line"], "pick_type": p["pick_type"],
            "pick_odds_decimal": p["cuota_tomada"], "is_milestone": p.get("is_milestone", 0),
        }, sub, partido_finalizado=True)
        if res["resultado"] == "PENDIENTE":
            continue
        nuevos.append({"tipo": "LIQUIDACION", "pick_id": e["pick_id"], "payload": {
            "resultado": res["resultado"], "valor_real": res["valor_real"],
            "unidades": res["unidades_ganadas"], "motivo": res["motivo"]}})
    return _agregar(nuevos)


def corregir(pick_id_: str, resultado: str, valor_real: Optional[float], unidades: float, motivo: str) -> None:
    """Correcciones manuales: quedan como evento visible y marcadas en el reporte."""
    if not motivo.strip():
        raise ValueError("Toda corrección exige un motivo.")
    _agregar([{"tipo": "CORRECCION", "pick_id": pick_id_, "payload": {
        "resultado": resultado, "valor_real": valor_real, "unidades": unidades, "motivo": motivo}}])


# ---------------------------------------------------------------- reporte
def tabla_picks() -> pd.DataFrame:
    filas: Dict[str, Dict[str, Any]] = {}
    for e in _leer():
        pid = e["pick_id"]
        if e["tipo"] == "PICK":
            filas[pid] = {**e["payload"], "pick_id": pid, "registrado_en": e["ts"], "corregido": False}
        elif pid in filas:
            if e["tipo"] == "CIERRE":
                filas[pid].update(e["payload"])  # el último cierre previo al juego prevalece
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
    if df.empty:
        return "Sin picks registrados todavía."
    if "resultado" not in df.columns:
        df["resultado"] = None
    cierre_ok = df.get("cuota_cierre").notna() if "cuota_cierre" in df.columns else pd.Series(False, index=df.index)
    liq = df[df.resultado.isin(["GANADA", "PERDIDA", "PUSH"])].copy()
    liq["gano"] = (liq.resultado == "GANADA").astype(int)
    liq["tipo"] = liq.pick_type

    out = [f"# Reporte de rendimiento NBA props",
           f"Generado: {_ahora()} UTC | Hash de cabecera: `{hash_cabecera()}`",
           f"Picks registrados: {len(df)} | Liquidados: {len(liq)} | Pendientes: {len(df) - len(liq)} "
           f"| Correcciones manuales: {int(df.corregido.sum())}", ""]

    def seccion(titulo: str, sub: pd.DataFrame, por: Optional[str] = None):
        out.append(f"## {titulo}")
        if por is None:
            out.append("```\n" + pd.DataFrame([_resumen(sub)]).to_string(index=False) + "\n```")
        else:
            filas = []
            for k, g in sub.groupby(por, dropna=False):
                filas.append({por: k, **_resumen(g)})
            out.append("```\n" + pd.DataFrame(filas).to_string(index=False) + "\n```")
        out.append("")

    seccion("Todos los picks registrados (sin filtrar por publicación)", liq)
    seccion("Solo picks publicados (Top 20)", liq[liq.publicado == True])  # noqa: E712
    seccion("Por lado", liq, "tipo")
    seccion("Por mercado", liq, "market")
    seccion("Milestones vs líneas regulares", liq, "is_milestone")
    seccion("Por versión de modelo", liq, "model_version")

    # CLV
    out.append("## CLV (cuota tomada vs cuota de cierre, misma línea)")
    c = liq[cierre_ok.reindex(liq.index, fill_value=False)].copy() if len(liq) else liq
    if not c.empty:
        c = c[c.linea_cierre.astype(float) == c.line.astype(float)]
        c["clv"] = c.cuota_tomada.astype(float) / c.cuota_cierre.astype(float) - 1
        out.append(f"```\nn={len(c)} | CLV medio={c.clv.mean()*100:+.2f}% | % picks con CLV>0={(c.clv>0).mean()*100:.0f}%\n```")
    else:
        out.append("Sin cierres capturados todavía (ejecuta `cierres` antes de cada bloque de partidos).")
    out.append("")

    # Brier / calibración (sin pushes)
    sp = liq[liq.resultado.isin(["GANADA", "PERDIDA"])].dropna(subset=["model_prob", "fair_implied_prob"])
    out.append("## ¿El modelo supera al mercado? (Brier, menor = mejor)")
    if len(sp) >= 30:
        bm = ((sp.model_prob.astype(float) - sp.gano) ** 2).mean()
        bk = ((sp.fair_implied_prob.astype(float) - sp.gano) ** 2).mean()
        out.append(f"```\nModelo: {bm:.4f} | Mercado: {bk:.4f} | n={len(sp)}\n```")
        sp = sp.assign(bucket=pd.qcut(sp.model_prob.astype(float), 5, duplicates="drop"))
        cal = sp.groupby("bucket", observed=True).agg(n=("gano", "size"), prob_modelo=("model_prob", "mean"),
                                                      frecuencia_real=("gano", "mean")).round(3)
        out.append("### Calibración\n```\n" + cal.to_string() + "\n```")
    else:
        out.append("Muestra insuficiente (<30 picks liquidados).")

    out += ["", "---",
            "**Aviso:** resultados pasados no garantizan resultados futuros. Las apuestas implican riesgo de "
            "pérdida. El historial es append-only y verificable por cadena de hashes; las correcciones "
            "manuales aparecen contadas arriba. Este reporte no es asesoría financiera ni promesa de ganancias."]
    texto = "\n".join(out)
    REPORTE_MD.write_text(texto, encoding="utf-8")
    return texto


# ---------------------------------------------------------------- CLI
if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ))
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["cierres", "liquidar", "verificar", "reporte"])
    a = ap.parse_args()
    if a.accion == "verificar":
        sys.exit(0 if verificar() else 1)
    elif a.accion == "reporte":
        print(generar_reporte())
    elif a.accion == "cierres":
        from nba.servicio_bovada_props import extraer_props_nba
        print("Cierres registrados:", registrar_cierres(extraer_props_nba(usar_cache=False)))
    elif a.accion == "liquidar":
        from nba.servicio_jugadores_boxscores import sincronizar_boxscores_jugadores
        print("Liquidaciones registradas:", registrar_liquidaciones(sincronizar_boxscores_jugadores()))
