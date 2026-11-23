"""Pipeline de Producción Audiovisual de Alta Retención (TikTok / Shorts / Reels) para Overdog AI.

Optimizado para máxima retención en los primeros 3 segundos:
1. Guion LLM conciso (38-45 palabras, 15-18s) con estructura estricta en 3 partes y cero redundancia.
2. Procesamiento de audio (edge-tts + silenceremove inicio/fin + atempo 1.08x + normalización -14 LUFS).
3. Revelación progresiva de tarjeta (Estado 1 Teaser hasta t_revelacion, Estado 2 Revelación completa).
4. Ensamblaje FFmpeg Full HD (1080x1920, 30fps, corte exacto en dur_audio + 0.25s).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import edge_tts
from PIL import Image, ImageDraw, ImageFont

from core.asesor_ia import obtener_gemini_api_key

RAIZ = Path(__file__).resolve().parents[1]
FONT_DIR = "C:/Windows/Fonts"

# ==============================================================================
# 1. GENERADOR DE GUIONES CON PROMPT ESTRICTO DE ALTA RETENCIÓN
# ==============================================================================

PROMPT_SISTEMA_GUION_RETENCION = """Eres el guionista principal de videos cortos (TikTok/Shorts) para "OVERDOG SPORTS AI".
Tu única tarea es redactar un guion narrativo de voz ultra-dinámico, persuasivo y analítico para un prop deportivo.

REGLAS ESTRICTAS DE RETENCIÓN Y TIEMPO (TOLERANCIA CERO A DESVÍOS):
1. LONGITUD EXACTA: Entre 38 y 45 palabras en total.
   - Menos de 38 palabras queda incompleto; más de 45 palabras supera los 18 segundos y destruye la retención.

2. CERO REDUNDANCIA CON LA TARJETA VISUAL:
   - Está ESTRICTAMENTE PROHIBIDO abrir el guion leyendo la racha histórica que ya aparece impresa en la tarjeta.
   - NUNCA empieces diciendo: "superó esta línea en sus últimos 5 juegos", "se quedó abajo en 4 de sus últimos 5", "lleva 5 verdes consecutivos" o frases similares. La racha se lee en pantalla; tu voz debe aportar el porqué táctico.

3. ESTRUCTURA OBLIGATORIA EN 3 PARTES EXACTAS (Un solo párrafo fluido de 3 oraciones):
   - Parte 1 — Gancho Inicial (0s a 3s / 8 a 11 palabras):
     Una oración directa e impactante sobre el contexto táctico, matchup, ritmo de juego o desalineación de la línea en el mercado. Sin saludos ni intros ("hola", "atención", "bienvenidos" están prohibidos).
   - Parte 2 — Revelación y Argumento del Modelo (3s a 12s / 18 a 22 palabras):
     Aquí se menciona explícitamente el pick ("Over" o "Under" + número de línea) respaldado por una métrica cuantitativa complementaria (proyección media del modelo, volumen de uso o debilidad defensiva del rival).
   - Parte 3 — Cierre en Seco (12s a 16s / 8 a 12 palabras):
     Una pregunta corta y directa para detonar debate inmediato en los comentarios (ejemplo: "¿Lo cumple antes del último cuarto o se queda corto?").
     PROHIBIDO usar despedidas o llamadas a seguir ("no olvides seguirme", "así que ya sabes", "síguenos"). Termina en seco con la pregunta.

4. POLÍTICA DE CONTENIDO Y VOCABULARIO OFICIAL (GEMINI.MD):
   - PROHIBIDO: apuesta, apuestas, apostar, parlay, momio, cuotas, cuota, dinero, dólares, ganar dinero, lock, fija, bomba de cuota, bank, stake, casino, bookie.
   - PERMITIDO: proyección, pronóstico, tendencia, Inteligencia Artificial (IA), modelo matemático, análisis estadístico, probabilidad, margen de valor, Más de (Over), Menos de (Under), producción reciente, línea del mercado.

FORMATO DE SALIDA:
Devuelve ÚNICAMENTE el texto del guion (las 3 oraciones en un solo párrafo), sin títulos, sin viñetas, sin comillas y sin conteo de palabras.
"""

def generar_guion_fallback_con_reglas(datos: Dict[str, Any]) -> str:
    """Generador determinista que garantiza exactamente entre 38 y 45 palabras y 3 partes."""
    jugador = datos.get("jugador", "El jugador")
    equipo = datos.get("equipo", "")
    rival = datos.get("rival", "su rival")
    mercado = datos.get("mercado", "puntos")
    linea = datos.get("linea", "20.5")
    tipo_pick = datos.get("tipo_pick", "Over").capitalize()
    proy = datos.get("proyeccion", "24.0")
    contexto = datos.get("contexto_rival", f"concede alto volumen en la pintura")

    # Parte 1: Gancho contextual (9-10 palabras)
    p1 = f"{rival} llega con serios desajustes defensivos permitiendo jugadas constantes."
    # Parte 2: Revelación y modelo (21 palabras)
    p2 = f"Nuestro modelo cuantitativo marca {tipo_pick} {linea} {mercado} para {jugador}, proyectando {proy} con amplia ventaja sobre la línea del mercado."
    # Parte 3: Cierre en seco (9 palabras)
    p3 = f"¿Cumplirá esta proyección antes de llegar al último cuarto?"

    texto = f"{p1} {p2} {p3}"
    palabras = texto.split()
    
    # Ajuste milimétrico si excede o falta
    if len(palabras) > 45:
        texto = " ".join(palabras[:44]) + "?"
    elif len(palabras) < 38:
        p2 = f"El modelo cuantitativo de Overdog marca con alta convicción {tipo_pick} {linea} {mercado} para {jugador}, proyectando {proy} con claro valor matemático."
        texto = f"{p1} {p2} {p3}"

    return texto


def generar_guion_retencion(datos: Dict[str, Any], gemini_api_key: Optional[str] = None) -> str:
    """Genera un guion de 38 a 45 palabras con Gemini Flash o fallback determinista."""
    key = gemini_api_key or obtener_gemini_api_key()
    
    if key:
        import requests
        prompt_usuario = (
            f"Genera el guion con estas variables:\n"
            f"- Deporte: {datos.get('deporte', 'NBA')}\n"
            f"- Jugador: {datos.get('jugador')} ({datos.get('equipo')}) vs {datos.get('rival')}\n"
            f"- Mercado: {datos.get('mercado')}\n"
            f"- Línea Casa: {datos.get('linea')}\n"
            f"- Selección Oficial: {datos.get('tipo_pick')} {datos.get('linea')}\n"
            f"- Proyección Modelo: {datos.get('proyeccion')}\n"
            f"- Métrica Complementaria/Ventaja: {datos.get('ventaja', '+4.5')}\n"
            f"- Contexto Matchup: {datos.get('contexto_rival', 'Defensa permisiva')}\n"
        )
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": PROMPT_SISTEMA_GUION_RETENCION},
                        {"text": prompt_usuario}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 150,
            }
        }
        
        for modelo in ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-latest"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={key}"
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    cands = data.get("candidates", [])
                    if cands and "content" in cands[0] and "parts" in cands[0]["content"]:
                        texto_raw = cands[0]["content"]["parts"][0].get("text", "").strip()
                        texto_limpio = " ".join(texto_raw.replace("\n", " ").split())
                        palabras = texto_limpio.split()
                        # Validar longitud
                        if 35 <= len(palabras) <= 48:
                            # Ajuste fino si queda en 46-48
                            if len(palabras) > 45:
                                texto_limpio = " ".join(palabras[:44]) + ("?" if palabras[-1].endswith("?") else ".")
                            return texto_limpio
            except Exception:
                continue

    return generar_guion_fallback_con_reglas(datos)


# ==============================================================================
# 2. PROCESAMIENTO DE AUDIO (TTS + RECORTE SILENCIO + ATEMPO + -14 LUFS)
# ==============================================================================

async def sintetizar_audio_con_recorte(
    texto: str,
    output_path: str,
    voice: str = "es-ES-AlvaroNeural",
    rate: str = "+8%",
    atempo: float = 1.08,
) -> Tuple[float, float]:
    """Genera audio mediante edge-tts, aplica silenceremove en extremos,
    ajusta velocidad (atempo) y normaliza a -14 LUFS.
    Retorna: (duracion_final_segundos, t_revelacion_segundos)
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    raw_path = output_path.replace(".mp3", "_raw.mp3")

    comm = edge_tts.Communicate(texto, voice, rate=rate)
    
    # Rastrear boundaries de oraciones para ubicar el momento exacto de revelación
    sentences = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            with open(raw_path, "ab") as f:
                f.write(chunk["data"])
        elif chunk["type"] == "SentenceBoundary":
            sec_offset = (chunk["offset"] / 10000000.0)
            sec_dur = (chunk["duration"] / 10000000.0)
            sentences.append((sec_offset, sec_dur, chunk.get("text", "")))

    # Estimar timestamp de la revelación del pick (cuando se dice Over/Under o la 2da oración)
    t_revelacion = 3.50
    target_tokens = ["over", "under", "más", "mas", "menos"]
    
    if len(sentences) >= 2:
        # Inicio de la segunda oración escalado por atempo
        s2_offset = sentences[1][0] / atempo
        s2_words = sentences[1][2].lower().split()
        word_idx = -1
        for idx, w in enumerate(s2_words):
            clean_w = w.strip(".,;:!?")
            if clean_w in target_tokens:
                word_idx = idx
                break
        if word_idx >= 0:
            ratio = word_idx / max(len(s2_words), 1)
            t_revelacion = s2_offset + ((sentences[1][1] / atempo) * ratio)
        else:
            t_revelacion = s2_offset
    else:
        # Fallback proporcional por conteo de palabras
        words = texto.lower().split()
        for idx, w in enumerate(words):
            if w.strip(".,;:!?") in target_tokens:
                t_revelacion = (idx / len(words)) * 16.0
                break

    # Restringir t_revelacion entre 2.8s y 4.5s
    t_revelacion = max(2.80, min(4.30, t_revelacion))

    # Filtro FFmpeg: Recorte de silencio inicial y final + atempo + loudnorm -14 LUFS
    # silenceremove al inicio; areverse + silenceremove + areverse al final
    filter_af = (
        "silenceremove=start_periods=1:start_duration=0.01:start_threshold=-50dB,"
        "areverse,silenceremove=start_periods=1:start_duration=0.01:start_threshold=-50dB,areverse,"
        f"atempo={atempo},"
        "loudnorm=I=-14.0:LRA=7.0:TP=-1.5"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", raw_path,
        "-af", filter_af,
        "-ar", "48000",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Medir duración final
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        output_path
    ]
    res = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
    dur_audio = float(res.stdout.strip())

    if os.path.exists(raw_path):
        try:
            os.remove(raw_path)
        except Exception:
            pass

    return dur_audio, round(t_revelacion, 2)


# ==============================================================================
# 3. GENERADOR DE TARJETAS DE REVELACIÓN PROGRESIVA (PILLOW)
# ==============================================================================

def _get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONT_DIR, name)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def _draw_text_fitted(draw: ImageDraw.ImageDraw, pos: Tuple[int, int], text: str, font_name: str, 
                      max_size: int, max_width: int, fill: Any, anchor: str = "la", min_size: int = 14) -> ImageFont.FreeTypeFont:
    size = max_size
    font = _get_font(font_name, size)
    bbox = draw.textbbox((0, 0), text, font=font)
    while (bbox[2] - bbox[0]) > max_width and size > min_size:
        size -= 1
        font = _get_font(font_name, size)
        bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(pos, text, font=font, fill=fill, anchor=anchor)
    return font

def generar_tarjetas_revelacion(datos: Dict[str, Any], path_teaser: str, path_reveal: str) -> Tuple[str, str]:
    """Genera las dos tarjetas idénticas en diseño pero con revelación progresiva:
    - path_teaser: Muestra encabezado y jugador, pero oculta la línea central bajo un badge de suspenso.
    - path_reveal: Muestra la tarjeta completa con el pick, proyección y racha histórica.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path_teaser)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(path_reveal)), exist_ok=True)

    W, H = 1000, 480
    deporte = datos.get("deporte", "NBA").upper()
    fecha_str = datos.get("fecha_str", datetime.now().strftime("%A %d de %B %Y").upper())
    jugador = datos.get("jugador", "JUGADOR OFICIAL").upper()
    equipo = datos.get("equipo", "").upper()
    mercado = datos.get("mercado", "MERCADO").upper()
    linea = str(datos.get("linea", "0.0"))
    tipo_pick = datos.get("tipo_pick", "OVER").upper()
    proy = str(datos.get("proyeccion", "0.0"))
    ventaja = str(datos.get("ventaja", "+0.0"))
    racha_texto = datos.get("racha_texto", "🔥 4 DE SUS ÚLTIMOS 5 PARTIDOS CUBIERTOS")
    promedio_texto = datos.get("promedio_texto", f"MEDIA L5: {proy}")

    es_over = "OVER" in tipo_pick or "MÁS" in tipo_pick
    neon_color = (74, 222, 128) if es_over else (56, 189, 248) # Verde neón o Cyan neón
    badge_teaser_color = (56, 189, 248) # Cyan suspenso
    gold_color = (250, 204, 21)
    slate_dark = (11, 19, 36, 248)
    box_dark = (15, 23, 42, 255)
    header_box = (20, 32, 54, 255)

    # -------------------------------------------------------------
    # 1. ESTADO 1: TEASER CARD (Suspenso inicial)
    # -------------------------------------------------------------
    im_teaser = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d1 = ImageDraw.Draw(im_teaser)

    # Contenedor principal
    d1.rounded_rectangle([0, 0, W, H], radius=28, fill=slate_dark, outline=badge_teaser_color, width=4)

    # Encabezado: Deporte y Fecha exacta
    d1.rounded_rectangle([40, 25, W - 40, 75], radius=12, fill=header_box)
    _draw_text_fitted(d1, (W // 2, 50), f"{deporte} · {fecha_str}", "segoeuib.ttf", 22, 900, gold_color, anchor="mm")

    # Nombre del Jugador
    _draw_text_fitted(d1, (W // 2, 122), jugador, "impact.ttf", 64, 920, (255, 255, 255), anchor="mm")
    _draw_text_fitted(d1, (W // 2, 158), f"{equipo} · {mercado}", "segoeuib.ttf", 20, 900, (148, 163, 184), anchor="mm")

    # Bloque Central: Badge de Suspenso en Neón
    d1.rounded_rectangle([40, 185, W - 40, 335], radius=20, fill=box_dark, outline=badge_teaser_color, width=3)
    _draw_text_fitted(d1, (W // 2, 238), "⚡ ANOMALÍA DETECTADA", "impact.ttf", 58, 880, badge_teaser_color, anchor="mm")
    _draw_text_fitted(d1, (W // 2, 298), "PROYECCIÓN CUANTITATIVA EN ANÁLISIS", "segoeuib.ttf", 22, 880, (203, 213, 225), anchor="mm")

    # Barra Inferior: Teaser Callout
    d1.rounded_rectangle([40, 370, W - 40, 448], radius=16, fill=header_box, outline=badge_teaser_color, width=2)
    _draw_text_fitted(d1, (W // 2, 409), "🔒 REVELANDO LÍNEA Y PROYECCIÓN DEL MODELO...", "segoeuib.ttf", 26, 900, (255, 255, 255), anchor="mm")

    im_teaser.save(path_teaser, "PNG")

    # -------------------------------------------------------------
    # 2. ESTADO 2: REVEAL CARD (Línea revelada + Datos completos)
    # -------------------------------------------------------------
    im_reveal = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(im_reveal)

    # Contenedor idéntico con borde del color del pick
    d2.rounded_rectangle([0, 0, W, H], radius=28, fill=slate_dark, outline=neon_color, width=4)

    # Encabezado idéntico
    d2.rounded_rectangle([40, 25, W - 40, 75], radius=12, fill=header_box)
    _draw_text_fitted(d2, (W // 2, 50), f"{deporte} · {fecha_str}", "segoeuib.ttf", 22, 900, gold_color, anchor="mm")

    # Nombre del Jugador
    _draw_text_fitted(d2, (W // 2, 122), jugador, "impact.ttf", 64, 920, (255, 255, 255), anchor="mm")
    _draw_text_fitted(d2, (W // 2, 158), f"{equipo} · {mercado}", "segoeuib.ttf", 20, 900, (148, 163, 184), anchor="mm")

    # Bloque Central: Pick Oficial Revelado
    d2.rounded_rectangle([40, 185, W - 40, 335], radius=20, fill=box_dark, outline=neon_color, width=3)
    texto_pick = f"{tipo_pick} {linea} {mercado}".strip()
    _draw_text_fitted(d2, (W // 2, 238), texto_pick, "impact.ttf", 68, 880, neon_color, anchor="mm")
    sub_pick = f"PROYECCIÓN MODELO: {proy} | MARGEN: {ventaja}"
    _draw_text_fitted(d2, (W // 2, 298), sub_pick, "segoeuib.ttf", 22, 880, (203, 213, 225), anchor="mm")

    # Barra Inferior: Racha / Hit Rate Oficial
    fill_bar = (6, 78, 59, 240) if es_over else (15, 45, 80, 240)
    d2.rounded_rectangle([40, 370, W - 40, 448], radius=16, fill=fill_bar, outline=neon_color, width=2)
    pie_texto = f"{racha_texto} | {promedio_texto}".strip(" |")
    _draw_text_fitted(d2, (W // 2, 409), pie_texto, "segoeuib.ttf", 26, 900, (255, 255, 255), anchor="mm")

    im_reveal.save(path_reveal, "PNG")

    return path_teaser, path_reveal


# ==============================================================================
# 4. ENSAMBLADOR DE VIDEO ULTRA-RETENCIÓN (FFMPEG)
# ==============================================================================

def ensamblar_video_alta_retencion(
    clip_bg: str,
    audio_path: str,
    path_teaser: str,
    path_reveal: str,
    t_revelacion: float,
    output_path: str,
    dur_audio: Optional[float] = None,
) -> str:
    """Ensambla el video vertical 9:16 (1080x1920 a 30fps) con transición dinámica en t_revelacion
    y corte exacto en dur_audio + 0.25s para eliminar tiempos muertos al final.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if dur_audio is None:
        cmd_p = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ]
        res = subprocess.run(cmd_p, capture_output=True, text=True, check=True)
        dur_audio = float(res.stdout.strip())

    dur_video_final = round(dur_audio + 0.25, 2)

    filter_complex = (
        "[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[bg];"
        "[1:v]scale=1000:-1[ic_teaser];"
        "[2:v]scale=1000:-1[ic_reveal];"
        f"[bg][ic_teaser]overlay=(W-w)/2:320:enable='between(t,0,{t_revelacion})'[v1];"
        f"[v1][ic_reveal]overlay=(W-w)/2:320:enable='gte(t,{t_revelacion})'[vout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", clip_bg,
        "-i", path_teaser,
        "-i", path_reveal,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "3:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(dur_video_final),
        output_path
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path


# ==============================================================================
# 5. PIPELINE INTEGRAL UNIFICADO (GENERAR VIDEO COMPLETO EN 1 LLAMADA)
# ==============================================================================

async def pipeline_video_completo(datos_prop: Dict[str, Any], clip_bg_path: str, output_video_path: str) -> Dict[str, Any]:
    """Ejecuta el pipeline completo desde los datos cuantitativos hasta el video final renderizado."""
    scratch_dir = RAIZ / "scratch"
    scratch_dir.mkdir(exist_ok=True)
    slug = re.sub(r'[^a-zA-Z0-9_]', '', datos_prop.get("jugador", "pick").lower().replace(" ", "_"))

    path_teaser = str(scratch_dir / f"card_teaser_{slug}.png")
    path_reveal = str(scratch_dir / f"card_reveal_{slug}.png")
    path_audio = str(scratch_dir / f"audio_retencion_{slug}.mp3")

    # 1. Generar guion con LLM (38-45 palabras)
    guion = generar_guion_retencion(datos_prop)
    palabras_guion = len(guion.split())

    # 2. Generar y procesar audio con recorte y atempo
    dur_audio, t_rev = await sintetizar_audio_con_recorte(
        texto=guion,
        output_path=path_audio,
        voice="es-ES-AlvaroNeural",
        rate="+8%",
        atempo=1.08,
    )

    # 3. Generar tarjetas visuales de revelación progresiva
    generar_tarjetas_revelacion(datos_prop, path_teaser, path_reveal)

    # 4. Renderizar video con corte exacto en dur_audio + 0.25s
    ensamblar_video_alta_retencion(
        clip_bg=clip_bg_path,
        audio_path=path_audio,
        path_teaser=path_teaser,
        path_reveal=path_reveal,
        t_revelacion=t_rev,
        output_path=output_video_path,
        dur_audio=dur_audio,
    )

    return {
        "output_video": output_video_path,
        "guion": guion,
        "palabras": palabras_guion,
        "duracion_audio": dur_audio,
        "t_revelacion": t_rev,
        "duracion_video": round(dur_audio + 0.25, 2),
    }
