import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1080
font_dir = "C:/Windows/Fonts"

f_nfl = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 170)
f_sub = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_nfl_big = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 220)

THEME_GREEN = (0, 255, 163)
THEME_GOLD = (255, 215, 0)

def create_base():
    # Deep dark circular gradient
    y, x = np.ogrid[:H, :W]
    dist_from_center = np.sqrt((x - W//2)**2 + (y - H//2)**2)
    radius = W // 2
    
    # Dark radial gradient from #121c2e at center to #070b12 at edges
    ratio = np.clip(dist_from_center / radius, 0, 1)
    r = (18 * (1 - ratio) + 7 * ratio).astype(np.uint8)
    g = (28 * (1 - ratio) + 11 * ratio).astype(np.uint8)
    b = (44 * (1 - ratio) + 18 * ratio).astype(np.uint8)
    
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    rgb[:, :, 0] = r
    rgb[:, :, 1] = g
    rgb[:, :, 2] = b
    
    img = Image.fromarray(rgb).convert("RGB")
    draw = ImageDraw.Draw(img)
    return img, draw

# =============================================================
# OPCIÓN 1: BOLD MINIMALIST "NFL" (Neon Emerald & Glass Ring)
# =============================================================
def gen_option1():
    img, draw = create_base()
    
    # Glowing rings matching Instagram highlight circle
    cx, cy = W // 2, H // 2
    
    # Outer ring
    draw.ellipse([cx - 360, cy - 360, cx + 360, cy + 360], fill=(13, 22, 35), outline=(0, 255, 163), width=8)
    # Inner thin ring
    draw.ellipse([cx - 325, cy - 325, cx + 325, cy + 325], fill=None, outline=(35, 55, 80), width=3)
    
    # Clean text NFL
    txt = "NFL"
    tw = draw.textlength(txt, font=f_nfl_big)
    draw.text((cx - tw / 2, cy - 145), txt, font=f_nfl_big, fill=(255, 255, 255))
    
    # Accent pill
    pill_txt = "AUDITORÍA"
    pw = draw.textlength(pill_txt, font=f_sub) + 40
    draw.rounded_rectangle([cx - pw / 2, cy + 130, cx + pw / 2, cy + 195], radius=18, fill=(6, 78, 59), outline=(0, 255, 163), width=2)
    draw.text((cx - draw.textlength(pill_txt, font=f_sub) / 2, cy + 140), pill_txt, font=f_sub, fill=(0, 255, 163))
    
    out = "assets/portada_destacada_nfl_opcion1.png"
    img.save(out, "PNG")
    img.save(out.replace(".png", ".jpg"), "JPEG", quality=95)
    print("Guardada:", out)

# =============================================================
# OPCIÓN 2: BALÓN AMERICANO MINIMALISTA VECTORIAL + "NFL"
# =============================================================
def gen_option2():
    img, draw = create_base()
    cx, cy = W // 2, H // 2
    
    # Glowing ring
    draw.ellipse([cx - 360, cy - 360, cx + 360, cy + 360], fill=(13, 22, 35), outline=(0, 255, 163), width=8)
    
    # Draw vector stylized football shape
    # Ellipse tilted or horizontal football
    fb_w = 420
    fb_h = 240
    fb_y = cy - 80
    
    # Football body
    draw.ellipse([cx - fb_w//2, fb_y - fb_h//2, cx + fb_w//2, fb_y + fb_h//2], fill=(18, 30, 48), outline=(0, 255, 163), width=6)
    
    # Football laces (stitches)
    draw.line([(cx - 80, fb_y), (cx + 80, fb_y)], fill=(255, 255, 255), width=6)
    for x_off in [-60, -20, 20, 60]:
        draw.line([(cx + x_off, fb_y - 28), (cx + x_off, fb_y + 28)], fill=(255, 255, 255), width=6)
    
    # Football tip stripes
    draw.arc([cx - fb_w//2 + 30, fb_y - fb_h//2 + 10, cx - fb_w//2 + 120, fb_y + fb_h//2 - 10], start=90, end=270, fill=(0, 255, 163), width=5)
    draw.arc([cx + fb_w//2 - 120, fb_y - fb_h//2 + 10, cx + fb_w//2 - 30, fb_y + fb_h//2 - 10], start=270, end=90, fill=(0, 255, 163), width=5)
    
    # NFL Text below football
    txt = "NFL"
    tw = draw.textlength(txt, font=f_nfl)
    draw.text((cx - tw / 2, cy + 85), txt, font=f_nfl, fill=(255, 255, 255))
    
    out = "assets/portada_destacada_nfl_opcion2.png"
    img.save(out, "PNG")
    img.save(out.replace(".png", ".jpg"), "JPEG", quality=95)
    print("Guardada:", out)

# =============================================================
# OPCIÓN 3: OVERDOG LOGO + NFL BADGE (Branding Oficial)
# =============================================================
def gen_option3():
    img, draw = create_base()
    cx, cy = W // 2, H // 2
    
    # Double ring
    draw.ellipse([cx - 360, cy - 360, cx + 360, cy + 360], fill=(13, 22, 35), outline=(0, 255, 163), width=8)
    draw.ellipse([cx - 330, cy - 330, cx + 330, cy + 330], fill=None, outline=(35, 55, 80), width=3)
    
    # Overdog Logo centered at top
    logo_path = "assets/overdog_logo_transparent.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize((280, 280), Image.Resampling.LANCZOS)
        img.paste(logo, (cx - 140, cy - 240), logo)
    
    # NFL Bold text
    txt = "NFL"
    tw = draw.textlength(txt, font=f_nfl)
    draw.text((cx - tw / 2, cy + 45), txt, font=f_nfl, fill=(255, 255, 255))
    
    # Small Gold Star
    s_txt = "★ MODELOS IA ★"
    sw = draw.textlength(s_txt, font=f_sub)
    draw.text((cx - sw / 2, cy + 225), s_txt, font=f_sub, fill=THEME_GOLD)
    
    out = "assets/portada_destacada_nfl_opcion3.png"
    img.save(out, "PNG")
    img.save(out.replace(".png", ".jpg"), "JPEG", quality=95)
    print("Guardada:", out)

gen_option1()
gen_option2()
gen_option3()
