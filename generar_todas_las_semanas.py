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

def generate_weekly_card(sem_num, total_picks, win_rate_str, record_str, profit_str, roi_str, bullets, out_path):
    img, draw = render_base(f"AUDITORIA OFICIAL · SEMANA {sem_num}")

    # 1. Hero Box
    hero_y = 350
    hero_h = 240
    draw.rounded_rectangle([CARD_X, hero_y, CARD_X + CARD_W, hero_y + hero_h], radius=30, fill=(10, 20, 30), outline=THEME_GREEN, width=3)
    h_sub = f"NFL 2026 · BALANCE CONSOLIDADO SEMANA {sem_num}"
    draw.text(((W - draw.textlength(h_sub, font=f_sub)) // 2, hero_y + 25), h_sub, font=f_sub, fill=(148, 163, 184))

    hero_val = f"{profit_str} UNIDADES"
    draw.text(((W - draw.textlength(hero_val, font=f_stat_hero_val)) // 2, hero_y + 65), hero_val, font=f_stat_hero_val, fill=THEME_GREEN)
    h_note = "Ganancia neta auditada con gestion disciplinada de 1 Unidad fija"
    draw.text(((W - draw.textlength(h_note, font=f_sub)) // 2, hero_y + 185), h_note, font=f_sub, fill=(203, 213, 225))

    # 2. Metric Grid
    grid_y = 615
    grid_h = 220
    col_w = (CARD_W - 30) // 3
    metrics = [
        ("TOTAL EVALUADOS", str(total_picks), "Muestra de mercado", (255, 255, 255)),
        ("WIN RATE", win_rate_str, record_str, THEME_GREEN),
        ("ROI CONSOLIDADO", roi_str, "Retorno sobre capital", THEME_GOLD)
    ]
    for i, (lbl, val, sub_txt, col) in enumerate(metrics):
        cx = CARD_X + i * (col_w + 15)
        draw.rounded_rectangle([cx, grid_y, cx + col_w, grid_y + grid_h], radius=24, fill=(12, 19, 32), outline=(35, 50, 70), width=2)
        draw.text((cx + (col_w - draw.textlength(lbl, font=f_grid_lbl)) // 2, grid_y + 25), lbl, font=f_grid_lbl, fill=(148, 163, 184))
        draw.text((cx + (col_w - draw.textlength(val, font=f_grid_val)) // 2, grid_y + 70), val, font=f_grid_val, fill=col)
        draw.text((cx + (col_w - draw.textlength(sub_txt, font=f_grid_sub)) // 2, grid_y + 165), sub_txt, font=f_grid_sub, fill=(148, 163, 184))

    # 3. Quantitative Analysis Card
    card_y = 865
    card_h = 600
    draw.rounded_rectangle([CARD_X, card_y, CARD_X + CARD_W, card_y + card_h], radius=32, fill=(13, 19, 32), outline=(35, 52, 75), width=2)

    s_title = "ANÁLISIS CUANTITATIVO DEL MODELO"
    draw.text(((W - draw.textlength(s_title, font=f_section)) // 2, card_y + 40), s_title, font=f_section, fill=THEME_GOLD)

    b_y = card_y + 105
    for b_title, b_desc in bullets:
        draw.text((CARD_X + 50, b_y), f"• {b_title}", font=f_bullet_bold, fill=(255, 255, 255))
        b_y += 42
        for line in b_desc.split("\n"):
            draw.text((CARD_X + 68, b_y), line, font=f_bullet_text, fill=(148, 163, 184))
            b_y += 34
        b_y += 24

    add_footer(draw)

    img.save(out_path, "PNG")
    img.save(out_path.replace(".png", ".jpg"), "JPEG", quality=95)
    print(f"Generada Semana {sem_num}: {out_path}")

# -------------------------------------------------------------
# DATA FROM USER SCREENSHOTS
# -------------------------------------------------------------
weeks_data = [
    {
        "num": 3, "picks": 68, "wr": "55.9%", "rec": "38G - 30P (Rentable)", "profit": "+4.87", "roi": "+7.2%",
        "bullets": [
            ("Dominio en Props de Jugadores (+7.27 U):", "Los mercados de yardas y pases de QB superaron el 59.3% de acierto,\ncompensando la volatilidad de los totales colectivos."),
            ("Muestra Solida (68 Selecciones):", "Volumen equilibrado en la primera semana oficial de operacion,\nsuperando el punto de equilibrio de Vegas (52.4%)."),
            ("Rendimiento Neto Consistente:", "+4.87 unidades limpias generadas con stake plano de 1 unidad.")
        ]
    },
    {
        "num": 4, "picks": 90, "wr": "62.5%", "rec": "55G - 33P (2 push)", "profit": "+17.87", "roi": "+19.9%",
        "bullets": [
            ("Semana Record del Algoritmo (+17.87 U):", "Efectividad masiva de 63.4% en Props de Jugadores (+18.18 U),\nmarcando una de las mejores jornadas de la temporada."),
            ("Retorno de Inversion Extraordinario (+19.9% ROI):", "Generar casi 20% de ROI en una muestra de 90 selecciones\nestablece un estandar cuantitativo de elite en el mercado."),
            ("Ejecucion Quirurgica sin Sobreexposicion:", "90 jugadas ejecutadas rigurosamente a 1 unidad fija.")
        ]
    },
    {
        "num": 5, "picks": 94, "wr": "52.7%", "rec": "49G - 44P (1 push)", "profit": "+3.29", "roi": "+3.5%",
        "bullets": [
            ("Victoria en Semana de Alta Dispersion (+3.29 U):", "En una semana de sorpresas defensivas en la NFL, el algoritmo\nmantuvo el balance en verde cerrando por encima de las casas."),
            ("Defensa del Capital y Control de Riesgo:", "52.8% de efectividad en los 90 props analizados, demostrando\nresiliencia cuando el mercado presenta alta varianza."),
            ("Disciplina de Bankroll Inquebrantable:", "Cero apuestas desesperadas; cierre con ganancia neta positiva.")
        ]
    },
    {
        "num": 6, "picks": 84, "wr": "59.5%", "rec": "50G - 34P (Rentable)", "profit": "+9.12", "roi": "+10.9%",
        "bullets": [
            ("Solidez Ofensiva en Todos los Frentes (+9.12 U):", "Efectividad del 58.5% en props (+7.22 U) y pleno perfecto de 2-0\nen totales colectivos (+1.91 U, 95.3% ROI)."),
            ("Doble Digito en Retorno (+10.9% ROI):", "50 victorias sobre 34 derrotas en una muestra de 84 apuestas,\nsuperando por +7.1 puntos porcentuales el equilibrio."),
            ("Consistencia Comprobada:", "Cuarta semana consecutiva cerrando en terreno positivo.")
        ]
    },
    {
        "num": 7, "picks": 82, "wr": "55.6%", "rec": "45G - 36P (1 push)", "profit": "+6.78", "roi": "+8.3%",
        "bullets": [
            ("Efectividad Superior en Moneyline (75.0% Win Rate):", "9 victorias en 12 partidos analizados (+2.10 U, +17.5% ROI),\naprovechando ventajas directas de cuota en ganadores de juego."),
            ("Aporte Constante de Props (+4.83 U):", "34 aciertos en recepciones y yardas terrestres completando\nla quinta semana consecutiva de ganancias."),
            ("Gestion Metodica de Capital:", "82 picks auditados con ganancia neta superior a 6.7 unidades.")
        ]
    },
    {
        "num": 8, "picks": 54, "wr": "59.3%", "rec": "32G - 22P (Rentable)", "profit": "+4.73", "roi": "+8.8%",
        "bullets": [
            ("Ventaja Matematica Real (+6.9% sobre Vegas):", "El punto de equilibrio en cuotas promedio (-110) es 52.4%.\nNuestro modelo cerro en 59.3%, generando beneficio consistente."),
            ("Muestra Significativa (54 Picks Auditados):", "No es suerte de 3 jugadas. Son 54 selecciones en los 6 mercados\nde props NFL evaluadas en tiempo real sin manipulacion."),
            ("Cierre Dorado en el Sunday Night Football:", "Pick oficial de Jayden Daniels Under 1.5 TDs cobrado con exito.")
        ]
    }
]

for w in weeks_data:
    out_p = f"assets/tarjeta_rendimiento_semana{w['num']}.png"
    generate_weekly_card(
        sem_num=w["num"],
        total_picks=w["picks"],
        win_rate_str=w["wr"],
        record_str=w["rec"],
        profit_str=w["profit"],
        roi_str=w["roi"],
        bullets=w["bullets"],
        out_path=out_p
    )

# -------------------------------------------------------------
# 5. MASTER FINAL CARD: ALL WEEKS CONSOLIDATED (SEASON TO DATE)
# -------------------------------------------------------------
def generate_master_card():
    img, draw = render_base("ACUMULADO OFICIAL · TEMPORADA COMPLETA")

    # Grand Totals
    # Picks: 68 + 90 + 94 + 84 + 82 + 54 = 472
    # Wins: 38 + 55 + 49 + 50 + 45 + 32 = 269
    # Loss: 30 + 33 + 44 + 34 + 36 + 22 = 199
    # Push: 4
    # Profit: 4.87 + 17.87 + 3.29 + 9.12 + 6.78 + 4.73 = +46.66 u
    # Win Rate: 269 / 468 = 57.5%
    # ROI: +46.66 / 472 = +9.9%

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

    # Render each of the 6 weeks as a sleek row
    row_y = card_y + 90
    rows = [
        ("Semana 3", "68 Picks", "38G - 30P (55.9%)", "+4.87 u", "+7.2% ROI"),
        ("Semana 4", "90 Picks", "55G - 33P (62.5%)", "+17.87 u", "+19.9% ROI"),
        ("Semana 5", "94 Picks", "49G - 44P (52.7%)", "+3.29 u", "+3.5% ROI"),
        ("Semana 6", "84 Picks", "50G - 34P (59.5%)", "+9.12 u", "+10.9% ROI"),
        ("Semana 7", "82 Picks", "45G - 36P (55.6%)", "+6.78 u", "+8.3% ROI"),
        ("Semana 8", "54 Picks", "32G - 22P (59.3%)", "+4.73 u", "+8.8% ROI"),
    ]

    for sem, p_cnt, rec, prof, r_val in rows:
        # Row card
        draw.rounded_rectangle([CARD_X + 35, row_y, CARD_X + CARD_W - 35, row_y + 68], radius=16, fill=(18, 25, 40), outline=(35, 48, 70), width=1)
        # Week Name
        draw.text((CARD_X + 55, row_y + 18), sem, font=f_row_bold, fill=(255, 255, 255))
        # Picks
        draw.text((CARD_X + 220, row_y + 22), p_cnt, font=f_sub, fill=(148, 163, 184))
        # Record
        draw.text((CARD_X + 370, row_y + 22), rec, font=f_sub, fill=(203, 213, 225))
        # Profit
        draw.text((CARD_X + 660, row_y + 14), prof, font=f_row_val, fill=THEME_GREEN)
        # ROI
        draw.text((CARD_X + 795, row_y + 22), r_val, font=f_sub, fill=THEME_GOLD)
        row_y += 82

    add_footer(draw)

    out_master = "assets/tarjeta_rendimiento_acumulado_total.png"
    img.save(out_master, "PNG")
    img.save(out_master.replace(".png", ".jpg"), "JPEG", quality=95)
    print("Tarjeta Maestra de Acumulado Total generada en:", out_master)

generate_master_card()
