import os
import asyncio
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# -------------------------------------------------------------
# 1. GENERATE FULL VOICEOVER WITH INTRO, PICK & OUTRO (DESPEDIDA)
# -------------------------------------------------------------
VOICE_FULL = """
¡Atención al juego estelar de esta noche en el Sunday Night Football!
Analizamos el partido entre las Águilas de Filadelfia y los Comandantes de Washington.
Para Jayden Daniels, el mercado colocó su línea en uno punto cinco pases de touchdown.
Sin embargo, nuestros algoritmos proyectan apenas uno punto cero nueve pases, ya que Washington resuelve la zona roja por tierra con acarreos de Daniels y sus corredores.
Nos quedamos con Jayden Daniels Menos de uno punto cinco pases de anotación.
Toda la analítica completa está gratis en nuestro canal de Telegram.
Toca el enlace en nuestro perfil y acompáñanos esta noche. ¡Mucho éxito en el kickoff!
""".strip()

AUDIO_PATH = "scratch/voice_snf_with_outro.mp3"

async def gen_full_audio():
    com = edge_tts.Communicate(
        text=VOICE_FULL,
        voice="es-MX-JorgeNeural",
        rate="+7%",
        pitch="+0Hz"
    )
    await com.save(AUDIO_PATH)
    print("Voz completa con outro guardada.")

asyncio.run(gen_full_audio())

# Probe audio duration
res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", AUDIO_PATH], capture_output=True, text=True)
audio_dur = float(res.stdout.strip())
print(f"Duración total del audio: {audio_dur:.2f} s")

# -------------------------------------------------------------
# 2. DESIGN THE OUTRO SCREEN (1080x1920)
# -------------------------------------------------------------
W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

y_coords = np.linspace(0, 1, H)
r = (14 * (1 - y_coords) + 6 * y_coords).astype(np.uint8)
g = (20 * (1 - y_coords) + 9 * y_coords).astype(np.uint8)
b = (35 * (1 - y_coords) + 16 * y_coords).astype(np.uint8)

bg = np.zeros((H, W, 3), dtype=np.uint8)
bg[:, :, 0] = r[:, None]
bg[:, :, 1] = g[:, None]
bg[:, :, 2] = b[:, None]

outro_img = Image.fromarray(bg).convert("RGBA")
odraw = ImageDraw.Draw(outro_img)

f_h1 = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 52)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 28)
f_tg_btn = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 40)
f_link = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_tag = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 22)

# Logo centered
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((190, 190), Image.Resampling.LANCZOS)
    outro_img.paste(logo, ((W - 190) // 2, 400), logo)

odraw.text((W // 2 - odraw.textlength("OVERDOG AI", font=f_brand) / 2, 620), "OVERDOG AI", font=f_brand, fill=(0, 255, 163, 255))
odraw.text((W // 2 - odraw.textlength("SPORTS INTELLIGENCE", font=f_sub) / 2, 670), "SPORTS INTELLIGENCE", font=f_sub, fill=(148, 163, 184, 255))

# Central CTA Box
box_y = 800
box_h = 490
odraw.rounded_rectangle([70, box_y, W - 70, box_y + box_h], radius=32, fill=(16, 24, 40, 245), outline=(0, 255, 163, 230), width=3)

# Question Header
odraw.text((W // 2 - odraw.textlength("¿LISTO PARA GANAR CON DATOS?", font=f_sub) / 2, box_y + 45), "¿LISTO PARA GANAR CON DATOS?", font=f_sub, fill=(255, 215, 0, 255))
odraw.text((W // 2 - odraw.textlength("ÚNETE A LA COMUNIDAD", font=f_h1) / 2, box_y + 95), "ÚNETE A LA COMUNIDAD", font=f_h1, fill=(255, 255, 255, 255))

# Telegram Big Button
btn_y = box_y + 200
odraw.rounded_rectangle([110, btn_y, W - 110, btn_y + 110], radius=26, fill=(0, 136, 204, 255))
odraw.text((W // 2 - odraw.textlength("CANAL DE TELEGRAM", font=f_tg_btn) / 2, btn_y + 18), "CANAL DE TELEGRAM", font=f_tg_btn, fill=(255, 255, 255, 255))
odraw.text((W // 2 - odraw.textlength("@overdogai", font=f_link) / 2, btn_y + 65), "@overdogai", font=f_link, fill=(255, 255, 255, 255))

# Bio instruction
odraw.text((W // 2 - odraw.textlength("👉 Enlace directo en la biografía del perfil", font=f_sub) / 2, box_y + 355), "👉 Enlace directo en la biografía del perfil", font=f_sub, fill=(0, 255, 163, 255))
odraw.text((W // 2 - odraw.textlength("Picks diarios gratis · 100% Transparentes", font=f_tag) / 2, box_y + 415), "Picks diarios gratis · 100% Transparentes", font=f_tag, fill=(148, 163, 184, 255))

# Footer note
odraw.text((W // 2 - odraw.textlength("GESTIÓN RESPONSABLE · 1 UNIDAD FIJA", font=f_tag) / 2, 1370), "GESTIÓN RESPONSABLE · 1 UNIDAD FIJA", font=f_tag, fill=(148, 163, 184, 255))

OUTRO_PATH = "scratch/outro_snf_slide.png"
outro_img.save(OUTRO_PATH, "PNG")
print("Outro guardada en:", OUTRO_PATH)

# -------------------------------------------------------------
# 3. TIMING AND SEGMENTS
# -------------------------------------------------------------
# Total audio is ~37 seconds
INTRO_DUR = 2.5
OUTRO_DUR = 4.0
TOTAL_DUR = round(audio_dur + 0.5, 2)
GAME_DUR = round(TOTAL_DUR - INTRO_DUR - OUTRO_DUR, 2)

print(f"Estructura del video: Intro {INTRO_DUR}s | Jugada {GAME_DUR}s | Outro {OUTRO_DUR}s | Total: {TOTAL_DUR}s")

INTRO_VID = "scratch/seg_intro.mp4"
GAME_VID = "scratch/seg_game.mp4"
OUTRO_VID = "scratch/seg_outro.mp4"

# 1. Intro Video
subprocess.run([
    "ffmpeg", "-y",
    "-loop", "1", "-i", "scratch/intro_snf_slide.png",
    "-t", str(INTRO_DUR),
    "-vf", "scale=1080:1920,format=yuv420p",
    "-r", "30",
    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
    "-an", INTRO_VID
], check=True)

# 2. Game Video (with slip card)
subprocess.run([
    "ffmpeg", "-y",
    "-ss", "00:00:01",
    "-i", "assets/daniels_clip.mp4",
    "-i", "scratch/card_slip_daniels.png",
    "-t", str(GAME_DUR),
    "-filter_complex",
    "[0:v]crop=608:1080:650:0,scale=1080:1920[v_crop];"
    "[v_crop][1:v]overlay=(1080-940)/2:180[outv]",
    "-map", "[outv]",
    "-r", "30",
    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
    "-an", GAME_VID
], check=True)

# 3. Outro Video
subprocess.run([
    "ffmpeg", "-y",
    "-loop", "1", "-i", OUTRO_PATH,
    "-t", str(OUTRO_DUR),
    "-vf", "scale=1080:1920,format=yuv420p",
    "-r", "30",
    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
    "-an", OUTRO_VID
], check=True)

# Concatenate all 3 video segments
concat_list = "scratch/concat_3part.txt"
with open(concat_list, "w") as f:
    f.write(f"file '{os.path.abspath(INTRO_VID).replace(chr(92), '/')}'\n")
    f.write(f"file '{os.path.abspath(GAME_VID).replace(chr(92), '/')}'\n")
    f.write(f"file '{os.path.abspath(OUTRO_VID).replace(chr(92), '/')}'\n")

CONCAT_3PART = "scratch/video_3part_no_audio.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0",
    "-i", concat_list,
    "-c", "copy",
    CONCAT_3PART
], check=True)

# Final Mix: Video + Boosted Loud Voice + Faint Background Crowd
FINAL_VIDEO_3PART = "assets/video_snf_daniels_master.mp4"

cmd_mix = [
    "ffmpeg", "-y",
    "-i", CONCAT_3PART,
    "-i", AUDIO_PATH,
    "-i", "assets/daniels_clip.mp4",
    "-filter_complex",
    "[1:a]volume=1.8[voice_boost];"
    "[2:a]volume=0.08[game_faint];"
    "[game_faint][voice_boost]amix=inputs=2:duration=first:dropout_transition=2[outa]",
    "-map", "0:v",
    "-map", "[outa]",
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "192k",
    "-t", str(TOTAL_DUR),
    FINAL_VIDEO_3PART
]

res = subprocess.run(cmd_mix, capture_output=True, text=True)
if res.returncode == 0:
    print("¡VIDEO MASTER CON INTRO, JUGADA Y DESPEDIDA GENERADO!", FINAL_VIDEO_3PART)
else:
    print("Error final:", res.stderr[-500:])
