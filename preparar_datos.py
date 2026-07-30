import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout
import tensorflow as tf

print("⚾ Cargando 10 años de historia de la MLB...")

# 1. Cargar el dataset
try:
    df = pd.read_csv('mlb_historico.csv')
    print(f"✅ ¡Archivo cargado! Encontramos {len(df)} partidos históricos.")
except FileNotFoundError:
    print("❌ No se encontró el archivo. Asegúrate de que se llame 'mlb_historico.csv'.")
    exit()

# ⚠️ ¡ATENCIÓN RICH! ⚠️
# Imprimimos los nombres de las columnas para que veas cómo se llaman en tu CSV
print("\n🔍 Estas son las columnas de tu dataset:")
print(df.columns.tolist())
print("-" * 50)

# ==============================================================================
# PASO MANUAL ACTUALIZADO
# ==============================================================================
COLUMNA_LOCAL = 'team'            
COLUMNA_VISITANTE = 'opponent'    
COLUMNA_CUOTA_L = 'moneyLine'     
COLUMNA_CUOTA_V = 'oppMoneyLine'  
COLUMNA_SCORE_L = 'runs'          
COLUMNA_SCORE_V = 'oppRuns'       
# ==============================================================================

try:
    # 2. LIMPIEZA DE DATOS
    # Quitamos filas que no tengan cuotas o resultados (datos corruptos)
    df = df.dropna(subset=[COLUMNA_CUOTA_L, COLUMNA_CUOTA_V, COLUMNA_SCORE_L, COLUMNA_SCORE_V])
    
    # 3. CREAR EL VECTOR 'Y' (Las Respuestas)
    # 1 si ganó el Local, 0 si ganó el Visitante
    print("🧠 Calculando quién ganó cada partido (Vector Y)...")
    y = (df[COLUMNA_SCORE_L] > df[COLUMNA_SCORE_V]).astype(int)
    
    # 4. CREAR LA MATRIZ 'X' (Las Pistas)
    print("🔢 Transformando nombres de equipos a números (One-Hot Encoding)...")
    # Convertimos los nombres de los equipos en columnas de 0s y 1s
    equipos_encoded = pd.get_dummies(df[[COLUMNA_LOCAL, COLUMNA_VISITANTE]])
    
    print("⚖️ Normalizando las cuotas de apuestas...")
    # Comprimimos las cuotas entre 0 y 1 para que la red neuronal no se maree
    scaler = MinMaxScaler()
    cuotas_escaladas = scaler.fit_transform(df[[COLUMNA_CUOTA_L, COLUMNA_CUOTA_V]])
    cuotas_df = pd.DataFrame(cuotas_escaladas, columns=['cuota_L_norm', 'cuota_V_norm'], index=df.index)
    
    # Juntamos los equipos codificados y las cuotas normalizadas en una sola mega-matriz
    X = pd.concat([equipos_encoded, cuotas_df], axis=1)
    
    # 5. DIVIDIR PARA ENTRENAR Y EXAMINAR
    # Guardamos 80% de los datos para enseñar, y 20% para hacerle un examen a la IA
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("\n✅ ¡Ingeniería de datos completada!")
    print(f"📚 Datos para enseñar a la IA: {len(X_train)} partidos.")
    print(f"📝 Datos para examinar a la IA: {len(X_test)} partidos.")
    print(f"🧩 Cantidad de variables (columnas) para analizar: {X_train.shape[1]}")
    
except KeyError as e:
    print(f"\n❌ ERROR: No encontré la columna {e}. Revisa la lista de columnas de arriba y actualiza los nombres en el código.")


print("\n🤖 CONSTRUYENDO LA INTELIGENCIA ARTIFICIAL...")

# 1. Definir la arquitectura del cerebro
modelo = Sequential([
    # Capa de entrada (las 62 variables) y primera capa oculta (32 neuronas)
    Dense(32, activation='relu', input_shape=(X_train.shape[1],)),
    Dropout(0.2),
    # Segunda capa oculta (16 neuronas) para aprender patrones más complejos
    Dense(16, activation='relu'),
    Dropout(0.2),
    # Capa de salida (1 neurona). Usamos 'sigmoid' porque queremos una probabilidad de 0 a 1
    Dense(1, activation='sigmoid')
])

# 2. Compilar el modelo (Enseñarle cómo aprender de sus errores)
modelo.compile(
    optimizer='adam', 
    loss='binary_crossentropy', 
    metrics=['accuracy'] # Queremos que mida qué tan preciso (exacto) es
)

print("🏋️ Entrenando la red neuronal... (Esto tomará unos segundos)")

# 3. Entrenar el modelo
# epochs=20 significa que leerá los 36,000 partidos 20 veces para memorizar los patrones
historial = modelo.fit(
    X_train, y_train, 
    epochs=20, 
    batch_size=32, 
    validation_data=(X_test, y_test),
    verbose=1
)

# 4. Evaluación final
print("\n📝 Aplicando el examen final (Con los 9,106 partidos que no ha visto)...")
perdida, precision = modelo.evaluate(X_test, y_test, verbose=0)
print("-" * 50)
print(f"🎯 PRECISIÓN FINAL DEL MODELO: {precision * 100:.2f}%")
print("-" * 50)

# 5. Guardar el cerebro para no tener que entrenarlo desde cero cada vez
modelo.save('cerebro_mlb.keras')
print("💾 Modelo guardado exitosamente como 'cerebro_mlb.keras'. ¡Listo para predecir el futuro!")