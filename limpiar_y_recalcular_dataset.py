import pandas as pd

print("🧹 Limpiando y recalculando mlb_dataset_ia.csv desde la fuente cruda...")

# --- 1. CARGAR LA FUENTE CRUDA (box scores sin racha/descanso calculados) ---
df = pd.read_csv('mlb_historial_22_26.csv')
df['fecha'] = pd.to_datetime(df['fecha'])
print(f"📄 Filas crudas cargadas: {len(df)}")

# --- 2. FILTRAR SOLO EQUIPOS REALES DE MLB (30 equipos) ---
# Esto quita partidos de pretemporada contra ligas menores, World Baseball
# Classic, Juego de Estrellas, universidades, etc. — partidos que no son
# temporada regular real y que contaminan racha/descanso/entrenamiento.
EQUIPOS_MLB_VALIDOS = {
    'Arizona Diamondbacks', 'Athletics', 'Atlanta Braves', 'Baltimore Orioles',
    'Boston Red Sox', 'Chicago Cubs', 'Chicago White Sox', 'Cincinnati Reds',
    'Cleveland Guardians', 'Colorado Rockies', 'Detroit Tigers', 'Houston Astros',
    'Kansas City Royals', 'Los Angeles Angels', 'Los Angeles Dodgers', 'Miami Marlins',
    'Milwaukee Brewers', 'Minnesota Twins', 'New York Mets', 'New York Yankees',
    'Philadelphia Phillies', 'Pittsburgh Pirates', 'San Diego Padres', 'San Francisco Giants',
    'Seattle Mariners', 'St. Louis Cardinals', 'Tampa Bay Rays', 'Texas Rangers',
    'Toronto Blue Jays', 'Washington Nationals'
}

antes = len(df)
df = df[
    df['equipo_local'].isin(EQUIPOS_MLB_VALIDOS) &
    df['equipo_visitante'].isin(EQUIPOS_MLB_VALIDOS)
].reset_index(drop=True)
despues = len(df)
print(f"🚫 Filas de exhibición/no-MLB eliminadas: {antes - despues}")
print(f"✅ Filas válidas de temporada MLB: {despues}")

# --- 3. ORDENAR CRONOLÓGICAMENTE (indispensable para calcular racha/descanso bien) ---
df = df.sort_values(by='fecha').reset_index(drop=True)

# --- 4. RECALCULAR RACHA Y DESCANSO DESDE CERO, PARTIDO POR PARTIDO ---
# Misma lógica exacta que usa dashboard.py en obtener_estado_actual():
# - racha positiva = rachas de victorias, racha negativa = rachas de derrotas
# - descanso = días desde el último partido (3 por defecto si es el primero que vemos)
print("🧠 Recalculando racha y descanso en orden cronológico...")

ultimo_estado = {}  # equipo -> (racha_actual, fecha_ultimo_juego)

racha_local_col, racha_visitante_col = [], []
descanso_local_col, descanso_visitante_col = [], []
resultado_final_col = []

for idx, row in df.iterrows():
    fecha = row['fecha']
    local = row['equipo_local']
    visita = row['equipo_visitante']

    # --- Estado del equipo LOCAL antes de este partido ---
    if local in ultimo_estado:
        racha_l_previa, fecha_ultimo_l = ultimo_estado[local]
        descanso_l = (fecha - fecha_ultimo_l).days
    else:
        racha_l_previa, descanso_l = 0, 3

    # --- Estado del equipo VISITANTE antes de este partido ---
    if visita in ultimo_estado:
        racha_v_previa, fecha_ultimo_v = ultimo_estado[visita]
        descanso_v = (fecha - fecha_ultimo_v).days
    else:
        racha_v_previa, descanso_v = 0, 3

    # Guardamos el estado CON el que llegaban a este partido (lo que la IA vería)
    racha_local_col.append(racha_l_previa)
    racha_visitante_col.append(racha_v_previa)
    descanso_local_col.append(descanso_l)
    descanso_visitante_col.append(descanso_v)

    # --- Calculamos el resultado de este partido para actualizar la racha hacia adelante ---
    gano_local = row['marcador_local'] > row['marcador_visitante']
    resultado_final_col.append(1 if gano_local else 0)

    if gano_local:
        racha_l_nueva = racha_l_previa + 1 if racha_l_previa > 0 else 1
        racha_v_nueva = racha_v_previa - 1 if racha_v_previa < 0 else -1
    else:
        racha_l_nueva = racha_l_previa - 1 if racha_l_previa < 0 else -1
        racha_v_nueva = racha_v_previa + 1 if racha_v_previa > 0 else 1

    ultimo_estado[local] = (racha_l_nueva, fecha)
    ultimo_estado[visita] = (racha_v_nueva, fecha)

df['racha_local'] = racha_local_col
df['racha_visitante'] = racha_visitante_col
df['descanso_local'] = descanso_local_col
df['descanso_visitante'] = descanso_visitante_col
df['resultado_final'] = resultado_final_col

# --- 5. FORMATEAR IGUAL QUE EL ORIGINAL Y GUARDAR ---
df['fecha'] = df['fecha'].dt.strftime('%Y-%m-%d')
columnas_finales = [
    'fecha', 'equipo_local', 'equipo_visitante', 'marcador_local', 'marcador_visitante',
    'racha_local', 'racha_visitante', 'descanso_local', 'descanso_visitante', 'resultado_final'
]
df = df[columnas_finales]

df.to_csv('mlb_dataset_ia_limpio.csv', index=False)
print(f"💾 Guardado: mlb_dataset_ia_limpio.csv ({len(df)} filas)")
print("✅ Listo. Revisa el archivo y, si todo se ve bien, reemplaza tu mlb_dataset_ia.csv con este.")
