import sys
from pathlib import Path
from core.db import get_db_connection
import pandas as pd

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Check latest lines in nfl_lineas_props
cursor.execute("SELECT MAX(timestamp_captura), COUNT(*) FROM nfl_lineas_props")
print("Latest nfl_lineas_props:", cursor.fetchone())

# Check recent entries in nfl_lineas_props
cursor.execute("""
    SELECT l.*, j.nombre as jugador_nombre 
    FROM nfl_lineas_props l
    LEFT JOIN nfl_jugadores j ON l.id_jugador = j.id_jugador
    ORDER BY l.timestamp_captura DESC
    LIMIT 10
""")
print("\nRecent lines in nfl_lineas_props:")
for r in cursor.fetchall():
    print(r['timestamp_captura'], r.get('jugador_nombre'), r['tipo_prop'], r['linea'], r['cuota_over'], r['cuota_under'], r['casa_apuestas'])

# Check candidatas in nfl_proyecciones_props
cursor.execute("""
    SELECT p.id_proyeccion, p.id_juego, ju.nombre, ju.equipo_actual, ju.posicion,
           p.tipo_prop, p.linea, p.proyeccion, p.edge, p.seleccion, 
           p.probabilidad_pick, p.cuota_pick, p.ev_estimado, p.estado_pick, 
           p.actualizado_en, p.generado_en, p.resultado_pick
    FROM nfl_proyecciones_props p
    JOIN nfl_jugadores ju ON p.id_jugador = ju.id_jugador
    WHERE p.estado_pick IN ('CANDIDATO', 'REVISAR LESION')
    ORDER BY p.actualizado_en DESC, p.ev_estimado DESC
    LIMIT 40
""")
candidatos = cursor.fetchall()
print(f"\nTotal candidatos: {len(candidatos)}")
for c in candidatos:
    print(f"[{c['actualizado_en']}] {c['nombre']} ({c['equipo_actual']} - {c['posicion']}) | {c['tipo_prop']} | Linea: {c['linea']} -> Proy: {c['proyeccion']:.1f} | Pick: {c['seleccion']} @ {c['cuota_pick']} | Prob: {c['probabilidad_pick']:.1%} | EV: {c['ev_estimado']}% | Estado: {c['estado_pick']} | Res: {c['resultado_pick']}")

conn.close()
