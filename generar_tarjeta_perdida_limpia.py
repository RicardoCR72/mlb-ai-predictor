import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

# Clean, modern font hierarchy
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 36)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_badge = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 24)
f_team = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 76)
f_score = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 84)
f_pick_lbl = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_res_big = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 64)
f_stat_bold = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_stat_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 26)
f_trust = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_cta = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)

# Deep dark solid gradient with rich margins
y_coords = np.linspace(0, 1, H)
r = (14 * (1 - y_coords) + 8 * y_coords).astype(np.uint8)
g = (18 * (1 - y_coords) + 10 * y_coords).astype(np.uint8)
b = (28 * (1 - y_coords) + 16 * y_coords).astype(np.uint8)

bg = np.zeros((H, W, 3), dtype=np.uint8)
bg[:, :, 0] = r[:, None]
bg[:, :, 1] = g[:, None]
bg[:, :, 2] = b[:, None]

img = Image.fromarray(bg).convert("RGBA")
draw = ImageDraw.Draw(img)

# Subtle crimson accent glow at the top center
for rad in range(160, 0, -4):
    alpha = int(22 * (rad / 160))
    draw.ellipse([W // 2 - rad * 3, 200 - rad, W // 2 + rad * 3, 200 + rad], fill=(239, 68, 68, alpha))

# Safe width: 880px (100px margins on both sides!)
CARD_X = 100
CARD_W = 880

# -------------------------------------------------------------
# 1. HEADER (y: 160 - 340)
# -------------------------------------------------------------
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((96, 96), Image.Resampling.LANCZOS)
    img.paste(logo, ((W - 96) // 2, 160), logo)

draw.text(((W - draw.textlength("OVERDOG AI", font=f_brand)) // 2, 275), "OVERDOG AI", font=f_brand, fill=(255, 255, 255, 255))

tag_header = "AUDITORÍA & LIQUIDACIÓN OFICIAL"
tw = draw.textlength(tag_header, font=f_badge) + 36
draw.rounded_rectangle([(W - tw) // 2, 335, (W + tw) // 2, 380], radius=18, fill=(26, 18, 24, 255), outline=(239, 68, 68, 180), width=2)
draw.text(((W - draw.textlength(tag_header, font=f_badge)) // 2, 345), tag_header, font=f_badge, fill=(248, 113, 113, 255))

# -------------------------------------------------------------
# 2. MAIN HERO CARD (ONE UNIFIED CLEAN CARD) (y: 430 - 1460)
# -------------------------------------------------------------
card_y = 430
card_h = 1040

# Outer subtle border glow
draw.rounded_rectangle([CARD_X - 2, card_y - 2, CARD_X + CARD_W + 2, card_y + card_h + 2], radius=34, outline=(239, 68, 68, 80), width=4)
# Card base
draw.rounded_rectangle([CARD_X, card_y, CARD_X + CARD_W, card_y + card_h], radius=32, fill=(15, 21, 35, 250), outline=(239, 68, 68, 220), width=2)

# Subheader inside card
s_tag = "🏀 NBA · TEMPORADA REGULAR"
draw.text(((W - draw.textlength(s_tag, font=f_sub)) // 2, card_y + 40), s_tag, font=f_sub, fill=(148, 163, 184, 255))

# Scoreboard Box (Super clean & prominent)
score_box_y = card_y + 90
draw.rounded_rectangle([CARD_X + 40, score_box_y, CARD_X + CARD_W - 40, score_box_y + 190], radius=24, fill=(10, 15, 26, 255), outline=(40, 50, 70, 255), width=2)

# Brooklyn Nets (Left)
draw.text((CARD_X + 80, score_box_y + 35), "NETS", font=f_team, fill=(255, 255, 255, 255))
draw.text((CARD_X + 80, score_box_y + 125), "Brooklyn", font=f_sub, fill=(148, 163, 184, 255))
draw.text((CARD_X + 310, score_box_y + 45), "98", font=f_score, fill=(0, 255, 163, 255))

# VS Divider
draw.text((CARD_X + 420, score_box_y + 60), "-", font=f_team, fill=(100, 116, 139, 255))

# Indiana Pacers (Right)
draw.text((CARD_X + 490, score_box_y + 45), "90", font=f_score, fill=(239, 68, 68, 255))
draw.text((CARD_X + 620, score_box_y + 35), "PACERS", font=f_team, fill=(255, 255, 255, 255))
draw.text((CARD_X + 620, score_box_y + 125), "Indiana", font=f_sub, fill=(148, 163, 184, 255))

# Pick Registered Info
pick_y = card_y + 325
p_lbl = "Pick Enviado: Indiana Pacers Moneyline"
draw.text(((W - draw.textlength(p_lbl, font=f_pick_lbl)) // 2, pick_y), p_lbl, font=f_pick_lbl, fill=(226, 232, 240, 255))

# The Big Result Pill (Clean, punchy)
res_y = pick_y + 65
res_text = "❌ NO CUBIERTA   (-1.00 U)"
rw = draw.textlength(res_text, font=f_res_big) + 60
rx = (W - rw) // 2
draw.rounded_rectangle([rx, res_y, rx + rw, res_y + 105], radius=26, fill=(55, 12, 18, 255), outline=(239, 68, 68, 255), width=3)
draw.text(((W - draw.textlength(res_text, font=f_res_big)) // 2, res_y + 16), res_text, font=f_res_big, fill=(255, 255, 255, 255))

# Divider
draw.line([(CARD_X + 60, res_y + 150), (CARD_X + CARD_W - 60, res_y + 150)], fill=(35, 45, 65, 255), width=2)

# Quick Data Stats (Only 2 clear, uncluttered points)
stat_title = "📊 ¿QUÉ SUCEDIÓ EN EL PARTIDO?"
draw.text(((W - draw.textlength(stat_title, font=f_badge)) // 2, res_y + 185), stat_title, font=f_badge, fill=(255, 215, 0, 255))

s1_bold = "• Colapso Ofensivo:"
s1_desc = "Pacers anotaron solo 90 pts (promedian 118.5 pts/juego)."
draw.text((CARD_X + 70, res_y + 245), s1_bold, font=f_stat_bold, fill=(255, 255, 255, 255))
draw.text((CARD_X + 70, res_y + 290), s1_desc, font=f_stat_sub, fill=(148, 163, 184, 255))

s2_bold = "• Pésima Efectividad:"
s2_desc = "38.2% de campo y 24% en triples ante la defensa de Brooklyn."
draw.text((CARD_X + 70, res_y + 345), s2_bold, font=f_stat_bold, fill=(255, 255, 255, 255))
draw.text((CARD_X + 70, res_y + 390), s2_desc, font=f_stat_sub, fill=(148, 163, 184, 255))

# -------------------------------------------------------------
# 3. FOOTER TRUST & CTA (y: 1530 - 1800)
# -------------------------------------------------------------
# Brand Promise Box
trust_y = 1520
draw.rounded_rectangle([CARD_X, trust_y, CARD_X + CARD_W, trust_y + 110], radius=24, fill=(12, 18, 30, 240), outline=(35, 45, 65, 255), width=2)

t_line1 = "🛡️ POLÍTICA 100% CERO HUMO"
t_line2 = "En Overdog AI no se borran picks ni se alteran balances."
draw.text(((W - draw.textlength(t_line1, font=f_trust)) // 2, trust_y + 22), t_line1, font=f_trust, fill=(0, 255, 163, 255))
draw.text(((W - draw.textlength(t_line2, font=f_sub)) // 2, trust_y + 64), t_line2, font=f_sub, fill=(148, 163, 184, 255))

# Telegram Button
btn_y = 1665
btn_w = CARD_W - 60
btn_x = (W - btn_w) // 2
draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + 80], radius=22, fill=(0, 136, 204, 255))
btn_txt = "Canal Oficial de Auditoría: @overdogai"
draw.text(((W - draw.textlength(btn_txt, font=f_cta)) // 2, btn_y + 22), btn_txt, font=f_cta, fill=(255, 255, 255, 255))

disc = "Gestión responsable · 1 Unidad fija por jugada"
draw.text(((W - draw.textlength(disc, font=f_sub)) // 2, 1780), disc, font=f_sub, fill=(100, 116, 139, 255))

# Save
out_png = "assets/tarjeta_liquidacion_pacers_limpia.png"
out_jpg = "assets/tarjeta_liquidacion_pacers_limpia.jpg"

img_rgb = img.convert("RGB")
img.save(out_png, "PNG")
img_rgb.save(out_jpg, "JPEG", quality=95)

print("Tarjeta limpia guardada en:", out_png)
