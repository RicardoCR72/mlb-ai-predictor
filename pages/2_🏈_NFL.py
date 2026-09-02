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
    api_key = st.secrets["ODDS_API_KEY"]
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
col1, col2 = st.columns(2)

with col1:
    st.markdown("**Partidos (nfl_data_py)**")
    st.dataframe(df_calendario, use_container_width=True)

with col2:
    st.markdown("**Cuotas de Las Vegas (The Odds API)**")
    st.dataframe(df_cuotas, use_container_width=True)

st.success("¡Datos descargados! Siguiente paso: unificar los nombres de los equipos para fusionar las tablas.")