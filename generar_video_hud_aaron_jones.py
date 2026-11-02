import os
import asyncio
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# 1. Generate Voiceover Audio with edge-tts
TEXT_AUDIO = """
¡Atención a esta anomalía detectada por nuestros algoritmos en la NFL!
Para el partido de Minnesota, el mercado abrió la línea de Aaron Jones en apenas veintiocho punto cinco yardas terrestres.
Nuestros modelos cuantitativos proyectan más de sesenta y seis yardas para este juego, dándonos una ventaja matemática superior al veintidós por ciento en el Over.
Toda la analítica completa y las proyecciones están gratis en nuestro canal de Telegram de la biografía.
""".strip()

AUDIO_PATH = "scratch/voice_aaron_jones.mp3"

async def crear_audio():
    comunicador = edge_tts.Communicate(
        text=TEXT_AUDIO,
        voice="es-MX-JorgeNeural",
        rate="+5%",
        pitch="+0Hz"
    )
    await comunicador.save(AUDIO_PATH)
    print("Audio generado en:", AUDIO_PATH)

asyncio.run(crear_audio())

# 2. Design the 1080x1920 PNG Overlay with HUD elements
W = 1080
H = 1920

overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

font_dir = "C:/Windows/Fonts"
f_hook_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_hook_main = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 46)
f_pill = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
f_player = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 44)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 22)
f_stat_lbl = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 18)
f_stat_val = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 40)
f_arrow = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 36)
f_bar = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_foot = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)

# --- TOP HOOK BANNER (y: 160 to 330) ---
hook_box = [60, 160, W - 60, 330]
draw.rounded_rectangle(hook_box, radius=24, fill=(10, 15, 26, 230), outline=(255, 215, 0, 220), width=3)

# Mini badge inside top box
draw.rounded_rectangle([90, 185, 430, 225], radius=15, fill=(255, 215, 0, 255))
draw.text((115, 192), "ERROR DE LÍNEA EN NFL", font=f_hook_tag, fill=(10, 15, 26, 255))

draw.text((90, 245), "AARON JONES · DESCUENTO +EV", font=f_hook_main, fill=(255, 255, 255, 255))

# --- BOTTOM FLOATING HUD CARD (y: 1220 to 1690) ---
card_box = [60, 1200, W - 60, 1680]
draw.rounded_rectangle(card_box, radius=28, fill=(13, 20, 34, 235), outline=(0, 255, 163, 220), width=3)

# Top badge
draw.rounded_rectangle([90, 1230, 480, 1275], radius=18, fill=(0, 255, 163, 255))
draw.text((110, 1238), "ANOMALÍA (+EV: +22.6%)", font=f_pill, fill=(10, 15, 26, 255))

# Market right
draw.text((W - 90 - draw.textlength("YARDAS TERRESTRES", font=f_sub), 1242), "YARDAS TERRESTRES", font=f_sub, fill=(148, 163, 184, 255))

# Player Name & Team
draw.text((90, 1300), "AARON JONES", font=f_player, fill=(255, 255, 255, 255))
draw.text((90, 1360), "RB · MINNESOTA VIKINGS · SEMANA 8", font=f_sub, fill=(148, 163, 184, 255))

# Stats Box comparison
sbox = [90, 1410, W - 90, 1530]
draw.rounded_rectangle(sbox, radius=18, fill=(9, 14, 24, 240), outline=(32, 45, 70, 255), width=2)

draw.text((120, 1425), "LÍNEA CASA", font=f_stat_lbl, fill=(148, 163, 184, 255))
draw.text((120, 1460), "28.5", font=f_stat_val, fill=(255, 255, 255, 255))

draw.text((370, 1455), "->", font=f_arrow, fill=(0, 255, 163, 255))

draw.text((490, 1425), "PROYECCIÓN OVERDOG IA", font=f_stat_lbl, fill=(0, 255, 163, 255))
draw.text((490, 1460), "66.5 YARDS", font=f_stat_val, fill=(0, 255, 163, 255))

# Pick and Cuota Bar
pbar = [90, 1555, W - 90, 1635]
draw.rounded_rectangle(pbar, radius=16, fill=(24, 34, 53, 255))

draw.text((120, 1575), "PICK: OVER 28.5", font=f_bar, fill=(255, 255, 255, 255))
draw.text((500, 1575), "MOMIO: -113 (1.88)", font=f_bar, fill=(255, 215, 0, 255))
draw.text((800, 1575), "PROB: 65%", font=f_bar, fill=(0, 255, 163, 255))

# Bottom Watermark / CTA
draw.rounded_rectangle([250, 1720, W - 250, 1780], radius=25, fill=(0, 136, 204, 240))
draw.text((290, 1735), "📲 TELEGRAM GRATIS: @OVERDOGAI", font=f_foot, fill=(255, 255, 255, 255))

OVERLAY_PATH = "scratch/hud_overlay_aaron_jones.png"
overlay.save(OVERLAY_PATH, "PNG")
print("Overlay guardado en:", OVERLAY_PATH)

# 3. Render Final Video with FFmpeg
# Background: Blurred fill + Center crisp 16:9 video + PNG overlay + Voiceover audio
INPUT_CLIP = "scratch/aaron_jones_clip.mp4"
OUTPUT_VIDEO = "assets/video_prueba_aaron_jones_hud.mp4"

# FFmpeg complex filter:
# [0:v] split [bg][fg];
# [bg] scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5 [blurred_bg];
# [fg] scale=1080:608 [sharp_center];
# [blurred_bg][sharp_center] overlay=0:(1920-608)/2 [comp1];
# [comp1][1:v] overlay=0:0 [outv]
cmd = [
    "ffmpeg", "-y",
    "-i", INPUT_CLIP,
    "-i", OVERLAY_PATH,
    "-i", AUDIO_PATH,
    "-filter_complex",
    "[0:v]split=2[bg][fg];"
    "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[blurred_bg];"
    "[fg]scale=1080:608[sharp_center];"
    "[blurred_bg][sharp_center]overlay=0:656[base_vid];"
    "[base_vid][1:v]overlay=0:0[outv];"
    "[0:a]volume=0.15[game_audio];"
    "[2:a]volume=1.0[voice];"
    "[game_audio][voice]amix=inputs=2:duration=first:dropout_transition=2[outa]",
    "-map", "[outv]",
    "-map", "[outa]",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "22",
    "-c:a", "aac",
    "-b:a", "192k",
    "-t", "19",
    OUTPUT_VIDEO
]

print("Ejecutando renderizado FFmpeg...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print("¡VIDEO GENERADO CON ÉXITO!", OUTPUT_VIDEO)
else:
    print("Error en FFmpeg:", res.stderr[-500:])
