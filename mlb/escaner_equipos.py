import sys
from datetime import datetime, timedelta
from pathlib import Path
import requests

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_MX, MLB_TEAMS_IDS
from core.db import get_db_connection

print("📊 Iniciando Escáner de Splits y Bullpen (7 días)...")

try:
    conexion = get_db_connection()
    cursor = conexion.cursor()
except Exception as e:
    print(f"❌ Error conectando a BD: {e}")
    exit(1)

fecha_actual = datetime.now(ZONA_MX)
hoy_str = fecha_actual.strftime('%Y-%m-%d')
hoy = hoy_str
hace_7_dias = (fecha_actual - timedelta(days=7)).strftime('%Y-%m-%d')
año_actual = fecha_actual.strftime('%Y')

EQUIPOS_ID = MLB_TEAMS_IDS

for equipo, team_id in EQUIPOS_ID.items():
    ops_zurdo = 0.700
    ops_derecho = 0.700
    era_bullpen = 4.50

    try:
        # 1. Extraer Splits de Bateo (OPS vs Zurdos y Derechos)
        url_splits = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=statSplits&group=hitting&season={año_actual}"
        res_splits = requests.get(url_splits).json()
        
        if 'stats' in res_splits:
            for stat in res_splits['stats']:
                for split in stat.get('splits', []):
                    desc = split.get('split', {}).get('description', '')
                    ops_val = split.get('stat', {}).get('ops', '.700')
                    if ops_val == '.---': ops_val = '.700'
                    
                    if desc == 'vs Left':
                        ops_zurdo = float(ops_val)
                    elif desc == 'vs Right':
                        ops_derecho = float(ops_val)

        # 2. Extraer ERA del Equipo en los últimos 7 días (Proxy de Bullpen/Fatiga)
        url_bullpen = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=byDateRange&group=pitching&startDate={hace_7_dias}&endDate={hoy_str}"
        res_bullpen = requests.get(url_bullpen).json()
        
        if 'stats' in res_bullpen and len(res_bullpen['stats']) > 0:
            era_val = res_bullpen['stats'][0]['splits'][0]['stat'].get('era', '4.50')
            if era_val != '-.--':
                era_bullpen = float(era_val)

        # 3. Guardar en XAMPP
        query = """
        INSERT INTO metricas_equipos (fecha, equipo, ops_vs_zurdo, ops_vs_derecho, era_bullpen_7d)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE ops_vs_zurdo=VALUES(ops_vs_zurdo), ops_vs_derecho=VALUES(ops_vs_derecho), era_bullpen_7d=VALUES(era_bullpen_7d)
        """
        cursor.execute(query, (hoy_str, equipo, ops_zurdo, ops_derecho, era_bullpen))
        print(f"✅ {equipo}: OPS vs L ({ops_zurdo}) | OPS vs R ({ops_derecho}) | ERA 7D ({era_bullpen})")

    except Exception as e:
        print(f"⚠️ Error procesando {equipo}: {e}")

conexion.commit()
cursor.close()
conexion.close()
print("🚀 ¡Métricas Avanzadas Listas!")