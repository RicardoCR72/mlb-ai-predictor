import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

# Standard fonts
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_header_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_score = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 86)
f_dash = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 68)
f_pick_lbl = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 34)
f_res_big = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 68)
f_section = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_bullet_bold = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_bullet_text = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 26)
f_trust_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
f_trust_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_cta = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)

def get_fitted_font(draw_obj, text, max_w, max_sz=56, min_sz=34):
    """Dynamically scales font size so team name fits with 100% certainty."""
    for sz in range(max_sz, min_sz - 1, -2):
        f = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), sz)
        if draw_obj.textlength(text, font=f) <= max_w:
            return f
    return ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), min_sz)

def create_card(
    is_win: bool,
    sport_tag: str,
    team1_name: str, team1_city: str, team1_score: str,
    team2_name: str, team2_city: str, team2_score: str,
    pick_text: str,
    res_text: str,
    units_text: str,
    why_title: str,
    bullet1_title: str, bullet1_desc: str,
    bullet2_title: str, bullet2_desc: str,
    out_png: str
):
    # Base dark gradient (Solid RGB, zero alpha-layer glitches)
    y_coords = np.linspace(0, 1, H)
    if is_win:
        r = (10 * (1 - y_coords) + 6 * y_coords).astype(np.uint8)
        g = (24 * (1 - y_coords) + 14 * y_coords).astype(np.uint8)
        b = (30 * (1 - y_coords) + 18 * y_coords).astype(np.uint8)
        theme_color = (0, 255, 163) # Neon Emerald
        pill_bg = (6, 78, 59)
        pill_border = (0, 255, 163)
        pill_text_col = (255, 255, 255)
    else:
        r = (18 * (1 - y_coords) + 10 * y_coords).astype(np.uint8)
        g = (14 * (1 - y_coords) + 10 * y_coords).astype(np.uint8)
        b = (22 * (1 - y_coords) + 16 * y_coords).astype(np.uint8)
        theme_color = (239, 68, 68) # Clean Red
        pill_bg = (69, 10, 10)
        pill_border = (239, 68, 68)
        pill_text_col = (255, 255, 255)

    bg = np.zeros((H, W, 3), dtype=np.uint8)
    bg[:, :, 0] = r[:, None]
    bg[:, :, 1] = g[:, None]
    bg[:, :, 2] = b[:, None]

    img = Image.fromarray(bg).convert("RGB")
    draw = ImageDraw.Draw(img)

    CARD_X = 90
    CARD_W = 900

    # -------------------------------------------------------------
    # 1. HEADER (y: 120 - 330)
    # -------------------------------------------------------------
    logo_path = "assets/overdog_logo_transparent.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize((90, 90), Image.Resampling.LANCZOS)
        img.paste(logo, ((W - 90) // 2, 120), logo)

    draw.text(((W - draw.textlength("OVERDOG AI", font=f_brand)) // 2, 225), "OVERDOG AI", font=f_brand, fill=(255, 255, 255))

    header_tag = "REPORTE DE RESULTADOS"
    tw = draw.textlength(header_tag, font=f_header_tag) + 40
    tx = (W - tw) // 2
    draw.rounded_rectangle([tx, 280, tx + tw, 325], radius=22, fill=(20, 28, 42), outline=theme_color, width=2)
    draw.text(((W - draw.textlength(header_tag, font=f_header_tag)) // 2, 290), header_tag, font=f_header_tag, fill=theme_color)

    # -------------------------------------------------------------
    # 2. MAIN CARD (y: 360 - 1460)
    # -------------------------------------------------------------
    card_y = 360
    card_h = 1080

    draw.rounded_rectangle([CARD_X, card_y, CARD_X + CARD_W, card_y + card_h], radius=32, fill=(13, 19, 32), outline=theme_color, width=2)

    # Sport Label
    draw.text(((W - draw.textlength(sport_tag, font=f_sub)) // 2, card_y + 40), sport_tag, font=f_sub, fill=(148, 163, 184))

    # Scoreboard Box
    sbox_x = CARD_X + 40 # 130
    sbox_w = CARD_W - 80 # 820
    sbox_y = card_y + 90
    sbox_h = 190
    draw.rounded_rectangle([sbox_x, sbox_y, sbox_x + sbox_w, sbox_y + sbox_h], radius=24, fill=(8, 13, 22), outline=(40, 52, 75), width=2)

    # Scores in Center
    mid_x = W // 2 # 540
    # Left Score
    s1_w = draw.textlength(team1_score, font=f_score)
    draw.text((mid_x - 65 - s1_w / 2, sbox_y + 42), team1_score, font=f_score, fill=(255, 255, 255) if not is_win else (148, 163, 184))
    # Center Dash
    draw.text((mid_x - 10, sbox_y + 52), "-", font=f_dash, fill=(100, 116, 139))
    # Right Score
    s2_w = draw.textlength(team2_score, font=f_score)
    draw.text((mid_x + 65 - s2_w / 2, sbox_y + 42), team2_score, font=f_score, fill=theme_color)

    # Left Team Name & City (Max width 250px, centered at x=275)
    left_col_center = 275
    f_t1 = get_fitted_font(draw, team1_name, max_w=250, max_sz=56, min_sz=36)
    t1_w = draw.textlength(team1_name, font=f_t1)
    draw.text((left_col_center - t1_w / 2, sbox_y + 48), team1_name, font=f_t1, fill=(255, 255, 255))
    c1_w = draw.textlength(team1_city, font=f_sub)
    draw.text((left_col_center - c1_w / 2, sbox_y + 125), team1_city, font=f_sub, fill=(148, 163, 184))

    # Right Team Name & City (Max width 250px, centered at x=805)
    right_col_center = 805
    f_t2 = get_fitted_font(draw, team2_name, max_w=250, max_sz=56, min_sz=36)
    t2_w = draw.textlength(team2_name, font=f_t2)
    draw.text((right_col_center - t2_w / 2, sbox_y + 48), team2_name, font=f_t2, fill=(255, 255, 255))
    c2_w = draw.textlength(team2_city, font=f_sub)
    draw.text((right_col_center - c2_w / 2, sbox_y + 125), team2_city, font=f_sub, fill=theme_color)

    # Pick details
    draw.text(((W - draw.textlength(pick_text, font=f_pick_lbl)) // 2, card_y + 330), pick_text, font=f_pick_lbl, fill=(255, 255, 255))

    # Result Pill
    full_res = f"{res_text}   {units_text}"
    rw = draw.textlength(full_res, font=f_res_big) + 60
    rx = (W - rw) // 2
    pill_y = card_y + 395
    draw.rounded_rectangle([rx, pill_y, rx + rw, pill_y + 105], radius=26, fill=pill_bg, outline=pill_border, width=3)
    draw.text(((W - draw.textlength(full_res, font=f_res_big)) // 2, pill_y + 16), full_res, font=f_res_big, fill=pill_text_col)

    # Clean Divider
    draw.line([(CARD_X + 50, card_y + 550), (CARD_X + CARD_W - 50, card_y + 550)], fill=(30, 42, 60), width=2)

    # Explanation Section
    draw.text(((W - draw.textlength(why_title, font=f_section)) // 2, card_y + 585), why_title, font=f_section, fill=(255, 215, 0))

    # Bullet 1
    b1_y = card_y + 655
    draw.text((CARD_X + 60, b1_y), f"• {bullet1_title}", font=f_bullet_bold, fill=(255, 255, 255))
    draw.text((CARD_X + 60, b1_y + 45), bullet1_desc, font=f_bullet_text, fill=(148, 163, 184))

    # Bullet 2
    b2_y = card_y + 780
    draw.text((CARD_X + 60, b2_y), f"• {bullet2_title}", font=f_bullet_bold, fill=(255, 255, 255))
    draw.text((CARD_X + 60, b2_y + 45), bullet2_desc, font=f_bullet_text, fill=(148, 163, 184))

    # Status / Bankroll note
    bank_note = "Asignacion de bankroll: 1 Unidad Fija (Sin martingalas)"
    draw.text(((W - draw.textlength(bank_note, font=f_sub)) // 2, card_y + 980), bank_note, font=f_sub, fill=(100, 116, 139))

    # -------------------------------------------------------------
    # 3. TRANSPARENCY BANNER (y: 1485 - 1625)
    # -------------------------------------------------------------
    t_y = 1485
    draw.rounded_rectangle([CARD_X, t_y, CARD_X + CARD_W, t_y + 120], radius=24, fill=(10, 16, 26), outline=(35, 48, 70), width=2)
    
    t_top = "POLITICA 100% CERO HUMO"
    t_bot = "En Overdog AI registramos victorias y derrotas. Datos reales."
    draw.text(((W - draw.textlength(t_top, font=f_trust_title)) // 2, t_y + 24), t_top, font=f_trust_title, fill=theme_color)
    draw.text(((W - draw.textlength(t_bot, font=f_trust_sub)) // 2, t_y + 68), t_bot, font=f_trust_sub, fill=(203, 213, 225))

    # -------------------------------------------------------------
    # 4. TELEGRAM BUTTON (y: 1640 - 1730)
    # -------------------------------------------------------------
    btn_y = 1640
    btn_w = CARD_W - 80
    btn_x = (W - btn_w) // 2
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + 85], radius=22, fill=(0, 136, 204))
    btn_text = "Canal Oficial de Picks: @overdogai"
    draw.text(((W - draw.textlength(btn_text, font=f_cta)) // 2, btn_y + 24), btn_text, font=f_cta, fill=(255, 255, 255))

    disc = "Sports Intelligence · Ventaja matematica a largo plazo"
    draw.text(((W - draw.textlength(disc, font=f_sub)) // 2, 1765), disc, font=f_sub, fill=(100, 116, 139))

    # Save
    img.save(out_png, "PNG")
    out_jpg = out_png.replace(".png", ".jpg")
    img.save(out_jpg, "JPEG", quality=95)
    print("Guardado exitosamente:", out_png)

# 1. PACERS
create_card(
    is_win=False,
    sport_tag="NBA · TEMPORADA REGULAR",
    team1_name="NETS", team1_city="Brooklyn", team1_score="98",
    team2_name="PACERS", team2_city="Indiana", team2_score="90",
    pick_text="Pick: Indiana Pacers a Ganar (Moneyline)",
    res_text="PERDIDA",
    units_text="(-1.00 U)",
    why_title="¿QUE SUCEDIO EN EL PARTIDO?",
    bullet1_title="Colapso Ofensivo Inusual:",
    bullet1_desc="Indiana anoto solo 90 pts (su peor registro de la temporada).",
    bullet2_title="Colapso en Tiro Exterior:",
    bullet2_desc="38.2% en tiros de campo y apenas 24% en triples.",
    out_png="assets/tarjeta_resultado_pacers.png"
)

# 2. SNF JAYDEN DANIELS (COMMANDERS FITS PERFECTLY NOW!)
create_card(
    is_win=True,
    sport_tag="NFL · SUNDAY NIGHT FOOTBALL (SEMANA 8)",
    team1_name="EAGLES", team1_city="Philadelphia", team1_score="10",
    team2_name="COMMANDERS", team2_city="Washington", team2_score="27",
    pick_text="Jayden Daniels: Menos de 1.5 Pases de TD",
    res_text="¡COBRADA!",
    units_text="(+0.68 U)",
    why_title="PRECISION DEL ALGORITMO",
    bullet1_title="Proyeccion vs Realidad:",
    bullet1_desc="El modelo proyecto 1.09 TDs → Daniels lanzo exactamente 1 TD.",
    bullet2_title="Lectura Tactica Impecable:",
    bullet2_desc="Washington controlo por tierra y defensa, limitando el volumen aereo.",
    out_png="assets/tarjeta_resultado_snf.png"
)
