import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

# 1. Create a sleek compact bet slip / pick card like in ejemplo.mp4
# Card size: 880x240 (at 1080x1920 scale)
card_w = 920
card_h = 240
card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
cdraw = ImageDraw.Draw(card)

font_dir = "C:/Windows/Fonts"
f_match = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_market = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_pick = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_ev = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 24)
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)

# Card Background: Clean Dark Glassmorphic with Neon Cyber Green border or High-contrast White
# In ejemplo.mp4 it's a clean white card or dark sleek card
cdraw.rounded_rectangle([0, 0, card_w, card_h], radius=24, fill=(13, 19, 31, 245), outline=(0, 255, 163, 230), width=3)

# Top Bar inside card: Brand & Matchup
cdraw.text((35, 25), "OVERDOG AI · MIN Vikings @ DET Lions", font=f_match, fill=(255, 255, 255, 255))

# EV badge top right
cdraw.rounded_rectangle([card_w - 240, 20, card_w - 30, 65], radius=15, fill=(0, 255, 163, 255))
cdraw.text((card_w - 225, 28), "VENTAJA +22.6%", font=f_ev, fill=(10, 15, 26, 255))

# Divider
cdraw.line([(35, 78), (card_w - 35, 78)], fill=(38, 52, 80, 255), width=2)

# Market Line
cdraw.text((35, 95), "Yardas Terrestres de jugador (Línea: 28.5 · Proy: 66.5 yds)", font=f_market, fill=(148, 163, 184, 255))

# Main Pick
cdraw.text((35, 140), "Aaron Jones (MIN)  MÁS DE 28.5", font=f_pick, fill=(0, 255, 163, 255))

# Odds
cdraw.text((card_w - 220, 145), "Momio -113", font=f_pick, fill=(255, 215, 0, 255))

CARD_PATH = "scratch/ejemplo_slip_card.png"
card.save(CARD_PATH, "PNG")

# 2. Render Fullscreen Vertical Cropped Video focused tightly on player!
# Input: scratch/aaron_jones_clip.mp4 (1920x1080)
# We crop 608x1080 from center-left where Aaron Jones runs (e.g. x=700), scale to 1080x1920,
# and overlay the compact card at y=160 (just like in ejemplo.mp4)!
OUTPUT_EJEMPLO = "assets/video_prueba_estilo_ejemplo.mp4"

cmd = [
    "ffmpeg", "-y",
    "-i", "scratch/aaron_jones_clip.mp4",
    "-i", CARD_PATH,
    "-i", "scratch/voice_aaron_jones.mp3",
    "-filter_complex",
    "[0:v]crop=608:1080:680:0,scale=1080:1920[player_focused];"
    "[player_focused][1:v]overlay=(1080-920)/2:180[outv];"
    "[0:a]volume=0.18[game_audio];"
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
    OUTPUT_EJEMPLO
]

print("Renderizando video estilo ejemplo con zoom directo al jugador...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print("¡VIDEO GENERADO CON ÉXITO!", OUTPUT_EJEMPLO)
else:
    print("Error FFmpeg:", res.stderr[-500:])
