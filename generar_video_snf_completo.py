import os
import asyncio
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# -------------------------------------------------------------
# 1. GENERATE CRISP, PUNCHY VOICEOVER WITH PERFECT TIMING
# -------------------------------------------------------------
VOICE_SCRIPT = """
¡Atención al juego estelar de esta noche en el Sunday Night Football!
Analizamos el partido entre las Águilas de Filadelfia y los Comandantes de Washington.
Para Jayden Daniels, el mercado colocó su línea en uno punto cinco pases de touchdown.
Sin embargo, nuestros algoritmos proyectan apenas uno punto cero nueve pases, ya que Washington resuelve la zona roja por tierra con Daniels y sus corredores.
Nos quedamos con Jayden Daniels Menos de uno punto cinco pases de anotación.
El análisis completo y las proyecciones están gratis en el Telegram de nuestro perfil.
""".strip()

AUDIO_SNF = "scratch/voice_snf_loud.mp3"

async def make_voice():
    com = edge_tts.Communicate(
        text=VOICE_SCRIPT,
        voice="es-MX-JorgeNeural",
        rate="+7%",
        pitch="+0Hz"
    )
    await com.save(AUDIO_SNF)
    print("Voz lista y guardada.")

asyncio.run(make_voice())

# Check audio length
res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", AUDIO_SNF], capture_output=True, text=True)
audio_duration = float(res.stdout.strip())
print(f"Duración del audio de voz: {audio_duration:.2f} s")

# -------------------------------------------------------------
# 2. DESIGN THE INTRO SCREEN (1080x1920)
# -------------------------------------------------------------
W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

# Background gradient
y_coords = np.linspace(0, 1, H)
r = (14 * (1 - y_coords) + 6 * y_coords).astype(np.uint8)
g = (20 * (1 - y_coords) + 9 * y_coords).astype(np.uint8)
b = (35 * (1 - y_coords) + 16 * y_coords).astype(np.uint8)

bg = np.zeros((H, W, 3), dtype=np.uint8)
bg[:, :, 0] = r[:, None]
bg[:, :, 1] = g[:, None]
bg[:, :, 2] = b[:, None]

intro_img = Image.fromarray(bg).convert("RGBA")
idraw = ImageDraw.Draw(intro_img)

# Fonts
f_intro_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_intro_h1 = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 68)
f_intro_vs = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 42)
f_intro_pick = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 48)
f_intro_sub = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 28)

# Logo centered
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((180, 180), Image.Resampling.LANCZOS)
    intro_img.paste(logo, ((W - 180) // 2, 420), logo)

# Brand name
idraw.text((W // 2 - idraw.textlength("OVERDOG AI", font=f_intro_tag) / 2, 630), "OVERDOG AI", font=f_intro_tag, fill=(0, 255, 163, 255))
idraw.text((W // 2 - idraw.textlength("SPORTS INTELLIGENCE", font=f_intro_sub) / 2, 675), "SPORTS INTELLIGENCE", font=f_intro_sub, fill=(148, 163, 184, 255))

# Central Banner Box
box_y = 800
box_h = 480
idraw.rounded_rectangle([70, box_y, W - 70, box_y + box_h], radius=32, fill=(16, 24, 40, 245), outline=(0, 229, 255, 220), width=3)

# SNF Badge
idraw.rounded_rectangle([W // 2 - 250, box_y + 40, W // 2 + 250, box_y + 100], radius=25, fill=(0, 229, 255, 255))
idraw.text((W // 2 - idraw.textlength("SUNDAY NIGHT FOOTBALL", font=f_intro_tag) / 2, box_y + 52), "SUNDAY NIGHT FOOTBALL", font=f_intro_tag, fill=(10, 15, 26, 255))

# Matchup
idraw.text((W // 2 - idraw.textlength("EAGLES", font=f_intro_h1) / 2, box_y + 130), "EAGLES", font=f_intro_h1, fill=(255, 255, 255, 255))
idraw.text((W // 2 - idraw.textlength("@", font=f_intro_vs) / 2, box_y + 215), "@", font=f_intro_vs, fill=(255, 215, 0, 255))
idraw.text((W // 2 - idraw.textlength("COMMANDERS", font=f_intro_h1) / 2, box_y + 265), "COMMANDERS", font=f_intro_h1, fill=(255, 255, 255, 255))

# Pill: Pick Exclusivo
idraw.rounded_rectangle([110, box_y + 375, W - 110, box_y + 445], radius=20, fill=(0, 255, 163, 255))
idraw.text((W // 2 - idraw.textlength("PICK OFICIAL DEL ALGORITMO (+EV)", font=f_intro_tag) / 2, box_y + 390), "PICK OFICIAL DEL ALGORITMO (+EV)", font=f_intro_tag, fill=(10, 15, 26, 255))

# Bottom date/time
idraw.text((W // 2 - idraw.textlength("19:20 CDMX · SEMANA 8", font=f_intro_sub) / 2, 1340), "19:20 CDMX · SEMANA 8", font=f_intro_sub, fill=(148, 163, 184, 255))

INTRO_PATH = "scratch/intro_snf_slide.png"
intro_img.save(INTRO_PATH, "PNG")
print("Intro guardada en:", INTRO_PATH)

# -------------------------------------------------------------
# 3. DESIGN THE TOP SLIP CARD (Same as earlier, pristine 940x240)
# -------------------------------------------------------------
card_w = 940
card_h = 240
card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
cdraw = ImageDraw.Draw(card)

f_match = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_market = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 23)
f_pick = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_ev = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)

cdraw.rounded_rectangle([0, 0, card_w, card_h], radius=24, fill=(13, 19, 31, 245), outline=(0, 255, 163, 230), width=3)
cdraw.text((35, 25), "OVERDOG AI · PHI Eagles @ WAS Commanders", font=f_match, fill=(255, 255, 255, 255))

cdraw.rounded_rectangle([card_w - 230, 20, card_w - 30, 65], radius=15, fill=(0, 255, 163, 255))
cdraw.text((card_w - 212, 28), "VENTAJA +EV", font=f_ev, fill=(10, 15, 26, 255))

cdraw.line([(35, 78), (card_w - 35, 78)], fill=(38, 52, 80, 255), width=2)
cdraw.text((35, 95), "Pases de Touchdown (Línea: 1.5 · Proy IA: 1.09 TDs · Prob: 59.8%)", font=f_market, fill=(148, 163, 184, 255))
cdraw.text((35, 142), "J.Daniels (WAS)  MENOS DE 1.5", font=f_pick, fill=(0, 255, 163, 255))
cdraw.text((card_w - 240, 145), "Momio -147", font=f_pick, fill=(255, 215, 0, 255))

CARD_PATH = "scratch/card_slip_daniels.png"
card.save(CARD_PATH, "PNG")

# -------------------------------------------------------------
# 4. RENDER INTRO VIDEO (2.5s) AND GAMEPLAY VIDEO, THEN CONCAT
# -------------------------------------------------------------
INTRO_VID = "scratch/intro_segment.mp4"
GAME_VID = "scratch/game_segment.mp4"
TOTAL_TIME = round(audio_duration + 0.5, 2)
INTRO_DUR = 2.5
GAME_DUR = round(TOTAL_TIME - INTRO_DUR, 2)

print(f"Generando intro de {INTRO_DUR}s y jugada de {GAME_DUR}s (Total: {TOTAL_TIME}s)...")

# Intro segment: 2.5s of the intro slide with slight slow zoom (Ken Burns)
cmd_intro = [
    "ffmpeg", "-y",
    "-loop", "1", "-i", INTRO_PATH,
    "-t", str(INTRO_DUR),
    "-vf", "scale=1080:1920,format=yuv420p",
    "-r", "30",
    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
    "-an",
    INTRO_VID
]
subprocess.run(cmd_intro, check=True)

# Game segment: crop and overlay card
cmd_game = [
    "ffmpeg", "-y",
    "-ss", "00:00:02",
    "-i", "assets/daniels_clip.mp4",
    "-i", CARD_PATH,
    "-t", str(GAME_DUR),
    "-filter_complex",
    "[0:v]crop=608:1080:650:0,scale=1080:1920[v_crop];"
    "[v_crop][1:v]overlay=(1080-940)/2:180[outv]",
    "-map", "[outv]",
    "-r", "30",
    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
    "-an",
    GAME_VID
]
subprocess.run(cmd_game, check=True)

# Concatenate intro + game video
CONCAT_VID = "scratch/video_sin_audio.mp4"
concat_txt = "scratch/concat_list.txt"
with open(concat_txt, "w") as f:
    f.write(f"file '{os.path.abspath(INTRO_VID).replace(chr(92), '/')}'\n")
    f.write(f"file '{os.path.abspath(GAME_VID).replace(chr(92), '/')}'\n")

cmd_concat = [
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0",
    "-i", concat_txt,
    "-c", "copy",
    CONCAT_VID
]
subprocess.run(cmd_concat, check=True)

# Final mix: Video + Loud, Clear Voiceover + Subtle Background Sound
OUTPUT_PERFECT = "assets/video_snf_daniels_con_intro.mp4"

# Use volume filter to make voice 100% loud and crisp (0 dB)
cmd_final = [
    "ffmpeg", "-y",
    "-i", CONCAT_VID,
    "-i", AUDIO_SNF,
    "-i", "assets/daniels_clip.mp4",
    "-filter_complex",
    "[1:a]volume=1.8[voice_boost];"
    "[2:a]volume=0.08[game_faint];"
    "[game_faint][voice_boost]amix=inputs=2:duration=first:dropout_transition=2[outa]",
    "-map", "0:v",
    "-map", "[outa]",
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "192k",
    "-t", str(TOTAL_TIME),
    OUTPUT_PERFECT
]

res_final = subprocess.run(cmd_final, capture_output=True, text=True)
if res_final.returncode == 0:
    print("¡VIDEO FINAL CON INTRO Y VOZ LOUD GENERADO EXITOSAMENTE!", OUTPUT_PERFECT)
else:
    print("Error final:", res_final.stderr[-500:])
