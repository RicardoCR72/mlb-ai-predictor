from streamlit import st

import pandas as pd
import requests
from bs4 import BeautifulSoup
import mysql.connector
from datetime import datetime

print("🏥 Iniciando Escáner Médico de la MLB...")

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

# Diccionario de traducción de nombres
traductor_equipos = {
    'Arizona': 'Arizona Diamondbacks',
    'Atlanta': 'Atlanta Braves',
    'Baltimore': 'Baltimore Orioles',
    'Boston': 'Boston Red Sox',
    'Chi. Cubs': 'Chicago Cubs',
    'Chi. White Sox': 'Chicago White Sox',
    'Cincinnati': 'Cincinnati Reds',
    'Cleveland': 'Cleveland Guardians',
    'Colorado': 'Colorado Rockies',
    'Detroit': 'Detroit Tigers',
    'Houston': 'Houston Astros',
    'Kansas City': 'Kansas City Royals',
    'L.A. Angels': 'Los Angeles Angels',
    'L.A. Dodgers': 'Los Angeles Dodgers',
    'Miami': 'Miami Marlins',
    'Milwaukee': 'Milwaukee Brewers',
    'Minnesota': 'Minnesota Twins',
    'N.Y. Mets': 'New York Mets',
    'N.Y. Yankees': 'New York Yankees',
    'Philadelphia': 'Philadelphia Phillies',
    'Pittsburgh': 'Pittsburgh Pirates',
    'San Diego': 'San Diego Padres',
    'San Francisco': 'San Francisco Giants',
    'Seattle': 'Seattle Mariners',
    'St. Louis': 'St. Louis Cardinals',
    'Tampa Bay': 'Tampa Bay Rays',
    'Texas': 'Texas Rangers',
    'Toronto': 'Toronto Blue Jays',
    'Washington': 'Washington Nationals',
    'Athletics': 'Athletics' # Este suele venir ya bien, pero lo dejamos por si acaso
}


url = "https://www.cbssports.com/mlb/injuries/"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/114.0.0.0 Safari/537.36'}

try:
    respuesta = requests.get(url, headers=headers)
    
    # MAGIA 1: BeautifulSoup extrae los nombres de los equipos
    soup = BeautifulSoup(respuesta.text, 'html.parser')
    # CBS usa la clase 'TeamName' para los títulos arriba de las tablas
    etiquetas_equipos = soup.find_all('span', class_='TeamName')
    nombres_equipos = [etiqueta.text.strip() for etiqueta in etiquetas_equipos]
    
    # MAGIA 2: Pandas extrae las tablas
    tablas = pd.read_html(respuesta.text)
    
    # A veces CBS pone una tabla extra al final de la página. Para evitar errores, 
    # nos aseguramos de procesar solo hasta donde haya parejas completas (Equipo + Tabla)
    limite = min(len(nombres_equipos), len(tablas))
    hoy = datetime.now().strftime('%Y-%m-%d')
    equipos_procesados = 0
    
    for i in range(limite):
        equipo = nombres_equipos[i]
        df_lesiones = tablas[i]

        equipo = traductor_equipos.get(equipo, equipo)
        # Normalizamos a los Athletics para que empate con tu scraper principal
        if "Oakland" in equipo or "Athletics" in equipo:
            equipo = "Athletics"
            
        impacto_total = 0
        
        # CBS a veces nombra la columna 'Position' o 'Pos', la buscamos dinámicamente
        col_posicion = 'Position' if 'Position' in df_lesiones.columns else 'Pos'
        
        # Si la tabla tiene datos médicos reales (no está vacía)
        if col_posicion in df_lesiones.columns:
            for index, fila in df_lesiones.iterrows():
                posicion = str(fila[col_posicion]).upper()
                
                # ⚖️ SISTEMA DE PESOS DE LESIÓN
                if 'SP' in posicion:
                    impacto_total -= 3  # Pitcher Abridor (Impacto máximo)
                elif 'RP' in posicion:
                    impacto_total -= 1  # Relevista (Impacto mínimo)
                else:
                    impacto_total -= 2  # Bateadores/Jugadores de campo (Impacto medio)
        
        # 3. GUARDAMOS EN TU NUEVA TABLA DE XAMPP
        query = """
        INSERT INTO factor_lesiones (fecha, equipo, impacto_total)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE impacto_total=VALUES(impacto_total)
        """
        cursor.execute(query, (hoy, equipo, impacto_total))
        equipos_procesados += 1
        
    conexion.commit()
    print("-" * 50)
    print(f"✅ ¡Operación Exitosa! {equipos_procesados} equipos analizados.")
    print("📊 La tabla 'factor_lesiones' ha sido actualizada para hoy.")
    print("-" * 50)
    
except Exception as e:
    print(f"🚨 Error durante la extracción: {e}")
finally:
    if 'cursor' in locals(): cursor.close()
    if 'conexion' in locals(): conexion.close()