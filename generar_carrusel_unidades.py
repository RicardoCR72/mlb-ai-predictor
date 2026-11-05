import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1350
font_dir = "C:/Windows/Fonts"

# Typography
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 24)
f_h1_huge = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 82)
f_h1 = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 68)
f_h2 = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
f_body_bold = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
f_body = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 26)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 22)
f_math = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 54)
f_btn = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_page = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)

THEME_GREEN = (0, 255, 163)
THEME_GOLD = (255, 215, 0)
THEME_BLUE = (56, 189, 248)
THEME_RED = (239, 68, 68)

MARGIN_X = 90
CONTENT_W = W - 2 * MARGIN_X # 900

def create_base(slide_num, total_slides=5):
    # Dark solid gradient
    y_coords = np.linspace(0, 1, H)
    r = (12 * (1 - y_coords) + 7 * y_coords).astype(np.uint8)
    g = (20 * (1 - y_coords) + 12 * y_coords).astype(np.uint8)
    b = (32 * (1 - y_coords) + 18 * y_coords).astype(np.uint8)
    
    bg = np.zeros((H, W, 3), dtype=np.uint8)
    bg[:, :, 0] = r[:, None]
    bg[:, :, 1] = g[:, None]
    bg[:, :, 2] = b[:, None]
    
    img = Image.fromarray(bg).convert("RGB")
    draw = ImageDraw.Draw(img)
    
    # Top Header: Logo + Brand + Page indicator
    logo_path = "assets/overdog_logo_transparent.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize((60, 60), Image.Resampling.LANCZOS)
        img.paste(logo, (MARGIN_X, 65), logo)
        draw.text((MARGIN_X + 75, 78), "OVERDOG AI · EDUCACIÓN", font=f_brand, fill=(255, 255, 255))
    else:
        draw.text((MARGIN_X, 78), "OVERDOG AI · EDUCACIÓN", font=f_brand, fill=(255, 255, 255))
        
    page_str = f"{slide_num}/{total_slides}"
    draw.text((W - MARGIN_X - draw.textlength(page_str, font=f_page), 78), page_str, font=f_page, fill=THEME_GREEN)
    
    # Subtle top separator
    draw.line([(MARGIN_X, 145), (W - MARGIN_X, 145)], fill=(30, 42, 60), width=2)
    
    return img, draw

# =============================================================
# SLIDE 1: COVER
# =============================================================
def make_slide1():
    img, draw = create_base(1)
    
    # Category pill
    pill_txt = "GUÍA DE GESTIÓN DE CAPITAL (BANKROLL)"
    pw = draw.textlength(pill_txt, font=f_tag) + 36
    draw.rounded_rectangle([MARGIN_X, 210, MARGIN_X + pw, 260], radius=16, fill=(16, 28, 42), outline=THEME_GREEN, width=2)
    draw.text((MARGIN_X + 18, 222), pill_txt, font=f_tag, fill=THEME_GREEN)
    
    # Hero Title
    draw.text((MARGIN_X, 310), "¿QUÉ SIGNIFICA", font=f_h1_huge, fill=(255, 255, 255))
    draw.text((MARGIN_X, 410), '"1 UNIDAD"', font=f_h1_huge, fill=THEME_GREEN)
    draw.text((MARGIN_X, 510), "EN LAS APUESTAS?", font=f_h1_huge, fill=(255, 255, 255))
    
    # Hero Subtitle Card
    c_y = 660
    c_h = 360
    draw.rounded_rectangle([MARGIN_X, c_y, MARGIN_X + CONTENT_W, c_y + c_h], radius=28, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
    
    s_h = "EL SECRETO QUE NADIE TE ENSEÑA:"
    draw.text((MARGIN_X + 45, c_y + 40), s_h, font=f_tag, fill=THEME_GOLD)
    
    desc_p1 = "La diferencia entre un apostador novato que pierde"
    desc_p2 = "todo su dinero en una semana y un inversionista"
    desc_p3 = "que gana a largo plazo no es la 'suerte'..."
    desc_p4 = "es la gestión matemática de unidades."
    
    draw.text((MARGIN_X + 45, c_y + 95), desc_p1, font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + 45, c_y + 140), desc_p2, font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + 45, c_y + 185), desc_p3, font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + 45, c_y + 250), desc_p4, font=f_body_bold, fill=THEME_GREEN)
    
    # Swipe CTA
    swipe_y = 1120
    draw.rounded_rectangle([MARGIN_X, swipe_y, MARGIN_X + CONTENT_W, swipe_y + 110], radius=24, fill=(10, 18, 30), outline=THEME_GREEN, width=2)
    sw_txt = "DESLIZA PARA APRENDER LA REGLA DE ORO →"
    draw.text(((W - draw.textlength(sw_txt, font=f_btn)) // 2, swipe_y + 36), sw_txt, font=f_btn, fill=(255, 255, 255))
    
    out = "assets/carrusel_unidades_slide1.png"
    img.save(out, "PNG")
    print("Slide 1 guardado:", out)

# =============================================================
# SLIDE 2: EL BANKROLL
# =============================================================
def make_slide2():
    img, draw = create_base(2)
    
    draw.text((MARGIN_X, 190), "PASO 1 · TU CAPITAL INICIAL", font=f_tag, fill=THEME_BLUE)
    draw.text((MARGIN_X, 235), "¿QUÉ ES EL BANKROLL?", font=f_h1, fill=(255, 255, 255))
    
    # Concept box
    c_y = 350
    c_h = 240
    draw.rounded_rectangle([MARGIN_X, c_y, MARGIN_X + CONTENT_W, c_y + c_h], radius=24, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
    draw.text((MARGIN_X + 45, c_y + 35), "TU 'BANCA' ES EL CAPITAL DE TU EMPRESA:", font=f_tag, fill=THEME_GOLD)
    t1 = "El Bankroll es la cantidad total de dinero que separas"
    t2 = "EXCLUSIVAMENTE para operar en deportes durante una"
    t3 = "temporada completa. Es tu fondo de inversión."
    draw.text((MARGIN_X + 45, c_y + 85), t1, font=f_body, fill=(226, 232, 240))
    draw.text((MARGIN_X + 45, c_y + 125), t2, font=f_body, fill=(226, 232, 240))
    draw.text((MARGIN_X + 45, c_y + 165), t3, font=f_body, fill=(226, 232, 240))
    
    # 2 Rules
    r_y = 630
    draw.text((MARGIN_X, r_y), "LAS 2 REGLAS SAGRADAS DEL BANKROLL:", font=f_h2, fill=(255, 255, 255))
    
    # Card Rule 1 (Red)
    draw.rounded_rectangle([MARGIN_X, r_y + 60, MARGIN_X + CONTENT_W, r_y + 190], radius=20, fill=(35, 15, 20), outline=THEME_RED, width=2)
    draw.text((MARGIN_X + 35, r_y + 85), "1. NUNCA ARRIESGUES DINERO DE VIVIR", font=f_body_bold, fill=THEME_RED)
    draw.text((MARGIN_X + 35, r_y + 130), "Prohibido usar dinero de renta, comida, servicios o deudas.", font=f_body, fill=(203, 213, 225))
    
    # Card Rule 2 (Green)
    draw.rounded_rectangle([MARGIN_X, r_y + 220, MARGIN_X + CONTENT_W, r_y + 350], radius=20, fill=(10, 32, 25), outline=THEME_GREEN, width=2)
    draw.text((MARGIN_X + 35, r_y + 245), "2. CONSIDERA ESE CAPITAL COMO UNA INVERSIÓN", font=f_body_bold, fill=THEME_GREEN)
    draw.text((MARGIN_X + 35, r_y + 290), "Dinero con el que puedes tolerar altas y bajas a largo plazo.", font=f_body, fill=(203, 213, 225))
    
    # Swipe
    s_note = "Ahora que tienes tu Bankroll... ¿Cómo se divide? Desliza →"
    draw.text(((W - draw.textlength(s_note, font=f_sub)) // 2, 1180), s_note, font=f_sub, fill=(148, 163, 184))
    
    out = "assets/carrusel_unidades_slide2.png"
    img.save(out, "PNG")
    print("Slide 2 guardado:", out)

# =============================================================
# SLIDE 3: LA FÓRMULA (1U = 1%)
# =============================================================
def make_slide3():
    img, draw = create_base(3)
    
    draw.text((MARGIN_X, 190), "PASO 2 · LA MEDIDA MATEMÁTICA", font=f_tag, fill=THEME_GOLD)
    draw.text((MARGIN_X, 235), "¿QUÉ ES EXACTAMENTE 1U?", font=f_h1, fill=(255, 255, 255))
    
    # Formula Box
    f_y = 330
    draw.rounded_rectangle([MARGIN_X, f_y, MARGIN_X + CONTENT_W, f_y + 150], radius=24, fill=(10, 30, 24), outline=THEME_GREEN, width=3)
    form_str = "1 UNIDAD (1U) = 1% DE TU BANKROLL"
    draw.text(((W - draw.textlength(form_str, font=f_math)) // 2, f_y + 45), form_str, font=f_math, fill=THEME_GREEN)
    
    # Explanation
    draw.text((MARGIN_X, 520), "EJEMPLOS PRÁCTICOS SEGÚN TU CAPITAL:", font=f_h2, fill=(255, 255, 255))
    
    table_y = 585
    examples = [
        ("Bankroll de $1,000 MXN", "1 Unidad (1U) =", "$10 MXN"),
        ("Bankroll de $5,000 MXN", "1 Unidad (1U) =", "$50 MXN"),
        ("Bankroll de $20,000 MXN", "1 Unidad (1U) =", "$200 MXN"),
        ("Bankroll de $100,000 MXN", "1 Unidad (1U) =", "$1,000 MXN")
    ]
    
    for i, (b_txt, u_lbl, val_txt) in enumerate(examples):
        ey = table_y + i * 115
        draw.rounded_rectangle([MARGIN_X, ey, MARGIN_X + CONTENT_W, ey + 95], radius=18, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
        draw.text((MARGIN_X + 35, ey + 30), b_txt, font=f_body_bold, fill=(255, 255, 255))
        draw.text((MARGIN_X + 440, ey + 32), u_lbl, font=f_sub, fill=(148, 163, 184))
        draw.text((MARGIN_X + 680, ey + 24), val_txt, font=f_body_bold, fill=THEME_GOLD)
        
    c_note = "Todos jugamos el mismo pick, pero cada quien arriesga su 1%."
    draw.text(((W - draw.textlength(c_note, font=f_sub)) // 2, 1140), c_note, font=f_sub, fill=THEME_GREEN)
    
    out = "assets/carrusel_unidades_slide3.png"
    img.save(out, "PNG")
    print("Slide 3 guardado:", out)

# =============================================================
# SLIDE 4: POR QUÉ USAR UNIDADES Y NO PESOS/DÓLARES
# =============================================================
def make_slide4():
    img, draw = create_base(4)
    
    draw.text((MARGIN_X, 190), "PASO 3 · TRANSPARENCIA REAL", font=f_tag, fill=THEME_BLUE)
    draw.text((MARGIN_X, 235), "¿POR QUÉ NO HABLAR DE DINERO?", font=f_h1, fill=(255, 255, 255))
    
    # Comparison 2 Columns
    c_y = 330
    h_box = 240
    box_w = (CONTENT_W - 30) // 2
    
    # Left: False tipster
    draw.rounded_rectangle([MARGIN_X, c_y, MARGIN_X + box_w, c_y + h_box], radius=20, fill=(35, 15, 20), outline=THEME_RED, width=2)
    draw.text((MARGIN_X + 25, c_y + 25), "EL VENDE-HUMO:", font=f_tag, fill=THEME_RED)
    draw.text((MARGIN_X + 25, c_y + 70), '“¡GANÉ $50,000 HOY!”', font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + 25, c_y + 120), "Te engaña mostrando dinero\npero ocultando que arriesgó\ntodo su capital a una sola carta.", font=f_sub, fill=(203, 213, 225))
    
    # Right: Overdog AI Quantitative
    rx = MARGIN_X + box_w + 30
    draw.rounded_rectangle([rx, c_y, rx + box_w, c_y + h_box], radius=20, fill=(10, 32, 25), outline=THEME_GREEN, width=2)
    draw.text((rx + 25, c_y + 25), "OVERDOG AI (DATOS):", font=f_tag, fill=THEME_GREEN)
    draw.text((rx + 25, c_y + 70), "MEDIMOS UNIDADES Y ROI", font=f_body_bold, fill=(255, 255, 255))
    draw.text((rx + 25, c_y + 120), "Muestra la rentabilidad real\ny matemática sin importar\nsi juegas $50 o $50,000 pesos.", font=f_sub, fill=(203, 213, 225))
    
    # Case Study: Season to date (+46.66 U)
    cs_y = 615
    cs_h = 470
    draw.rounded_rectangle([MARGIN_X, cs_y, MARGIN_X + CONTENT_W, cs_y + cs_h], radius=24, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
    
    draw.text((MARGIN_X + 40, cs_y + 35), "CASO REAL · OVERDOG AI SEMANAS 3 A 8 (NFL):", font=f_tag, fill=THEME_GOLD)
    draw.text((MARGIN_X + 40, cs_y + 75), "+46.66 UNIDADES GANADAS", font=f_h1, fill=THEME_GREEN)
    
    draw.line([(MARGIN_X + 40, cs_y + 170), (MARGIN_X + CONTENT_W - 40, cs_y + 170)], fill=(30, 42, 60), width=2)
    
    draw.text((MARGIN_X + 40, cs_y + 195), "Si tu unidad era de $100:", font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + CONTENT_W - 250, cs_y + 195), "+$4,666 MXN", font=f_body_bold, fill=THEME_GREEN)
    
    draw.text((MARGIN_X + 40, cs_y + 255), "Si tu unidad era de $500:", font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + CONTENT_W - 250, cs_y + 255), "+$23,330 MXN", font=f_body_bold, fill=THEME_GREEN)
    
    draw.text((MARGIN_X + 40, cs_y + 315), "Si tu unidad era de $1,000:", font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + CONTENT_W - 250, cs_y + 315), "+$46,660 MXN", font=f_body_bold, fill=THEME_GREEN)
    
    draw.text((MARGIN_X + 40, cs_y + 395), "La ventaja matemática funciona exactamente igual para todos.", font=f_sub, fill=(148, 163, 184))
    
    out = "assets/carrusel_unidades_slide4.png"
    img.save(out, "PNG")
    print("Slide 4 guardado:", out)

# =============================================================
# SLIDE 5: CONCLUSIÓN Y LLAMADO A LA ACCIÓN
# =============================================================
def make_slide5():
    img, draw = create_base(5)
    
    draw.text((MARGIN_X, 190), "CONCLUSIÓN · LA REGLA DE ÉXITO", font=f_tag, fill=THEME_GREEN)
    draw.text((MARGIN_X, 235), "CÓMO OPERAR CON ÉXITO:", font=f_h1, fill=(255, 255, 255))
    
    # 3 Mantras
    m_y = 330
    mantras = [
        ("1. ASIGNA SIEMPRE 1 UNIDAD FIJA", "Nunca hagas 'All-in' ni aumentes el monto para recuperar pérdidas."),
        ("2. ACEPTA LA VARIANZA A CORTO PLAZO", "Habrá días con -1U o -2U, pero a 50 picks el algoritmo gana."),
        ("3. AUDITA CADA JUGADA EN FRÍO", "Lleva registro de tus unidades ganadas y perdidas en una hoja o app.")
    ]
    
    for i, (m_h, m_d) in enumerate(mantras):
        my_box = m_y + i * 145
        draw.rounded_rectangle([MARGIN_X, my_box, MARGIN_X + CONTENT_W, my_box + 120], radius=20, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
        draw.text((MARGIN_X + 35, my_box + 25), m_h, font=f_body_bold, fill=THEME_GOLD)
        draw.text((MARGIN_X + 35, my_box + 68), m_d, font=f_body, fill=(203, 213, 225))
        
    # Big CTA Box
    cta_y = 800
    cta_h = 320
    draw.rounded_rectangle([MARGIN_X, cta_y, MARGIN_X + CONTENT_W, cta_y + cta_h], radius=28, fill=(10, 24, 38), outline=THEME_GREEN, width=3)
    
    draw.text(((W - draw.textlength("¿LISTO PARA OPERAR CON DATOS REALES?", font=f_tag)) // 2, cta_y + 35), "¿LISTO PARA OPERAR CON DATOS REALES?", font=f_tag, fill=THEME_GOLD)
    draw.text(((W - draw.textlength("ÚNETE AL CANAL DE TELEGRAM", font=f_h2)) // 2, cta_y + 80), "ÚNETE AL CANAL DE TELEGRAM", font=f_h2, fill=(255, 255, 255))
    
    # Telegram Button inside CTA
    btn_y = cta_y + 155
    btn_w = CONTENT_W - 80
    btn_x = (W - btn_w) // 2
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + 85], radius=22, fill=(0, 136, 204))
    b_txt = "Canal Gratuito: @overdogai"
    draw.text(((W - draw.textlength(b_txt, font=f_btn)) // 2, btn_y + 24), b_txt, font=f_btn, fill=(255, 255, 255))
    
    bio_txt = "Enlace directo en la biografía del perfil"
    draw.text(((W - draw.textlength(bio_txt, font=f_sub)) // 2, cta_y + 265), bio_txt, font=f_sub, fill=(148, 163, 184))
    
    # Bottom Reminder
    rem = "💾 GUARDA ESTE POST PARA REVISAR TU GESTIÓN DE CAPITAL"
    draw.text(((W - draw.textlength(rem, font=f_sub)) // 2, 1180), rem, font=f_sub, fill=THEME_GREEN)
    
    out = "assets/carrusel_unidades_slide5.png"
    img.save(out, "PNG")
    print("Slide 5 guardado:", out)

make_slide1()
make_slide2()
make_slide3()
make_slide4()
make_slide5()
