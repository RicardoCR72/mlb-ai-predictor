import streamlit as st
import nfl_data_py as nfl
import pandas as pd
import requests
import mysql.connector

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

st.markdown("---")
st.subheader("🎯 Proyecciones: Yardas por Pase (Quarterbacks)")

# 1. Filtramos solo a los Quarterbacks
df_qbs = df_jugadores[df_jugadores['position'] == 'QB'].copy()

# 2. Agrupamos por jugador y calculamos las matemáticas del Oráculo
proyecciones_qb = df_qbs.groupby('player_name').agg(
    Partidos=('week', 'count'),
    Promedio_Yardas=('passing_yards', 'mean'),
    Mediana_Yardas=('passing_yards', 'median'),
    Max_Yardas=('passing_yards', 'max')
).reset_index()

# 3. Limpiamos la data: Exigimos mínimo 5 partidos jugados para evitar suplentes
proyecciones_qb = proyecciones_qb[proyecciones_qb['Partidos'] >= 5]

# 4. Redondeamos los números para que se vean elegantes
proyecciones_qb['Promedio_Yardas'] = proyecciones_qb['Promedio_Yardas'].round(1)
proyecciones_qb['Mediana_Yardas'] = proyecciones_qb['Mediana_Yardas'].round(1)

# 5. Ordenamos a los mejores de arriba hacia abajo
proyecciones_qb = proyecciones_qb.sort_values('Promedio_Yardas', ascending=False)

# Mostramos el resultado en el Dashboard
st.dataframe(proyecciones_qb, use_container_width=True)
st.info("💡 Tip del Oráculo: La 'Mediana' es un mejor indicador que el Promedio para apostar Props, ya que elimina los partidos atípicos.")

st.markdown("---")
st.subheader("🎰 Líneas Reales del Casino (Player Props)")

@st.cache_data(ttl=3600)
def obtener_lineas_props_qb():
    api_key = st.secrets["odds_api_key"]
    sport = "americanfootball_nfl"
    regions = "us" # Puedes cambiarlo a 'eu' o 'uk' si usas otros mercados, pero 'us' trae las líneas más sólidas
    markets = "player_passing_yards"
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={api_key}&regions={regions}&markets={markets}"
    
    respuesta = requests.get(url)
    if respuesta.status_code != 200:
        st.warning("No hay líneas de Props de QB disponibles en este momento (los casinos suelen soltarlas más cerca del domingo).")
        return pd.DataFrame()
        
    datos = respuesta.json()
    
    filas = []
    for juego in datos:
        if not juego.get('bookmakers'):
            continue
            
        casino = juego['bookmakers'][0] 
        mercados = casino.get('markets', [])
        
        for m in mercados:
            if m['key'] == 'player_passing_yards':
                for outcome in m['outcomes']:
                    # En los props, The Odds API pone el nombre del jugador en 'description'
                    if outcome['name'] == 'Over': 
                        filas.append({
                            'Jugador_API': outcome['description'],
                            'Linea_Casino': outcome['point']
                        })
                        
    df_lineas = pd.DataFrame(filas)
    
    # Eliminamos duplicados por si un jugador sale dos veces
    if not df_lineas.empty:
        df_lineas = df_lineas.drop_duplicates(subset=['Jugador_API'])
        
    return df_lineas

with st.spinner("💸 Hackeando las líneas de Las Vegas para Quarterbacks..."):
    df_lineas_qb = obtener_lineas_props_qb()
    
    if not df_lineas_qb.empty:
        st.dataframe(df_lineas_qb, use_container_width=True)
    else:
        st.info("Esperando a que los casinos liberen las líneas de yardas por pase de la Semana 1...")

# 6. El Motor de Valor (La trampa inteligente)
if not df_lineas_qb.empty:
    st.markdown("---")
    st.subheader("🔥 Detector de Apuestas de Valor (QBs)")
    
    # Función rápida para convertir "Patrick Mahomes" a "P.Mahomes"
    def traducir_nombre_jugador(nombre_completo):
        partes = nombre_completo.split(" ", 1)
        if len(partes) > 1:
            return f"{partes[0][0]}.{partes[1]}"
        return nombre_completo
        
    # Aplicamos la traducción a la tabla del casino
    df_lineas_qb['player_name'] = df_lineas_qb['Jugador_API'].apply(traducir_nombre_jugador)
    
    # Cruzamos tus proyecciones con las líneas del casino
    df_valor_qb = pd.merge(
        proyecciones_qb, 
        df_lineas_qb, 
        on='player_name', 
        how='inner'
    )
    
    # Calculamos la diferencia matemática (Edge) usando la Mediana
    df_valor_qb['Diferencia (Edge)'] = df_valor_qb['Mediana_Yardas'] - df_valor_qb['Linea_Casino']
    
    # Limpiamos y ordenamos para mostrar las mejores oportunidades
    columnas_finales = ['player_name', 'Promedio_Yardas', 'Mediana_Yardas', 'Linea_Casino', 'Diferencia (Edge)']
    df_valor_qb = df_valor_qb[columnas_finales].sort_values('Diferencia (Edge)', ascending=False)
    
    st.dataframe(df_valor_qb, use_container_width=True)
    st.success("¡Líneas detectadas y analizadas! Busca los números más altos en el 'Edge'.")

st.markdown("---")
st.header("🚜 Proyecciones: Yardas Terrestres (Corredores)")

# 1. Filtramos solo a los Corredores (RB)
df_rbs = df_jugadores[df_jugadores['position'] == 'RB'].copy()

# 2. Agrupamos por jugador y calculamos basándonos en 'rushing_yards'
proyecciones_rb = df_rbs.groupby('player_name').agg(
    Partidos=('week', 'count'),
    Promedio_Yardas=('rushing_yards', 'mean'),
    Mediana_Yardas=('rushing_yards', 'median'),
    Max_Yardas=('rushing_yards', 'max')
).reset_index()

# 3. Limpiamos: Exigimos mínimo 5 partidos jugados para quedarnos con los titulares
proyecciones_rb = proyecciones_rb[proyecciones_rb['Partidos'] >= 5]

# 4. Redondeamos para mantener el formato limpio
proyecciones_rb['Promedio_Yardas'] = proyecciones_rb['Promedio_Yardas'].round(1)
proyecciones_rb['Mediana_Yardas'] = proyecciones_rb['Mediana_Yardas'].round(1)

# 5. Ordenamos a los corredores más dominantes hasta arriba
proyecciones_rb = proyecciones_rb.sort_values('Promedio_Yardas', ascending=False)

# Mostramos el ranking base en el Dashboard
st.dataframe(proyecciones_rb, use_container_width=True)

# 6. Conexión al casino para RBs
@st.cache_data(ttl=3600)
def obtener_lineas_props_rb():
    api_key = st.secrets["odds_api_key"]
    sport = "americanfootball_nfl"
    regions = "us" 
    markets = "player_rushing_yards" # <-- Mercado específico de corredores
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={api_key}&regions={regions}&markets={markets}"
    
    respuesta = requests.get(url)
    if respuesta.status_code != 200:
        return pd.DataFrame()
        
    datos = respuesta.json()
    filas = []
    for juego in datos:
        if not juego.get('bookmakers'):
            continue
        casino = juego['bookmakers'][0] 
        mercados = casino.get('markets', [])
        for m in mercados:
            if m['key'] == 'player_rushing_yards':
                for outcome in m['outcomes']:
                    if outcome['name'] == 'Over': 
                        filas.append({
                            'Jugador_API': outcome['description'],
                            'Linea_Casino': outcome['point']
                        })
                        
    df_lineas = pd.DataFrame(filas)
    if not df_lineas.empty:
        df_lineas = df_lineas.drop_duplicates(subset=['Jugador_API'])
    return df_lineas

with st.spinner("💸 Escaneando líneas terrestres en Las Vegas..."):
    df_lineas_rb = obtener_lineas_props_rb()
    
    if not df_lineas_rb.empty:
        st.subheader("🔥 Detector de Apuestas de Valor (Corredores)")
        
        # Traductor de nombres rápido (por si la tabla de QBs está vacía)
        def traducir_nombre_rb(nombre):
            partes = nombre.split(" ", 1)
            return f"{partes[0][0]}.{partes[1]}" if len(partes) > 1 else nombre
            
        df_lineas_rb['player_name'] = df_lineas_rb['Jugador_API'].apply(traducir_nombre_rb)
        
        # El cruce de datos
        df_valor_rb = pd.merge(proyecciones_rb, df_lineas_rb, on='player_name', how='inner')
        df_valor_rb['Diferencia (Edge)'] = df_valor_rb['Mediana_Yardas'] - df_valor_rb['Linea_Casino']
        
        columnas_finales = ['player_name', 'Promedio_Yardas', 'Mediana_Yardas', 'Linea_Casino', 'Diferencia (Edge)']
        df_valor_rb = df_valor_rb[columnas_finales].sort_values('Diferencia (Edge)', ascending=False)
        
        st.dataframe(df_valor_rb, use_container_width=True)
    else:
        st.info("Esperando a que los casinos liberen las líneas de corredores para la Semana 1...")

st.markdown("---")
st.header("👐 Proyecciones: Yardas por Recepción (Receptores y Alas Cerradas)")

# 1. Filtramos a los Receptores (WR) y Alas Cerradas (TE)
df_wrs = df_jugadores[df_jugadores['position'].isin(['WR', 'TE'])].copy()

# 2. Agrupamos por jugador calculando sus yardas de recepción
proyecciones_wr = df_wrs.groupby('player_name').agg(
    Partidos=('week', 'count'),
    Promedio_Yardas=('receiving_yards', 'mean'),
    Mediana_Yardas=('receiving_yards', 'median'),
    Max_Yardas=('receiving_yards', 'max')
).reset_index()

# 3. Exigimos mínimo 5 partidos jugados para filtrar ruido
proyecciones_wr = proyecciones_wr[proyecciones_wr['Partidos'] >= 5]

# 4. Limpiamos los decimales
proyecciones_wr['Promedio_Yardas'] = proyecciones_wr['Promedio_Yardas'].round(1)
proyecciones_wr['Mediana_Yardas'] = proyecciones_wr['Mediana_Yardas'].round(1)

# 5. Ordenamos a los líderes en yardas aéreas
proyecciones_wr = proyecciones_wr.sort_values('Promedio_Yardas', ascending=False)

st.dataframe(proyecciones_wr, use_container_width=True)

# 6. Conexión al casino para Receptores
@st.cache_data(ttl=3600)
def obtener_lineas_props_wr():
    api_key = st.secrets["odds_api_key"]
    sport = "americanfootball_nfl"
    regions = "us" 
    markets = "player_receiving_yards" # <-- Mercado específico de recepciones
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={api_key}&regions={regions}&markets={markets}"
    
    respuesta = requests.get(url)
    if respuesta.status_code != 200:
        return pd.DataFrame()
        
    datos = respuesta.json()
    filas = []
    for juego in datos:
        if not juego.get('bookmakers'):
            continue
        casino = juego['bookmakers'][0] 
        mercados = casino.get('markets', [])
        for m in mercados:
            if m['key'] == 'player_receiving_yards':
                for outcome in m['outcomes']:
                    if outcome['name'] == 'Over': 
                        filas.append({
                            'Jugador_API': outcome['description'],
                            'Linea_Casino': outcome['point']
                        })
                        
    df_lineas = pd.DataFrame(filas)
    if not df_lineas.empty:
        df_lineas = df_lineas.drop_duplicates(subset=['Jugador_API'])
    return df_lineas

with st.spinner("💸 Cazando líneas aéreas en Las Vegas..."):
    df_lineas_wr = obtener_lineas_props_wr()
    
    if not df_lineas_wr.empty:
        st.subheader("🔥 Detector de Apuestas de Valor (Receptores)")
        
        # Traductor de nombres para la tabla de receptores
        def traducir_nombre_wr(nombre):
            partes = nombre.split(" ", 1)
            return f"{partes[0][0]}.{partes[1]}" if len(partes) > 1 else nombre
            
        df_lineas_wr['player_name'] = df_lineas_wr['Jugador_API'].apply(traducir_nombre_wr)
        
        # Cruzamos las proyecciones contra la realidad del casino
        df_valor_wr = pd.merge(proyecciones_wr, df_lineas_wr, on='player_name', how='inner')
        df_valor_wr['Diferencia (Edge)'] = df_valor_wr['Mediana_Yardas'] - df_valor_wr['Linea_Casino']
        
        columnas_finales = ['player_name', 'Promedio_Yardas', 'Mediana_Yardas', 'Linea_Casino', 'Diferencia (Edge)']
        df_valor_wr = df_valor_wr[columnas_finales].sort_values('Diferencia (Edge)', ascending=False)
        
        st.dataframe(df_valor_wr, use_container_width=True)
    else:
        st.info("Esperando a que los casinos liberen las líneas de receptores para la Semana 1...")

st.markdown("---")
st.header("🗄️ Administración de Base de Datos")

def sincronizar_jugadores_nfl():
    try:
        # 1. Tu conexión clásica de XAMPP / Aiven
        conexion = mysql.connector.connect(
            host=st.secrets["host"],
            port=st.secrets["port"],
            user=st.secrets["user"],
            password=st.secrets["password"],
            database=st.secrets["database"]
        )
        cursor = conexion.cursor()
        
        with st.spinner("Inyectando el roster en MySQL..."):
            # Filtramos para tener un solo registro por jugador (el más reciente)
            roster = df_jugadores.sort_values('week').drop_duplicates(subset=['player_name'], keep='last')
            
            contador = 0
            # 2. Iteramos como en tu scraper.py
            for index, fila in roster.iterrows():
                query = """
                INSERT INTO nfl_jugadores (id_jugador, nombre, posicion, equipo_actual)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE equipo_actual=VALUES(equipo_actual)
                """
                # Usamos el formato "P.Mahomes" como ID y Nombre
                cursor.execute(query, (
                    fila['player_name'], 
                    fila['player_name'], 
                    fila['position'], 
                    fila['recent_team']
                ))
                contador += 1
                
            conexion.commit()
            st.success(f"✅ ¡Catálogo sincronizado! {contador} jugadores listos en DBeaver.")
            
    except Exception as e:
        st.error(f"🚨 Error de base de datos: {e}")
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conexion' in locals(): conexion.close()

if st.button("Sincronizar Catálogo de Jugadores (Roster)"):
    sincronizar_jugadores_nfl()