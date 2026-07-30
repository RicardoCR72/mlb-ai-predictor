import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout
import joblib

print("🛠️ Preparando el set de datos avanzado...")

# 1. Cargar los datos matemáticos
df = pd.read_csv('mlb_dataset_ia.csv')

# 2. Preparar Variables (Features)
# A) Los equipos se convierten a columnas binarias (1s y 0s)
equipos_encoded = pd.get_dummies(df[['equipo_local', 'equipo_visitante']])

# B) Las rachas y descansos se escalan para que la IA los procese mejor
variables_numericas = df[['racha_local', 'racha_visitante', 'descanso_local', 'descanso_visitante']]
scaler = MinMaxScaler()
variables_escaladas = pd.DataFrame(
    scaler.fit_transform(variables_numericas), 
    columns=variables_numericas.columns
)

# Unimos todo en nuestra matriz maestra (X)
X = pd.concat([equipos_encoded, variables_escaladas], axis=1)

# La respuesta correcta que la IA debe aprender (y)
y = df['resultado_final'] 

# 3. Dividir los datos (80% para estudiar, 20% para el examen final)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print("🧠 Construyendo la Arquitectura de la Red Neuronal...")

# 4. Construir el Cerebro (Versión 2.0)
modelo = Sequential([
    # Capa de entrada (recibe equipos, rachas y fatiga)
    Dense(64, activation='relu', input_shape=(X_train.shape[1],)),
    Dropout(0.3), # Apaga el 30% de las neuronas para evitar memorización
    
    # Capa oculta para encontrar patrones complejos
    Dense(32, activation='relu'),
    Dropout(0.2),
    
    # Capa de salida (1 sola neurona que escupe probabilidad de 0 a 1)
    Dense(1, activation='sigmoid') 
])

modelo.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

# 5. Entrenar
print("🚀 Iniciando entrenamiento (Epochs)...")
historial = modelo.fit(X_train, y_train, epochs=50, batch_size=32, validation_split=0.2, verbose=1)

# 6. Examen Final
perdida, precision = modelo.evaluate(X_test, y_test)
print("-" * 50)
print(f"✅ Precisión en partidos nunca antes vistos: {precision * 100:.2f}%")
print("-" * 50)

# 7. Guardar el ecosistema completo
modelo.save('cerebro_mlb_v2.keras')
joblib.dump(scaler, 'scaler_v2.pkl')
joblib.dump(X.columns, 'columnas_entrenamiento_v2.pkl')

print("💾 ¡Archivo 'cerebro_mlb_v2.keras' generado con éxito!")