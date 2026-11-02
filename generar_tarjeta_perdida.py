import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

f_title = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 68)
f_h2 = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 46)
f_score = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 90)
f_badge = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_body = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 22)
f_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 34)

# Create deep dark gradient background with subtle crimson/dark slate tones
y_coords = np.linspace(0, 1, H)
r = (18 * (1 - y_coords) + 10 * y_coords).astype(np.uint8)
g = (14 * (1 - y_coords) + 12 * y_coords).astype(np.uint8)
b = (24 * (1 - y_coords) + 18 * y_coords).astype(np.uint8)

bg = np.zeros((H, W, 3), dtype=np.uint8)
bg[:, :, 0] = r[:, None]
bg[:, :, 1] = g[:, None]
bg[:, :, 2] = b[:, None]

img = Image.fromarray(bg).convert("RGBA")
draw = ImageDraw.Draw(img)

# Top crimson subtle ambient glow
for i in range(120):
    alpha = int(40 * (1 - i / 120))
    draw.line([(0, i), (W, i)], fill=(239, 68, 68, alpha))

# -------------------------------------------------------------
# 1. HEADER & LOGO (y: 120 - 320)
# -------------------------------------------------------------
logo_path = "assets/overdog_logo_transparent.png"
if os.path.exists(logo_path):
    logo = Image.open(logo_path).convert("RGBA").resize((90, 90), Image.Resampling.LANCZOS)
    img.paste(logo, ((W - 90) // 2, 110), logo)

draw.text(((W - draw.textlength("OVERDOG AI", font=f_brand)) // 2, 215), "OVERDOG AI", font=f_brand, fill=(255, 255, 255, 255))

# Transparency Pill
pill_text = "AUDITORÍA & TRANSPARENCIA · CERO HUMO"
pw = draw.textlength(pill_text, font=f_badge) + 36
draw.rounded_rectangle([(W - pw) // 2, 275, (W + pw) // 2, 320], radius=20, fill=(30, 20, 30, 255), outline=(239, 68, 68, 200), width=2)
draw.text(((W - draw.textlength(pill_text, font=f_badge)) // 2, 285), pill_text, font=f_badge, fill=(248, 113, 113, 255))

# -------------------------------------------------------------
# 2. MATCH & SCORE HERO (y: 350 - 580)
# -------------------------------------------------------------
card_w = 940
cx = (W - card_w) // 2
draw.rounded_rectangle([cx, 350, cx + card_w, 570], radius=28, fill=(15, 20, 32, 250), outline=(51, 65, 85, 255), width=2)

draw.text(((W - draw.textlength("🏀 NBA · TEMPORADA REGULAR", font=f_sub)) // 2, 375), "🏀 NBA · TEMPORADA REGULAR", font=f_sub, fill=(148, 163, 184, 255))

# Teams & Score
match_str = "BROOKLYN NETS  98  -  90  INDIANA PACERS"
draw.text(((W - draw.textlength(match_str, font=f_title)) // 2, 420), match_str, font=f_title, fill=(255, 255, 255, 255))
venue_str = "Gainbridge Fieldhouse · Resultado Oficial Final"
draw.text(((W - draw.textlength(venue_str, font=f_sub)) // 2, 515), venue_str, font=f_sub, fill=(148, 163, 184, 255))

# -------------------------------------------------------------
# 3. SETTLEMENT BOX (y: 600 - 930)
# -------------------------------------------------------------
box_y = 600
box_h = 330
# Crimson border card
draw.rounded_rectangle([cx, box_y, cx + card_w, box_y + box_h], radius=32, fill=(26, 18, 24, 250), outline=(239, 68, 68, 255), width=3)

# Tag inside
sub_pick = "PICK REGISTRADO"
draw.text((cx + 40, box_y + 35), sub_pick, font=f_sub, fill=(248, 113, 113, 255))

pick_name = "INDIANA PACERS - MONEYLINE"
draw.text((cx + 40, box_y + 70), pick_name, font=f_h2, fill=(255, 255, 255, 255))

# Result badge & Units
draw.line([(cx + 35, box_y + 150), (cx + card_w - 35, box_y + 150)], fill=(75, 29, 39, 255), width=2)

res_badge = "❌ NO CUBIERTA / PERDIDA"
draw.rounded_rectangle([cx + 40, box_y + 185, cx + 40 + draw.textlength(res_badge, font=f_tag) + 30, box_y + 255], radius=18, fill=(69, 10, 10, 255), outline=(239, 68, 68, 255), width=2)
draw.text((cx + 55, box_y + 200), res_badge, font=f_tag, fill=(254, 202, 202, 255))

unit_str = "-1.00 UNIDAD"
draw.text((cx + card_w - draw.textlength(unit_str, font=f_title) - 45, box_y + 185), unit_str, font=f_title, fill=(239, 68, 68, 255))

status_desc = "Asignación fija: 1 Unidad · Sin martingalas ni persecución de pérdidas"
draw.text(((W - draw.textlength(status_desc, font=f_sub)) // 2, box_y + 285), status_desc, font=f_sub, fill=(148, 163, 184, 255))

# -------------------------------------------------------------
# 4. TACTICAL POST-MORTEM (y: 960 - 1380)
# -------------------------------------------------------------
post_y = 960
post_h = 420
draw.rounded_rectangle([cx, post_y, cx + card_w, post_y + post_h], radius=28, fill=(15, 23, 42, 240), outline=(51, 65, 85, 200), width=2)

p_head = "🔍 DESGLOSE TÁCTICO & ANÁLISIS POST-PARTIDO"
draw.text((cx + 40, post_y + 35), p_head, font=f_badge, fill=(56, 189, 248, 255))

bullets = [
    ("📉 Colapso Ofensivo Inusual:", "Indiana venía promediando 118.5 pts por juego y hoy anotó apenas 90 puntos en casa."),
    ("🎯 Colapso en Tiro Exterior:", "Efectividad atípica de 38.2% de campo y 24.1% en triples contra la zona de Brooklyn."),
    ("📊 Varianza Estadística:", "El modelo detectó valor matemático pre-partido (+6.1% EV), pero la ejecución deportiva no acompañó.")
]

by_cur = post_y + 90
for b_title, b_desc in bullets:
    draw.text((cx + 40, by_cur), b_title, font=f_body, fill=(255, 215, 0, 255))
    by_cur += 38
    # Wrap text if long
    draw.text((cx + 40, by_cur), b_desc, font=f_sub, fill=(203, 213, 225, 255))
    by_cur += 65

# -------------------------------------------------------------
# 5. PHILOSOPHY & TRANSPARENCY PROMISE (y: 1410 - 1670)
# -------------------------------------------------------------
phil_y = 1410
phil_h = 240
draw.rounded_rectangle([cx, phil_y, cx + card_w, phil_y + phil_h], radius=24, fill=(10, 16, 28, 250), outline=(30, 41, 59, 255), width=2)

ph_title = "🛡️ LA FILOSOFÍA DE OVERDOG AI:"
draw.text(((W - draw.textlength(ph_title, font=f_badge)) // 2, phil_y + 30), ph_title, font=f_badge, fill=(0, 255, 163, 255))

quote1 = "“El 99% de los canales borran sus apuestas cuando pierden."
quote2 = "Nosotros auditamos cada pick porque los números son reales."
quote3 = "Aceptamos la varianza con la cabeza fría y disciplina de bankroll.”"

draw.text(((W - draw.textlength(quote1, font=f_body)) // 2, phil_y + 75), quote1, font=f_body, fill=(226, 232, 240, 255))
draw.text(((W - draw.textlength(quote2, font=f_body)) // 2, phil_y + 115), quote2, font=f_body, fill=(226, 232, 240, 255))
draw.text(((W - draw.textlength(quote3, font=f_body)) // 2, phil_y + 155), quote3, font=f_body, fill=(148, 163, 184, 255))

# -------------------------------------------------------------
# 6. FOOTER (y: 1690 - 1840)
# -------------------------------------------------------------
cta_y = 1690
draw.rounded_rectangle([cx + 50, cta_y, cx + card_w - 50, cta_y + 80], radius=20, fill=(0, 136, 204, 255))
tg_text = "📲 AUDITORÍA EN VIVO: t.me/overdogai"
draw.text(((W - draw.textlength(tg_text, font=f_tag)) // 2, cta_y + 22), tg_text, font=f_tag, fill=(255, 255, 255, 255))

f_disc = "SPORTS ANALYTICS & INTELLIGENCE · PROCESO ESTADÍSTICO A LARGO PLAZO"
draw.text(((W - draw.textlength(f_disc, font=f_sub)) // 2, 1800), f_disc, font=f_sub, fill=(100, 116, 139, 255))

# Save
out_png = "assets/tarjeta_liquidacion_pacers.png"
out_jpg = "assets/tarjeta_liquidacion_pacers.jpg"

img_rgb = img.convert("RGB")
img.save(out_png, "PNG")
img_rgb.save(out_jpg, "JPEG", quality=95)

print("Tarjeta de liquidación guardada en:", out_png)
