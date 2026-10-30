"""Script automatizado para consolidar y enviar alertas de picks de alto valor (+EV).

Escanea las predicciones activas de NBA, Fútbol (8 ligas) y NFL, selecciona las oportunidades
con mayor ventaja estadística (Edge >= 4.5% o confianza ALTA/MEDIA con EV > 0) y despacha
un reporte formateado a Telegram y Discord.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.alerts import enviar_alerta_multicanal, get_telegram_config, get_discord_config
from core.constants import ZONA_CDMX

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("notificador_alto_ev")


def obtener_picks_alto_ev_futbol(min_edge: float = 0.045, max_picks: int = 5) -> List[Dict[str, Any]]:
    """Extrae las mejores oportunidades activas de fútbol mundial y Liga MX."""
    ruta_json = RAIZ / "data" / "futbol" / "predicciones_futbol_mundial.json"
    if not ruta_json.exists():
        return []

    try:
        with open(ruta_json, "r", encoding="utf-8") as f:
            juegos = json.load(f)
    except Exception as exc:
        logger.warning(f"No se pudo leer predicciones de fútbol: {exc}")
        return []

    hoy_str = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
    picks_validos = []

    for j in juegos:
        if j.get("resultado_pick") in ["GANADA", "PERDIDA", "PUSH"]:
            continue
        estado = str(j.get("estado", "")).upper()
        if any(k in estado for k in ["FINAL", "FT", "POST", "FULL_TIME"]):
            continue

        confianza = str(j.get("confianza", "")).upper()
        if confianza not in ["ALTA", "MEDIA", "LONGSHOT"]:
            continue

        edge = float(j.get("pick_edge") or 0.0)
        if edge < min_edge:
            continue

        picks_validos.append({
            "deporte": "Fútbol",
            "liga": j.get("liga_nombre", "Fútbol"),
            "partido": j.get("partido", f"{j.get('equipo_local')} vs {j.get('equipo_visita')}"),
            "fecha": j.get("fecha_cdmx", hoy_str),
            "hora": j.get("hora_cdmx", "TBD"),
            "mercado": j.get("pick_mercado", "1X2 / Totales"),
            "seleccion": j.get("pick_seleccion", ""),
            "cuota": j.get("pick_cuota", ""),
            "cuota_dec": float(j.get("pick_cuota_dec") or 1.91),
            "probabilidad": float(j.get("pick_probabilidad") or 0.5),
            "edge": edge,
            "ev": float(j.get("pick_ev") or 0.0),
            "confianza": confianza,
            "detalle": j.get("pick_detalle", ""),
        })

    # Ordenar por mayor Edge y retornar los mejores
    picks_validos.sort(key=lambda x: x["edge"], reverse=True)
    return picks_validos[:max_picks]


def obtener_picks_alto_ev_nba(min_edge: float = 0.040, max_picks: int = 5) -> List[Dict[str, Any]]:
    """Extrae las mejores oportunidades activas de NBA."""
    ruta_json = RAIZ / "data" / "nba" / "predictions" / "predicciones_nba_hoy.json"
    if not ruta_json.exists():
        return []

    try:
        with open(ruta_json, "r", encoding="utf-8") as f:
            juegos = json.load(f)
    except Exception as exc:
        logger.warning(f"No se pudo leer predicciones de NBA: {exc}")
        return []

    hoy_str = datetime.now(ZONA_CDMX).strftime("%Y-%m-%d")
    picks_validos = []

    for j in juegos:
        if j.get("resultado") in ["GANADA", "PERDIDA", "PUSH"]:
            continue
        estado = str(j.get("estado", "")).upper()
        if any(k in estado for k in ["FINAL", "STATUS_FINAL", "POST"]):
            continue

        confianza = str(j.get("confianza", "")).upper()
        if confianza not in ["ALTA", "MEDIA", "LONGSHOT"]:
            continue

        edge = float(j.get("pick_edge") or 0.0)
        if edge < min_edge:
            continue

        picks_validos.append({
            "deporte": "NBA",
            "liga": "NBA",
            "partido": j.get("partido", f"{j.get('equipo_visita')} @ {j.get('equipo_local')}"),
            "fecha": j.get("fecha_cdmx", hoy_str),
            "hora": j.get("hora_cdmx", "TBD"),
            "mercado": j.get("pick_mercado", "Moneyline"),
            "seleccion": j.get("pick_seleccion", ""),
            "cuota": j.get("pick_cuota", "-110"),
            "cuota_dec": float(j.get("pick_cuota_dec") or 1.91),
            "probabilidad": float(j.get("pick_probabilidad") or 0.5),
            "edge": edge,
            "ev": float(j.get("pick_ev") or 0.0),
            "confianza": confianza,
            "detalle": j.get("pick_detalle", ""),
        })

    picks_validos.sort(key=lambda x: x["edge"], reverse=True)
    return picks_validos[:max_picks]


def obtener_picks_alto_ev_nfl(min_edge: float = 0.050, max_picks: int = 5) -> List[Dict[str, Any]]:
    """Extrae las mejores oportunidades activas de NFL (Marcadores y Props)."""
    picks_validos = []

    # 1. Intentar desde base de datos MySQL (nfl_registro_picks pendientes)
    try:
        from core.db import get_db_connection
        conn = get_db_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT juego, tipo_apuesta AS mercado, seleccion, linea, cuota,
                       probabilidad, edge, confianza, unidades_apostadas
                FROM nfl_registro_picks
                WHERE resultado = 'PENDIENTE'
                  AND edge >= %s
                ORDER BY edge DESC
                LIMIT %s
            """, (min_edge, max_picks))
            filas = cur.fetchall()
            for r in filas:
                picks_validos.append({
                    "deporte": "NFL",
                    "liga": "NFL",
                    "partido": r.get("juego", ""),
                    "fecha": "Semana Activa",
                    "hora": "",
                    "mercado": r.get("mercado", ""),
                    "seleccion": r.get("seleccion", ""),
                    "cuota": str(r.get("cuota", "")),
                    "cuota_dec": float(r.get("cuota") or 1.91) if str(r.get("cuota", "")).replace(".", "").isdigit() else 1.91,
                    "probabilidad": float(r.get("probabilidad") or 0.5),
                    "edge": float(r.get("edge") or 0.0),
                    "ev": float(r.get("edge") or 0.0),
                    "confianza": str(r.get("confianza", "MEDIA")),
                    "detalle": f"Línea: {r.get('linea', '')}",
                })
        conn.close()
    except Exception as exc:
        logger.debug(f"NFL DB query omitida o sin registros: {exc}")

    # 2. Si no hay en DB, verificar archivos JSON locales de props de la semana
    if not picks_validos:
        ruta_props = RAIZ / "data" / "nfl" / "props"
        if ruta_props.exists():
            for archivo in ruta_props.glob("*.json"):
                try:
                    with open(archivo, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    items = data if isinstance(data, list) else data.get("props", [])
                    for item in items:
                        edge = float(item.get("edge", 0.0) or 0.0)
                        if edge >= min_edge and item.get("estado", "PENDIENTE") == "PENDIENTE":
                            picks_validos.append({
                                "deporte": "NFL",
                                "liga": "NFL Player Props",
                                "partido": item.get("partido", item.get("juego", "")),
                                "fecha": "Semana Activa",
                                "hora": "",
                                "mercado": item.get("mercado", "Player Prop"),
                                "seleccion": item.get("jugador", "") + " - " + item.get("prop", item.get("seleccion", "")),
                                "cuota": str(item.get("cuota", "")),
                                "cuota_dec": float(item.get("cuota_dec") or 1.91),
                                "probabilidad": float(item.get("probabilidad") or 0.5),
                                "edge": edge,
                                "ev": edge,
                                "confianza": item.get("confianza", "ALTA"),
                                "detalle": item.get("detalle", ""),
                            })
                except Exception:
                    pass

    picks_validos.sort(key=lambda x: x["edge"], reverse=True)
    return picks_validos[:max_picks]


def formatear_mensaje_reporte(
    picks_futbol: List[Dict[str, Any]],
    picks_nba: List[Dict[str, Any]],
    picks_nfl: List[Dict[str, Any]],
) -> str:
    """Construye un mensaje enriquecido en HTML para Telegram y Discord."""
    ahora_cdmx = datetime.now(ZONA_CDMX).strftime("%d/%m/%Y %H:%M")
    total_picks = len(picks_futbol) + len(picks_nba) + len(picks_nfl)

    if total_picks == 0:
        return (
            f"ℹ️ <b>INFORME DIARIO DE VALOR ESPERADO (+EV)</b>\n"
            f"📅 <i>{ahora_cdmx} CDMX</i>\n\n"
            f"No se detectaron selecciones que superen el umbral estricto de ventaja matemática (+4.5% Edge) para esta jornada.\n\n"
            f"🛡️ <i>La disciplina y no forzar apuestas sin ventaja es la clave para la rentabilidad a largo plazo.</i>"
        )

    lineas = [
        f"🎯 <b>ALERTAS DE ALTO VALOR ESPERADO (+EV)</b>",
        f"📅 <i>{ahora_cdmx} CDMX</i> · <b>{total_picks} oportunidad(es) detectada(s)</b>",
        f"━━━━━━━━━━━━━━━━━━━━",
    ]

    # --- SECCIÓN FÚTBOL ---
    if picks_futbol:
        lineas.append(f"\n⚽ <b>FÚTBOL MUNDIAL &amp; LIGA MX ({len(picks_futbol)})</b>")
        for p in picks_futbol:
            badge = "🔥" if p["confianza"] == "ALTA" else "⚡"
            cuota_str = f"<b>{p['cuota']}</b>" if p['cuota'] else f"<b>{p['cuota_dec']:.2f}</b>"
            hora_str = f" · ⏰ {p['hora']}" if p.get('hora') and p['hora'] != 'TBD' else ""
            lineas.append(
                f"\n🏆 <i>{p['liga']}</i>{hora_str}\n"
                f"⚔️ {p['partido']}\n"
                f"👉 <b>Selección:</b> <code>{p['seleccion']}</code> ({cuota_str})\n"
                f"📊 Prob IA: <b>{p['probabilidad']*100:.1f}%</b> | Edge: <b>+{p['edge']*100:.1f}%</b>\n"
                f"💡 Confianza: {badge} {p['confianza']} · <i>Recomendación: 1.0 u</i>"
            )

    # --- SECCIÓN NBA ---
    if picks_nba:
        lineas.append(f"\n🏀 <b>NBA ({len(picks_nba)})</b>")
        for p in picks_nba:
            badge = "🔥" if p["confianza"] == "ALTA" else "⚡"
            cuota_str = f"<b>{p['cuota']}</b>" if p['cuota'] else f"<b>{p['cuota_dec']:.2f}</b>"
            hora_str = f" · ⏰ {p['hora']}" if p.get('hora') and p['hora'] != 'TBD' else ""
            lineas.append(
                f"\n⚔️ {p['partido']}{hora_str}\n"
                f"👉 <b>Selección:</b> <code>{p['seleccion']}</code> ({cuota_str})\n"
                f"📊 Prob IA: <b>{p['probabilidad']*100:.1f}%</b> | Edge: <b>+{p['edge']*100:.1f}%</b>\n"
                f"💡 Confianza: {badge} {p['confianza']} · <i>Recomendación: 1.0 u</i>"
            )

    # --- SECCIÓN NFL ---
    if picks_nfl:
        lineas.append(f"\n🏈 <b>NFL ({len(picks_nfl)})</b>")
        for p in picks_nfl:
            badge = "🔥" if p["confianza"] == "ALTA" else "⚡"
            cuota_str = f"<b>{p['cuota']}</b>" if p['cuota'] else f"<b>{p['cuota_dec']:.2f}</b>"
            lineas.append(
                f"\n⚔️ {p['partido']}\n"
                f"👉 <b>Prop / Selección:</b> <code>{p['seleccion']}</code> ({cuota_str})\n"
                f"📊 Prob IA: <b>{p['probabilidad']*100:.1f}%</b> | Edge: <b>+{p['edge']*100:.1f}%</b>\n"
                f"💡 Confianza: {badge} {p['confianza']} · <i>Recomendación: 1.0 u</i>"
            )

    lineas.append(f"\n━━━━━━━━━━━━━━━━━━━━")
    lineas.append(f"🛡️ <i>Gestión de Bankroll: Apuesta con disciplina respetando unidades fijas.</i>")
    return "\n".join(lineas)


def ejecutar_notificador(min_edge: float = 0.045, max_picks: int = 5, dry_run: bool = False):
    """Recolecta picks de alto valor y envía el mensaje a Telegram y Discord."""
    logger.info("🔍 Recolectando picks de alto valor en Fútbol, NBA y NFL...")
    picks_fut = obtener_picks_alto_ev_futbol(min_edge=min_edge, max_picks=max_picks)
    picks_nba = obtener_picks_alto_ev_nba(min_edge=0.040, max_picks=max_picks)
    picks_nfl = obtener_picks_alto_ev_nfl(min_edge=min_edge, max_picks=max_picks)

    logger.info(f"Picks detectados: Fútbol ({len(picks_fut)}), NBA ({len(picks_nba)}), NFL ({len(picks_nfl)})")

    mensaje = formatear_mensaje_reporte(picks_fut, picks_nba, picks_nfl)

    if dry_run:
        print("\n=== VISTA PREVIA DEL MENSAJE (DRY RUN) ===")
        print(mensaje)
        print("==========================================\n")
        return {"ok": True, "dry_run": True, "total_picks": len(picks_fut) + len(picks_nba) + len(picks_nfl)}

    tg_token, tg_chat = get_telegram_config()
    dc_url = get_discord_config()

    if not tg_token and not dc_url:
        logger.warning(
            "⚠️ No hay credenciales configuradas para Telegram (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) "
            "ni Discord (DISCORD_WEBHOOK_URL)."
        )
        print("\n=== VISTA PREVIA DEL MENSAJE ===")
        print(mensaje)
        print("===============================\n")
        return {
            "ok": False,
            "error": "Credenciales no configuradas",
            "mensaje_generado": True,
            "total_picks": len(picks_fut) + len(picks_nba) + len(picks_nfl)
        }

    resultados = enviar_alerta_multicanal(mensaje)
    logger.info(f"Envío completado: {resultados}")
    return {"ok": True, "resultados": resultados, "total_picks": len(picks_fut) + len(picks_nba) + len(picks_nfl)}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Notificador de Picks de Alto Valor (+EV)")
    parser.add_argument("--min-edge", type=float, default=0.045, help="Edge mínimo requerido (ej: 0.045)")
    parser.add_argument("--max-picks", type=int, default=5, help="Máximo de picks por deporte")
    parser.add_argument("--dry-run", action="store_true", help="Solo generar y mostrar en consola sin enviar")
    args = parser.parse_args()

    ejecutar_notificador(min_edge=args.min_edge, max_picks=args.max_picks, dry_run=args.dry_run)

