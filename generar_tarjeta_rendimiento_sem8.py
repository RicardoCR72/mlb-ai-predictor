import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

# Clean, robust font hierarchy
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_header_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_stat_hero_lbl = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_stat_hero_val = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 96)
f_grid_val = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 68)
f_grid_lbl = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 24)
f_grid_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 22)
f_section = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_bullet_bold = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_bullet_text = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 25)
f_trust_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_trust_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_cta = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)

# Solid dark background with rich emerald glow (zero alpha blending bugs)
y_coords = np.linspace(0, 1, H)
r = (10 * (1 - y_coords) + 6 * y_coords).astype(np.uint8)
g = (24 * (1 - y_coords) + 14 * y_coords).astype(np.uint8)
b = (30 * (1 - y_coords) + 18 * y_coords).astype(np.uint8)

bg = np.zeros((H, W, 3), dtype=np.uint8)
bg[:, :, 0] = r[:, None]
bg[:, :, 1] = g[:, None]
bg[:, :, 2] = b[:, None]

img = Image.fromarray(bg).convert("RGB")
draw = ImageDraw.Draw(img)

# Layout constants: 90px margins for safe display
CARD_X = 90
CARD_W = 900
THEME_GREEN = (0, 255, 163)
THEME_GOLD = (255, 215, 0)
THEME_BLUE = (56, 189, 248)

# -------------------------------------------------------------
# 1. HEADER (y: 110 - 320)
# -------------------------------------------------------------
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((90, 90), Image.Resampling.LANCZOS)
    img.paste(logo, ((W - 90) // 2, 110), logo)

draw.text(((W - draw.textlength("OVERDOG AI", font=f_brand)) // 2, 215), "OVERDOG AI", font=f_brand, fill=(255, 255, 255))

header_tag = "REPORTE OFICIAL DE RENDIMIENTO"
tw = draw.textlength(header_tag, font=f_header_tag) + 40
tx = (W - tw) // 2
draw.rounded_rectangle([tx, 275, tx + tw, 320], radius=22, fill=(15, 28, 38), outline=THEME_GREEN, width=2)
draw.text(((W - draw.textlength(header_tag, font=f_header_tag)) // 2, 285), header_tag, font=f_header_tag, fill=THEME_GREEN)

# -------------------------------------------------------------
# 2. HERO BOX: BENEFICIO NETO TOTAL (+4.73 U) (y: 350 - 580)
# -------------------------------------------------------------
hero_y = 350
hero_h = 240
draw.rounded_rectangle([CARD_X, hero_y, CARD_X + CARD_W, hero_y + hero_h], radius=30, fill=(10, 20, 30), outline=THEME_GREEN, width=3)

# Subtitle inside hero
h_sub = "NFL 2026 · BALANCE CONSOLIDADO SEMANA 8"
draw.text(((W - draw.textlength(h_sub, font=f_sub)) // 2, hero_y + 25), h_sub, font=f_sub, fill=(148, 163, 184))

# Big Value
hero_val = "+4.73 UNIDADES"
draw.text(((W - draw.textlength(hero_val, font=f_stat_hero_val)) // 2, hero_y + 65), hero_val, font=f_stat_hero_val, fill=THEME_GREEN)

# Bottom note
h_note = "Ganancia neta auditada con gestion disciplinada de 1 Unidad fija"
draw.text(((W - draw.textlength(h_note, font=f_sub)) // 2, hero_y + 185), h_note, font=f_sub, fill=(203, 213, 225))

# -------------------------------------------------------------
# 3. 3-COLUMN METRIC GRID (y: 615 - 845)
# -------------------------------------------------------------
grid_y = 615
grid_h = 220
col_w = (CARD_W - 30) // 3

metrics = [
    ("TOTAL EVALUADOS", "54", "Muestra de mercado", (255, 255, 255)),
    ("WIN RATE", "59.3%", "32G - 22P (Rentable)", THEME_GREEN),
    ("ROI CONSOLIDADO", "+8.8%", "Retorno sobre capital", THEME_GOLD)
]

for i, (lbl, val, sub_txt, col) in enumerate(metrics):
    cx = CARD_X + i * (col_w + 15)
    # Individual pill box
    draw.rounded_rectangle([cx, grid_y, cx + col_w, grid_y + grid_h], radius=24, fill=(12, 19, 32), outline=(35, 50, 70), width=2)
    # Label
    draw.text((cx + (col_w - draw.textlength(lbl, font=f_grid_lbl)) // 2, grid_y + 25), lbl, font=f_grid_lbl, fill=(148, 163, 184))
    # Big Value
    draw.text((cx + (col_w - draw.textlength(val, font=f_grid_val)) // 2, grid_y + 70), val, font=f_grid_val, fill=col)
    # Subtext
    draw.text((cx + (col_w - draw.textlength(sub_txt, font=f_grid_sub)) // 2, grid_y + 165), sub_txt, font=f_grid_sub, fill=(148, 163, 184))

# -------------------------------------------------------------
# 4. QUANTITATIVE ANALYSIS CARD (y: 865 - 1475)
# -------------------------------------------------------------
card_y = 865
card_h = 600
draw.rounded_rectangle([CARD_X, card_y, CARD_X + CARD_W, card_y + card_h], radius=32, fill=(13, 19, 32), outline=(35, 52, 75), width=2)

s_title = "ANÁLISIS CUANTITATIVO DEL MODELO"
draw.text(((W - draw.textlength(s_title, font=f_section)) // 2, card_y + 40), s_title, font=f_section, fill=THEME_GOLD)

# Bullets
bullets = [
    (
        "Ventaja Matematica Real (+6.9% sobre Vegas):",
        "El punto de equilibrio en cuotas promedio (-110) es 52.4%.\nNuestro modelo cerro en 59.3%, generando beneficio consistente."
    ),
    (
        "Muestra Significativa (54 Picks Auditados):",
        "No es suerte de 3 jugadas. Son 54 selecciones en los 6 mercados\nde props NFL evaluadas en tiempo real sin manipulacion."
    ),
    (
        "Disciplina Estricta de Bankroll:",
        "Todas las selecciones se gestionan con 1 unidad fija.\nCero martingalas, cero apuestas desesperadas para 'recuperar'."
    )
]

b_y = card_y + 105
for b_title, b_desc in bullets:
    draw.text((CARD_X + 50, b_y), f"• {b_title}", font=f_bullet_bold, fill=(255, 255, 255))
    b_y += 42
    for line in b_desc.split("\n"):
        draw.text((CARD_X + 68, b_y), line, font=f_bullet_text, fill=(148, 163, 184))
        b_y += 34
    b_y += 24

# -------------------------------------------------------------
# 5. TRANSPARENCY BANNER (y: 1500 - 1630)
# -------------------------------------------------------------
t_y = 1495
draw.rounded_rectangle([CARD_X, t_y, CARD_X + CARD_W, t_y + 125], radius=24, fill=(10, 16, 26), outline=(35, 48, 70), width=2)

t_top = "POLITICA 100% CERO HUMO"
t_bot = "Todos los picks se auditan en nuestra base de datos publica SQL."
draw.text(((W - draw.textlength(t_top, font=f_trust_title)) // 2, t_y + 25), t_top, font=f_trust_title, fill=THEME_GREEN)
draw.text(((W - draw.textlength(t_bot, font=f_trust_sub)) // 2, t_y + 70), t_bot, font=f_trust_sub, fill=(203, 213, 225))

# -------------------------------------------------------------
# 6. FOOTER BUTTON (y: 1650 - 1740)
# -------------------------------------------------------------
btn_y = 1645
btn_w = CARD_W - 80
btn_x = (W - btn_w) // 2
draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + 85], radius=22, fill=(0, 136, 204))
btn_text = "Canal Oficial de Picks: @overdogai"
draw.text(((W - draw.textlength(btn_text, font=f_cta)) // 2, btn_y + 24), btn_text, font=f_cta, fill=(255, 255, 255))

disc = "Sports Intelligence · Datos matemáticos sin sesgos emocionales"
draw.text(((W - draw.textlength(disc, font=f_sub)) // 2, 1770), disc, font=f_sub, fill=(100, 116, 139))

# Save
out_png = "assets/tarjeta_rendimiento_semana8.png"
out_jpg = "assets/tarjeta_rendimiento_semana8.jpg"

img.save(out_png, "PNG")
img.save(out_jpg, "JPEG", quality=95)

print("Tarjeta de rendimiento Semana 8 generada exitosamente en:", out_png)
