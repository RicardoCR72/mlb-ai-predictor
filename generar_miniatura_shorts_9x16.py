import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

def generate_shorts_thumbnail():
    W = 1080
    H = 1920
    font_dir = "C:/Windows/Fonts"
    
    # Fonts
    f_pill = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
    f_title = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 140)
    f_ev = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 72)
    f_brand = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 42)
    f_card_sub = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
    f_card_title = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 38)
    f_badge = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
    f_footer = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
    
    # 1. Dark Athletic Background with Radial Glow
    y, x = np.ogrid[:H, :W]
    cx, cy = W // 2, 700
    dist = np.sqrt(((x - cx) / (W * 0.8))**2 + ((y - cy) / (H * 0.6))**2)
    ratio = np.clip(dist, 0, 1)
    
    r = (18 * (1 - ratio) + 6 * ratio).astype(np.uint8)
    g = (28 * (1 - ratio) + 9 * ratio).astype(np.uint8)
    b = (46 * (1 - ratio) + 16 * ratio).astype(np.uint8)
    
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    rgb[:, :, 0] = r
    rgb[:, :, 1] = g
    rgb[:, :, 2] = b
    base = Image.fromarray(rgb).convert("RGBA")
    
    # Subtle blur background texture from court
    if os.path.exists("scratch/raw_curry_16x9.jpg"):
        bg_tex = Image.open("scratch/raw_curry_16x9.jpg").convert("RGBA").resize((W, H))
        bg_tex = ImageEnhance.Brightness(bg_tex).enhance(0.18)
        bg_tex = bg_tex.filter(ImageFilter.GaussianBlur(15))
        base = Image.blend(base, bg_tex, 0.40)
        
    # 2. Player Cutouts side by side (Upper-Middle Section)
    # Steph Curry (Left)
    if os.path.exists("scratch/curry_cutout.png"):
        curry = Image.open("scratch/curry_cutout.png").convert("RGBA")
        cw = 560
        ch = int(curry.height * (cw / curry.width))
        curry = curry.resize((cw, ch), Image.Resampling.LANCZOS)
        
        curry_x = -30
        curry_y = 480
        
        glow_c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gdraw_c = ImageDraw.Draw(glow_c)
        gdraw_c.ellipse([curry_x + 40, curry_y + 40, curry_x + cw, curry_y + ch - 50], fill=(255, 179, 0, 140))
        glow_c = glow_c.filter(ImageFilter.GaussianBlur(60))
        base = Image.alpha_composite(base, glow_c)
        base.paste(curry, (curry_x, curry_y), curry)
        
    # Zay Flowers (Right)
    if os.path.exists("scratch/flowers_cutout.png"):
        flowers = Image.open("scratch/flowers_cutout.png").convert("RGBA")
        fw = 580
        fh = int(flowers.height * (fw / flowers.width))
        flowers = flowers.resize((fw, fh), Image.Resampling.LANCZOS)
        
        flowers_x = W - fw + 40
        flowers_y = 480
        
        glow_f = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gdraw_f = ImageDraw.Draw(glow_f)
        gdraw_f.ellipse([flowers_x, flowers_y + 40, flowers_x + fw - 40, flowers_y + fh - 50], fill=(123, 31, 162, 160))
        glow_f = glow_f.filter(ImageFilter.GaussianBlur(60))
        base = Image.alpha_composite(base, glow_f)
        base.paste(flowers, (flowers_x, flowers_y), flowers)

    # 3. Vignette Overlays
    vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    
    # Top solid shadow for header/title
    for y_pos in range(500):
        alpha = int(240 - (y_pos / 500) * 120)
        vdraw.line([(0, y_pos), (W, y_pos)], fill=(7, 11, 20, alpha))
        
    # Bottom solid shadow for cards
    for y_pos in range(950, H):
        alpha = int(((y_pos - 950) / (H - 950)) * 255)
        vdraw.line([(0, y_pos), (W, y_pos)], fill=(6, 10, 18, alpha))
        
    vignette = vignette.filter(ImageFilter.GaussianBlur(20))
    base = Image.alpha_composite(base, vignette)
    
    draw = ImageDraw.Draw(base)
    
    # 4. Logos on Top Corners
    if os.path.exists("scratch/warriors_logo.png"):
        wlogo = Image.open("scratch/warriors_logo.png").convert("RGBA").resize((95, 95))
        base.paste(wlogo, (60, 60), wlogo)
        
    if os.path.exists("scratch/ravens_logo.png"):
        rlogo = Image.open("scratch/ravens_logo.png").convert("RGBA").resize((115, 75))
        base.paste(rlogo, (W - 175, 70), rlogo)

    # 5. Header Pill (Top Center)
    pill_text = "• NFL THURSDAY NIGHT + NBA •"
    pw = draw.textlength(pill_text, font=f_pill) + 40
    px = (W - pw) // 2
    py = 75
    draw.rounded_rectangle([px, py, px + pw, py + 52], radius=26, fill=(15, 23, 42, 235), outline=(0, 229, 255), width=2)
    draw.text((px + 20, py + 10), pill_text, fill=(0, 229, 255), font=f_pill)
    
    # 6. Main Title: "TOP 3 PICKS"
    t_main = "TOP 3 PICKS"
    tw = draw.textlength(t_main, font=f_title)
    tx = (W - tw) // 2
    ty = 165
    
    # 3D Drop Shadow
    for off in [4, 6, 8]:
        draw.text((tx + off, ty + off), t_main, fill=(0, 0, 0, 250), font=f_title)
    draw.text((tx, ty), t_main, fill=(255, 255, 255), font=f_title)
    
    # 7. EV Subtitle: "+12.5% VALOR EV"
    t_ev = "+12.5% VALOR EV"
    ew = draw.textlength(t_ev, font=f_ev)
    ex = (W - ew) // 2
    ey = 315
    for off in [3, 5]:
        draw.text((ex + off, ey + off), t_ev, fill=(0, 0, 0, 230), font=f_ev)
    draw.text((ex, ey), t_ev, fill=(0, 230, 118), font=f_ev)
    
    # 8. Overdog Brand Stamp
    t_brand = "MODELO MATEMÁTICO OVERDOG AI"
    bw_brand = draw.textlength(t_brand, font=f_brand)
    draw.text(((W - bw_brand) // 2, 400), t_brand, fill=(255, 215, 0), font=f_brand)
    
    # 9. Pick Cards Stacked Vertically (Bottom Half: 1080 to 1750)
    cards_data = [
        ("NBA · HEAT @ WARRIORS", "UNDER 235.5 PUNTOS", "+12.5% EV", (255, 179, 0)),
        ("NFL · ZAY FLOWERS (BAL)", "OVER 4.5 RECEPCIONES", "4 DE 5 (80%)", (0, 230, 118)),
        ("NFL · RASHOD BATEMAN (BAL)", "OVER 13.5 YDS RECEPCIÓN", "32.6 YDS PROM", (0, 229, 255))
    ]
    
    card_w = 960
    card_h = 165
    card_gap = 25
    card_start_y = 1080
    card_x = (W - card_w) // 2
    
    for i, (team, pick, stat, accent) in enumerate(cards_data):
        cy = card_start_y + i * (card_h + card_gap)
        
        # Card Background
        draw.rounded_rectangle([card_x, cy, card_x + card_w, cy + card_h], radius=22, fill=(13, 20, 36, 245), outline=(30, 41, 59), width=3)
        # Left Accent Bar
        draw.rounded_rectangle([card_x, cy, card_x + 12, cy + card_h], radius=6, fill=accent)
        
        # Team/Market Label
        draw.text((card_x + 35, cy + 24), team, fill=(148, 163, 184), font=f_card_sub)
        
        # Pick Selection
        draw.text((card_x + 35, cy + 62), pick, fill=(255, 255, 255), font=f_card_title)
        
        # Badge Pill (Right aligned)
        bw = draw.textlength(stat, font=f_badge) + 32
        bx = card_x + card_w - bw - 30
        by = cy + (card_h - 48) // 2
        draw.rounded_rectangle([bx, by, bx + bw, by + 48], radius=24, fill=(15, 23, 42), outline=accent, width=2)
        draw.text((bx + 16, by + 9), stat, fill=accent, font=f_badge)
        
    # 10. Footer Call to Action
    t_foot = "• ANÁLISIS MATEMÁTICO EN EL VIDEO •"
    fw_foot = draw.textlength(t_foot, font=f_footer)
    draw.text(((W - fw_foot) // 2, 1720), t_foot, fill=(203, 213, 225), font=f_footer)
    
    # Save Outputs
    out_path = "assets/miniatura_youtube_shorts_9x16.jpg"
    base.convert("RGB").save(out_path, quality=95)
    
    art_path = "C:/Users/rcabr/.gemini/antigravity/brain/8db99efe-a7c9-44ba-88ff-2a8317829757/miniatura_youtube_shorts_9x16.jpg"
    base.convert("RGB").save(art_path, quality=95)
    print("Miniatura Shorts 9:16 creada con éxito en:", out_path)

if __name__ == "__main__":
    generate_shorts_thumbnail()
