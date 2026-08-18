import streamlit as st
import requests
import mysql.connector
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

print("📊 Iniciando Escáner de Splits y Bullpen (7 días)...")

try:
    conexion = mysql.connector.connect(
        host=st.secrets["host"], port=st.secrets["port"],
        user=st.secrets["user"], password=st.secrets["password"], database=st.secrets["database"]
    )
    cursor = conexion.cursor()
except Exception as e:
    print(f"❌ Error conectando a BD: {e}")
    exit()

ZONA_MX = ZoneInfo("America/Mazatlan")
hoy = datetime.now(ZONA_MX).strftime('%Y-%m-%d')
hace_7_dias = (hoy - timedelta(days=7)).strftime('%Y-%m-%d')
hoy_str = hoy.strftime('%Y-%m-%d')
año_actual = hoy.strftime('%Y')

# IDs de la MLB para extraer información
EQUIPOS_ID = {
    'Arizona Diamondbacks': 109, 'Atlanta Braves': 144, 'Baltimore Orioles': 110, 'Boston Red Sox': 111,
    'Chicago Cubs': 112, 'Chicago White Sox': 145, 'Cincinnati Reds': 113, 'Cleveland Guardians': 114,
    'Colorado Rockies': 115, 'Detroit Tigers': 116, 'Houston Astros': 117, 'Kansas City Royals': 118,
    'Los Angeles Angels': 108, 'Los Angeles Dodgers': 119, 'Miami Marlins': 146, 'Milwaukee Brewers': 158,
    'Minnesota Twins': 142, 'New York Mets': 121, 'New York Yankees': 147, 'Athletics': 133,
    'Philadelphia Phillies': 143, 'Pittsburgh Pirates': 134, 'San Diego Padres': 135, 'San Francisco Giants': 137,
    'Seattle Mariners': 136, 'St. Louis Cardinals': 138, 'Tampa Bay Rays': 139, 'Texas Rangers': 140,
    'Toronto Blue Jays': 141, 'Washington Nationals': 120
}

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