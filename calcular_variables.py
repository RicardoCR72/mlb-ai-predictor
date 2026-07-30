import pandas as pd

print("🧠 Calculando rachas y fatiga de los equipos...")

# 1. Cargar los datos y ordenarlos por fecha (muy importante para viajar en el tiempo)
df = pd.read_csv('mlb_historial_22_26.csv')
df['fecha'] = pd.to_datetime(df['fecha'])
df = df.sort_values('fecha').reset_index(drop=True)

# 2. Diccionarios para la "memoria" de los equipos
rachas = {}        # Guarda la racha actual (ej. 3 victorias o -2 derrotas)
ultima_fecha = {}  # Guarda cuándo fue la última vez que jugaron

# Listas para guardar los nuevos datos
racha_local, racha_visitante = [], []
descanso_local, descanso_visitante = [], []

# 3. Recorremos la historia partido por partido
for index, row in df.iterrows():
    fecha = row['fecha']
    local = row['equipo_local']
    visita = row['equipo_visitante']
    score_l = row['marcador_local']
    score_v = row['marcador_visitante']

    # Si es el primer juego del equipo, iniciamos sus valores en 0
    if local not in rachas: rachas[local] = 0
    if visita not in rachas: rachas[visita] = 0
    
    # Calcular días de descanso (Fatiga)
    # Si descansaron 1 día, es normal. Si descansaron 0, es "Back-to-Back" (cansados).
    dias_l = (fecha - ultima_fecha[local]).days if local in ultima_fecha else 3
    dias_v = (fecha - ultima_fecha[visita]).days if visita in ultima_fecha else 3

    # GUARDAR el dato de cómo llegaron AL partido (ANTES de jugar)
    racha_local.append(rachas[local])
    racha_visitante.append(rachas[visita])
    descanso_local.append(dias_l)
    descanso_visitante.append(dias_v)

    # ACTUALIZAR la memoria para su SIGUIENTE partido
    ultima_fecha[local] = fecha
    ultima_fecha[visita] = fecha

    # ¿Quién ganó? Modificamos la racha para el futuro
    if score_l > score_v:
        # Gana el Local
        rachas[local] = rachas[local] + 1 if rachas[local] > 0 else 1
        rachas[visita] = rachas[visita] - 1 if rachas[visita] < 0 else -1
    elif score_v > score_l:
        # Gana la Visita
        rachas[visita] = rachas[visita] + 1 if rachas[visita] > 0 else 1
        rachas[local] = rachas[local] - 1 if rachas[local] < 0 else -1
    else:
        # Empate (muy raro en beisbol, pero por si acaso)
        rachas[local] = 0
        rachas[visita] = 0

# 4. Pegamos las nuevas columnas a nuestra tabla
df['racha_local'] = racha_local
df['racha_visitante'] = racha_visitante
df['descanso_local'] = descanso_local
df['descanso_visitante'] = descanso_visitante

# ¿Quién ganó el partido al final? (Esta será la respuesta que la IA intentará adivinar)
# 1 = Gana Local, 0 = Gana Visita
df['resultado_final'] = (df['marcador_local'] > df['marcador_visitante']).astype(int)

# Guardar el dataset maestro
df.to_csv('mlb_dataset_ia.csv', index=False)
print("✅ ¡Listo! Se creó 'mlb_dataset_ia.csv' con el cálculo matemático completado.")