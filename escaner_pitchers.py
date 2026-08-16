from turtle import st

import requests
import mysql.connector
from datetime import datetime

print("⚾ Iniciando Escáner de Pitchers Abridores...")

# 1. CONEXIÓN A XAMPP
try:
    conexion = mysql.connector.connect(
        host=st.secrets["host"],
        port=st.secrets["port"],
        user=st.secrets["user"],
        password=st.secrets["password"],
        database=st.secrets["database"]
    )
    cursor = conexion.cursor()
except Exception as e:
    print(f"❌ Error conectando a BD: {e}")
    exit()

hoy = datetime.now().strftime('%Y-%m-%d')
print(f"📅 Buscando abridores programados para hoy: {hoy}")

# MAGIA: Usamos el parámetro 'hydrate' para que la API nos devuelva el ERA de una vez
url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={hoy}&hydrate=probablePitcher(stats)"

try:
    respuesta = requests.get(url).json()
    
    if 'dates' in respuesta and len(respuesta['dates']) > 0:
        juegos = respuesta['dates'][0]['games']
        pitchers_guardados = 0
        
        for juego in juegos:
            equipos = ['home', 'away']
            
            for tipo in equipos:
                equipo_nombre = juego['teams'][tipo]['team']['name']
                
                # Normalizamos a los Athletics para mantener tu estándar
                if "Oakland" in equipo_nombre or "Athletics" in equipo_nombre:
                    equipo_nombre = "Athletics"
                    
                # Verificamos si el equipo ya anunció a su pitcher
                if 'probablePitcher' in juego['teams'][tipo]:
                    pitcher = juego['teams'][tipo]['probablePitcher']
                    nombre_pitcher = pitcher['fullName']
                    
                    pitcher_id = pitcher.get('id')
                    
                    # === NUEVO BLOQUE DE EXTRACCIÓN DE ERA (A PRUEBA DE BALAS) ===
                    era = 4.50 # Nuestro salvavidas por defecto
                    
                    if pitcher_id:
                        # Consultamos directamente el perfil de ese pitcher en la API
                        url_stats = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=season&group=pitching"
                        try:
                            res_stats = requests.get(url_stats).json()
                            
                            if 'stats' in res_stats and len(res_stats['stats']) > 0:
                                splits = res_stats['stats'][0].get('splits', [])
                                
                                if len(splits) > 0:
                                    # ¡Aquí está escondido el ERA!
                                    era_str = splits[0]['stat'].get('era', '4.50')
                                    
                                    # Si es novato y la API manda "-.--", lo dejamos en 4.50
                                    if era_str != '-.--':
                                        era = float(era_str)
                        except Exception:
                            era = 4.50 # Si la API falla por algo, usamos el salvavidas
                    # ==============================================================
                    
                    # 2. GUARDAMOS EN XAMPP (Esta línea ya la tenías, déjala igual)
                                    
                    # 2. GUARDAMOS EN XAMPP
                    query = """
                    INSERT INTO abridores (fecha, equipo, nombre_pitcher, era)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE nombre_pitcher=VALUES(nombre_pitcher), era=VALUES(era)
                    """
                    cursor.execute(query, (hoy, equipo_nombre, nombre_pitcher, era))
                    pitchers_guardados += 1
                    print(f"⚾ {equipo_nombre}: {nombre_pitcher} (ERA: {era})")
                    
        conexion.commit()
        print("-" * 50)
        print(f"✅ ¡Rotación lista! Se guardaron {pitchers_guardados} pitchers para hoy.")
    else:
        print("😴 No hay juegos programados para hoy en la API.")
        
except Exception as e:
    print(f"🚨 Error durante la extracción: {e}")
finally:
    if 'cursor' in locals(): cursor.close()
    if 'conexion' in locals(): conexion.close()