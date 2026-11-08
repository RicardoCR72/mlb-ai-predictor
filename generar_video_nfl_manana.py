import os
import asyncio
import subprocess
import edge_tts
from PIL import Image, ImageDraw, ImageFont

# Directorios
os.makedirs("assets", exist_ok=True)
os.makedirs("scratch", exist_ok=True)

IMG_CARD = "assets/tarjeta_nfl_bengals_falcons.png"
AUDIO_OUTPUT = "scratch/voz_nfl_manana.mp3"
VIDEO_OUTPUT = "assets/video_nfl_bengals_falcons.mp4"

TEXTO_LOCUCION = (
    "¡Arranca la NFL en Europa! Y para este juego mañanero entre Cincinnati Bengals y Atlanta Falcons, "
    "nuestro modelo matemático detectó cuatro ventajas brutales en yardas por recepción. "
    "Número uno: Tee Higgins, MÁS de 76.5 yardas. Línea en 76 y el modelo lo proyecta en 93.6 yardas, "
    "doce por ciento de valor esperado. Con la defensa cuidando a Chase, Higgins explota el perímetro. "
    "Número dos: Kyle Pitts, MENOS de 42.5 yardas. Proyectado en 33 yardas con casi trece por ciento de Edge. "
    "Número tres: Drake London, MENOS de 77.5 yardas. Proyectado en 66 yardas, una línea inflada por las casas. "
    "Y número cuatro, la joya sorpresa: Jahan Dotson, MÁS de 27.5 yardas, con proyección de 41 yardas. "
    "Guarda este video antes de la patada inicial y síguenos para la cartelera completa del mediodía."
)

def crear_tarjeta_visual():
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (10, 14, 22, 255))
    draw = ImageDraw.Draw(img)

    font_dir = "C:/Windows/Fonts"
    f_title = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 68)
    f_sub = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 30)
    f_player = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 38)
    f_stat = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
    f_pick_big = ImageFont.truetype(os.path.join(font_dir, "impact.ttf"), 48)
    f_badge = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 24)
    f_footer = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)

    # Fondo degradado o acentos
    # Header Glow
    draw.rectangle([0, 0, W, 220], fill=(16, 24, 38, 255))
    draw.line([(0, 220), (W, 220)], fill=(251, 79, 20, 255), width=4) # Bengals Orange

    # Título Header
    draw.text((W // 2, 70), "🏈 NFL · ESPECIAL MAÑANERO", font=f_title, fill=(255, 255, 255, 255), anchor="mm")
    draw.text((W // 2, 145), "BENGALS @ FALCONS · 4 PROPS DE VALOR", font=f_sub, fill=(255, 170, 102, 255), anchor="mm")
    draw.text((W // 2, 185), "Semana 9 · Modelos Cuantitativos OVERDOG", font=f_badge, fill=(164, 180, 200, 255), anchor="mm")

    picks_data = [
        {
            "jugador": "Tee Higgins (CIN)",
            "mercado": "Yardas de Recepción",
            "linea": "76.5 yd",
            "proy": "93.6 yd",
            "edge_txt": "+17.1 yd vs línea",
            "pick": "OVER 76.5",
            "color_pick": (0, 255, 163, 255), # Verde Neón
            "bg_pick": (10, 48, 30, 255),
            "ev": "+12.0% EV ⭐⭐⭐",
            "momio": "Momio: 1.91 (-115)",
            "border": (251, 79, 20, 200), # Orange
        },
        {
            "jugador": "Kyle Pitts (ATL)",
            "mercado": "Yardas de Recepción",
            "linea": "42.5 yd",
            "proy": "33.8 yd",
            "edge_txt": "-8.7 yd vs línea",
            "pick": "UNDER 42.5",
            "color_pick": (56, 189, 248, 255), # Azul Under
            "bg_pick": (12, 38, 64, 255),
            "ev": "+12.9% EV ⭐⭐⭐",
            "momio": "Momio: 1.91 (-115)",
            "border": (167, 25, 48, 200), # Falcons Red
        },
        {
            "jugador": "Drake London (ATL)",
            "mercado": "Yardas de Recepción",
            "linea": "77.5 yd",
            "proy": "66.9 yd",
            "edge_txt": "-10.6 yd vs línea",
            "pick": "UNDER 77.5",
            "color_pick": (56, 189, 248, 255), # Azul Under
            "bg_pick": (12, 38, 64, 255),
            "ev": "+12.6% EV ⭐⭐⭐",
            "momio": "Momio: 1.91 (-115)",
            "border": (167, 25, 48, 200), # Falcons Red
        },
        {
            "jugador": "Jahan Dotson (ATL)",
            "mercado": "Yardas de Recepción",
            "linea": "27.5 yd",
            "proy": "41.6 yd",
            "edge_txt": "+14.1 yd vs línea",
            "pick": "OVER 27.5",
            "color_pick": (0, 255, 163, 255), # Verde Neón
            "bg_pick": (10, 48, 30, 255),
            "ev": "+5.8% EV ⭐⭐",
            "momio": "Momio: 1.91 (-120)",
            "border": (255, 215, 0, 200), # Gold
        },
    ]

    card_y_start = 260
    card_h = 320
    card_gap = 35
    card_w = 980
    card_x = (W - card_w) // 2

    for idx, p in enumerate(picks_data):
        cy = card_y_start + idx * (card_h + card_gap)
        
        # Tarjeta contenedor
        draw.rounded_rectangle(
            [card_x, cy, card_x + card_w, cy + card_h],
            radius=20,
            fill=(18, 26, 42, 245),
            outline=p["border"],
            width=2
        )

        # Nombre jugador y EV Badge
        draw.text((card_x + 35, cy + 24), p["jugador"], font=f_player, fill=(255, 255, 255, 255))
        
        # EV pill
        ev_w = 230
        draw.rounded_rectangle(
            [card_x + card_w - ev_w - 30, cy + 20, card_x + card_w - 30, cy + 65],
            radius=12,
            fill=(26, 38, 60, 255),
            outline=(255, 215, 0, 255),
            width=1
        )
        draw.text((card_x + card_w - (ev_w // 2) - 30, cy + 42), p["ev"], font=f_badge, fill=(255, 215, 0, 255), anchor="mm")

        # Mercado
        draw.text((card_x + 35, cy + 80), f"Mercado: {p['mercado']}", font=f_stat, fill=(156, 175, 200, 255))

        # Línea divisoria suave
        draw.line([(card_x + 30, cy + 125), (card_x + card_w - 30, cy + 125)], fill=(34, 48, 74, 255), width=2)

        # Proyección y Línea
        draw.text((card_x + 35, cy + 145), f"Línea Casa: {p['linea']}", font=f_stat, fill=(200, 215, 235, 255))
        draw.text((card_x + 35, cy + 185), f"Proyección IA: ", font=f_stat, fill=(200, 215, 235, 255))
        draw.text((card_x + 230, cy + 185), p["proy"], font=f_stat, fill=(255, 215, 0, 255))
        draw.text((card_x + 35, cy + 225), f"Colchón: {p['edge_txt']}", font=f_badge, fill=(140, 160, 185, 255))
        draw.text((card_x + 35, cy + 265), p["momio"], font=f_badge, fill=(120, 140, 165, 255))

        # Recuadro grande del PICK (Derecha)
        pick_box_w = 340
        pick_box_h = 130
        p_bx = card_x + card_w - pick_box_w - 35
        p_by = cy + 145

        draw.rounded_rectangle(
            [p_bx, p_by, p_bx + pick_box_w, p_by + pick_box_h],
            radius=16,
            fill=p["bg_pick"],
            outline=p["color_pick"],
            width=3
        )
        draw.text((p_bx + pick_box_w // 2, p_by + 45), p["pick"], font=f_pick_big, fill=p["color_pick"], anchor="mm")
        draw.text((p_bx + pick_box_w // 2, p_by + 95), "RECOMENDACIÓN IA", font=f_badge, fill=(220, 240, 255, 255), anchor="mm")

    # Footer CTA
    footer_y = H - 180
    draw.rounded_rectangle(
        [60, footer_y, W - 60, footer_y + 110],
        radius=16,
        fill=(14, 20, 32, 250),
        outline=(0, 255, 163, 200),
        width=2
    )
    draw.text((W // 2, footer_y + 38), "📲 PICKS DE LA TARDE EN TELEGRAM", font=f_footer, fill=(0, 255, 163, 255), anchor="mm")
    draw.text((W // 2, footer_y + 75), "Enlace directo en la biografía / perfil", font=f_badge, fill=(200, 220, 240, 255), anchor="mm")

    img.save(IMG_CARD, "PNG")
    print(f"✅ Tarjeta vertical creada en {IMG_CARD}")


async def generar_locucion():
    print("🎙️ Generando locución con Edge-TTS (es-MX-JorgeNeural)...")
    comunicador = edge_tts.Communicate(TEXTO_LOCUCION, "es-MX-JorgeNeural", rate="+5%")
    await comunicador.save(AUDIO_OUTPUT)
    print(f"✅ Audio generado en {AUDIO_OUTPUT}")


def compilar_video():
    cmd_probe = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", AUDIO_OUTPUT
    ]
    dur_str = subprocess.check_output(cmd_probe).decode().strip()
    duracion = float(dur_str) + 0.6
    print(f"⏱️ Duración de audio: {duracion:.2f}s")

    print("🎬 Renderizando video vertical (1080x1920) con FFmpeg...")
    cmd_ffmpeg = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", IMG_CARD,
        "-i", AUDIO_OUTPUT,
        "-vf", (
            "scale=1080:1920,"
            "zoompan=z='min(zoom+0.00025,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"
        ),
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-af", "loudnorm=I=-14:LRA=7:tp=-1",
        "-t", str(duracion),
        "-shortest",
        VIDEO_OUTPUT
    ]
    subprocess.run(cmd_ffmpeg, check=True)
    print(f"🎉 ¡Video listo en {VIDEO_OUTPUT}!")


async def main():
    crear_tarjeta_visual()
    await generar_locucion()
    compilar_video()

if __name__ == "__main__":
    asyncio.run(main())

