import asyncio
import edge_tts
import subprocess
import os

VOZ_LOCUTOR = "es-MX-JorgeNeural"
AUDIO_OUTPUT = "assets/voz_nba_top3.mp3"
VIDEO_FINAL = "assets/video_top3_nba_tiktok.mp4"

TEXTO_GUION = (
    "Hoy la cartelera de la NBA tiene quince partidos, y nuestro modelo matemático "
    "detectó tres ventajas brutales frente a las casas de apuestas para este lunes. "
    "Número uno: en Charlotte, Detroit Pistons frente a Hornets, Over doscientos diez punto cinco puntos. "
    "Una línea de piso ridículamente baja para el ritmo acelerado de ambos equipos. "
    "Número dos: Orlando Magic a ganar directo en Moneyline. Su defensa en casa es de élite "
    "y reciben a unos Wizards en plena reconstrucción. "
    "Y número tres: Chicago Bulls más once punto cinco frente a Filadelfia, un colchón de casi doce puntos "
    "con gran valor estadístico de cobertura. "
    "Recuerda: siempre una unidad fija por jugada. "
    "Los momios y análisis completos están gratis en nuestro canal de Telegram. Enlace directo en el perfil."
)

async def generar_audio():
    print("Generando voz en off profesional con Jorge Neural (es-MX)...")
    comunicador = edge_tts.Communicate(TEXTO_GUION, VOZ_LOCUTOR, rate="+4%")
    await comunicador.save(AUDIO_OUTPUT)
    print("Audio generado exitosamente:", AUDIO_OUTPUT)

def ensamblar_video():
    # Get audio duration
    cmd_probe = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", AUDIO_OUTPUT
    ]
    dur_str = subprocess.check_output(cmd_probe).decode().strip()
    duracion = float(dur_str) + 0.8
    print(f"Duración de voz en off: {duracion:.2f}s")

    # Combine card image with zoompan effect and voice audio
    cmd_ffmpeg = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", "assets/tarjeta_top3_nba_lunes.png",
        "-i", AUDIO_OUTPUT,
        "-vf", (
            f"scale=1080:1920,"
            f"zoompan=z='min(zoom+0.0003,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"
        ),
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duracion),
        "-shortest",
        VIDEO_FINAL
    ]
    print("Renderizando video MP4 para TikTok...")
    subprocess.run(cmd_ffmpeg, check=True)
    print("Video listo:", VIDEO_FINAL)

async def main():
    await generar_audio()
    ensamblar_video()

if __name__ == "__main__":
    asyncio.run(main())
