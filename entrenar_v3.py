import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout
import joblib

print("📊 1. Iniciando Reingeniería del Historial MLB (Versión 3.0)...")
df = pd.read_csv('mlb_historico.csv')

# --- CONFIGURACIÓN CRONOLÓGICA ---
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(by='date').reset_index(drop=True)

# 🔧 DEBUG: confirma cuántas filas trae el CSV crudo, antes de cualquier filtro
print(f"🔍 Filas totales en el CSV: {len(df)}")
print(f"🔍 Muestra de moneyLine: {df['moneyLine'].head(5).tolist()}")
print(f"🔍 Rango de moneyLine: min={df['moneyLine'].min()}, max={df['moneyLine'].max()}")

# Limpieza inicial de datos corruptos sin cuotas
df = df.dropna(subset=['moneyLine', 'oppMoneyLine', 'runs', 'oppRuns'])
print(f"🔍 Filas después de quitar NaN: {len(df)}")

# ==========================================================
# 🔧 CORRECCIÓN: DETECCIÓN Y CONVERSIÓN DE FORMATO DE CUOTAS
# ==========================================================
# El filtro original "(moneyLine > 0) & (oppMoneyLine > 0)" solo tiene sentido
# si las cuotas ya vienen en formato DECIMAL (ej. 1.85), donde ambas siempre
# son positivas. Si tus cuotas vienen en formato AMERICANO (ej. -150 / +130),
# ese filtro borra casi TODAS las filas, porque en cuotas americanas casi
# siempre una es negativa (el favorito) y la otra positiva (el underdog) —
# nunca las dos positivas al mismo tiempo. Esto es justo lo que causaba el
# ValueError de "n_samples=0".
#
# Aquí detectamos el formato automáticamente y convertimos cuotas americanas
# a decimales antes de seguir, para que el resto del script funcione igual
# sin importar en qué formato vengan tus datos históricos.

def moneyline_a_decimal(valor):
    """Convierte una cuota americana a decimal. Si ya es decimal, la deja igual."""
    # Heurística: las cuotas americanas son enteros grandes (>=100 o <=-100).
    # Las cuotas decimales normales de MLB rondan entre 1.01 y ~15.00.
    if valor <= -100:
        # Favorito en formato americano: ej. -150 -> decimal 1.6667
        return (100 / abs(valor)) + 1
    elif valor >= 100:
        # Underdog en formato americano: ej. +130 -> decimal 2.30
        return (valor / 100) + 1
    else:
        # Ya viene en formato decimal (o algún valor atípico entre -100 y 100
        # que no es válido en formato americano real)
        return valor

# Detectamos el formato mirando si existen valores negativos o mayores a ~20
# (las cuotas decimales de MLB casi nunca pasan de 15-20)
parece_americano = (df['moneyLine'] < 0).any() or (df['moneyLine'] > 20).any()

if parece_americano:
    print("💵 Formato de cuotas detectado: AMERICANO. Convirtiendo a decimal...")
    df['moneyLine'] = df['moneyLine'].apply(moneyline_a_decimal)
    df['oppMoneyLine'] = df['oppMoneyLine'].apply(moneyline_a_decimal)
else:
    print("💵 Formato de cuotas detectado: DECIMAL. No se requiere conversión.")

# Ahora sí, el filtro tiene sentido: en formato decimal, las cuotas SIEMPRE
# deben ser mayores a 1.0 (nunca 0 o negativas). Cambiamos el filtro de
# "> 0" a "> 1" para ser más estrictos y detectar datos corruptos reales.
df = df[(df['moneyLine'] > 1) & (df['oppMoneyLine'] > 1)].reset_index(drop=True)
print(f"🔍 Filas después del filtro de cuotas válidas: {len(df)}")

if len(df) == 0:
    raise ValueError(
        "🚨 El DataFrame quedó vacío después de limpiar las cuotas. "
        "Revisa manualmente los valores de moneyLine/oppMoneyLine en tu CSV — "
        "puede que tengan un formato distinto al americano o decimal estándar."
    )

# Target: 1 si ganó el equipo (team), 0 si perdió
df['gano'] = np.where(df['runs'] > df['oppRuns'], 1, 0)

# --- INGENIERÍA DE VARIABLES (FEATURE ENGINEERING) SIN SESGO ---
print("🧠 Calculando métricas de rendimiento acumuladas (Viaje en el tiempo)...")

# Diccionarios maestros para simular la memoria del sistema en el tiempo
juegos_jugados = {}
victorias = {}
carreras_anotadas = {}
carreras_recibidas = {}

# Listas donde guardaremos las características exactas con las que iniciaba cada partido
win_pct_team, win_pct_opp = [], []
run_diff_team, run_diff_opp = [], []
descanso_team, descanso_opp = [], []
racha_5_team, racha_5_opp = [], []

# Guardas temporales para calcular días de descanso y rachas rodantes
ultima_fecha = {}
historial_ganadas = {} 

for idx, row in df.iterrows():
    fecha = row['date']
    t = row['team']
    o = row['opponent']
    
    # Inicializar si es el primer juego que ve el script de ese equipo
    for equipo in [t, o]:
        if equipo not in juegos_jugados:
            juegos_jugados[equipo] = 0
            victorias[equipo] = 0
            carreras_anotadas[equipo] = 0
            carreras_recibidas[equipo] = 0
            historial_ganadas[equipo] = []

    # A) CALCULAR VALORES ANTES DEL PARTIDO (Lo que la IA usará para predecir)
    # Porcentaje de victorias previo
    pct_t = victorias[t] / juegos_jugados[t] if juegos_jugados[t] > 0 else 0.500
    pct_o = victorias[o] / juegos_jugados[o] if juegos_jugados[o] > 0 else 0.500
    
    # Diferencial de carreras previo
    diff_t = carreras_anotadas[t] - carreras_recibidas[t]
    diff_o = carreras_anotadas[o] - carreras_recibidas[o]
    
    # Fatiga (Días de descanso)
    desc_t = (fecha - ultima_fecha[t]).days if t in ultima_fecha else 3
    desc_o = (fecha - ultima_fecha[o]).days if o in ultima_fecha else 3
    
    # Racha rodante últimos 5 juegos
    r_t = np.mean(historial_ganadas[t][-5:]) if len(historial_ganadas[t]) > 0 else 0.5
    r_o = np.mean(historial_ganadas[o][-5:]) if len(historial_ganadas[o]) > 0 else 0.5

    # Guardar en las listas de la mega-matriz
    win_pct_team.append(pct_t)
    win_pct_opp.append(pct_o)
    run_diff_team.append(diff_t)
    run_diff_opp.append(diff_o)
    descanso_team.append(desc_t)
    descanso_opp.append(desc_o)
    racha_5_team.append(r_t)
    racha_5_opp.append(r_o)

    # B) ACTUALIZAR LA MEMORIA CON EL RESULTADO DE ESTE PARTIDO (Para el futuro)
    juegos_jugados[t] += 1
    juegos_jugados[o] += 1
    
    carreras_anotadas[t] += row['runs']
    carreras_recibidas[t] += row['oppRuns']
    carreras_anotadas[o] += row['oppRuns']
    carreras_recibidas[o] += row['runs']
    
    if row['gano'] == 1:
        victorias[t] += 1
        historial_ganadas[t].append(1)
        historial_ganadas[o].append(0)
    else:
        victorias[o] += 1
        historial_ganadas[t].append(0)
        historial_ganadas[o].append(1)
        
    ultima_fecha[t] = fecha
    ultima_fecha[o] = fecha

# Inyectar las nuevas columnas limpias al DataFrame
df['win_pct_team'] = win_pct_team
df['win_pct_opp'] = win_pct_opp
df['run_diff_team'] = run_diff_team
df['run_diff_opp'] = run_diff_opp
df['dias_descanso_team'] = descanso_team
df['dias_descanso_opp'] = descanso_opp
df['racha_5_team'] = racha_5_team
df['racha_5_opp'] = racha_5_opp

# --- DESPARASITAR EL MONEYLINE (CÁLCULO DE PROBABILIDAD IMPLÍCITA PURA) ---
print("💸 Desparasitando cuotas de Las Vegas (Removiendo el Margen/Vig)...")

# Convertimos cuotas decimales a probabilidades implícitas base
# (Ya garantizamos arriba que moneyLine/oppMoneyLine están en formato decimal)
df['prob_impl_team_cruda'] = 1 / df['moneyLine']
df['prob_impl_opp_cruda'] = 1 / df['oppMoneyLine']

# Calculamos el Overround (El impuesto cobrado por la casa, ej: 1.04 significa 4% de ganancia para ellos)
df['overround'] = df['prob_impl_team_cruda'] + df['prob_impl_opp_cruda']

# Remover el impuesto dividiendo la probabilidad cruda entre el overround total
df['prob_pure_team'] = df['prob_impl_team_cruda'] / df['overround']
df['prob_pure_opp'] = df['prob_impl_opp_cruda'] / df['overround']


# --- PREPARACIÓN DE MATRICES FINALES ---
print("⚙️ Armando la nueva matriz de inputs sin identidades numéricas...")

# X contiene únicamente variables métricas puras y continuas. ¡Ya no hay team_code ruidoso!
X = df[[
    'win_pct_team', 'win_pct_opp', 
    'run_diff_team', 'run_diff_opp', 
    'dias_descanso_team', 'dias_descanso_opp',
    'racha_5_team', 'racha_5_opp',
    'prob_pure_team', 'prob_pure_opp'
]]
y = df['gano']

print(f"🔍 Forma final de X antes de dividir: {X.shape}")

# Dividir en 80% entrenamiento y 20% prueba
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Escalar la matriz de forma homogénea
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)


print("🧠 3. Construyendo Red Neuronal v3.0 (Enfoque en Edge Matemático)...")
model = Sequential([
    Dense(32, activation='relu', input_shape=(X_train_scaled.shape[1],)),
    Dropout(0.2),
    Dense(16, activation='relu'),
    Dropout(0.2),
    Dense(1, activation='sigmoid')
])

model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

# Entrenar el nuevo modelo
print("🏋️ Entrenando modelo...")
model.fit(X_train_scaled, y_train, epochs=40, batch_size=32, validation_data=(X_test_scaled, y_test), verbose=1)


print("💾 4. Guardando el nuevo ecosistema v3.0...")
model.save_weights('pesos_mlb_v3.weights.h5')
joblib.dump(scaler, 'scaler_v3.pkl')
# Guardamos los nombres de las columnas para que el dashboard sepa exactamente en qué orden van
joblib.dump(X.columns.tolist(), 'columnas_v3.pkl')

print("✅ ¡Ecosistema v3.0 completado! La IA ahora evalúa talento y ventaja real, ignorando nombres.")