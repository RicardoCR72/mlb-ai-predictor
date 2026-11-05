import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W = 1080
H = 1920
font_dir = "C:/Windows/Fonts"

# Typography
f_brand = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 36)
f_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26)
f_h1_huge = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 96)
f_h1 = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 76)
f_h2 = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 42)
f_body_bold = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_body = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 28)
f_sub = ImageFont.truetype(os.path.join(font_dir, "arial.ttf"), 24)
f_math = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 60)
f_btn = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
f_page = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)

THEME_GREEN = (0, 255, 163)
THEME_GOLD = (255, 215, 0)
THEME_BLUE = (56, 189, 248)
THEME_RED = (239, 68, 68)

# TikTok Safe Zone: Margins 90px on sides, clear 180px on top, clear 280px on bottom
MARGIN_X = 90
CONTENT_W = W - 2 * MARGIN_X # 900

def create_base(slide_num, total_slides=5):
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
    
    # Top Header inside safe area (y: 140)
    logo_path = "assets/overdog_logo_transparent.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize((70, 70), Image.Resampling.LANCZOS)
        img.paste(logo, (MARGIN_X, 135), logo)
        draw.text((MARGIN_X + 85, 148), "OVERDOG AI · EDUCACIÓN", font=f_brand, fill=(255, 255, 255))
    else:
        draw.text((MARGIN_X, 148), "OVERDOG AI · EDUCACIÓN", font=f_brand, fill=(255, 255, 255))
        
    page_str = f"{slide_num}/{total_slides}"
    draw.text((W - MARGIN_X - draw.textlength(page_str, font=f_page), 148), page_str, font=f_page, fill=THEME_GREEN)
    
    draw.line([(MARGIN_X, 225), (W - MARGIN_X, 225)], fill=(30, 42, 60), width=2)
    return img, draw

# =============================================================
# SLIDE 1: PORTADA TIKTOK (9:16)
# =============================================================
def make_slide1():
    img, draw = create_base(1)
    
    pill_txt = "GUÍA DE GESTIÓN DE CAPITAL (BANKROLL)"
    pw = draw.textlength(pill_txt, font=f_tag) + 36
    draw.rounded_rectangle([MARGIN_X, 290, MARGIN_X + pw, 345], radius=16, fill=(16, 28, 42), outline=THEME_GREEN, width=2)
    draw.text((MARGIN_X + 18, 303), pill_txt, font=f_tag, fill=THEME_GREEN)
    
    draw.text((MARGIN_X, 400), "¿QUÉ SIGNIFICA", font=f_h1_huge, fill=(255, 255, 255))
    draw.text((MARGIN_X, 510), '"1 UNIDAD"', font=f_h1_huge, fill=THEME_GREEN)
    draw.text((MARGIN_X, 620), "EN LAS APUESTAS?", font=f_h1_huge, fill=(255, 255, 255))
    
    c_y = 800
    c_h = 440
    draw.rounded_rectangle([MARGIN_X, c_y, MARGIN_X + CONTENT_W, c_y + c_h], radius=28, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
    
    draw.text((MARGIN_X + 45, c_y + 45), "EL SECRETO QUE NADIE TE ENSEÑA:", font=f_tag, fill=THEME_GOLD)
    
    desc_lines = [
        "La diferencia entre un apostador novato que pierde",
        "todo su dinero en una semana y un inversionista",
        "que gana a largo plazo no es la 'suerte'...",
        "",
        "es la gestión matemática de unidades."
    ]
    dy = c_y + 110
    for l in desc_lines:
        if l == "es la gestión matemática de unidades.":
            draw.text((MARGIN_X + 45, dy), l, font=f_body_bold, fill=THEME_GREEN)
        else:
            draw.text((MARGIN_X + 45, dy), l, font=f_body_bold, fill=(255, 255, 255))
        dy += 50
        
    swipe_y = 1320
    draw.rounded_rectangle([MARGIN_X, swipe_y, MARGIN_X + CONTENT_W, swipe_y + 110], radius=24, fill=(10, 18, 30), outline=THEME_GREEN, width=2)
    sw_txt = "DESLIZA PARA APRENDER LA REGLA DE ORO →"
    draw.text(((W - draw.textlength(sw_txt, font=f_btn)) // 2, swipe_y + 36), sw_txt, font=f_btn, fill=(255, 255, 255))
    
    out = "assets/tiktok_unidades_slide1.png"
    img.save(out, "PNG")
    print("Guardado:", out)

# =============================================================
# SLIDE 2: EL BANKROLL (9:16)
# =============================================================
def make_slide2():
    img, draw = create_base(2)
    
    draw.text((MARGIN_X, 270), "PASO 1 · TU CAPITAL INICIAL", font=f_tag, fill=THEME_BLUE)
    draw.text((MARGIN_X, 320), "¿QUÉ ES EL BANKROLL?", font=f_h1, fill=(255, 255, 255))
    
    c_y = 440
    c_h = 280
    draw.rounded_rectangle([MARGIN_X, c_y, MARGIN_X + CONTENT_W, c_y + c_h], radius=24, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
    draw.text((MARGIN_X + 45, c_y + 40), "TU 'BANCA' ES EL CAPITAL DE TU EMPRESA:", font=f_tag, fill=THEME_GOLD)
    t_lines = [
        "El Bankroll es la cantidad total de dinero que separas",
        "EXCLUSIVAMENTE para operar en deportes durante una",
        "temporada completa. Es tu fondo de inversión."
    ]
    ty = c_y + 95
    for l in t_lines:
        draw.text((MARGIN_X + 45, ty), l, font=f_body, fill=(226, 232, 240))
        ty += 45
        
    r_y = 780
    draw.text((MARGIN_X, r_y), "LAS 2 REGLAS SAGRADAS DEL BANKROLL:", font=f_h2, fill=(255, 255, 255))
    
    # Rule 1
    draw.rounded_rectangle([MARGIN_X, r_y + 70, MARGIN_X + CONTENT_W, r_y + 230], radius=20, fill=(35, 15, 20), outline=THEME_RED, width=2)
    draw.text((MARGIN_X + 35, r_y + 95), "1. NUNCA ARRIESGUES DINERO DE VIVIR", font=f_body_bold, fill=THEME_RED)
    draw.text((MARGIN_X + 35, r_y + 145), "Prohibido usar dinero de renta, despensa o deudas.", font=f_body, fill=(203, 213, 225))
    
    # Rule 2
    draw.rounded_rectangle([MARGIN_X, r_y + 270, MARGIN_X + CONTENT_W, r_y + 430], radius=20, fill=(10, 32, 25), outline=THEME_GREEN, width=2)
    draw.text((MARGIN_X + 35, r_y + 295), "2. CONSIDERA ESTO COMO UNA INVERSIÓN", font=f_body_bold, fill=THEME_GREEN)
    draw.text((MARGIN_X + 35, r_y + 345), "Dinero con el que puedes tolerar altas y bajas.", font=f_body, fill=(203, 213, 225))
    
    s_note = "Ahora que tienes tu Bankroll... ¿Cómo se divide? Desliza →"
    draw.text(((W - draw.textlength(s_note, font=f_sub)) // 2, 1380), s_note, font=f_sub, fill=(148, 163, 184))
    
    out = "assets/tiktok_unidades_slide2.png"
    img.save(out, "PNG")
    print("Guardado:", out)

# =============================================================
# SLIDE 3: LA FÓRMULA (1U = 1%) (9:16)
# =============================================================
def make_slide3():
    img, draw = create_base(3)
    
    draw.text((MARGIN_X, 270), "PASO 2 · LA MEDIDA MATEMÁTICA", font=f_tag, fill=THEME_GOLD)
    draw.text((MARGIN_X, 320), "¿QUÉ ES EXACTAMENTE 1U?", font=f_h1, fill=(255, 255, 255))
    
    f_y = 440
    draw.rounded_rectangle([MARGIN_X, f_y, MARGIN_X + CONTENT_W, f_y + 160], radius=24, fill=(10, 30, 24), outline=THEME_GREEN, width=3)
    form_str = "1 UNIDAD (1U) = 1% DE TU BANKROLL"
    draw.text(((W - draw.textlength(form_str, font=f_math)) // 2, f_y + 48), form_str, font=f_math, fill=THEME_GREEN)
    
    draw.text((MARGIN_X, 660), "EJEMPLOS PRÁCTICOS SEGÚN TU CAPITAL:", font=f_h2, fill=(255, 255, 255))
    
    table_y = 740
    examples = [
        ("Bankroll de $1,000 MXN", "1 Unidad (1U) =", "$10 MXN"),
        ("Bankroll de $5,000 MXN", "1 Unidad (1U) =", "$50 MXN"),
        ("Bankroll de $20,000 MXN", "1 Unidad (1U) =", "$200 MXN"),
        ("Bankroll de $100,000 MXN", "1 Unidad (1U) =", "$1,000 MXN")
    ]
    
    for i, (b_txt, u_lbl, val_txt) in enumerate(examples):
        ey = table_y + i * 125
        draw.rounded_rectangle([MARGIN_X, ey, MARGIN_X + CONTENT_W, ey + 105], radius=18, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
        draw.text((MARGIN_X + 35, ey + 32), b_txt, font=f_body_bold, fill=(255, 255, 255))
        draw.text((MARGIN_X + 440, ey + 36), u_lbl, font=f_sub, fill=(148, 163, 184))
        draw.text((MARGIN_X + 680, ey + 28), val_txt, font=f_body_bold, fill=THEME_GOLD)
        
    c_note = "Todos jugamos el mismo pick, pero cada quien arriesga su 1%."
    draw.text(((W - draw.textlength(c_note, font=f_sub)) // 2, 1340), c_note, font=f_sub, fill=THEME_GREEN)
    
    out = "assets/tiktok_unidades_slide3.png"
    img.save(out, "PNG")
    print("Guardado:", out)

# =============================================================
# SLIDE 4: POR QUÉ USAR UNIDADES (9:16)
# =============================================================
def make_slide4():
    img, draw = create_base(4)
    
    draw.text((MARGIN_X, 270), "PASO 3 · TRANSPARENCIA REAL", font=f_tag, fill=THEME_BLUE)
    draw.text((MARGIN_X, 320), "¿POR QUÉ NO HABLAR DE DINERO?", font=f_h1, fill=(255, 255, 255))
    
    c_y = 440
    h_box = 250
    box_w = (CONTENT_W - 30) // 2
    
    draw.rounded_rectangle([MARGIN_X, c_y, MARGIN_X + box_w, c_y + h_box], radius=20, fill=(35, 15, 20), outline=THEME_RED, width=2)
    draw.text((MARGIN_X + 25, c_y + 25), "EL VENDE-HUMO:", font=f_tag, fill=THEME_RED)
    draw.text((MARGIN_X + 25, c_y + 70), '“¡GANÉ $50,000 HOY!”', font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + 25, c_y + 120), "Te engaña mostrando dinero\npero ocultando que arriesgó\ntodo su capital a una carta.", font=f_sub, fill=(203, 213, 225))
    
    rx = MARGIN_X + box_w + 30
    draw.rounded_rectangle([rx, c_y, rx + box_w, c_y + h_box], radius=20, fill=(10, 32, 25), outline=THEME_GREEN, width=2)
    draw.text((rx + 25, c_y + 25), "OVERDOG AI (DATOS):", font=f_tag, fill=THEME_GREEN)
    draw.text((rx + 25, c_y + 70), "MEDIMOS UNIDADES Y ROI", font=f_body_bold, fill=(255, 255, 255))
    draw.text((rx + 25, c_y + 120), "Muestra la rentabilidad real\ny matemática sin importar\nsi juegas $50 o $50,000.", font=f_sub, fill=(203, 213, 225))
    
    cs_y = 740
    cs_h = 520
    draw.rounded_rectangle([MARGIN_X, cs_y, MARGIN_X + CONTENT_W, cs_y + cs_h], radius=24, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
    draw.text((MARGIN_X + 40, cs_y + 35), "CASO REAL · OVERDOG AI SEMANAS 3 A 8 (NFL):", font=f_tag, fill=THEME_GOLD)
    draw.text((MARGIN_X + 40, cs_y + 75), "+46.66 UNIDADES GANADAS", font=f_h1, fill=THEME_GREEN)
    
    draw.line([(MARGIN_X + 40, cs_y + 175), (MARGIN_X + CONTENT_W - 40, cs_y + 175)], fill=(30, 42, 60), width=2)
    
    draw.text((MARGIN_X + 40, cs_y + 210), "Si tu unidad era de $100:", font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + CONTENT_W - 250, cs_y + 210), "+$4,666 MXN", font=f_body_bold, fill=THEME_GREEN)
    
    draw.text((MARGIN_X + 40, cs_y + 275), "Si tu unidad era de $500:", font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + CONTENT_W - 250, cs_y + 275), "+$23,330 MXN", font=f_body_bold, fill=THEME_GREEN)
    
    draw.text((MARGIN_X + 40, cs_y + 340), "Si tu unidad era de $1,000:", font=f_body_bold, fill=(255, 255, 255))
    draw.text((MARGIN_X + CONTENT_W - 250, cs_y + 340), "+$46,660 MXN", font=f_body_bold, fill=THEME_GREEN)
    
    draw.text((MARGIN_X + 40, cs_y + 430), "La ventaja matemática funciona exactamente igual para todos.", font=f_sub, fill=(148, 163, 184))
    
    out = "assets/tiktok_unidades_slide4.png"
    img.save(out, "PNG")
    print("Guardado:", out)

# =============================================================
# SLIDE 5: CONCLUSIÓN & CTA (9:16)
# =============================================================
def make_slide5():
    img, draw = create_base(5)
    
    draw.text((MARGIN_X, 270), "CONCLUSIÓN · LA REGLA DE ÉXITO", font=f_tag, fill=THEME_GREEN)
    draw.text((MARGIN_X, 320), "CÓMO OPERAR CON ÉXITO:", font=f_h1, fill=(255, 255, 255))
    
    m_y = 440
    mantras = [
        ("1. ASIGNA SIEMPRE 1 UNIDAD FIJA", "Nunca hagas 'All-in' ni aumentes el monto para recuperar pérdidas."),
        ("2. ACEPTA LA VARIANZA A CORTO PLAZO", "Habrá días con -1U o -2U, pero a 50 picks el algoritmo gana."),
        ("3. AUDITA CADA JUGADA EN FRÍO", "Lleva registro de tus unidades ganadas y perdidas en una hoja.")
    ]
    for i, (m_h, m_d) in enumerate(mantras):
        my_box = m_y + i * 155
        draw.rounded_rectangle([MARGIN_X, my_box, MARGIN_X + CONTENT_W, my_box + 130], radius=20, fill=(14, 22, 36), outline=(35, 52, 75), width=2)
        draw.text((MARGIN_X + 35, my_box + 25), m_h, font=f_body_bold, fill=THEME_GOLD)
        draw.text((MARGIN_X + 35, my_box + 72), m_d, font=f_body, fill=(203, 213, 225))
        
    cta_y = 960
    cta_h = 340
    draw.rounded_rectangle([MARGIN_X, cta_y, MARGIN_X + CONTENT_W, cta_y + cta_h], radius=28, fill=(10, 24, 38), outline=THEME_GREEN, width=3)
    draw.text(((W - draw.textlength("¿LISTO PARA OPERAR CON DATOS REALES?", font=f_tag)) // 2, cta_y + 40), "¿LISTO PARA OPERAR CON DATOS REALES?", font=f_tag, fill=THEME_GOLD)
    draw.text(((W - draw.textlength("ÚNETE AL CANAL DE TELEGRAM", font=f_h2)) // 2, cta_y + 90), "ÚNETE AL CANAL DE TELEGRAM", font=f_h2, fill=(255, 255, 255))
    
    btn_y = cta_y + 170
    btn_w = CONTENT_W - 80
    btn_x = (W - btn_w) // 2
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + 85], radius=22, fill=(0, 136, 204))
    b_txt = "Canal Gratuito: @overdogai"
    draw.text(((W - draw.textlength(b_txt, font=f_btn)) // 2, btn_y + 24), b_txt, font=f_btn, fill=(255, 255, 255))
    
    bio_txt = "Enlace directo en la biografía del perfil"
    draw.text(((W - draw.textlength(bio_txt, font=f_sub)) // 2, cta_y + 280), bio_txt, font=f_sub, fill=(148, 163, 184))
    
    rem = "💾 GUARDA ESTE VIDEO/POST PARA REVISAR TU GESTIÓN"
    draw.text(((W - draw.textlength(rem, font=f_sub)) // 2, 1380), rem, font=f_sub, fill=THEME_GREEN)
    
    out = "assets/tiktok_unidades_slide5.png"
    img.save(out, "PNG")
    print("Guardado:", out)

make_slide1()
make_slide2()
make_slide3()
make_slide4()
make_slide5()
