import json
from pathlib import Path
from core.db import get_db_connection
import pandas as pd

print("=== PARTIDOS EN predicciones_nfl_moneyline.json ===")
p_json = Path("data/nfl/predictions/predicciones_nfl_moneyline.json")
if p_json.exists():
    with open(p_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    for g in data:
        print(f"{g.get('fecha_cdmx')} {g.get('hora_cdmx')} :: {g.get('partido')} :: Pick: {g.get('pick_seleccion')} ({g.get('pick_cuota')}) :: EV: {g.get('ev_estimado')}% :: Conf: {g.get('confianza')} :: Estado: {g.get('descripcion_estado')}")
else:
    print("No existe predicciones_nfl_moneyline.json")

print("\n=== REVISANDO BASE DE DATOS DE PROPS ===")
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute("SHOW TABLES LIKE 'nfl%'")
tables = [list(r.values())[0] for r in cursor.fetchall()]
print("Tablas NFL:", tables)

cursor.execute("SELECT COUNT(*) as cnt FROM nfl_proyecciones_props")
print("Total proyecciones props:", cursor.fetchone()['cnt'])

cursor.execute("SELECT estado_pick, COUNT(*) as cnt FROM nfl_proyecciones_props GROUP BY estado_pick")
print("Estados pick props:", cursor.fetchall())

cursor.execute("SELECT MAX(actualizado_en), MAX(generado_en) FROM nfl_proyecciones_props")
print("Fechas props:", cursor.fetchone())

cursor.execute("SELECT id_juego, fecha, equipo_local, equipo_visitante, estado FROM nfl_juegos WHERE fecha >= '2026-10-25' ORDER BY fecha DESC")
print("Juegos recientes en nfl_juegos:", cursor.fetchall())

conn.close()
