import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout
import joblib

print("📊 1. Iniciando Entrenamiento V4.0 (Edge + Jetlag + Métricas Avanzadas)...")
df = pd.read_csv('mlb_historico.csv')

df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(by='date').reset_index(drop=True)

# 🛡️ Filtro de cuotas válidas (igual que en V3)
def moneyline_a_decimal(valor):
    if valor <= -100: return (100 / abs(valor)) + 1
    elif valor >= 100: return (valor / 100) + 1
    else: return valor

if (df['moneyLine'] < 0).any() or (df['moneyLine'] > 20).any():
    df['moneyLine'] = df['moneyLine'].apply(moneyline_a_decimal)
    df['oppMoneyLine'] = df['oppMoneyLine'].apply(moneyline_a_decimal)

df = df.dropna(subset=['moneyLine', 'oppMoneyLine', 'runs', 'oppRuns'])
df = df[(df['moneyLine'] > 1) & (df['oppMoneyLine'] > 1)].reset_index(drop=True)
df['gano'] = np.where(df['runs'] > df['oppRuns'], 1, 0)

print("🧠 Calculando métricas de rendimiento y Desgaste por Viaje (Jetlag)...")

# 🌍 Diccionario de Zonas Horarias
ZONAS_HORARIAS = {
    'ARI': -7, 'ATL': -5, 'BAL': -5, 'BOS': -5, 'CHC': -6, 'CWS': -6, 'CIN': -5, 'CLE': -5,
    'COL': -7, 'DET': -5, 'HOU': -6, 'KC': -6, 'LAA': -8, 'LAD': -8, 'MIA': -5, 'MIL': -6,
    'MIN': -6, 'NYM': -5, 'NYY': -5, 'OAK': -8, 'PHI': -5, 'PIT': -5, 'SD': -8, 'SF': -8,
    'SEA': -8, 'STL': -6, 'TB': -5, 'TEX': -6, 'TOR': -5, 'WSH': -5
}

# --- MAPEO DE EQUIPOS PARA EL JETLAG ---
MAPEO_NOMBRES = {
    'Arizona Diamondbacks': 'ARI', 'Athletics': 'OAK', 'Atlanta Braves': 'ATL',
    'Baltimore Orioles': 'BAL', 'Boston Red Sox': 'BOS', 'Chicago Cubs': 'CHC',
    'Chicago White Sox': 'CWS', 'Cincinnati Reds': 'CIN', 'Cleveland Guardians': 'CLE',
    'Colorado Rockies': 'COL', 'Detroit Tigers': 'DET', 'Houston Astros': 'HOU',
    'Kansas City Royals': 'KC', 'Los Angeles Angels': 'LAA', 'Los Angeles Dodgers': 'LAD',
    'Miami Marlins': 'MIA', 'Milwaukee Brewers': 'MIL', 'Minnesota Twins': 'MIN',
    'New York Mets': 'NYM', 'New York Yankees': 'NYY', 'Philadelphia Phillies': 'PHI',
    'Pittsburgh Pirates': 'PIT', 'San Diego Padres': 'SD', 'San Francisco Giants': 'SF',
    'Seattle Mariners': 'SEA', 'St. Louis Cardinals': 'STL', 'Tampa Bay Rays': 'TB',
    'Texas Rangers': 'TEX', 'Toronto Blue Jays': 'TOR', 'Washington Nationals': 'WSH',
}

def obtener_zona(nombre_equipo):
    abbr = MAPEO_NOMBRES.get(nombre_equipo, 'NYY') # NYY por defecto si no lo encuentra
    return ZONAS_HORARIAS.get(abbr, -5)

juegos_jugados = {}
victorias = {}
carreras_anotadas = {}
carreras_recibidas = {}
ultima_fecha = {}
historial_ganadas = {}
ultimo_estadio = {} 

win_pct_team, win_pct_opp = [], []
run_diff_team, run_diff_opp = [], []
descanso_team, descanso_opp = [], []
racha_5_team, racha_5_opp = [], []
jetlag_team, jetlag_opp = [], []

for idx, row in df.iterrows():
    fecha = row['date']
    t = row['team']
    o = row['opponent']
    estadio_hoy = obtener_zona(t) # El equipo local dicta el huso horario de hoy
    
    for equipo in [t, o]:
        if equipo not in juegos_jugados:
            juegos_jugados[equipo] = 0
            victorias[equipo] = 0
            carreras_anotadas[equipo] = 0
            carreras_recibidas[equipo] = 0
            historial_ganadas[equipo] = []
            ultimo_estadio[equipo] = obtener_zona(equipo) # Empiezan en su casa

    # A) CALCULAR VALORES
    pct_t = victorias[t] / juegos_jugados[t] if juegos_jugados[t] > 0 else 0.500
    pct_o = victorias[o] / juegos_jugados[o] if juegos_jugados[o] > 0 else 0.500
    
    diff_t = carreras_anotadas[t] - carreras_recibidas[t]
    diff_o = carreras_anotadas[o] - carreras_recibidas[o]
    
    desc_t = (fecha - ultima_fecha[t]).days if t in ultima_fecha else 3
    desc_o = (fecha - ultima_fecha[o]).days if o in ultima_fecha else 3
    
    r_t = np.mean(historial_ganadas[t][-5:]) if len(historial_ganadas[t]) > 0 else 0.5
    r_o = np.mean(historial_ganadas[o][-5:]) if len(historial_ganadas[o]) > 0 else 0.5

    # 🔥 EL CALCULO DEL JETLAG (Desgaste por viaje)
    jl_t = abs(estadio_hoy - ultimo_estadio[t])
    jl_o = abs(estadio_hoy - ultimo_estadio[o])

    win_pct_team.append(pct_t)
    win_pct_opp.append(pct_o)
    run_diff_team.append(diff_t)
    run_diff_opp.append(diff_o)
    descanso_team.append(desc_t)
    descanso_opp.append(desc_o)
    racha_5_team.append(r_t)
    racha_5_opp.append(r_o)
    jetlag_team.append(jl_t)
    jetlag_opp.append(jl_o)

    # B) ACTUALIZAR MEMORIA
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
    ultimo_estadio[t] = estadio_hoy
    ultimo_estadio[o] = estadio_hoy

df['win_pct_team'] = win_pct_team
df['win_pct_opp'] = win_pct_opp
df['run_diff_team'] = run_diff_team
df['run_diff_opp'] = run_diff_opp
df['dias_descanso_team'] = descanso_team
df['dias_descanso_opp'] = descanso_opp
df['racha_5_team'] = racha_5_team
df['racha_5_opp'] = racha_5_opp
df['jetlag_team'] = jetlag_team
df['jetlag_opp'] = jetlag_opp

# 🔥 INYECTAMOS PROMEDIOS PARA LAS VARIABLES QUE AÚN NO TIENEN HISTORIAL
# Esto prepara la "tubería" para que el modelo acepte estos datos en vivo desde el dashboard
df['ops_l_team'] = 0.700
df['ops_r_team'] = 0.700
df['era_bullpen_team'] = 4.50
df['ops_l_opp'] = 0.700
df['ops_r_opp'] = 0.700
df['era_bullpen_opp'] = 4.50

print("💸 Desparasitando cuotas...")
df['prob_impl_team_cruda'] = 1 / df['moneyLine']
df['prob_impl_opp_cruda'] = 1 / df['oppMoneyLine']
df['overround'] = df['prob_impl_team_cruda'] + df['prob_impl_opp_cruda']
df['prob_pure_team'] = df['prob_impl_team_cruda'] / df['overround']
df['prob_pure_opp'] = df['prob_impl_opp_cruda'] / df['overround']

print("⚙️ Armando la MEGA-MATRIZ V4 de 16 variables...")
X = df[[
    'win_pct_team', 'win_pct_opp', 
    'run_diff_team', 'run_diff_opp', 
    'dias_descanso_team', 'dias_descanso_opp',
    'racha_5_team', 'racha_5_opp',
    'jetlag_team', 'jetlag_opp',
    'ops_l_team', 'ops_r_team', 'era_bullpen_team',
    'ops_l_opp', 'ops_r_opp', 'era_bullpen_opp',
    'prob_pure_team', 'prob_pure_opp'
]]
y = df['gano']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print("🧠 Construyendo Red Neuronal Profunda v4.0...")
model = Sequential([
    Dense(64, activation='relu', input_shape=(X_train_scaled.shape[1],)),
    Dropout(0.3),
    Dense(32, activation='relu'),
    Dropout(0.2),
    Dense(16, activation='relu'),
    Dropout(0.2),
    Dense(1, activation='sigmoid')
])

model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
model.fit(X_train_scaled, y_train, epochs=40, batch_size=32, validation_data=(X_test_scaled, y_test), verbose=1)

print("💾 Guardando el ecosistema V4.0...")
model.save_weights('pesos_mlb_v4.weights.h5')
joblib.dump(scaler, 'scaler_v4.pkl')
joblib.dump(X.columns.tolist(), 'columnas_v4.pkl')

print("✅ ¡Versión 4 lista! Tienes los archivos 'pesos_mlb_v4.weights.h5', 'scaler_v4.pkl' y 'columnas_v4.pkl'.")