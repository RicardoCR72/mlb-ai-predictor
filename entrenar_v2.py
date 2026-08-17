import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout
import joblib

print("📊 1. Cargando historial de MLB...")
df = pd.read_csv('mlb_historico.csv')

# --- INICIO DEL FEATURE ENGINEERING ---

# A. Crear el Target (Ganó = 1, Perdió = 0) deduciendo del marcador
df['gano'] = np.where(df['runs'] > df['oppRuns'], 1, 0)

# B. Ordenar por equipo y fecha para no mezclar el tiempo
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(by=['team', 'date'])

# C. Calcular Fatiga (Días de descanso)
df['dias_descanso'] = df.groupby('team')['date'].diff().dt.days
df['dias_descanso'] = df['dias_descanso'].fillna(3) # Si es inicio de temporada, asume 3 días

# D. Calcular Momento (Racha de victorias en los últimos 5 juegos)
df['racha_ultimos_5'] = df.groupby('team')['gano'].transform(
    lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
)
df['racha_ultimos_5'] = df['racha_ultimos_5'].fillna(0.5) # Neutral al inicio de temporada

# Limpiamos valores nulos por si alguna fila no tiene cuota registrada
df = df.dropna(subset=['moneyLine', 'oppMoneyLine'])

# --- FIN DEL FEATURE ENGINEERING ---

print("⚙️ 2. Procesando variables para la Red Neuronal...")
# Convertir los nombres de los equipos (ej. "LAD", "NYY") a números para que la IA los entienda
encoder = LabelEncoder()
df['team_code'] = encoder.fit_transform(df['team'])
df['opponent_code'] = encoder.transform(df['opponent'])

# Definir X (Lo que la IA estudia) y Y (El resultado del partido)
X = df[['team_code', 'opponent_code', 'moneyLine', 'oppMoneyLine', 'dias_descanso', 'racha_ultimos_5']]
y = df['gano']

# Dividir en datos de entrenamiento (80%) y prueba (20%)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Escalar los datos (para que las cuotas de -150 y los 3 días de descanso se midan con la misma regla)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print("🧠 3. Construyendo y Entrenando la Red Neuronal v2.0...")
model = Sequential()
model.add(Dense(32, activation='relu', input_shape=(X_train_scaled.shape[1],)))
model.add(Dropout(0.2)) # <-- PARCHE ANTI-TRAMPAS: Apaga 20% de neuronas al azar
model.add(Dense(16, activation='relu'))
model.add(Dropout(0.2)) # <-- PARCHE ANTI-TRAMPAS
model.add(Dense(1, activation='sigmoid'))

model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

# Entrenar (Puedes subir los epochs a 100 si ves que sigue aprendiendo bien)
model.fit(X_train_scaled, y_train, epochs=50, batch_size=32, validation_data=(X_test_scaled, y_test))

print("💾 4. Guardando el cerebro y los procesadores...")
# Guardamos todo con nombres nuevos para no borrar tu versión 1.0 que ya funciona
model.save_weights('pesos_mlb_v2.weights.h5')
joblib.dump(scaler, 'scaler_v2.pkl')
joblib.dump(encoder, 'encoder_equipos.pkl')

print("✅ ¡Entrenamiento de la Versión 2.0 completado con éxito!")