import os
import asyncio
import subprocess
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import edge_tts

# -------------------------------------------------------------
# 1. GENERATE SYNCHRONIZED AUDIO TRACKS (INTRO, GAME, OUTRO)
# -------------------------------------------------------------
TEXT_INTRO = "¡Pick confirmado para el Sunday Night Football!"
TEXT_GAME = (
    "Analizamos Filadelfia contra Washington. "
    "Para Jayden Daniels, el mercado colocó su línea en uno punto cinco pases de touchdown. "
    "Sin embargo, nuestros algoritmos proyectan apenas uno punto cero nueve pases, "
    "ya que Washington resuelve la zona roja por tierra con acarreos de Daniels y sus corredores. "
    "Nos quedamos con Jayden Daniels Menos de uno punto cinco pases de anotación."
)
TEXT_OUTRO = (
    "Toda la analítica completa está gratis en nuestro canal de Telegram. "
    "Toca el enlace en nuestro perfil y entra gratis a la comunidad. "
    "¡Mucho éxito en el kickoff!"
)

AUDIO_INTRO = "scratch/audio_synced_intro.mp3"
AUDIO_GAME = "scratch/audio_synced_game.mp3"
AUDIO_OUTRO = "scratch/audio_synced_outro.mp3"

async def generate_all_voices():
    jobs = [
        (TEXT_INTRO, AUDIO_INTRO, "+6%"),
        (TEXT_GAME, AUDIO_GAME, "+7%"),
        (TEXT_OUTRO, AUDIO_OUTRO, "+6%")
    ]
    for text, path, rate in jobs:
        comm = edge_tts.Communicate(text=text, voice="es-MX-JorgeNeural", rate=rate)
        await comm.save(path)
        print(f"Audio generado: {path}")

asyncio.run(generate_all_voices())

def get_dur(file_path):
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        capture_output=True, text=True, check=True
    )
    return float(res.stdout.strip())

dur_intro_aud = get_dur(AUDIO_INTRO)
dur_game_aud = get_dur(AUDIO_GAME)
dur_outro_aud = get_dur(AUDIO_OUTRO)

print(f"Duraciones de audio: Intro={dur_intro_aud:.2f}s | Game={dur_game_aud:.2f}s | Outro={dur_outro_aud:.2f}s")

# Give each segment a tiny tail padding (0.3s) for breathing room
DUR_INTRO = round(dur_intro_aud + 0.35, 2)
DUR_GAME = round(dur_game_aud + 0.35, 2)
DUR_OUTRO = round(dur_outro_aud + 0.50, 2)
TOTAL_DUR = DUR_INTRO + DUR_GAME + DUR_OUTRO
print(f"Duraciones de video sincronizadas: Intro={DUR_INTRO}s | Game={DUR_GAME}s | Outro={DUR_OUTRO}s | Total={TOTAL_DUR:.2f}s")

# -------------------------------------------------------------
# 2. PRODUCE SEGMENT 1 (INTRO SLIDE + INTRO VOICE)
# -------------------------------------------------------------
SEG1_PATH = "scratch/segment1_intro.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-loop", "1", "-i", "scratch/intro_snf_slide.png",
    "-i", AUDIO_INTRO,
    "-t", str(DUR_INTRO),
    "-filter_complex",
    "[0:v]scale=1080:1920,format=yuv420p[v];[1:a]volume=1.8[a]",
    "-map", "[v]",
    "-map", "[a]",
    "-r", "30",
    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
    "-c:a", "aac", "-b:a", "192k",
    SEG1_PATH
], check=True)
print("Segmento 1 Intro generado exitosamente.")

# -------------------------------------------------------------
# 3. PRODUCE SEGMENT 2 (GAMEPLAY + CARD + GAME VOICE + FAINT CROWD)
# -------------------------------------------------------------
SEG2_PATH = "scratch/segment2_game.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-ss", "00:00:00.5",
    "-i", "assets/daniels_clip.mp4",
    "-i", "scratch/card_slip_daniels.png",
    "-i", AUDIO_GAME,
    "-t", str(DUR_GAME),
    "-filter_complex",
    "[0:v]crop=608:1080:650:0,scale=1080:1920[v_crop];"
    "[v_crop][1:v]overlay=(1080-940)/2:180[v_final];"
    "[2:a]volume=1.8[voice_boost];"
    "[0:a]volume=0.08[game_faint];"
    "[game_faint][voice_boost]amix=inputs=2:duration=first:dropout_transition=2[a_mix]",
    "-map", "[v_final]",
    "-map", "[a_mix]",
    "-r", "30",
    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
    "-c:a", "aac", "-b:a", "192k",
    SEG2_PATH
], check=True)
print("Segmento 2 Jugada con HUD generado exitosamente.")

# -------------------------------------------------------------
# 4. PRODUCE SEGMENT 3 (OUTRO SLIDE + OUTRO VOICE)
# -------------------------------------------------------------
SEG3_PATH = "scratch/segment3_outro.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-loop", "1", "-i", "scratch/outro_snf_slide.png",
    "-i", AUDIO_OUTRO,
    "-t", str(DUR_OUTRO),
    "-filter_complex",
    "[0:v]scale=1080:1920,format=yuv420p[v];[1:a]volume=1.8[a]",
    "-map", "[v]",
    "-map", "[a]",
    "-r", "30",
    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
    "-c:a", "aac", "-b:a", "192k",
    SEG3_PATH
], check=True)
print("Segmento 3 Despedida generado exitosamente.")

# -------------------------------------------------------------
# 5. CONCATENATE ALL 3 WITH PERFECT AUDIO/VIDEO SYNC
# -------------------------------------------------------------
FINAL_MASTER = "assets/video_snf_daniels_master.mp4"
concat_list = "scratch/concat_segments.txt"
with open(concat_list, "w") as f:
    f.write(f"file '{os.path.abspath(SEG1_PATH).replace(chr(92), '/')}'\n")
    f.write(f"file '{os.path.abspath(SEG2_PATH).replace(chr(92), '/')}'\n")
    f.write(f"file '{os.path.abspath(SEG3_PATH).replace(chr(92), '/')}'\n")

# Use concat demuxer with re-encoding to guarantee clean timestamps across all platforms
subprocess.run([
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0",
    "-i", concat_list,
    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
    "-c:a", "aac", "-b:a", "192k",
    FINAL_MASTER
], check=True)

print("¡VIDEO MASTER 100% SINCRONIZADO GENERADO EN:", FINAL_MASTER)
