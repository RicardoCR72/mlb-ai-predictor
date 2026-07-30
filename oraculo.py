import pandas as pd
import numpy as np
import mysql.connector
from tensorflow.keras.models import load_model
from sklearn.preprocessing import MinMaxScaler
import warnings

# Apagar advertencias molestas de Pandas
warnings.filterwarnings('ignore')

print("🧠 Despertando a la IA y preparando la memoria...")

# 1. RECUPERAR EL MOLDE (Para que la matriz coincida con las 62 variables)
df_hist = pd.read_csv('mlb_historico.csv')
df_hist = df_hist.dropna(subset=['team', 'opponent', 'moneyLine', 'oppMoneyLine', 'runs', 'oppRuns'])
equipos_encoded_hist = pd.get_dummies(df_hist[['team', 'opponent']])
columnas_entrenamiento = equipos_encoded_hist.columns 

# Re-entrenamos rápidamente el scaler original para no perder la proporción matemática
scaler = MinMaxScaler()
scaler.fit(df_hist[['moneyLine', 'oppMoneyLine']])

# 2. CARGAR EL CEREBRO
modelo = load_model('cerebro_mlb.keras')

# 3. EXTRAER LOS DATOS DE HOY DESDE XAMPP
print("📡 Buscando los partidos de hoy en tu base de datos...")
try:
    conexion = mysql.connector.connect(host="127.0.0.1", user="root", password="", database="sports_analytics")
    # Hacemos GROUP BY para que no nos repita el mismo partido si hay varias casas de apuestas
    consulta = """
        SELECT j.equipo_local AS 'team', j.equipo_visitante AS 'opponent', 
               MAX(c.cuota_local) AS 'moneyLine', MAX(c.cuota_visitante) AS 'oppMoneyLine'
        FROM juegos j
        JOIN cuotas_moneyline c ON j.id_juego = c.id_juego
        GROUP BY j.id_juego
    """
    df_hoy = pd.read_sql(consulta, conexion)
    conexion.close()
except mysql.connector.Error as err:
    print(f"❌ Error al conectar a MySQL: {err}")
    exit()

if df_hoy.empty:
    print("⚠️ No hay partidos guardados. Revisa que tu scraper automático haya corrido hoy.")
    exit()

# 4. INGENIERÍA DE DATOS DE HOY
print("🔄 Traduciendo nombres de API a formato de Inteligencia Artificial...")

# Diccionario traductor de todas las franquicias
traductor_equipos = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Cleveland Indians": "CLE", # Por si el dataset viejo usa el nombre anterior
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Oakland Athletics": "OAK",
    "Athletics": "OAK", # Tu API a veces omite "Oakland"
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH"
}

# Traducimos las columnas de tu base de datos al formato de Kaggle
df_hoy['team'] = df_hoy['team'].map(traductor_equipos).fillna(df_hoy['team'])
df_hoy['opponent'] = df_hoy['opponent'].map(traductor_equipos).fillna(df_hoy['opponent'])

# Convertimos los nombres traducidos a 1s y 0s
equipos_hoy = pd.get_dummies(df_hoy[['team', 'opponent']])

# Alineamos las columnas de hoy con el molde de 62 columnas histórico
equipos_hoy = equipos_hoy.reindex(columns=columnas_entrenamiento, fill_value=0)

# Normalizamos las cuotas de hoy usando el mismo factor de escala
cuotas_hoy = scaler.transform(df_hoy[['moneyLine', 'oppMoneyLine']])
cuotas_df = pd.DataFrame(cuotas_hoy, columns=['cuota_L_norm', 'cuota_V_norm'])

# Unimos todo en la matriz final X
X_hoy = pd.concat([equipos_hoy, cuotas_df], axis=1)

# 5. GENERAR PREDICCIONES
print("🔮 Consultando al oráculo...\n")
predicciones = modelo.predict(X_hoy, verbose=0)

print("=" * 60)
print("⚾ PREDICCIONES DEL MODELO TENSORFLOW ⚾")
print("=" * 60)

for i in range(len(df_hoy)):
    local = df_hoy.loc[i, 'team']
    visitante = df_hoy.loc[i, 'opponent']
    
    # La neurona de salida nos da un número (ej. 0.65), lo pasamos a porcentaje
    prob_local = predicciones[i][0] * 100
    prob_visitante = 100 - prob_local
    
    # Lógica para definir quién tiene más ventaja
    favorito_ia = local if prob_local > 50 else visitante
    confianza = max(prob_local, prob_visitante)
    
    print(f"🏟️ {local} vs {visitante}")
    print(f"   🤖 Ganador proyectado: {favorito_ia} (Confianza: {confianza:.1f}%)")
    print(f"   📊 Probabilidades: {local} ({prob_local:.1f}%) | {visitante} ({prob_visitante:.1f}%)")
    print("-" * 60)