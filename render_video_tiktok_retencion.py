"""Script de generación y renderizado de videos TikTok/Shorts de alta retención (Overdog AI).
Aplica el pipeline unificado con guion de 38-45 palabras, recorte de audio a t=0.0s,
velocidad 1.08x, normalización -14 LUFS, revelación progresiva y corte en dur_audio + 0.25s.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from core.pipeline_video_retencion import pipeline_video_completo
from core.asesor_ia import cargar_candidatos_hoy

RAIZ = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description="Renderizador de video TikTok/Shorts de alta retención Overdog AI")
    parser.add_argument("--jugador", type=str, default=None, help="Nombre del jugador")
    parser.add_argument("--deporte", type=str, default="NBA", help="Deporte (NBA o NFL)")
    parser.add_argument("--mercado", type=str, default="Total Rebotes", help="Mercado analizado")
    parser.add_argument("--linea", type=str, default="7.5", help="Línea de la casa")
    parser.add_argument("--pick", type=str, default="Under", help="Over o Under")
    parser.add_argument("--proyeccion", type=str, default="5.8", help="Proyección del modelo")
    parser.add_argument("--ventaja", type=str, default="-1.7 Reb", help="Margen o ventaja")
    parser.add_argument("--clip", type=str, default=None, help="Ruta al video de fondo (1080p)")
    parser.add_argument("--output", type=str, default=None, help="Ruta del video final mp4")
    
    args = parser.parse_args()

    # Si no se pasó jugador, buscar el candado o top pick de hoy
    if not args.jugador:
        candidatos = cargar_candidatos_hoy()
        top_props = candidatos.get("nba_props", []) or candidatos.get("nfl_props", [])
        if top_props:
            cand = top_props[0]
            jugador = cand.get("jugador", "Josh Hart")
            equipo = cand.get("equipo", "NYK")
            deporte = cand.get("deporte", "NBA")
            mercado = cand.get("mercado", "Total Rebotes")
            linea = str(cand.get("linea", 7.5))
            pick = "Over" if "OVER" in str(cand.get("seleccion", "")).upper() else "Under"
            proy = str(cand.get("proyeccion", 5.8))
        else:
            jugador = "Josh Hart"
            equipo = "New York Knicks"
            deporte = "NBA"
            mercado = "Total Rebotes"
            linea = "7.5"
            pick = "Under"
            proy = "5.8"
    else:
        jugador = args.jugador
        equipo = ""
        deporte = args.deporte
        mercado = args.mercado
        linea = args.linea
        pick = args.pick
        proy = args.proyeccion

    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    fecha_display = datetime.now().strftime("%A %d de %B %Y").upper()

    datos = {
        "deporte": deporte,
        "fecha_str": fecha_display,
        "jugador": jugador,
        "equipo": equipo,
        "rival": "su rival",
        "mercado": mercado,
        "linea": linea,
        "tipo_pick": pick,
        "proyeccion": proy,
        "ventaja": args.ventaja,
        "racha_texto": f"🔥 TENDENCIA FAVORABLE EN SUS ÚLTIMOS ENCUENTROS",
        "promedio_texto": f"PROYECCIÓN: {proy}"
    }

    # Buscar clip por defecto si no se especificó
    clip_path = args.clip
    if not clip_path:
        for c in [
            f"assets/clip_{jugador.lower().replace(' ', '_')}.mp4",
            "assets/clip_courtland_sutton.mp4",
            "assets/clip_xavier_worthy.mp4",
            "assets/clip_rudy_gobert.mp4"
        ]:
            if os.path.exists(c):
                clip_path = c
                break

    if not clip_path or not os.path.exists(clip_path):
        print(f"Error: no se encontró un clip de video de fondo en assets/")
        sys.exit(1)

    slug_jugador = jugador.lower().replace(" ", "_")
    output_vid = args.output or f"assets/{deporte.lower()}_{fecha_hoy}_video_tiktok_{slug_jugador}.mp4"

    print(f"=== INICIANDO PIPELINE DE ALTA RETENCIÓN: {jugador} ({deporte}) ===")
    res = asyncio.run(pipeline_video_completo(datos, clip_path, output_vid))
    
    print("\n" + "="*50)
    print("✅ ¡VIDEO GENERADO Y RENDERIZADO CON ÉXITO!")
    print(f"📹 Archivo final: {res['output_video']}")
    print(f"📝 Guion narrado ({res['palabras']} palabras):")
    print(f"   \"{res['guion']}\"")
    print(f"⏱️ Duración audio: {res['duracion_audio']:.2f}s")
    print(f"🎯 Timestamp revelación: {res['t_revelacion']:.2f}s")
    print(f"✂️ Duración video renderizado: {res['duracion_video']:.2f}s")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
