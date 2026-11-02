import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 36)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_badge = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 24)
f_team = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 72)
f_score = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 84)
f_pick_lbl = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_res_big = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 66)
f_stat_bold = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_stat_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 26)
f_trust = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_cta = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_units = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 54)

# Create deep dark gradient with emerald athletic glow
y_coords = np.linspace(0, 1, H)
r = (10 * (1 - y_coords) + 6 * y_coords).astype(np.uint8)
g = (24 * (1 - y_coords) + 14 * y_coords).astype(np.uint8)
b = (28 * (1 - y_coords) + 18 * y_coords).astype(np.uint8)

bg = np.zeros((H, W, 3), dtype=np.uint8)
bg[:, :, 0] = r[:, None]
bg[:, :, 1] = g[:, None]
bg[:, :, 2] = b[:, None]

img = Image.fromarray(bg).convert("RGBA")
draw = ImageDraw.Draw(img)

# Emerald green ambient glow at top
for rad in range(180, 0, -4):
    alpha = int(30 * (rad / 180))
    draw.ellipse([W // 2 - rad * 3, 200 - rad, W // 2 + rad * 3, 200 + rad], fill=(0, 255, 163, alpha))

CARD_X = 100
CARD_W = 880

# -------------------------------------------------------------
# 1. HEADER (y: 160 - 340)
# -------------------------------------------------------------
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((96, 96), Image.Resampling.LANCZOS)
    img.paste(logo, ((W - 96) // 2, 160), logo)

draw.text(((W - draw.textlength("OVERDOG AI", font=f_brand)) // 2, 275), "OVERDOG AI", font=f_brand, fill=(0, 255, 163, 255))

tag_header = "PICK COBRADO · AUDITORÍA OFICIAL"
tw = draw.textlength(tag_header, font=f_badge) + 36
draw.rounded_rectangle([(W - tw) // 2, 335, (W + tw) // 2, 380], radius=18, fill=(6, 40, 30, 255), outline=(0, 255, 163, 220), width=2)
draw.text(((W - draw.textlength(tag_header, font=f_badge)) // 2, 345), tag_header, font=f_badge, fill=(0, 255, 163, 255))

# -------------------------------------------------------------
# 2. MAIN HERO CARD (y: 430 - 1460)
# -------------------------------------------------------------
card_y = 430
card_h = 1040

# Outer glowing border
draw.rounded_rectangle([CARD_X - 2, card_y - 2, CARD_X + CARD_W + 2, card_y + card_h + 2], radius=34, outline=(0, 255, 163, 80), width=4)
draw.rounded_rectangle([CARD_X, card_y, CARD_X + CARD_W, card_y + card_h], radius=32, fill=(11, 20, 28, 250), outline=(0, 255, 163, 240), width=3)

# Subheader inside card
s_tag = "🏈 SUNDAY NIGHT FOOTBALL · SEMANA 8 NFL"
draw.text(((W - draw.textlength(s_tag, font=f_sub)) // 2, card_y + 40), s_tag, font=f_sub, fill=(255, 215, 0, 255))

# Scoreboard Box
score_box_y = card_y + 90
draw.rounded_rectangle([CARD_X + 40, score_box_y, CARD_X + CARD_W - 40, score_box_y + 190], radius=24, fill=(10, 16, 24, 255), outline=(30, 50, 65, 255), width=2)

# Eagles (Left)
draw.text((CARD_X + 80, score_box_y + 35), "EAGLES", font=f_team, fill=(148, 163, 184, 255))
draw.text((CARD_X + 80, score_box_y + 125), "Philadelphia", font=f_sub, fill=(100, 116, 139, 255))
draw.text((CARD_X + 330, score_box_y + 45), "10", font=f_score, fill=(148, 163, 184, 255))

# Divider
draw.text((CARD_X + 425, score_box_y + 60), "-", font=f_team, fill=(100, 116, 139, 255))

# Commanders (Right)
draw.text((CARD_X + 490, score_box_y + 45), "27", font=f_score, fill=(0, 255, 163, 255))
draw.text((CARD_X + 580, score_box_y + 35), "COMMANDERS", font=f_team, fill=(255, 255, 255, 255))
draw.text((CARD_X + 580, score_box_y + 125), "Washington · Final", font=f_sub, fill=(0, 255, 163, 255))

# Pick Registered Info
pick_y = card_y + 325
p_lbl = "Jayden Daniels - Menos de 1.5 Pases de TD"
draw.text(((W - draw.textlength(p_lbl, font=f_pick_lbl)) // 2, pick_y), p_lbl, font=f_pick_lbl, fill=(255, 255, 255, 255))

# Big Winning Result Pill
res_y = pick_y + 65
res_text = "🟢 VERDE / COBRADA   (+0.68 U)"
rw = draw.textlength(res_text, font=f_res_big) + 60
rx = (W - rw) // 2
draw.rounded_rectangle([rx, res_y, rx + rw, res_y + 105], radius=26, fill=(6, 78, 59, 255), outline=(0, 255, 163, 255), width=3)
draw.text(((W - draw.textlength(res_text, font=f_res_big)) // 2, res_y + 16), res_text, font=f_res_big, fill=(255, 255, 255, 255))

# Divider
draw.line([(CARD_X + 60, res_y + 150), (CARD_X + CARD_W - 60, res_y + 150)], fill=(20, 50, 45, 255), width=2)

# Quick Data Stats
stat_title = "🎯 PRECISIÓN QUIRÚRGICA DEL ALGORITMO"
draw.text(((W - draw.textlength(stat_title, font=f_badge)) // 2, res_y + 185), stat_title, font=f_badge, fill=(255, 215, 0, 255))

s1_bold = "• Proyección vs Realidad:"
s1_desc = "El modelo proyectó 1.09 TDs → Daniels lanzó exactamente 1 TD."
draw.text((CARD_X + 70, res_y + 245), s1_bold, font=f_stat_bold, fill=(0, 255, 163, 255))
draw.text((CARD_X + 70, res_y + 290), s1_desc, font=f_stat_sub, fill=(226, 232, 240, 255))

s2_bold = "• Lectura Táctica Impecable:"
s2_desc = "Washington liquidó por tierra y defensa; Daniels lanzó solo 217 yds."
draw.text((CARD_X + 70, res_y + 345), s2_bold, font=f_stat_bold, fill=(0, 255, 163, 255))
draw.text((CARD_X + 70, res_y + 390), s2_desc, font=f_stat_sub, fill=(226, 232, 240, 255))

# -------------------------------------------------------------
# 3. FOOTER TRUST & CTA (y: 1520 - 1800)
# -------------------------------------------------------------
trust_y = 1520
draw.rounded_rectangle([CARD_X, trust_y, CARD_X + CARD_W, trust_y + 110], radius=24, fill=(10, 18, 25, 240), outline=(20, 50, 45, 255), width=2)

t_line1 = "🛡️ CIERRE OFICIAL SUNDAY NIGHT FOOTBALL"
t_line2 = "Cuota: -147 (1.68) · Stake 1.00 U · Retorno Neto: +0.68 U"
draw.text(((W - draw.textlength(t_line1, font=f_trust)) // 2, trust_y + 22), t_line1, font=f_trust, fill=(255, 215, 0, 255))
draw.text(((W - draw.textlength(t_line2, font=f_sub)) // 2, trust_y + 64), t_line2, font=f_sub, fill=(226, 232, 240, 255))

# Telegram Button
btn_y = 1665
btn_w = CARD_W - 60
btn_x = (W - btn_w) // 2
draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + 80], radius=22, fill=(0, 136, 204, 255))
btn_txt = "Canal Oficial de Picks: @overdogai"
draw.text(((W - draw.textlength(btn_txt, font=f_cta)) // 2, btn_y + 22), btn_txt, font=f_cta, fill=(255, 255, 255, 255))

disc = "Sports Intelligence · Datos matemáticos sin sesgos"
draw.text(((W - draw.textlength(disc, font=f_sub)) // 2, 1780), disc, font=f_sub, fill=(100, 116, 139, 255))

# Save
out_png = "assets/tarjeta_victoria_snf_daniels.png"
out_jpg = "assets/tarjeta_victoria_snf_daniels.jpg"

img_rgb = img.convert("RGB")
img.save(out_png, "PNG")
img_rgb.save(out_jpg, "JPEG", quality=95)

print("Tarjeta verde guardada en:", out_png)
