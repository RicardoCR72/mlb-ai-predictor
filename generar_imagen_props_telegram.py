import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1350

# 1. Background: Dark sleek gradient from #0D131F to #070A10
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

# Load fonts
font_dir = "C:/Windows/Fonts"
f_title_big = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 52)
f_title_sub = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
f_pill = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 18)
f_player = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 40)
f_meta = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 20)
f_stat_lbl = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 15)
f_stat_val = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 34)
f_arrow = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_pick_bar = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
f_footer = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)

# Top Bar: Logo & Brand
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((68, 68), Image.Resampling.LANCZOS)
    img.paste(logo, (50, 48), logo)

draw.text((135, 52), "OVERDOG AI", font=f_brand, fill=(0, 255, 163, 255))
draw.text((135, 86), "SPORTS INTELLIGENCE · CERO HUMO", font=f_title_sub, fill=(148, 163, 184, 255))

# Date Pill Top Right
draw.rounded_rectangle([750, 55, 1030, 100], radius=22, fill=(24, 34, 53, 255), outline=(0, 229, 255, 140), width=1)
draw.text((780, 68), "DOMINGO NFL · SEMANA 8", font=f_pill, fill=(0, 229, 255, 255))

# Main Title Header
draw.text((50, 145), "TOP PLAYER PROPS (+EV)", font=f_title_big, fill=(255, 255, 255, 255))
draw.text((50, 212), "Discrepancias estadísticas del modelo frente a las líneas del mercado", font=f_title_sub, fill=(148, 163, 184, 255))

# Cards Data
cards = [
    {
        "badge_text": "ANOMALÍA (+EV: +22.6%)",
        "badge_bg": (0, 255, 163, 255),
        "badge_fg": (7, 10, 16, 255),
        "player": "AARON JONES",
        "team_meta": "RB · MINNESOTA VIKINGS  (MIN @ DET)",
        "market": "YARDAS TERRESTRES",
        "line": "28.5",
        "proy": "66.5 YDS",
        "pick": "PICK: OVER 28.5",
        "cuota": "MOMIO: -113 (1.88)",
        "prob": "PROB: 65.0%",
        "accent": (0, 255, 163, 255)
    },
    {
        "badge_text": "ALTO VOLUMEN (+EV: +22.6%)",
        "badge_bg": (255, 184, 0, 255),
        "badge_fg": (7, 10, 16, 255),
        "player": "JONATHAN TAYLOR",
        "team_meta": "RB · INDIANAPOLIS COLTS  (IND @ JAX)",
        "market": "YARDAS TERRESTRES",
        "line": "48.5",
        "proy": "70.5 YDS",
        "pick": "PICK: OVER 48.5",
        "cuota": "MOMIO: -113 (1.88)",
        "prob": "PROB: 65.0%",
        "accent": (255, 184, 0, 255)
    },
    {
        "badge_text": "PLUS MONEY VALUE (+EV: +25.7%)",
        "badge_bg": (56, 189, 248, 255),
        "badge_fg": (7, 10, 16, 255),
        "player": "JA'MARR CHASE",
        "team_meta": "WR · CINCINNATI BENGALS  (TEN @ CIN)",
        "market": "RECEPCIONES",
        "line": "6.5",
        "proy": "5.6 REC",
        "pick": "PICK: UNDER 6.5",
        "cuota": "MOMIO: +114 (2.14)",
        "prob": "PROB: 58.7%",
        "accent": (56, 189, 248, 255)
    }
]

y_start = 270
card_h = 285
spacing = 30

for idx, c in enumerate(cards):
    cy = y_start + idx * (card_h + spacing)
    
    # Outer Card
    draw.rounded_rectangle([50, cy, WIDTH - 50, cy + card_h], radius=22, fill=(19, 27, 43, 255), outline=(38, 52, 80, 255), width=2)
    
    # Left accent line
    draw.rounded_rectangle([50, cy + 25, 56, cy + card_h - 25], radius=3, fill=c["accent"])
    
    # Badge (Pill)
    badge_w = int(draw.textlength(c["badge_text"], font=f_pill)) + 36
    draw.rounded_rectangle([80, cy + 22, 80 + badge_w, cy + 56], radius=17, fill=c["badge_bg"])
    draw.text((98, cy + 28), c["badge_text"], font=f_pill, fill=c["badge_fg"])
    
    # Market on top right
    m_w = draw.textlength(c["market"], font=f_title_sub)
    draw.text((WIDTH - 85 - m_w, cy + 28), c["market"], font=f_title_sub, fill=(148, 163, 184, 255))
    
    # Player Name & Meta
    draw.text((80, cy + 72), c["player"], font=f_player, fill=(255, 255, 255, 255))
    draw.text((80, cy + 124), c["team_meta"], font=f_meta, fill=(148, 163, 184, 255))
    
    # Stats Box
    box_x = 570
    box_y = cy + 70
    box_w = 430
    box_h = 100
    draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=16, fill=(12, 17, 28, 255), outline=(32, 45, 70, 255), width=1)
    
    # Line column
    draw.text((box_x + 25, box_y + 18), "LÍNEA CASA", font=f_stat_lbl, fill=(148, 163, 184, 255))
    draw.text((box_x + 25, box_y + 45), c["line"], font=f_stat_val, fill=(241, 245, 249, 255))
    
    # Arrow separator
    draw.text((box_x + 155, box_y + 44), "->", font=f_arrow, fill=c["accent"])
    
    # Proy column
    draw.text((box_x + 220, box_y + 18), "PROYECCIÓN IA", font=f_stat_lbl, fill=(0, 255, 163, 255))
    draw.text((box_x + 220, box_y + 45), c["proy"], font=f_stat_val, fill=(0, 255, 163, 255))
    
    # Bottom Bar inside card
    bar_y = cy + 200
    draw.rounded_rectangle([80, bar_y, WIDTH - 80, bar_y + 60], radius=14, fill=(28, 39, 62, 255))
    
    draw.text((105, bar_y + 16), c["pick"], font=f_pick_bar, fill=(255, 255, 255, 255))
    draw.text((450, bar_y + 16), c["cuota"], font=f_pick_bar, fill=(255, 215, 0, 255))
    draw.text((800, bar_y + 16), c["prob"], font=f_pick_bar, fill=(0, 255, 163, 255))

# Footer
foot_y = 1230
draw.line([(50, foot_y), (WIDTH - 50, foot_y)], fill=(32, 45, 70, 255), width=2)

draw.text((50, foot_y + 32), "GESTIÓN: 1 UNIDAD FIJA · SIN CORAZONADAS, SOLO DATOS", font=f_footer, fill=(148, 163, 184, 255))

# Telegram Pill
tg_w = 260
tg_box = [WIDTH - 50 - tg_w, foot_y + 20, WIDTH - 50, foot_y + 72]
draw.rounded_rectangle(tg_box, radius=26, fill=(0, 136, 204, 255))
draw.text((WIDTH - 50 - tg_w + 32, foot_y + 32), "t.me/overdogai", font=f_footer, fill=(255, 255, 255, 255))

# Save PNG and JPG
out_png = "assets/nfl_props_domingo.png"
out_jpg = "assets/nfl_props_domingo.jpg"

img.save(out_png, "PNG")
img.convert("RGB").save(out_jpg, "JPEG", quality=95)

# Also copy to artifacts directory
artifact_dir = "C:/Users/rcabr/.gemini/antigravity/brain/8db99efe-a7c9-44ba-88ff-2a8317829757"
if os.path.exists(artifact_dir):
    import shutil
    shutil.copy2(out_png, os.path.join(artifact_dir, "nfl_props_domingo.png"))
    shutil.copy2(out_jpg, os.path.join(artifact_dir, "nfl_props_domingo.jpg"))

print("¡Listo! Imágenes actualizadas perfectamente.")
