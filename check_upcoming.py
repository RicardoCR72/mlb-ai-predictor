import sys
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from core.db import get_db_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ZONA_CDMX = ZoneInfo("America/Mexico_City")
ahora = datetime.now(ZONA_CDMX)
print(f"Hora actual CDMX: {ahora.strftime('%Y-%m-%d %H:%M:%S')}")

print("\n=== NBA DE HOY ===")
p_nba = Path("data/nba/predictions/predicciones_nba_hoy.json")
if p_nba.exists():
    with open(p_nba, "r", encoding="utf-8") as f:
        nba_data = json.load(f)
    print(f"Total partidos NBA: {len(nba_data)}")
    for g in nba_data:
        p_name = g.get('partido', f"{g.get('equipo_visita')} @ {g.get('equipo_local')}")
        h_cdmx = g.get('hora_cdmx', g.get('hora_partido', 'N/D'))
        est = g.get('estado', 'N/D')
        print(f"\n🏀 {p_name} ({h_cdmx}) - Estado: {est}")
        print(f"   ML: Pick={g.get('pick_ml_equipo')} Cuota={g.get('pick_ml_cuota')} Prob={g.get('prob_victoria_local')} Conf={g.get('confianza_ml')} EV={g.get('ev_ml_local')}")
        print(f"   Totales: Línea={g.get('linea_total')} Proy={g.get('total_puntos_esperado')} Pick={g.get('pick_totales')} Conf={g.get('confianza_totales')}")
        print(f"   Spread: Línea={g.get('linea_spread')} Pick={g.get('pick_spread')} Conf={g.get('confianza_spread')}")
else:
    print("No hay archivo predicciones_nba_hoy.json")

print("\n=== NFL SNF (WASHINGTON @ EAGLES) ===")
p_nfl = Path("data/nfl/predictions/predicciones_nfl_moneyline.json")
if p_nfl.exists():
    with open(p_nfl, "r", encoding="utf-8") as f:
        nfl_data = json.load(f)
    for g in nfl_data:
        if 'WAS' in g.get('partido', '') or 'PHI' in g.get('partido', ''):
            print(f"🏈 {g.get('partido')} ({g.get('hora_cdmx')}) - Estado: {g.get('descripcion_estado')}")
            print(f"   Pick ML: {g.get('pick_seleccion')} Cuota: {g.get('pick_cuota')} Prob: {g.get('pick_probabilidad')} EV: {g.get('ev_estimado')}% Conf: {g.get('confianza')}")

print("\n=== NFL PROPS ACTIVAS DE LA TARDE / SNF ===")
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("""
    SELECT p.id_proyeccion, p.id_juego, ju.nombre, ju.equipo_actual, ju.posicion,
           p.tipo_prop, p.linea, p.proyeccion, p.edge, p.seleccion, 
           p.probabilidad_pick, p.cuota_pick, p.ev_estimado, p.estado_pick, p.resultado_pick
    FROM nfl_proyecciones_props p
    JOIN nfl_jugadores ju ON p.id_jugador = ju.id_jugador
    WHERE p.resultado_pick = 'PENDIENTE' AND p.estado_pick IN ('CANDIDATO', 'REVISAR LESION')
    ORDER BY p.ev_estimado DESC
    LIMIT 20
""")
props_pend = cursor.fetchall()
print(f"Total props pendientes: {len(props_pend)}")
for pp in props_pend:
    print(f"   {pp['nombre']} ({pp['equipo_actual']}) | {pp['tipo_prop']} | Línea: {pp['linea']} Proy: {pp['proyeccion']:.1f} | Pick: {pp['seleccion']} @ {pp['cuota_pick']} | Prob: {pp['probabilidad_pick']:.1%} | EV: {pp['ev_estimado']}%")
conn.close()
