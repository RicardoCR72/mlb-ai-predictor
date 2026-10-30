"""Módulo central de alertas y notificaciones a Telegram y Discord."""
from __future__ import annotations

import json
import os
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("core.alerts")


def get_telegram_config() -> Tuple[Optional[str], Optional[str]]:
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


def get_discord_config() -> Optional[str]:
    """Obtiene el webhook URL de Discord desde Streamlit secrets o variables de entorno."""
    url = None
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            url = st.secrets.get("DISCORD_WEBHOOK_URL")
    except Exception:
        pass

    if not url:
        url = os.environ.get("DISCORD_WEBHOOK_URL")

    return url


def enviar_telegram(mensaje: str, parse_mode: str = "HTML") -> bool:
    """Envía un mensaje a Telegram (divide en fragmentos si excede 4000 caracteres)."""
    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        logger.warning("Telegram no configurado (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ausentes).")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram límite de 4096 caracteres por mensaje
    max_len = 3900
    trozos = [mensaje[i:i + max_len] for i in range(0, len(mensaje), max_len)]
    exito = True

    for trozo in trozos:
        payload = json.dumps({
            "chat_id": chat_id,
            "text": trozo,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }).encode("utf-8")

        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    exito = False
        except HTTPError as err:
            try:
                body = err.read().decode("utf-8")
                err_data = json.loads(body)
                desc = err_data.get("description", str(err))
            except Exception:
                desc = str(err)
            logger.error(f"Error Telegram: {desc}")
            exito = False
        except (URLError, Exception) as err:
            logger.error(f"Error de conexión con Telegram: {err}")
            exito = False

    return exito


def enviar_discord(mensaje: str) -> bool:
    """Envía una notificación a Discord vía Incoming Webhook."""
    webhook_url = get_discord_config()
    if not webhook_url:
        return False

    max_len = 1950
    trozos = [mensaje[i:i + max_len] for i in range(0, len(mensaje), max_len)]
    exito = True

    for trozo in trozos:
        payload = json.dumps({"content": trozo}).encode("utf-8")
        req = Request(webhook_url, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": "Antigravity-Sports-Bot/2.0"
        })
        try:
            with urlopen(req, timeout=15) as resp:
                if resp.status not in (200, 204):
                    exito = False
        except Exception as err:
            logger.error(f"Error al enviar mensaje a Discord: {err}")
            exito = False

    return exito


def enviar_alerta_multicanal(mensaje: str, parse_mode: str = "HTML") -> Dict[str, bool]:
    """Difunde el mensaje a todos los canales configurados (Telegram y Discord)."""
    res_tg = enviar_telegram(mensaje, parse_mode=parse_mode)
    res_dc = enviar_discord(mensaje)
    return {"telegram": res_tg, "discord": res_dc}


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
    enviar_alerta_multicanal(mensaje)
    return True


def notificar_oportunidad_valor(
    deporte: str,
    partido: str,
    seleccion: str,
    prob_ia: float,
    cuota: float,
    edge: float,
    stake_kelly: float,
) -> bool:
    """Envía una señal individual de oportunidad con Valor Esperado Positivo (+EV)."""
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
    enviar_alerta_multicanal(mensaje)
    return True
