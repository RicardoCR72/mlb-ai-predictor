import os
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1350

# 1. Background Gradient
y_coords = np.linspace(0, 1, HEIGHT)
r = (13 * (1 - y_coords) + 7 * y_coords).astype(np.uint8)
g = (19 * (1 - y_coords) + 10 * y_coords).astype(np.uint8)
b = (31 * (1 - y_coords) + 16 * y_coords).astype(np.uint8)

gradient = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
gradient[:, :, 0] = r[:, None]
gradient[:, :, 1] = g[:, None]
gradient[:, :, 2] = b[:, None]

img = Image.fromarray(gradient).convert("RGBA")
draw = ImageDraw.Draw(img)

# Fonts
font_dir = "C:/Windows/Fonts"
f_title_big = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 48)
f_title_sub = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
f_pill = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)
f_player = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 54)
f_meta = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 22)
f_stat_lbl = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 16)
f_stat_val = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 44)
f_arrow = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 36)
f_bar = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_desc = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 20)
f_footer = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)

# Top Bar
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((68, 68), Image.Resampling.LANCZOS)
    img.paste(logo, (50, 48), logo)

draw.text((135, 52), "OVERDOG AI", font=f_brand, fill=(0, 255, 163, 255))
draw.text((135, 86), "SPORTS INTELLIGENCE · CERO HUMO", font=f_title_sub, fill=(148, 163, 184, 255))

# Date Pill Top Right
draw.rounded_rectangle([720, 55, 1030, 102], radius=23, fill=(24, 34, 53, 255), outline=(0, 229, 255, 160), width=1)
draw.text((750, 69), "SNF · 19:20 CDMX", font=f_pill, fill=(0, 229, 255, 255))

# Main Title Header
draw.text((50, 145), "SUNDAY NIGHT FOOTBALL", font=f_title_big, fill=(255, 255, 255, 255))
draw.text((50, 212), "Philadelphia Eagles @ Washington Commanders · Pick Oficial del Modelo", font=f_title_sub, fill=(148, 163, 184, 255))

# Hero Card (Jayden Daniels Under 1.5 Passing TDs)
cy = 280
card_h = 680
draw.rounded_rectangle([50, cy, WIDTH - 50, cy + card_h], radius=28, fill=(19, 27, 43, 255), outline=(0, 255, 163, 230), width=3)

# Left accent line
draw.rounded_rectangle([50, cy + 30, 58, cy + card_h - 30], radius=4, fill=(0, 255, 163, 255))

# Badge
draw.rounded_rectangle([90, cy + 35, 490, cy + 80], radius=20, fill=(0, 255, 163, 255))
draw.text((115, cy + 44), "PICK QUIRÚRGICO DE LA NOCHE", font=f_pill, fill=(10, 15, 26, 255))

# Market right
draw.text((WIDTH - 90 - draw.textlength("PASES DE TOUCHDOWN", font=f_meta), cy + 45), "PASES DE TOUCHDOWN", font=f_meta, fill=(148, 163, 184, 255))

# Player Name & Meta
draw.text((90, cy + 105), "JAYDEN DANIELS", font=f_player, fill=(255, 255, 255, 255))
draw.text((90, cy + 175), "QB · WASHINGTON COMMANDERS · SEMANA 8", font=f_meta, fill=(148, 163, 184, 255))

# Stats comparison box
box_x = 90
box_y = cy + 230
box_w = WIDTH - 180
box_h = 130
draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=20, fill=(12, 17, 28, 255), outline=(32, 45, 70, 255), width=2)

# Line Column
draw.text((box_x + 40, box_y + 24), "LÍNEA DRAFTKINGS", font=f_stat_lbl, fill=(148, 163, 184, 255))
draw.text((box_x + 40, box_y + 55), "1.5 PASES", font=f_stat_val, fill=(241, 245, 249, 255))

# Arrow
draw.text((box_x + 400, box_y + 55), "->", font=f_arrow, fill=(0, 255, 163, 255))

# Proy Column
draw.text((box_x + 530, box_y + 24), "PROYECCIÓN OVERDOG IA", font=f_stat_lbl, fill=(0, 255, 163, 255))
draw.text((box_x + 530, box_y + 55), "1.09 PASES DE TD", font=f_stat_val, fill=(0, 255, 163, 255))

# Bottom Bar inside card (Selection & Odds)
bar_y = cy + 390
draw.rounded_rectangle([90, bar_y, WIDTH - 90, bar_y + 75], radius=18, fill=(28, 39, 62, 255))

draw.text((120, bar_y + 20), "PICK: UNDER 1.5", font=f_bar, fill=(255, 255, 255, 255))
draw.text((450, bar_y + 20), "MOMIO: -147 (1.68)", font=f_bar, fill=(255, 215, 0, 255))
draw.text((760, bar_y + 20), "PROB: 59.8%", font=f_bar, fill=(0, 255, 163, 255))

# Tactical Insight Box
desc_box_y = cy + 495
draw.rounded_rectangle([90, desc_box_y, WIDTH - 90, desc_box_y + 145], radius=18, fill=(15, 22, 35, 255), outline=(36, 50, 78, 255), width=1)
draw.text((115, desc_box_y + 20), "CLAVE TÁCTICA DEL MODELO:", font=f_stat_lbl, fill=(255, 215, 0, 255))
draw.text((115, desc_box_y + 52), "Washington concentra su anotación en zona roja en acarreos diseñados para", font=f_desc, fill=(203, 213, 225, 255))
draw.text((115, desc_box_y + 80), "Daniels o Brian Robinson. Ante la defensiva profunda de Filadelfia, el algoritmo", font=f_desc, fill=(203, 213, 225, 255))
draw.text((115, desc_box_y + 108), "proyecta su techo por pase en máximo 1 touchdown en el 59.8% de los escenarios.", font=f_desc, fill=(203, 213, 225, 255))

# Bottom Discipline Banner
dis_y = 1000
draw.rounded_rectangle([50, dis_y, WIDTH - 50, dis_y + 180], radius=22, fill=(18, 26, 42, 255), outline=(32, 45, 70, 255), width=1)
draw.text((90, dis_y + 30), "DISCIPLINA CUANTITATIVA", font=f_meta, fill=(0, 229, 255, 255))
draw.text((90, dis_y + 68), "El algoritmo descartó el resto del tablero para el Sunday Night Football", font=f_desc, fill=(241, 245, 249, 255))
draw.text((90, dis_y + 98), "por no presentar ventaja matemática suficiente contra los momios del mercado.", font=f_desc, fill=(148, 163, 184, 255))
draw.text((90, dis_y + 128), "En OVERDOG no forzamos jugadas por espectáculo: solo jugamos el valor (+EV).", font=f_desc, fill=(0, 255, 163, 255))

# Footer
foot_y = 1230
draw.line([(50, foot_y), (WIDTH - 50, foot_y)], fill=(32, 45, 70, 255), width=2)
draw.text((50, foot_y + 32), "GESTIÓN: 1 UNIDAD FIJA · TRANSPARENCIA 100%", font=f_footer, fill=(148, 163, 184, 255))

# Telegram Pill
tg_w = 260
tg_box = [WIDTH - 50 - tg_w, foot_y + 20, WIDTH - 50, foot_y + 72]
draw.rounded_rectangle(tg_box, radius=26, fill=(0, 136, 204, 255))
draw.text((WIDTH - 50 - tg_w + 32, foot_y + 32), "t.me/overdogai", font=f_footer, fill=(255, 255, 255, 255))

# Save files
out_png = "assets/nfl_snf_jayden_daniels.png"
out_jpg = "assets/nfl_snf_jayden_daniels.jpg"

img.save(out_png, "PNG")
img.convert("RGB").save(out_jpg, "JPEG", quality=95)

artifact_dir = "C:/Users/rcabr/.gemini/antigravity/brain/8db99efe-a7c9-44ba-88ff-2a8317829757"
if os.path.exists(artifact_dir):
    shutil.copy2(out_png, os.path.join(artifact_dir, "nfl_snf_jayden_daniels.png"))
    shutil.copy2(out_jpg, os.path.join(artifact_dir, "nfl_snf_jayden_daniels.jpg"))

print("Imagen SNF Daniels generada con éxito:", out_png)
