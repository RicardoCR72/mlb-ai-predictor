import streamlit as st
import requests
import mysql.connector
from datetime import datetime
from zoneinfo import ZoneInfo

print("⚾ Iniciando Escáner de Pitchers Abridores V3 (ERA Acumulado + ERA Últimas 3)...")

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
url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={hoy}&hydrate=probablePitcher(stats)"

try:
    respuesta = requests.get(url).json()
    if 'dates' in respuesta and len(respuesta['dates']) > 0:
        juegos = respuesta['dates'][0]['games']
        for juego in juegos:
            for tipo in ['home', 'away']:
                equipo_nombre = juego['teams'][tipo]['team']['name']
                if "Oakland" in equipo_nombre or "Athletics" in equipo_nombre: equipo_nombre = "Athletics"
                    
                if 'probablePitcher' in juego['teams'][tipo]:
                    pitcher = juego['teams'][tipo]['probablePitcher']
                    nombre_pitcher = pitcher['fullName']
                    pitcher_id = pitcher.get('id')
                    
                    era_global = 4.50
                    era_3_juegos = 4.50
                    
                    if pitcher_id:
                        # 1. Extraer ERA Global
                        url_stats = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=season&group=pitching"
                        try:
                            res_stats = requests.get(url_stats).json()
                            if 'stats' in res_stats and len(res_stats['stats']) > 0:
                                era_str = res_stats['stats'][0].get('splits', [])[0]['stat'].get('era', '4.50')
                                if era_str != '-.--': era_global = float(era_str)
                        except: pass
                        
                        # 2. 🔥 NUEVO: Extraer ERA de las Últimas 3 Aperturas
                        url_log = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=gameLog&group=pitching&season={hoy[:4]}"
                        try:
                            res_log = requests.get(url_log).json()
                            if 'stats' in res_log and len(res_log['stats']) > 0:
                                ultimos_3 = res_log['stats'][0].get('splits', [])[:3]
                                if ultimos_3:
                                    carreras_limpias = 0
                                    tercios_inning = 0
                                    for j in ultimos_3:
                                        carreras_limpias += int(j['stat'].get('earnedRuns', 0))
                                        ip_str = str(j['stat'].get('inningsPitched', '0.0'))
                                        parts = ip_str.split('.')
                                        enteros = int(parts[0])
                                        decimales = int(parts[1]) if len(parts) > 1 else 0
                                        tercios_inning += (enteros * 3) + decimales
                                    
                                    if tercios_inning > 0:
                                        # Matemática pura de ERA: (Earned Runs * 27 tercios) / Tercios lanzados
                                        era_3_juegos = (carreras_limpias * 27) / tercios_inning
                        except: pass

                    # Guardar ambos ERAs en XAMPP
                    query = """
                    INSERT INTO abridores (fecha, equipo, nombre_pitcher, era, era_ultimas_3)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE nombre_pitcher=VALUES(nombre_pitcher), era=VALUES(era), era_ultimas_3=VALUES(era_ultimas_3)
                    """
                    cursor.execute(query, (hoy, equipo_nombre, nombre_pitcher, era_global, round(era_3_juegos, 2)))
                    print(f"⚾ {equipo_nombre}: {nombre_pitcher} (Global: {era_global} | Últimas 3: {round(era_3_juegos,2)})")
        
        conexion.commit()
        print("✅ ¡Pitchers actualizados con métricas avanzadas!")
except Exception as e:
    print(f"🚨 Error: {e}")
finally:
    if 'cursor' in locals(): cursor.close()
    if 'conexion' in locals(): conexion.close()