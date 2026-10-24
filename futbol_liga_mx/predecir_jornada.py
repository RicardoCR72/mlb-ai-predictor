"""Pipeline de predicciones diarias y de jornada para la Liga MX.

Genera pronósticos probabilísticos para los dos mercados oficiales solicitados:
1. Totales (Over / Under 2.5 goles).
2. Moneyline (1X2: Victoria Local, Empate, Victoria Visitante).

Preserva cuotas y picks pre-partido para evitar sobreescritura cuando los partidos ya iniciaron.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_CDMX
from futbol_liga_mx.proveedor_cuotas import (
    obtener_calendario_y_cuotas_ligamx,
    normalizar_equipo_ligamx
)
from futbol_liga_mx.modelo_bivariado import (
    proyectar_partido_bivariado,
    entrenar_modelo_bivariado,
    cargar_perfiles_recientes_equipos_ligamx,
    RUTA_MODELO_BIVARIADO,
    FEATURES_BIVARIADO
)

logger = logging.getLogger(__name__)

RUTA_PREDICCIONES_DIR = RAIZ / "futbol_liga_mx" / "data"
RUTA_PREDICCIONES_JSON = RUTA_PREDICCIONES_DIR / "predicciones_ligamx_hoy.json"
RUTA_PREDICCIONES_PARQUET = RUTA_PREDICCIONES_DIR / "predicciones_ligamx_hoy.parquet"


def obtener_jornada_completa_ligamx(force_refresh: bool = False, dias_adelante: int = 4) -> List[Dict[str, Any]]:
    """Consulta los partidos de hoy y los próximos días del fin de semana en la Liga MX."""
    hoy = datetime.now(ZONA_CDMX).date()
    fechas = [(hoy + timedelta(days=i)).strftime("%Y%m%d") for i in range(dias_adelante + 1)]

    juegos_por_id: Dict[str, Dict[str, Any]] = {}
    
    # 1. Consulta sin fecha para la cartelera activa del día
    activos = obtener_calendario_y_cuotas_ligamx(force_refresh=force_refresh, ttl_minutes=15)
    for j in activos:
        juegos_por_id[j["id_evento"]] = j

    # 2. Consultar fechas específicas del fin de semana
    for f_str in fechas:
        sub_juegos = obtener_calendario_y_cuotas_ligamx(fecha=f_str, force_refresh=force_refresh, ttl_minutes=15)
        for j in sub_juegos:
            if j["id_evento"] not in juegos_por_id:
                juegos_por_id[j["id_evento"]] = j

    lista_juegos = list(juegos_por_id.values())
    lista_juegos.sort(key=lambda x: (x.get("fecha_cdmx", ""), x.get("hora_cdmx", "")))
    return lista_juegos


def predecir_jornada_ligamx(force_refresh: bool = False, fecha: Optional[str] = None) -> List[Dict[str, Any]]:
    """Ejecuta el pipeline de inferencia cuantitativa para los partidos de la Liga MX."""
    logger.info("⚽ Iniciando pipeline de inferencia para la Liga MX...")

    if not RUTA_MODELO_BIVARIADO.exists():
        logger.info("Entrenando modelo bivariado Poisson inicial...")
        entrenar_modelo_bivariado()

    bundle = joblib.load(RUTA_MODELO_BIVARIADO)
    perfiles = cargar_perfiles_recientes_equipos_ligamx()

    # Consultar eventos (hoy o fecha específica o fin de semana completo)
    if fecha:
        juegos = obtener_calendario_y_cuotas_ligamx(fecha=fecha, force_refresh=force_refresh)
    else:
        juegos = obtener_jornada_completa_ligamx(force_refresh=force_refresh, dias_adelante=3)

    if not juegos:
        logger.info("No hay partidos programados de Liga MX en este momento.")
        if RUTA_PREDICCIONES_JSON.exists():
            try:
                with open(RUTA_PREDICCIONES_JSON, "w", encoding="utf-8") as f:
                    json.dump([], f)
            except Exception:
                pass
        return []

    # Cargar predicciones previas para preservar picks y momios pre-partido
    predicciones_previas: Dict[str, Dict[str, Any]] = {}
    if RUTA_PREDICCIONES_JSON.exists():
        try:
            with open(RUTA_PREDICCIONES_JSON, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
            for p in prev_data:
                if p.get("id_evento"):
                    predicciones_previas[str(p["id_evento"])] = p
        except Exception:
            pass

    # Promedios generales de la liga como prior
    media_gf_loc = bundle["metricas"].get("media_goles_home", 1.50)
    media_gf_vis = bundle["metricas"].get("media_goles_away", 1.15)

    predicciones = []

    for j in juegos:
        id_ev = str(j.get("id_evento", "")).strip()
        prev = predicciones_previas.get(id_ev)

        # Si el partido ya inició o finalizó, PRESERVAR pick congelado
        estado_juego = str(j.get("estado", "")).upper()
        ya_comenzo = ("PROGRESS" in estado_juego) or ("FINAL" in estado_juego)
        cuotas_vacias = (j.get("moneyline_local") is None and j.get("over_momio") is None)

        if prev and ya_comenzo and prev.get("pick_seleccion"):
            prev_act = dict(prev)
            prev_act["estado"] = j.get("estado", prev.get("estado"))
            prev_act["descripcion_estado"] = j.get("descripcion_estado", prev.get("descripcion_estado"))
            if j.get("marcador_local") is not None:
                prev_act["marcador_local"] = j["marcador_local"]
            if j.get("marcador_visita") is not None:
                prev_act["marcador_visita"] = j["marcador_visita"]

            # Si ya terminó y aún no tenía resultado liquidado, evaluarlo
            if ("FINAL" in str(prev_act.get("estado", "")).upper()) and prev_act.get("marcador_local") is not None:
                try:
                    from futbol_liga_mx.registro import liquidar_partido_ligamx
                    res, u_gan = liquidar_partido_ligamx(pd.Series({
                        "equipo_local": prev_act.get("equipo_local"),
                        "equipo_visitante": prev_act.get("equipo_visita"),
                        "mercado": prev_act.get("pick_mercado"),
                        "seleccion": prev_act.get("pick_seleccion"),
                        "linea": prev_act.get("linea_total", 2.5),
                        "cuota": prev_act.get("pick_cuota_dec", 1.85),
                        "marcador_local": prev_act.get("marcador_local"),
                        "marcador_visitante": prev_act.get("marcador_visita"),
                    }))
                    prev_act["resultado"] = res
                    prev_act["unidades_ganadas"] = u_gan
                except Exception:
                    pass

            predicciones.append(prev_act)
            continue

        home_team = normalizar_equipo_ligamx(j["equipo_local"])
        away_team = normalizar_equipo_ligamx(j["equipo_visita"])

        prof_home = perfiles.get(home_team, {})
        prof_away = perfiles.get(away_team, {})

        feats = {
            "gf_local_5": prof_home.get("gf_local_5", media_gf_loc),
            "gc_local_5": prof_home.get("gc_local_5", media_gf_vis),
            "gf_visitante_5": prof_away.get("gf_visitante_5", media_gf_vis),
            "gc_visitante_5": prof_away.get("gc_visitante_5", media_gf_loc),
            "puntos_local_5": prof_home.get("puntos_local_5", 1.4),
            "puntos_visitante_5": prof_away.get("puntos_visitante_5", 1.1),
            "descanso_local": prof_home.get("descanso", 7.0),
            "descanso_visitante": prof_away.get("descanso", 7.0),
            "media_liga_local": media_gf_loc,
            "media_liga_visitante": media_gf_vis,
        }

        linea_tot = float(j.get("linea_total") or 2.5)
        res_biv = proyectar_partido_bivariado(bundle, feats, linea_total=linea_tot)

        # Probabilidades implícitas del mercado
        p_book_home = j.get("ml_local_prob") or 0.40
        p_book_draw = j.get("ml_empate_prob") or 0.28
        p_book_away = j.get("ml_visita_prob") or 0.32
        p_book_over = j.get("over_prob_implicita") or 0.52
        p_book_under = j.get("under_prob_implicita") or 0.48

        # Edges contra el mercado
        edge_ml_home = res_biv["prob_local"] - p_book_home
        edge_ml_draw = res_biv["prob_empate"] - p_book_draw
        edge_ml_away = res_biv["prob_visita"] - p_book_away
        edge_over = res_biv["prob_over"] - p_book_over
        edge_under = res_biv["prob_under"] - p_book_under

        # Selección del mejor pick (SOLO Over/Under y Moneyline)
        candidatos = []

        # 1. Candidato Totales: OVER
        if edge_over >= 0.02 and res_biv["prob_over"] >= 0.505:
            candidatos.append({
                "mercado": "Totales (Over/Under)",
                "seleccion": f"OVER {linea_tot:g}",
                "probabilidad": res_biv["prob_over"],
                "edge": edge_over,
                "cuota_americana": j.get("over_momio") or "-115",
                "cuota_dec": j.get("over_momio_dec") or 1.85,
                "detalle": f"xG Total: {res_biv['total_proyectado']:.2f} (Prob: {res_biv['prob_over']*100:.1f}% vs Book: {p_book_over*100:.1f}%)"
            })
        # 2. Candidato Totales: UNDER
        elif edge_under >= 0.02 and res_biv["prob_under"] >= 0.505:
            candidatos.append({
                "mercado": "Totales (Over/Under)",
                "seleccion": f"UNDER {linea_tot:g}",
                "probabilidad": res_biv["prob_under"],
                "edge": edge_under,
                "cuota_americana": j.get("under_momio") or "-115",
                "cuota_dec": j.get("under_momio_dec") or 1.85,
                "detalle": f"xG Total: {res_biv['total_proyectado']:.2f} (Prob: {res_biv['prob_under']*100:.1f}% vs Book: {p_book_under*100:.1f}%)"
            })

        # 3. Candidato Moneyline: Local (Debe ser favorito proyectado con probabilidad sólida)
        if res_biv["prob_local"] >= 0.44 and res_biv["prob_local"] > res_biv["prob_visita"] and edge_ml_home >= -0.05:
            candidatos.append({
                "mercado": "Moneyline",
                "seleccion": f"{home_team} ML",
                "probabilidad": res_biv["prob_local"],
                "edge": max(edge_ml_home, 0.01),
                "cuota_americana": j.get("moneyline_local") or "+110",
                "cuota_dec": j.get("ml_local_dec") or 2.10,
                "detalle": f"Favorito proyectado {res_biv['prob_local']*100:.1f}% (xG: {res_biv['xg_local']:.2f} vs {res_biv['xg_visita']:.2f})"
            })
        # 4. Candidato Moneyline: Visita (Debe ser favorito visitante proyectado con probabilidad sólida)
        elif res_biv["prob_visita"] >= 0.44 and res_biv["prob_visita"] > res_biv["prob_local"] and edge_ml_away >= -0.05:
            candidatos.append({
                "mercado": "Moneyline",
                "seleccion": f"{away_team} ML",
                "probabilidad": res_biv["prob_visita"],
                "edge": max(edge_ml_away, 0.01),
                "cuota_americana": j.get("moneyline_visita") or "+180",
                "cuota_dec": j.get("ml_visita_dec") or 2.80,
                "detalle": f"Favorito visitante proyectado {res_biv['prob_visita']*100:.1f}% (xG: {res_biv['xg_visita']:.2f} vs {res_biv['xg_local']:.2f})"
            })

        # Ordenar candidatos priorizando probabilidad real de acierto combinada con valor
        def score_candidato(c):
            p = float(c.get("probabilidad", 0.0))
            ed = float(c.get("edge", 0.0))
            return p * (1.0 + max(ed, 0.0))

        candidatos.sort(key=score_candidato, reverse=True)
        if candidatos:
            mejor = candidatos[0]
        else:
            # Fallback natural con mayor probabilidad intrínseca
            if res_biv["prob_over"] >= res_biv["prob_under"]:
                mejor = {
                    "mercado": "Totales (Over/Under)",
                    "seleccion": f"OVER {linea_tot:g}",
                    "probabilidad": res_biv["prob_over"],
                    "edge": max(edge_over, 0.01),
                    "cuota_americana": j.get("over_momio") or "-115",
                    "cuota_dec": j.get("over_momio_dec") or 1.85,
                    "detalle": f"xG Proyectado: {res_biv['total_proyectado']:.2f} goles."
                }
            else:
                mejor = {
                    "mercado": "Totales (Over/Under)",
                    "seleccion": f"UNDER {linea_tot:g}",
                    "probabilidad": res_biv["prob_under"],
                    "edge": max(edge_under, 0.01),
                    "cuota_americana": j.get("under_momio") or "-115",
                    "cuota_dec": j.get("under_momio_dec") or 1.85,
                    "detalle": f"xG Proyectado: {res_biv['total_proyectado']:.2f} goles."
                }

        # Nivel de confianza
        if mejor["probabilidad"] >= 0.58 or (mejor["probabilidad"] >= 0.52 and mejor["edge"] >= 0.03):
            confianza = "ALTA"
        elif mejor["probabilidad"] >= 0.46:
            confianza = "MEDIA"
        else:
            confianza = "NEUTRAL"

        pred = {
            "id_evento": j["id_evento"],
            "partido": j["partido"],
            "equipo_local": home_team,
            "equipo_visita": away_team,
            "fecha_cdmx": j["fecha_cdmx"],
            "hora_cdmx": j["hora_cdmx"],
            "estado": j["estado"],
            "descripcion_estado": j.get("descripcion_estado", ""),
            "marcador_local": j.get("marcador_local"),
            "marcador_visita": j.get("marcador_visita"),
            "provider": j.get("provider", "DraftKings"),
            # Cuotas Mercado
            "ml_local": j.get("moneyline_local"),
            "ml_empate": j.get("moneyline_empate"),
            "ml_visita": j.get("moneyline_visita"),
            "ml_local_dec": j.get("ml_local_dec"),
            "ml_empate_dec": j.get("ml_empate_dec"),
            "ml_visita_dec": j.get("ml_visita_dec"),
            "linea_total": linea_tot,
            "over_momio": j.get("over_momio"),
            "under_momio": j.get("under_momio"),
            "over_momio_dec": j.get("over_momio_dec"),
            "under_momio_dec": j.get("under_momio_dec"),
            # Modelo Bivariado Poisson
            "xg_local": res_biv["xg_local"],
            "xg_visita": res_biv["xg_visita"],
            "total_proyectado": res_biv["total_proyectado"],
            "marcador_mas_probable": res_biv["marcador_mas_probable"],
            "prob_local": res_biv["prob_local"],
            "prob_empate": res_biv["prob_empate"],
            "prob_visita": res_biv["prob_visita"],
            "prob_over": res_biv["prob_over"],
            "prob_under": res_biv["prob_under"],
            # Pick Oficial
            "pick_mercado": mejor["mercado"],
            "pick_seleccion": mejor["seleccion"],
            "pick_cuota": mejor["cuota_americana"],
            "pick_cuota_dec": mejor["cuota_dec"],
            "pick_probabilidad": round(mejor["probabilidad"], 4),
            "pick_edge": round(mejor["edge"], 4),
            "pick_detalle": mejor["detalle"],
            "confianza": confianza,
            "timestamp": datetime.now(ZONA_CDMX).isoformat(),
        }
        predicciones.append(pred)

    # Guardar en disco
    with open(RUTA_PREDICCIONES_JSON, "w", encoding="utf-8") as f:
        json.dump(predicciones, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 Predicciones guardadas en {RUTA_PREDICCIONES_JSON} ({len(predicciones)} partidos)")

    pd.DataFrame(predicciones).to_parquet(RUTA_PREDICCIONES_PARQUET, index=False)

    # Sincronización en Base de Datos MySQL e historial acumulado
    try:
        from futbol_liga_mx.registro import guardar_predicciones_ligamx
        guardar_predicciones_ligamx(predicciones)
    except Exception as exc:
        logger.warning(f"No se pudo sincronizar en base de datos: {exc}")

    return predicciones


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    preds = predecir_jornada_ligamx(force_refresh=True)
    print(f"\n⚽ Resumen de Predicciones Liga MX ({len(preds)} partidos):")
    for p in preds:
        print(f"\n[{p['fecha_cdmx']} {p['hora_cdmx']} CDMX] {p['partido']}")
        print(f"   xG Proyectado: {p['equipo_local']} {p['xg_local']} vs {p['equipo_visita']} {p['xg_visita']} (Total: {p['total_proyectado']})")
        print(f"   Probabilidades: Local {p['prob_local']*100:.1f}% | Empate {p['prob_empate']*100:.1f}% | Visita {p['prob_visita']*100:.1f}%")
        print(f"   Totales 2.5: Over {p['prob_over']*100:.1f}% | Under {p['prob_under']*100:.1f}%")
        print(f"   🎯 PICK RECOMENDADO: {p['pick_seleccion']} (Momio: {p['pick_cuota']} / {p['pick_cuota_dec']}) [{p['confianza']}] -> {p['pick_detalle']}")
