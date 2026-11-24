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

    # 1. Resolver fecha en español estricto según GEMINI.md
    DIAS_ES = {0: "LUNES", 1: "MARTES", 2: "MIÉRCOLES", 3: "JUEVES", 4: "VIERNES", 5: "SÁBADO", 6: "DOMINGO"}
    MESES_ES = {1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"}
    ahora = datetime.now()
    fecha_hoy = ahora.strftime("%Y-%m-%d")
    fecha_display = f"{DIAS_ES[ahora.weekday()]} {ahora.day} DE {MESES_ES[ahora.month]} {ahora.year}"

    # 2. Cargar candidato o buscar por jugador en predicciones del día
    candidatos = cargar_candidatos_hoy()
    candidato_encontrado = None

    if args.jugador:
        nombre_buscar = args.jugador.lower().strip()
        todos_props = candidatos.get("nba_props", []) + candidatos.get("nfl_props", [])
        mercado_filtro = args.mercado.lower().strip() if args.mercado else ""
        # 1. Buscar coincidencia exacta por jugador y mercado
        for c in todos_props:
            if nombre_buscar in str(c.get("jugador", "")).lower():
                c_m = str(c.get("mercado", "")).lower()
                if any(w in c_m for w in ["rebound", "rebote"]) and any(w in mercado_filtro for w in ["rebound", "rebote"]):
                    candidato_encontrado = c
                    break
                elif any(w in c_m for w in ["point", "punto"]) and any(w in mercado_filtro for w in ["point", "punto"]):
                    candidato_encontrado = c
                    break
                elif any(w in c_m for w in ["assist", "asistencia"]) and any(w in mercado_filtro for w in ["assist", "asistencia"]):
                    candidato_encontrado = c
                    break
        # 2. Si no hubo coincidencia de mercado, tomar la primera opción del jugador
        if not candidato_encontrado:
            for c in todos_props:
                if nombre_buscar in str(c.get("jugador", "")).lower():
                    candidato_encontrado = c
                    break

    if not candidato_encontrado:
        # Si no se pasó jugador o no se encontró, usar el #1 oficial de menor varianza
        from core.asesor_ia import seleccionar_candado_oficial
        candidato_encontrado = seleccionar_candado_oficial(candidatos, deporte=args.deporte)

    if candidato_encontrado:
        jugador = candidato_encontrado.get("jugador", "Josh Hart")
        equipo = candidato_encontrado.get("equipo", "NYK")
        deporte = candidato_encontrado.get("deporte", args.deporte or "NBA")
        mercado_raw = candidato_encontrado.get("mercado", args.mercado or "Total Rebotes")
        linea = str(candidato_encontrado.get("linea", args.linea or "7.5"))
        pick = "Over" if "OVER" in str(candidato_encontrado.get("seleccion", "")).upper() else "Under"
        proy = str(candidato_encontrado.get("proyeccion", args.proyeccion or "6.8"))
        
        # Calcular margen
        try:
            diff = float(proy) - float(linea)
            margen_str = f"{diff:+.1f} {mercado_raw.split()[-1]}"
        except Exception:
            margen_str = args.ventaja or "-0.7 Reb"
            
        racha_texto = candidato_encontrado.get("tendencia") or f"4 DE SUS ÚLTIMOS 5 POR DEBAJO | PROY: {proy}"
        rival = candidato_encontrado.get("partido", "su rival")
    else:
        jugador = args.jugador or "Josh Hart"
        equipo = "New York Knicks"
        deporte = args.deporte or "NBA"
        mercado_raw = args.mercado or "Total Rebotes"
        linea = args.linea or "7.5"
        pick = args.pick or "Under"
        proy = args.proyeccion or "6.8"
        margen_str = args.ventaja or "-0.7 Reb"
        racha_texto = "4 DE SUS ÚLTIMOS 5 POR DEBAJO | MEDIA L5: 5.6 REB"
        rival = "su rival"

    # Traducir mercado para despliegue gráfico si viene en inglés
    mapa_mercados = {
        "Total Rebounds": "TOTAL REBOTES",
        "Total Points": "TOTAL PUNTOS",
        "Total Assists": "TOTAL ASISTENCIAS",
        "Total Triples": "TOTAL TRIPLES",
        "Total PRA": "PUNTOS + REBOTES + ASISTENCIAS",
        "Total PR": "PUNTOS + REBOTES",
        "Total PA": "PUNTOS + ASISTENCIAS",
    }
    mercado_display = mapa_mercados.get(mercado_raw, mercado_raw.upper())
    deporte_display = "NBA · BASKETBALL" if deporte.upper() == "NBA" else f"{deporte.upper()} · FOOTBALL"

    datos = {
        "deporte": deporte_display,
        "fecha_str": fecha_display,
        "jugador": jugador,
        "equipo": equipo,
        "rival": rival,
        "mercado": mercado_display,
        "linea": linea,
        "tipo_pick": pick,
        "proyeccion": proy,
        "ventaja": margen_str,
        "racha_texto": racha_texto,
        "promedio_texto": f"PROYECCIÓN MODELO: {proy} | MARGEN: {margen_str}"
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
