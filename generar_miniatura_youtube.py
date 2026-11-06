import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

def generate_youtube_thumbnail():
    W, H = 1280, 720
    font_dir = "C:/Windows/Fonts"
    
    f_pill = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
    f_title_huge = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 120)
    f_ev = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 54)
    f_card_title = ImageFont.truetype(os.path.join(font_dir, "arialbd.ttf"), 20)
    f_card_sub = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 15)
    f_badge = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 16)
    f_brand = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 26)
    
    # 1. Dark Athletic Background with Radial Glow
    y, x = np.ogrid[:H, :W]
    cx, cy = W // 2, H // 2 - 40
    dist = np.sqrt(((x - cx) / (W * 0.7))**2 + ((y - cy) / (H * 0.8))**2)
    ratio = np.clip(dist, 0, 1)
    
    r = (18 * (1 - ratio) + 6 * ratio).astype(np.uint8)
    g = (28 * (1 - ratio) + 9 * ratio).astype(np.uint8)
    b = (46 * (1 - ratio) + 16 * ratio).astype(np.uint8)
    
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    rgb[:, :, 0] = r
    rgb[:, :, 1] = g
    rgb[:, :, 2] = b
    base = Image.fromarray(rgb).convert("RGBA")
    
    # 2. Add court/stadium background atmosphere
    if os.path.exists("scratch/raw_curry_16x9.jpg"):
        bg_tex = Image.open("scratch/raw_curry_16x9.jpg").convert("RGBA").resize((W, H))
        bg_tex = ImageEnhance.Brightness(bg_tex).enhance(0.20)
        bg_tex = bg_tex.filter(ImageFilter.GaussianBlur(12))
        base = Image.blend(base, bg_tex, 0.40)
        
    # 3. Left Player: Steph Curry (Scaled large, visible from y=100)
    if os.path.exists("scratch/curry_cutout.png"):
        curry = Image.open("scratch/curry_cutout.png").convert("RGBA")
        cw = 580
        ch = int(curry.height * (cw / curry.width))
        curry = curry.resize((cw, ch), Image.Resampling.LANCZOS)
        
        curry_x = -70
        curry_y = 110  # Raised so head is fully visible
        
        # Yellow Golden Glow behind Curry
        glow_c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow_c)
        gdraw.ellipse([curry_x + 60, curry_y + 40, curry_x + cw - 40, curry_y + ch - 100], fill=(255, 179, 0, 130))
        glow_c = glow_c.filter(ImageFilter.GaussianBlur(55))
        base = Image.alpha_composite(base, glow_c)
        base.paste(curry, (curry_x, curry_y), curry)
        
    # 4. Right Player: Zay Flowers (Scaled large, visible from y=100)
    if os.path.exists("scratch/flowers_cutout.png"):
        flowers = Image.open("scratch/flowers_cutout.png").convert("RGBA")
        fw = 610
        fh = int(flowers.height * (fw / flowers.width))
        flowers = flowers.resize((fw, fh), Image.Resampling.LANCZOS)
        
        flowers_x = W - fw + 70
        flowers_y = 110  # Raised so head is fully visible
        
        # Purple Glow behind Flowers
        glow_f = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gdraw_f = ImageDraw.Draw(glow_f)
        gdraw_f.ellipse([flowers_x + 60, flowers_y + 40, flowers_x + fw - 40, flowers_y + fh - 100], fill=(123, 31, 162, 145))
        glow_f = glow_f.filter(ImageFilter.GaussianBlur(55))
        base = Image.alpha_composite(base, glow_f)
        base.paste(flowers, (flowers_x, flowers_y), flowers)

    # 5. Vignette Overlay for Center Contrast & Dark Bottom Shelf
    center_dim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(center_dim)
    
    # Heavy dark backdrop behind center text
    cdraw.ellipse([W//2 - 340, 30, W//2 + 340, 420], fill=(7, 11, 20, 210))
    
    # Bottom solid shelf for cards
    for y_pos in range(H):
        if y_pos > 520:
            alpha = int(((y_pos - 520) / 200) * 245)
            cdraw.line([(0, y_pos), (W, y_pos)], fill=(5, 8, 16, alpha))
            
    center_dim = center_dim.filter(ImageFilter.GaussianBlur(25))
    base = Image.alpha_composite(base, center_dim)
    
    draw = ImageDraw.Draw(base)
    
    # 6. Team Logos
    if os.path.exists("scratch/warriors_logo.png"):
        wlogo = Image.open("scratch/warriors_logo.png").convert("RGBA").resize((75, 75))
        base.paste(wlogo, (35, 30), wlogo)
        
    if os.path.exists("scratch/ravens_logo.png"):
        rlogo = Image.open("scratch/ravens_logo.png").convert("RGBA").resize((90, 58))
        base.paste(rlogo, (W - 125, 38), rlogo)
        
    # 7. Header Category Pill
    pill_text = "• NFL THURSDAY NIGHT + NBA •"
    pw = draw.textlength(pill_text, font=f_pill) + 36
    px = (W - pw) // 2
    py = 32
    draw.rounded_rectangle([px, py, px + pw, py + 42], radius=21, fill=(15, 23, 42, 235), outline=(0, 229, 255), width=2)
    draw.text((px + 18, py + 8), pill_text, fill=(0, 229, 255), font=f_pill)
    
    # 8. Main Title: "TOP 3 PICKS"
    t_main = "TOP 3 PICKS"
    tw = draw.textlength(t_main, font=f_title_huge)
    tx = (W - tw) // 2
    ty = 85
    
    # 3D Shadow
    for off in [3, 5, 7]:
        draw.text((tx + off, ty + off), t_main, fill=(0, 0, 0, 245), font=f_title_huge)
    draw.text((tx, ty), t_main, fill=(255, 255, 255), font=f_title_huge)
    
    # 9. EV Badge: "+12.5% VALOR EV"
    t_ev = "+12.5% VALOR EV"
    ew = draw.textlength(t_ev, font=f_ev)
    ex = (W - ew) // 2
    ey = 215
    for off in [2, 4]:
        draw.text((ex + off, ey + off), t_ev, fill=(0, 0, 0, 225), font=f_ev)
    draw.text((ex, ey), t_ev, fill=(0, 230, 118), font=f_ev)
    
    # 10. Overdog AI Brand Stamp
    t_brand = "OVERDOG AI"
    bw_brand = draw.textlength(t_brand, font=f_brand)
    bx_brand = (W - bw_brand) // 2
    draw.text((bx_brand, 290), t_brand, fill=(255, 215, 0), font=f_brand)
    
    # 11. Pick Cards (Bottom Section: 3 Columns)
    cards_data = [
        ("HEAT @ WARRIORS", "UNDER 235.5", "+12.5% EV", (255, 179, 0)),
        ("ZAY FLOWERS", "OVER 4.5 REC", "4/5 (80%)", (0, 230, 118)),
        ("RASHOD BATEMAN", "OVER 13.5 YDS", "32.6 PROM", (0, 229, 255))
    ]
    
    total_card_w = 350
    card_h = 115
    card_gap = 20
    start_x = (W - (3 * total_card_w + 2 * card_gap)) // 2
    card_y = 575
    
    for i, (team, pick, stat, accent) in enumerate(cards_data):
        cx = start_x + i * (total_card_w + card_gap)
        
        # Glass Card Background
        draw.rounded_rectangle([cx, card_y, cx + total_card_w, card_y + card_h], radius=14, fill=(13, 20, 36, 245), outline=(30, 41, 59), width=2)
        # Top Accent Line
        draw.rounded_rectangle([cx, card_y, cx + total_card_w, card_y + 5], radius=3, fill=accent)
        
        # League / Team Label
        draw.text((cx + 18, card_y + 14), team, fill=(148, 163, 184), font=f_card_sub)
        
        # Pick Name
        draw.text((cx + 18, card_y + 36), pick, fill=(255, 255, 255), font=f_card_title)
        
        # Badge Pill
        bw = draw.textlength(stat, font=f_badge) + 20
        bx = cx + 18
        by = card_y + 72
        draw.rounded_rectangle([bx, by, bx + bw, by + 28], radius=14, fill=(15, 23, 42), outline=accent, width=2)
        draw.text((bx + 10, by + 5), stat, fill=accent, font=f_badge)
        
    # Save 16:9 Thumbnail
    out_path = "assets/miniatura_youtube_top3_jueves.jpg"
    base.convert("RGB").save(out_path, quality=95)
    
    art_path = "C:/Users/rcabr/.gemini/antigravity/brain/8db99efe-a7c9-44ba-88ff-2a8317829757/miniatura_youtube_top3_jueves.jpg"
    base.convert("RGB").save(art_path, quality=95)
    print("Miniatura 16:9 creada con éxito en:", out_path)

if __name__ == "__main__":
    generate_youtube_thumbnail()
