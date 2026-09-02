import streamlit as st
import nfl_data_py as nfl
import pandas as pd
import requests

st.title("🏈 NFL Oráculo V1.0: Spreads & Props")
st.markdown("---")

st.subheader("📅 Calendario y Líneas - Semana 1")

# 1. Cargamos el calendario (como ya lo tenías)
@st.cache_data
def cargar_calendario():
    schedules = nfl.import_schedules([2026])
    semana1 = schedules[(schedules['week'] == 1) & (schedules['game_type'] == 'REG')]
    return semana1[['game_id', 'away_team', 'home_team']].copy()

# 2. Nueva función: Descargamos las cuotas de The Odds API (guardadas en caché por 1 hora)
@st.cache_data(ttl=3600)
def obtener_cuotas_nfl():
    api_key = st.secrets["odds_api_key"]
    sport = "americanfootball_nfl"
    regions = "us" # Mercados americanos (DraftKings, FanDuel, etc.)
    markets = "spreads,totals"
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={api_key}&regions={regions}&markets={markets}"
    
    respuesta = requests.get(url)
    if respuesta.status_code != 200:
        st.error("Error al conectar con The Odds API. Revisa tu cuota de peticiones.")
        return pd.DataFrame()
        
    datos = respuesta.json()
    
    # Extraemos solo lo que nos importa (Equipo Local, Visitante, Spread y Total)
    filas = []
    for juego in datos:
        # Buscamos el casino DraftKings (o el primero que aparezca) como referencia
        if not juego.get('bookmakers'):
            continue
            
        casino = juego['bookmakers'][0] 
        mercados = casino.get('markets', [])
        
        spread = "N/A"
        total = "N/A"
        
        for m in mercados:
            if m['key'] == 'spreads':
                # El spread del equipo local
                spread = [outcome['point'] for outcome in m['outcomes'] if outcome['name'] == juego['home_team']][0]
            elif m['key'] == 'totals':
                # El total de puntos (Over)
                total = [outcome['point'] for outcome in m['outcomes'] if outcome['name'] == 'Over'][0]
                
        filas.append({
            'Visita_API': juego['away_team'],
            'Local_API': juego['home_team'],
            'Spread (Local)': spread,
            'Total (O/U)': total
        })
        
    return pd.DataFrame(filas)

# Ejecutamos las descargas con spinners visuales
with st.spinner("🏈 Descargando bases de datos..."):
    df_calendario = cargar_calendario()

with st.spinner("💸 Obteniendo líneas de Las Vegas..."):
    df_cuotas = obtener_cuotas_nfl()

# Mostramos los resultados (Temporalmente separados para que veas que ambas fuentes funcionan)
mapa_equipos = {
    'ARI': 'Arizona Cardinals', 'ATL': 'Atlanta Falcons', 'BAL': 'Baltimore Ravens',
    'BUF': 'Buffalo Bills', 'CAR': 'Carolina Panthers', 'CHI': 'Chicago Bears',
    'CIN': 'Cincinnati Bengals', 'CLE': 'Cleveland Browns', 'DAL': 'Dallas Cowboys',
    'DEN': 'Denver Broncos', 'DET': 'Detroit Lions', 'GB': 'Green Bay Packers',
    'HOU': 'Houston Texans', 'IND': 'Indianapolis Colts', 'JAX': 'Jacksonville Jaguars',
    'KC': 'Kansas City Chiefs', 'LA': 'Los Angeles Rams', 'LAC': 'Los Angeles Chargers',
    'LV': 'Las Vegas Raiders', 'MIA': 'Miami Dolphins', 'MIN': 'Minnesota Vikings',
    'NE': 'New England Patriots', 'NO': 'New Orleans Saints', 'NYG': 'New York Giants',
    'NYJ': 'New York Jets', 'PHI': 'Philadelphia Eagles', 'PIT': 'Pittsburgh Steelers',
    'SEA': 'Seattle Seahawks', 'SF': 'San Francisco 49ers', 'TB': 'Tampa Bay Buccaneers',
    'TEN': 'Tennessee Titans', 'WAS': 'Washington Commanders'
}

# 4. Creamos columnas nuevas traduciendo las siglas
df_calendario['Visita_Traduccion'] = df_calendario['away_team'].map(mapa_equipos)
df_calendario['Local_Traduccion'] = df_calendario['home_team'].map(mapa_equipos)

# 5. ¡La Fusión! Juntamos las tablas usando los nombres completos
df_fusionado = pd.merge(
    df_calendario, 
    df_cuotas, 
    left_on=['Visita_Traduccion', 'Local_Traduccion'], 
    right_on=['Visita_API', 'Local_API'], 
    how='inner'
)

# 6. Limpiamos el reguero para dejar un DataFrame elegante
columnas_finales = ['game_id', 'Visita_API', 'Local_API', 'Spread (Local)', 'Total (O/U)']
df_final = df_fusionado[columnas_finales].copy()
df_final.columns = ['ID Juego', 'Visita', 'Local', 'Spread (Local)', 'Total']

st.markdown("---")
st.subheader("🔥 Dashboard Maestro: Calendario + Líneas de Las Vegas")
st.dataframe(df_final, use_container_width=True)
st.success("¡Fusión exitosa! Ya tenemos la base de datos central.")

st.markdown("---")
st.header("🏃‍♂️ Motor de Player Props: Línea Base")

# 7. Función para descargar estadísticas de jugadores
@st.cache_data
def cargar_stats_jugadores():
    # Descargamos la data histórica reciente para perfilar la Semana 1
    stats = nfl.import_weekly_data([2024])
    
    # Filtramos para quedarnos solo con las posiciones clave (Fantasy/Props)
    posiciones_clave = ['QB', 'WR', 'RB', 'TE']
    stats_limpias = stats[stats['position'].isin(posiciones_clave)].copy()
    
    # Seleccionamos las métricas que nos interesan para los Props
    columnas_props = [
        'player_name', 'position', 'recent_team', 'week', 
        'passing_yards', 'rushing_yards', 'receiving_yards', 'fantasy_points_ppr'
    ]
    
    return stats_limpias[columnas_props]

with st.spinner("📊 Procesando rendimiento histórico de jugadores..."):
    df_jugadores = cargar_stats_jugadores()
    
    # Creamos un pequeño buscador interactivo en el Dashboard
    st.subheader("Buscador de Jugadores")
    jugador_buscado = st.selectbox("Selecciona un jugador para ver su perfil:", df_jugadores['player_name'].unique())
    
    # Filtramos la tabla según el jugador seleccionado
    perfil_jugador = df_jugadores[df_jugadores['player_name'] == jugador_buscado]
    st.dataframe(perfil_jugador, use_container_width=True)