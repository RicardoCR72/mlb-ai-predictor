"""Módulo central de alertas y notificaciones a Telegram."""
from __future__ import annotations

import os
import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_telegram_config() -> tuple[Optional[str], Optional[str]]:
    """Obtiene el bot token y chat ID de Telegram desde Streamlit secrets o variables de entorno."""
    token = None
    chat_id = None
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            token = st.secrets.get("TELEGRAM_BOT_TOKEN")
            chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    except Exception:
        pass

    if not token:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    return token, chat_id


def enviar_telegram(mensaje: str, parse_mode: str = "HTML") -> bool:
    """Envía un mensaje a Telegram. Retorna True si se envió correctamente."""
    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        print("⚠️ Telegram no configurado (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except (HTTPError, URLError) as err:
        print(f"❌ Error al enviar mensaje a Telegram: {err}")
        return False


def notificar_fallo(nombre_tarea: str, detalle: str = "") -> bool:
    """Envía una alerta de alta prioridad a Telegram si un bot o workflow falla."""
    mensaje = (
        f"🚨 <b>ALERTA DE ERROR EN AUTOMATIZACIÓN</b> 🚨\n\n"
        f"<b>Proceso:</b> <code>{nombre_tarea}</code>\n"
        f"<b>Estado:</b> ❌ Falló la ejecución\n"
    )
    if detalle:
        mensaje += f"<b>Detalle:</b>\n<pre>{detalle[:1000]}</pre>\n"
    mensaje += "\n<i>Revisa los logs en GitHub Actions para más información.</i>"
    return enviar_telegram(mensaje)


def notificar_oportunidad_valor(
    deporte: str,
    partido: str,
    seleccion: str,
    prob_ia: float,
    cuota: float,
    edge: float,
    stake_kelly: float,
) -> bool:
    """Envía una señal de oportunidad con Valor Esperado Positivo (+EV)."""
    mensaje = (
        f"🎯 <b>OPORTUNIDAD DE VALOR (+EV) DETECTADA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>Deporte:</b> {deporte}\n"
        f"⚔️ <b>Partido:</b> {partido}\n"
        f"👉 <b>Selección:</b> <code>{seleccion}</code>\n"
        f"📊 <b>Probabilidad IA:</b> {prob_ia * 100:.1f}%\n"
        f"💰 <b>Cuota Mercado:</b> {cuota:.2f}\n"
        f"📈 <b>Edge:</b> +{edge * 100:.1f}%\n"
        f"💡 <b>Kelly sugerido:</b> {stake_kelly:.2f} unidades\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    return enviar_telegram(mensaje)
