import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_header_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
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
f_row_bold = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_row_val = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 38)

CARD_X = 90
CARD_W = 900
THEME_GREEN = (0, 255, 163)
THEME_GOLD = (255, 215, 0)
THEME_BLUE = (56, 189, 248)

def render_base(title_tag):
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

    # Logo
    logo_path = "assets/overdog_logo_transparent.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize((90, 90), Image.Resampling.LANCZOS)
        img.paste(logo, ((W - 90) // 2, 110), logo)

    draw.text(((W - draw.textlength("OVERDOG AI", font=f_brand)) // 2, 215), "OVERDOG AI", font=f_brand, fill=(255, 255, 255))

    tw = draw.textlength(title_tag, font=f_header_tag) + 40
    tx = (W - tw) // 2
    draw.rounded_rectangle([tx, 275, tx + tw, 320], radius=22, fill=(15, 28, 38), outline=THEME_GREEN, width=2)
    draw.text(((W - draw.textlength(title_tag, font=f_header_tag)) // 2, 285), title_tag, font=f_header_tag, fill=THEME_GREEN)

    return img, draw

def add_footer(draw):
    t_y = 1495
    draw.rounded_rectangle([CARD_X, t_y, CARD_X + CARD_W, t_y + 125], radius=24, fill=(10, 16, 26), outline=(35, 48, 70), width=2)
    t_top = "POLITICA 100% CERO HUMO"
    t_bot = "Todos los picks se auditan en nuestra base de datos publica SQL."
    draw.text(((W - draw.textlength(t_top, font=f_trust_title)) // 2, t_y + 25), t_top, font=f_trust_title, fill=THEME_GREEN)
    draw.text(((W - draw.textlength(t_bot, font=f_trust_sub)) // 2, t_y + 70), t_bot, font=f_trust_sub, fill=(203, 213, 225))

    btn_y = 1645
    btn_w = CARD_W - 80
    btn_x = (W - btn_w) // 2
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + 85], radius=22, fill=(0, 136, 204))
    btn_text = "Canal Oficial de Picks: @overdogai"
    draw.text(((W - draw.textlength(btn_text, font=f_cta)) // 2, btn_y + 24), btn_text, font=f_cta, fill=(255, 255, 255))

    disc = "Sports Intelligence · Datos matemáticos sin sesgos emocionales"
    draw.text(((W - draw.textlength(disc, font=f_sub)) // 2, 1770), disc, font=f_sub, fill=(100, 116, 139))

def generate_master_card():
    img, draw = render_base("ACUMULADO OFICIAL · TEMPORADA COMPLETA")

    # 1. Hero Box: Massive Accumulator
    hero_y = 350
    hero_h = 240
    draw.rounded_rectangle([CARD_X, hero_y, CARD_X + CARD_W, hero_y + hero_h], radius=30, fill=(10, 20, 30), outline=THEME_GREEN, width=3)
    h_sub = "NFL 2026 · AUDITORÍA GLOBAL (SEMANAS 3 A 8)"
    draw.text(((W - draw.textlength(h_sub, font=f_sub)) // 2, hero_y + 25), h_sub, font=f_sub, fill=(148, 163, 184))

    hero_val = "+46.66 UNIDADES"
    draw.text(((W - draw.textlength(hero_val, font=f_stat_hero_val)) // 2, hero_y + 65), hero_val, font=f_stat_hero_val, fill=THEME_GREEN)
    h_note = "100% DE SEMANAS POSITIVAS (6 DE 6 SEMANAS EN VERDE)"
    draw.text(((W - draw.textlength(h_note, font=f_bullet_bold)) // 2, hero_y + 185), h_note, font=f_bullet_bold, fill=THEME_GOLD)

    # 2. Metric Grid
    grid_y = 615
    grid_h = 220
    col_w = (CARD_W - 30) // 3
    metrics = [
        ("TOTAL AUDITADOS", "472", "Picks verificados", (255, 255, 255)),
        ("WIN RATE GLOBAL", "57.5%", "269G - 199P (4P)", THEME_GREEN),
        ("ROI CONSOLIDADO", "+9.9%", "Sobre capital apostado", THEME_GOLD)
    ]
    for i, (lbl, val, sub_txt, col) in enumerate(metrics):
        cx = CARD_X + i * (col_w + 15)
        draw.rounded_rectangle([cx, grid_y, cx + col_w, grid_y + grid_h], radius=24, fill=(12, 19, 32), outline=(35, 50, 70), width=2)
        draw.text((cx + (col_w - draw.textlength(lbl, font=f_grid_lbl)) // 2, grid_y + 25), lbl, font=f_grid_lbl, fill=(148, 163, 184))
        draw.text((cx + (col_w - draw.textlength(val, font=f_grid_val)) // 2, grid_y + 70), val, font=f_grid_val, fill=col)
        draw.text((cx + (col_w - draw.textlength(sub_txt, font=f_grid_sub)) // 2, grid_y + 165), sub_txt, font=f_grid_sub, fill=(148, 163, 184))

    # 3. Weekly Breakdown Table Card
    card_y = 865
    card_h = 600
    draw.rounded_rectangle([CARD_X, card_y, CARD_X + CARD_W, card_y + card_h], radius=32, fill=(13, 19, 32), outline=(35, 52, 75), width=2)

    s_title = "DESGLOSE HISTÓRICO SEMANA POR SEMANA"
    draw.text(((W - draw.textlength(s_title, font=f_section)) // 2, card_y + 35), s_title, font=f_section, fill=THEME_GOLD)

    row_y = card_y + 90
    rows = [
        ("Semana 3", "68 Picks", "38G - 30P", "+4.87 u", "+7.2% ROI"),
        ("Semana 4", "90 Picks", "55G - 33P", "+17.87 u", "+19.9% ROI"),
        ("Semana 5", "94 Picks", "49G - 44P", "+3.29 u", "+3.5% ROI"),
        ("Semana 6", "84 Picks", "50G - 34P", "+9.12 u", "+10.9% ROI"),
        ("Semana 7", "82 Picks", "45G - 36P", "+6.78 u", "+8.3% ROI"),
        ("Semana 8", "54 Picks", "32G - 22P", "+4.73 u", "+8.8% ROI"),
    ]

    for sem, p_cnt, rec, prof, r_val in rows:
        # Row card background: from x = 125 to x = 955 (width 830)
        draw.rounded_rectangle([CARD_X + 35, row_y, CARD_X + CARD_W - 35, row_y + 68], radius=16, fill=(18, 25, 40), outline=(35, 48, 70), width=1)
        
        # 1. Week Name (Starts at 145)
        draw.text((145, row_y + 18), sem, font=f_row_bold, fill=(255, 255, 255))
        
        # 2. Picks (Cleanly separated, starts at 310 -> 37px gap from Week!)
        draw.text((310, row_y + 22), p_cnt, font=f_sub, fill=(148, 163, 184))
        
        # 3. Record (Starts at 445 -> 45px gap from Picks!)
        draw.text((445, row_y + 22), rec, font=f_sub, fill=(203, 213, 225))
        
        # 4. Profit (Right-aligned to 760 -> ~95px gap from Record!)
        w_prof = draw.textlength(prof, font=f_row_val)
        draw.text((760 - w_prof, row_y + 14), prof, font=f_row_val, fill=THEME_GREEN)
        
        # 5. ROI (Right-aligned strictly to 930 -> 25px safety margin from row edge!)
        w_roi = draw.textlength(r_val, font=f_sub)
        draw.text((930 - w_roi, row_y + 22), r_val, font=f_sub, fill=THEME_GOLD)
        
        row_y += 82

    add_footer(draw)

    out_master = "assets/tarjeta_rendimiento_acumulado_total.png"
    img.save(out_master, "PNG")
    img.save(out_master.replace(".png", ".jpg"), "JPEG", quality=95)
    print("Tarjeta Maestra con columnas perfectamente separadas guardada en:", out_master)

generate_master_card()
