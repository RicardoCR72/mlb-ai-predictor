import os
import asyncio
import subprocess
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# 1. Voiceover
VOICE_TEXT = """
¡Atención al pick quirúrgico de esta noche en el Sunday Night Football!
Nuestros modelos analizaron el partido entre Águilas de Filadelfia y Comandantes de Washington.
Para Jayden Daniels, el mercado tiene su línea en uno punto cinco pases de touchdown.
Sin embargo, el algoritmo proyecta apenas uno punto cero nueve pases de anotación, ya que Washington concentra la zona roja en acarreos terrestres.
Nos quedamos con Jayden Daniels Menos de uno punto cinco pases de touchdown.
El análisis completo está gratis en el Telegram de nuestro perfil.
""".strip()

AUDIO_PATH = "scratch/voice_daniels_snf.mp3"

async def gen_voice():
    com = edge_tts.Communicate(
        text=VOICE_TEXT,
        voice="es-MX-JorgeNeural",
        rate="+5%",
        pitch="+0Hz"
    )
    await com.save(AUDIO_PATH)
    print("Voz SNF lista:", AUDIO_PATH)

asyncio.run(gen_voice())

# 2. Design the Compact Slip Card (Style ejemplo.mp4)
card_w = 940
card_h = 240
card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
cdraw = ImageDraw.Draw(card)

font_dir = "C:/Windows/Fonts"
f_match = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_market = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 23)
f_pick = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_ev = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)

# Sleek Dark Slate Card with subtle neon cyan border
cdraw.rounded_rectangle([0, 0, card_w, card_h], radius=24, fill=(13, 19, 31, 245), outline=(0, 255, 163, 230), width=3)

# Matchup Top
cdraw.text((35, 25), "OVERDOG AI · PHI Eagles @ WAS Commanders", font=f_match, fill=(255, 255, 255, 255))

# Top right badge
cdraw.rounded_rectangle([card_w - 230, 20, card_w - 30, 65], radius=15, fill=(0, 255, 163, 255))
cdraw.text((card_w - 212, 28), "VENTAJA +EV", font=f_ev, fill=(10, 15, 26, 255))

# Divider
cdraw.line([(35, 78), (card_w - 35, 78)], fill=(38, 52, 80, 255), width=2)

# Market details
cdraw.text((35, 95), "Pases de Touchdown (Línea: 1.5 · Proy IA: 1.09 TDs · Prob: 59.8%)", font=f_market, fill=(148, 163, 184, 255))

# Main Pick
cdraw.text((35, 142), "J.Daniels (WAS)  MENOS DE 1.5", font=f_pick, fill=(0, 255, 163, 255))

# Momio
cdraw.text((card_w - 240, 145), "Momio -147", font=f_pick, fill=(255, 215, 0, 255))

CARD_PATH = "scratch/card_slip_daniels.png"
card.save(CARD_PATH, "PNG")
print("Tarjeta guardada:", CARD_PATH)

# 3. Render 9:16 Fullscreen Vertical Video centered on Daniels with card on top
OUTPUT_FINAL = "assets/video_snf_daniels_final.mp4"

cmd = [
    "ffmpeg", "-y",
    "-i", "assets/daniels_clip.mp4",
    "-i", CARD_PATH,
    "-i", AUDIO_PATH,
    "-filter_complex",
    "[0:v]crop=608:1080:650:0,scale=1080:1920[player_v];"
    "[player_v][1:v]overlay=(1080-940)/2:180[outv];"
    "[0:a]volume=0.20[crowd];"
    "[2:a]volume=1.0[voice];"
    "[crowd][voice]amix=inputs=2:duration=first:dropout_transition=2[outa]",
    "-map", "[outv]",
    "-map", "[outa]",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "21",
    "-c:a", "aac",
    "-b:a", "192k",
    "-t", "20",
    OUTPUT_FINAL
]

print("Renderizando video SNF Daniels con FFmpeg...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print("¡VIDEO SNF GENERADO EXITOSAMENTE!", OUTPUT_FINAL)
else:
    print("Error FFmpeg:", res.stderr[-500:])
