import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

# Typography
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_title = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 76)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_card_team = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_card_type = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
f_pick_val = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 48)
f_stat_lbl = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
f_stat_val = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 32)
f_desc = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 22)
f_cta = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_badge = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)

THEME_GREEN = (0, 255, 163)
THEME_GOLD = (255, 215, 0)
THEME_BLUE = (56, 189, 248)

CARD_X = 90
CARD_W = 900

def create_card():
    # Vertical dark gradient
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

    # 1. Header (Logo + Brand)
    logo_path = "assets/overdog_logo_transparent.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize((90, 90), Image.Resampling.LANCZOS)
        img.paste(logo, ((W - 90) // 2, 105), logo)

    draw.text(((W - draw.textlength("OVERDOG AI", font=f_brand)) // 2, 210), "OVERDOG AI", font=f_brand, fill=(255, 255, 255))

    title_tag = "NBA MONDAY NIGHT · MODELO V2"
    tw = draw.textlength(title_tag, font=f_tag) + 40
    tx = (W - tw) // 2
    draw.rounded_rectangle([tx, 270, tx + tw, 315], radius=20, fill=(15, 28, 38), outline=THEME_GREEN, width=2)
    draw.text(((W - draw.textlength(title_tag, font=f_tag)) // 2, 280), title_tag, font=f_tag, fill=THEME_GREEN)

    # Main Headline
    draw.text(((W - draw.textlength("TOP 3 PICKS DE LA NBA", font=f_title)) // 2, 340), "TOP 3 PICKS DE LA NBA", font=f_title, fill=(255, 255, 255))
    h_sub = "Ventajas matemáticas detectadas por IA frente a las casas de apuestas"
    draw.text(((W - draw.textlength(h_sub, font=f_sub)) // 2, 430), h_sub, font=f_sub, fill=(148, 163, 184))

    # -------------------------------------------------------------
    # 3 PICK CARDS (Y: 480 to 1480)
    # -------------------------------------------------------------
    picks = [
        {
            "tag": "TOTAL DE PARTIDO · LÍNEA DE PISO",
            "tag_color": THEME_GOLD,
            "matchup": "Detroit Pistons @ Charlotte Hornets",
            "time": "18:30 CDMX",
            "market": "OVER 210.5 PUNTOS",
            "odds": "MOMIO: -110 (1.91)",
            "conf": "ALTA CONVICCIÓN",
            "desc": "Línea sumamente baja para la NBA moderna (media: 228 pts).\nRitmo acelerado de posesiones y defensas vulnerables.",
            "metrics": [("PROYECCIÓN IA", "219+ PTS"), ("EVALUACIÓN", "VALOR ALTO")]
        },
        {
            "tag": "MONEYLINE · EFICIENCIA NETA",
            "tag_color": THEME_GREEN,
            "matchup": "Washington Wizards @ Orlando Magic",
            "time": "18:30 CDMX",
            "market": "ORLANDO MAGIC ML",
            "odds": "MOMIO: -148 (1.68)",
            "conf": "ALTA CONVICCIÓN",
            "desc": "Orlando es defensa Top 5 en casa y recibe a un equipo en\nreconstrucción. Cuota inflada frente a la probabilidad real.",
            "metrics": [("PROB. MODELO", "68.4%"), ("VENTAJA", "+EDGE 6.1%")]
        },
        {
            "tag": "SPREAD · COLCHÓN DEFENSIVO",
            "tag_color": THEME_BLUE,
            "matchup": "Chicago Bulls @ Philadelphia 76ers",
            "time": "18:30 CDMX",
            "market": "CHICAGO BULLS +11.5",
            "odds": "MOMIO: -110 (1.91)",
            "conf": "ALTA CONVICCIÓN",
            "desc": "Colchón de casi 12 puntos en favor de Bulls. Philadelphia\nbaja el ritmo en 4to cuarto y Chicago compite en perímetro.",
            "metrics": [("LÍNEA BOOK", "+11.5 PTS"), ("VALORACIÓN", "COBERTURA")]
        }
    ]

    card_y = 485
    card_h = 300

    for i, p in enumerate(picks):
        # Container Box
        draw.rounded_rectangle([CARD_X, card_y, CARD_X + CARD_W, card_y + card_h], radius=24, fill=(12, 19, 32), outline=(35, 52, 75), width=2)

        # Top Tag Bar
        draw.text((CARD_X + 35, card_y + 22), p["tag"], font=f_badge, fill=p["tag_color"])
        draw.text((CARD_X + CARD_W - 165, card_y + 22), p["time"], font=f_badge, fill=(148, 163, 184))

        # Matchup Title
        draw.text((CARD_X + 35, card_y + 55), p["matchup"], font=f_card_team, fill=(255, 255, 255))

        # Inner Pick Banner
        p_box_y = card_y + 105
        draw.rounded_rectangle([CARD_X + 30, p_box_y, CARD_X + CARD_W - 30, p_box_y + 90], radius=16, fill=(18, 28, 44), outline=(45, 65, 95), width=1)
        
        # Pick Name (Left)
        draw.text((CARD_X + 50, p_box_y + 18), p["market"], font=f_pick_val, fill=THEME_GREEN)
        
        # Odds (Right)
        w_odds = draw.textlength(p["odds"], font=f_card_team)
        draw.text((CARD_X + CARD_W - 55 - w_odds, p_box_y + 28), p["odds"], font=f_card_team, fill=THEME_GOLD)

        # Description
        desc_lines = p["desc"].split("\n")
        d_y = card_y + 215
        for dl in desc_lines:
            draw.text((CARD_X + 35, d_y), dl, font=f_desc, fill=(203, 213, 225))
            d_y += 30

        card_y += card_h + 35

    # -------------------------------------------------------------
    # FOOTER / CTA
    # -------------------------------------------------------------
    t_y = 1525
    draw.rounded_rectangle([CARD_X, t_y, CARD_X + CARD_W, t_y + 105], radius=20, fill=(10, 16, 26), outline=(35, 48, 70), width=2)
    t_top = "GESTIÓN DE CAPITAL: 1 UNIDAD FIJA POR JUGADA"
    t_bot = "Sin martingalas. Jugar en derecho para rentabilidad sostenida."
    draw.text(((W - draw.textlength(t_top, font=f_tag)) // 2, t_y + 22), t_top, font=f_tag, fill=THEME_GREEN)
    draw.text(((W - draw.textlength(t_bot, font=f_sub)) // 2, t_y + 60), t_bot, font=f_sub, fill=(203, 213, 225))

    btn_y = 1655
    btn_w = CARD_W - 80
    btn_x = (W - btn_w) // 2
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + 85], radius=22, fill=(0, 136, 204))
    btn_text = "Picks completos en Telegram: @overdogai"
    draw.text(((W - draw.textlength(btn_text, font=f_cta)) // 2, btn_y + 24), btn_text, font=f_cta, fill=(255, 255, 255))

    disc = "Sports Intelligence · Cero humo · Solo modelos matemáticos"
    draw.text(((W - draw.textlength(disc, font=f_sub)) // 2, 1775), disc, font=f_sub, fill=(100, 116, 139))

    out_p = "assets/tarjeta_top3_nba_lunes.png"
    img.save(out_p, "PNG")
    img.save(out_p.replace(".png", ".jpg"), "JPEG", quality=95)
    print("Tarjeta guardada en:", out_p)

create_card()
