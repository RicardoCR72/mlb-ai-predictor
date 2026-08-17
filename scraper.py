import streamlit as st

import requests
import mysql.connector
from datetime import datetime, timedelta

def conectar_bd():
    try:
        return mysql.connector.connect(
        host=st.secrets["host"],
        port=st.secrets["port"],
        user=st.secrets["user"],
        password=st.secrets["password"],
        database=st.secrets["database"]
    )
    except mysql.connector.Error as err:
        print(f"❌ Error DB: {err}")
        return None

def descargar_mlb():
    print("📡 Descargando Béisbol MLB (Moneyline y Over/Under Totales)...")
    API_KEY = "d0230dfdf8f783bc76cf780dca47e21d" 
    
    # Cambiamos pitcher_strikeouts por totals (Over/Under de carreras)
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={API_KEY}&regions=us&markets=h2h,totals"
    
    try:
        respuesta = requests.get(url)
        if respuesta.status_code == 200:
            return respuesta.json()
        else:
            print(f"❌ Error API: {respuesta.json()}")
    except Exception as e:
        print(f"❌ Error de red: {e}")
    return []

def guardar_todo(conexion, datos):
    cursor = conexion.cursor()
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    contador_juegos, contador_moneyline, contador_props = 0, 0, 0
    
    print("⏳ Procesando el JSON y guardando en XAMPP...")
    
    for partido in datos:
        id_juego = partido['id']
        equipo_local = partido.get('home_team')
        equipo_visitante = partido.get('away_team')
        
        if not equipo_local or not equipo_visitante:
            continue
            
        # 1. GUARDAR EL JUEGO
        fecha_utc = datetime.strptime(partido['commence_time'], "%Y-%m-%dT%H:%M:%SZ")
        fecha_local = fecha_utc - timedelta(hours=6)
        fecha_limpia = fecha_local.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute("""
            INSERT INTO juegos (id_juego, fecha, equipo_local, equipo_visitante)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE equipo_local=VALUES(equipo_local)
        """, (id_juego, fecha_limpia, equipo_local, equipo_visitante))
        contador_juegos += 1

        # 2. RECORRER CASAS DE APUESTAS
        for bookmaker in partido.get('bookmakers', []):
            casa = bookmaker['title']
            
            for market in bookmaker.get('markets', []):
                
                # 3. GUARDAR MONEYLINE (h2h)
                if market['key'] == 'h2h':
                    cuota_local = 0
                    cuota_visitante = 0
                    for outcome in market['outcomes']:
                        if outcome['name'] == equipo_local:
                            cuota_local = outcome['price']
                        elif outcome['name'] == equipo_visitante:
                            cuota_visitante = outcome['price']
                            
                    cursor.execute("""
                        INSERT INTO cuotas_moneyline (id_juego, casa_apuestas, cuota_local, cuota_visitante, timestamp_captura)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (id_juego, casa, cuota_local, cuota_visitante, fecha_actual))
                    contador_moneyline += 1

                # 4. GUARDAR OVER/UNDER (Totales)
                elif market['key'] == 'totals':
                    linea = 0
                    cuota_over = 0
                    cuota_under = 0
                    
                    for outcome in market['outcomes']:
                        linea = outcome.get('point', 0)
                        if outcome['name'] == 'Over':
                            cuota_over = outcome['price']
                        elif outcome['name'] == 'Under':
                            cuota_under = outcome['price']
                            
                    # Registramos este mercado general como si fuera un "jugador" para respetar la llave foránea
                    nombre_prop = f"Total Carreras: {equipo_local} vs {equipo_visitante}"
                    
                    cursor.execute("""
                        INSERT INTO jugadores (id_jugador, nombre, equipo_actual)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE nombre=VALUES(nombre)
                    """, (id_juego, nombre_prop, 'MLB'))
                    
                    cursor.execute("""
                        INSERT INTO lineas_props (id_juego, id_jugador, casa_apuestas, tipo_prop, linea, cuota_over, cuota_under, timestamp_captura)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (id_juego, id_juego, casa, 'totales_carreras', linea, cuota_over, cuota_under, fecha_actual))
                    contador_props += 1

    conexion.commit()
    print("--------------------------------------------------")
    print("✅ ¡BASE DE DATOS ACTUALIZADA CON ÉXITO!")
    print(f"⚾ Juegos guardados/actualizados: {contador_juegos}")
    print(f"💰 Cuotas Moneyline guardadas: {contador_moneyline}")
    print(f"🔥 Líneas Over/Under guardadas: {contador_props}")
    print("--------------------------------------------------")
    cursor.close()

if __name__ == "__main__":
    db = conectar_bd()
    if db:
        datos_api = descargar_mlb()
        if datos_api:
            guardar_todo(db, datos_api)
        db.close()