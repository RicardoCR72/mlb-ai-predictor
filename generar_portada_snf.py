import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

# 1. Base Setup
W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

f_badge = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_match = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_title = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 88)
f_subtitle = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 36)
f_pick_tag = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 28)
f_pick_main = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 72)
f_odds = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 34)
f_stat_val = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 48)
f_stat_lbl = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 20)
f_hook = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 36)
f_tg = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)

# Load background frame (Daniels in action)
bg_path = "scratch/crop_frame2.png"
if os.path.exists(bg_path):
    bg_raw = Image.open(bg_path).convert("RGB")
else:
    bg_raw = Image.new("RGB", (W, H), (15, 23, 42))

# Enhance contrast & slightly darken player background
enhancer = ImageEnhance.Brightness(bg_raw)
bg_dark = enhancer.enhance(0.55)
bg_dark = bg_dark.filter(ImageFilter.GaussianBlur(radius=3))

# Add deep dark athletic gradient
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
odraw = ImageDraw.Draw(overlay)

# Gradient top-to-bottom
for y in range(H):
    # heavy dark on top, dark on bottom, slightly clearer in middle
    if y < 400:
        alpha = int(220 + (400 - y) / 400 * 35)
    elif y > 1400:
        alpha = int(220 + (y - 1400) / 520 * 35)
    else:
        alpha = 185
    odraw.line([(0, y), (W, y)], fill=(10, 16, 28, alpha))

base = Image.alpha_composite(bg_dark.convert("RGBA"), overlay)
draw = ImageDraw.Draw(base)

# -------------------------------------------------------------
# 1. HEADER (y: 180 - 320)
# -------------------------------------------------------------
# SNF Badge
badge_text = "🏈 SUNDAY NIGHT FOOTBALL · SEMANA 8"
bw = draw.textlength(badge_text, font=f_badge) + 40
bx = (W - bw) // 2
by = 180
draw.rounded_rectangle([bx, by, bx + bw, by + 48], radius=24, fill=(16, 24, 40, 230), outline=(255, 215, 0, 255), width=2)
draw.text(((W - draw.textlength(badge_text, font=f_badge)) // 2, by + 10), badge_text, font=f_badge, fill=(255, 215, 0, 255))

# Matchup
match_text = "PHILADELPHIA EAGLES  @  WASHINGTON COMMANDERS"
draw.text(((W - draw.textlength(match_text, font=f_match)) // 2, 250), match_text, font=f_match, fill=(226, 232, 240, 255))

# -------------------------------------------------------------
# 2. PLAYER HEADLINE (y: 330 - 500)
# -------------------------------------------------------------
# Overdog AI Logo mark
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((70, 70), Image.Resampling.LANCZOS)
    base.paste(logo, (W // 2 - 35, 320), logo)

title_p1 = "JAYDEN DANIELS"
draw.text(((W - draw.textlength(title_p1, font=f_title)) // 2 + 3, 403), title_p1, font=f_title, fill=(0, 0, 0, 200))
draw.text(((W - draw.textlength(title_p1, font=f_title)) // 2, 400), title_p1, font=f_title, fill=(255, 255, 255, 255))

sub_text = "PICK OFICIAL PROYECTADO POR IA"
draw.text(((W - draw.textlength(sub_text, font=f_subtitle)) // 2, 500), sub_text, font=f_subtitle, fill=(0, 255, 163, 255))

# -------------------------------------------------------------
# 3. CENTRAL PICK HUD / HERO CARD (y: 570 - 1160) - PERFECT FOR IG/TIKTOK GRID
# -------------------------------------------------------------
card_w = 960
card_h = 580
card_x = (W - card_w) // 2
card_y = 570

# Outer Neon Glow
draw.rounded_rectangle([card_x - 3, card_y - 3, card_x + card_w + 3, card_y + card_h + 3], radius=38, outline=(0, 255, 163, 100), width=6)
# Inner Solid Dark Glass Card
draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=34, fill=(11, 19, 34, 250), outline=(0, 255, 163, 240), width=3)

# Inside Card: Tag Pill
ptag = "PROP CONFIRMADA · MODELO MATEMÁTICO"
draw.rounded_rectangle([card_x + 30, card_y + 35, card_x + 30 + draw.textlength(ptag, font=f_pick_tag) + 30, card_y + 80], radius=16, fill=(15, 23, 42, 255), outline=(148, 163, 184, 180), width=1)
draw.text((card_x + 45, card_y + 44), ptag, font=f_pick_tag, fill=(148, 163, 184, 255))

# The Main Prop Pick
prop_main = "MENOS DE 1.5 PASES TD"
draw.text((card_x + 40, card_y + 105), prop_main, font=f_pick_main, fill=(255, 255, 255, 255))

# Line & Odds
odds_str = "Línea: 1.50 Pases  ·  Cuota: -147 (1.68)  ·  DraftKings"
draw.text((card_x + 42, card_y + 195), odds_str, font=f_odds, fill=(255, 215, 0, 255))

# Divider line
draw.line([(card_x + 35, card_y + 255), (card_x + card_w - 35, card_y + 255)], fill=(30, 41, 59, 255), width=2)

# 3 Stat Columns
cols = [
    ("PROYECCIÓN IA", "1.09 TDs", (0, 255, 163, 255)),
    ("PROBABILIDAD", "59.8%", (56, 189, 248, 255)),
    ("VALOR ESPERADO", "+7.2% EV", (255, 215, 0, 255))
]

col_w = (card_w - 70) // 3
for idx, (lbl, val, col) in enumerate(cols):
    cx = card_x + 35 + idx * col_w
    cy = card_y + 285
    # Small box for each metric
    draw.rounded_rectangle([cx + 5, cy, cx + col_w - 10, cy + 130], radius=20, fill=(15, 23, 42, 255), outline=(30, 41, 59, 255), width=2)
    # Label
    draw.text((cx + (col_w - 10 - draw.textlength(lbl, font=f_stat_lbl)) // 2 + 5, cy + 22), lbl, font=f_stat_lbl, fill=(148, 163, 184, 255))
    # Value
    draw.text((cx + (col_w - 10 - draw.textlength(val, font=f_stat_val)) // 2 + 5, cy + 58), val, font=f_stat_val, fill=col)

# Bottom note inside card
c_note = "⭐ Alta probabilidad estadística por tendencia terrestre de Washington"
draw.text((card_x + (card_w - draw.textlength(c_note, font=f_pick_tag)) // 2, card_y + 445), c_note, font=f_pick_tag, fill=(226, 232, 240, 255))

# Status pill inside card
status_text = "🟢 ACTIVO PARA ESTA NOCHE"
sw = draw.textlength(status_text, font=f_pick_tag) + 36
sx = card_x + (card_w - sw) // 2
draw.rounded_rectangle([sx, card_y + 495, sx + sw, card_y + 545], radius=18, fill=(6, 78, 59, 230), outline=(0, 255, 163, 255), width=2)
draw.text((sx + 18, card_y + 506), status_text, font=f_pick_tag, fill=(0, 255, 163, 255))

# -------------------------------------------------------------
# 4. HOOK PILL (y: 1190 - 1280)
# -------------------------------------------------------------
hook_box_y = 1190
draw.rounded_rectangle([card_x, hook_box_y, card_x + card_w, hook_box_y + 90], radius=24, fill=(15, 23, 42, 230), outline=(56, 189, 248, 180), width=2)
h_t1 = "📊 100% Datos y Modelos Matemáticos · Cero Humo"
draw.text((card_x + (card_w - draw.textlength(h_t1, font=f_hook)) // 2, hook_box_y + 28), h_t1, font=f_hook, fill=(255, 255, 255, 255))

# -------------------------------------------------------------
# 5. TELEGRAM CALL TO ACTION & BRAND FOOTER (y: 1320 - 1580)
# -------------------------------------------------------------
cta_y = 1320
draw.rounded_rectangle([card_x + 40, cta_y, card_x + card_w - 40, cta_y + 110], radius=28, fill=(0, 136, 204, 255))
tg_title = "CANAL DE TELEGRAM: @overdogai"
tg_sub = "👉 Enlace directo en la biografía del perfil"
draw.text(((W - draw.textlength(tg_title, font=f_odds)) // 2, cta_y + 18), tg_title, font=f_odds, fill=(255, 255, 255, 255))
draw.text(((W - draw.textlength(tg_sub, font=f_pick_tag)) // 2, cta_y + 65), tg_sub, font=f_pick_tag, fill=(255, 255, 255, 255))

# Bottom Brand line
brand_str = "OVERDOG AI · SPORTS INTELLIGENCE"
draw.text(((W - draw.textlength(brand_str, font=f_brand)) // 2, 1470), brand_str, font=f_brand, fill=(0, 255, 163, 255))

units_str = "Gestión de Bankroll: 1 Unidad Fija · Juego Responsable"
draw.text(((W - draw.textlength(units_str, font=f_pick_tag)) // 2, 1525), units_str, font=f_pick_tag, fill=(148, 163, 184, 255))

# -------------------------------------------------------------
# SAVE AS BOTH PNG AND JPG
# -------------------------------------------------------------
out_png = "assets/portada_snf_daniels.png"
out_jpg = "assets/portada_snf_daniels.jpg"

base_rgb = base.convert("RGB")
base.save(out_png, "PNG")
base_rgb.save(out_jpg, "JPEG", quality=95)

print(f"Portada guardada exitosamente en:\n- {out_png}\n- {out_jpg}")
