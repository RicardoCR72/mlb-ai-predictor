import os
import subprocess

def get_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())

def main():
    print("=== REGENERANDO VIDEO MASTER NBA CON INTRO Y OUTRO CORREGIDOS ===")
    os.makedirs("scratch", exist_ok=True)
    os.makedirs("assets", exist_ok=True)

    d_intro = get_duration("scratch/nba_audio1_intro.mp3")
    d_outro = get_duration("scratch/nba_audio5_outro.mp3")

    # 1. Render Segment 1 (Intro with fixed éne-be-a audio)
    print(f"Renderizando Segmento 1 (Intro, {d_intro:.2f}s)...")
    s1_vid = "scratch/nba_seg1_intro.mp4"
    cmd_s1 = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", "scratch/intro_nba_slide.png",
        "-i", "scratch/nba_audio1_intro.mp3",
        "-t", str(d_intro),
        "-vf", "scale=1080:1920,format=yuv420p",
        "-r", "30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        s1_vid
    ]
    subprocess.run(cmd_s1, check=True)

    # 2. Render Segment 5 (Outro with perfectly centered Telegram button)
    print(f"Renderizando Segmento 5 (Outro, {d_outro:.2f}s)...")
    s5_vid = "scratch/nba_seg5_outro.mp4"
    cmd_s5 = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", "scratch/outro_nba_slide.png",
        "-i", "scratch/nba_audio5_outro.mp3",
        "-t", str(d_outro),
        "-vf", "scale=1080:1920,format=yuv420p",
        "-r", "30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        s5_vid
    ]
    subprocess.run(cmd_s5, check=True)

    # Segments 2, 3, 4 already rendered and verified
    s2_vid = "scratch/nba_seg2_pick1.mp4"
    s3_vid = "scratch/nba_seg3_pick2.mp4"
    s4_vid = "scratch/nba_seg4_pick3.mp4"

    # Concatenate all 5 segments
    print("Concatenando los 5 segmentos...")
    concat_txt = "scratch/concat_nba_5parts.txt"
    with open(concat_txt, "w") as f:
        for s in [s1_vid, s2_vid, s3_vid, s4_vid, s5_vid]:
            p = os.path.abspath(s).replace("\\", "/")
            f.write(f"file '{p}'\n")

    master_output = "assets/video_top3_nba_master.mp4"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_txt,
        "-c", "copy",
        master_output
    ]
    subprocess.run(cmd_concat, check=True)
    print(f"\n¡ÉXITO TOTAL! Video master NBA actualizado en: {master_output}")

    # Copy to brain artifacts
    brain_dst = "C:/Users/rcabr/.gemini/antigravity/brain/8db99efe-a7c9-44ba-88ff-2a8317829757/video_top3_nba_tiktok.mp4"
    with open(master_output, "rb") as fin:
        with open(brain_dst, "wb") as fout:
            fout.write(fin.read())
    print(f"Copiado a artefacto brain: {brain_dst}")

if __name__ == "__main__":
    main()
