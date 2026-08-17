import os
import streamlit as st
import pandas as pd
import mysql.connector
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Input
import joblib
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo


warnings.filterwarnings('ignore')

# 🔧 CORRECCIÓN: Streamlit Cloud corre en UTC, pero tus datos se guardan
# con la fecha de México. Usamos esta zona horaria en vez de datetime.now()
# "a secas" para que "hoy" siempre coincida con tu fecha local.
ZONA_MX = ZoneInfo("America/Mazatlan")  # Misma zona que Durango (UTC-6 / UTC-7 en horario de verano)

def hoy_mx():
    """Regresa la fecha de hoy en la zona horaria de México, sin importar dónde corra el servidor."""
    return datetime.now(ZONA_MX).date()

# 1. Configuración de la página web
st.set_page_config(page_title="MLB AI Dashboard V2", page_icon="🤖", layout="wide")
st.title("🤖 MLB Oráculo V2: Inteligencia Artificial")
st.markdown("Predicciones del mercado usando rachas y fatiga de la temporada 2026.")

# 2. Cargar la Inteligencia Artificial V2
@st.cache_resource
def cargar_oraculo():
    try:
        # Recreamos la arquitectura exacta de este script (32 -> 16 -> 1 con input_shape=6)
        modelo = Sequential([
            Input(shape=(6,)), # ¡Son 6 variables de entrada, no 102!
            Dense(32, activation='relu'),
            Dropout(0.2),
            Dense(16, activation='relu'),
            Dropout(0.2),
            Dense(1, activation='sigmoid')
        ])
        
        # Cargamos los pesos limpios
        modelo.load_weights('pesos_mlb_v2.weights.h5')
        
        # Cargamos el scaler y el encoder de equipos
        scaler = joblib.load('scaler_v2.pkl')
        encoder = joblib.load('encoder_equipos.pkl')
        
        return modelo, scaler, encoder
    except Exception as e:
        st.error(f"Error real de Python cargando la IA: {e}")
        return None, None, None

def conectar_bd():
    return mysql.connector.connect(
        host=st.secrets["host"],
        port=st.secrets["port"],
        user=st.secrets["user"],
        password=st.secrets["password"],
        database=st.secrets["database"]
    )

# ==========================================================
# 🔧 CORRECCIÓN: Mapeo de nombres completos (BD) -> abreviaturas (encoder)
# ==========================================================
MAPEO_EQUIPOS = {
    'Arizona Diamondbacks': 'ARI',
    'Athletics': 'OAK',
    'Atlanta Braves': 'ATL',
    'Baltimore Orioles': 'BAL',
    'Boston Red Sox': 'BOS',
    'Chicago Cubs': 'CHC',
    'Chicago White Sox': 'CWS',
    'Cincinnati Reds': 'CIN',
    'Cleveland Guardians': 'CLE',
    'Colorado Rockies': 'COL',
    'Detroit Tigers': 'DET',
    'Houston Astros': 'HOU',
    'Kansas City Royals': 'KC',
    'Los Angeles Angels': 'LAA',
    'Los Angeles Dodgers': 'LAD',
    'Miami Marlins': 'MIA',
    'Milwaukee Brewers': 'MIL',
    'Minnesota Twins': 'MIN',
    'New York Mets': 'NYM',
    'New York Yankees': 'NYY',
    'Philadelphia Phillies': 'PHI',
    'Pittsburgh Pirates': 'PIT',
    'San Diego Padres': 'SD',
    'San Francisco Giants': 'SF',
    'Seattle Mariners': 'SEA',
    'St. Louis Cardinals': 'STL',
    'Tampa Bay Rays': 'TB',
    'Texas Rangers': 'TEX',
    'Toronto Blue Jays': 'TOR',
    'Washington Nationals': 'WSH',
}

def normalizar_equipo(nombre):
    """Convierte el nombre completo que viene de la BD a la abreviatura que conoce el encoder."""
    return MAPEO_EQUIPOS.get(nombre, nombre)

# 3. Descargar cuotas de hoy y limpiar repetidos
@st.cache_data(ttl=60)
def cargar_datos_hoy():
    conexion = conectar_bd()
    consulta = """
        SELECT j.equipo_local AS 'Equipo Local', j.equipo_visitante AS 'Equipo Visitante',
               MAX(c.cuota_local) AS 'Paga Local', MAX(c.cuota_visitante) AS 'Paga Visitante'
        FROM juegos j
        JOIN cuotas_moneyline c ON j.id_juego = c.id_juego
        WHERE j.marcador_local IS NULL AND DATE(j.fecha) >= %s
        GROUP BY j.id_juego
    """
    # 🔧 CORRECCIÓN: usamos la fecha de México calculada en Python en vez de
    # CURDATE() de MySQL, que puede depender de la zona horaria del servidor.
    df = pd.read_sql(consulta, conexion, params=(hoy_mx(),))
    conexion.close()
    
    if not df.empty:
        df = df.drop_duplicates(subset=['Equipo Local', 'Equipo Visitante'], keep='last').reset_index(drop=True)
    return df

modelo, scaler, encoder = cargar_oraculo()

# 4. EL MOTOR MATEMÁTICO: Calcular racha y fatiga en vivo (con viaje en el tiempo)
def obtener_estado_actual(equipo, df_hist, fecha_objetivo=None):
    # Si no le pasamos fecha, asume que es hoy (en zona horaria de México)
    if fecha_objetivo is None:
        fecha_objetivo = hoy_mx()
    else:
        # Convertimos la fecha que nos pasen a formato puro de fecha
        fecha_objetivo = pd.to_datetime(fecha_objetivo).date()
        
    df_hist_copy = df_hist.copy()
    df_hist_copy['fecha_solo_dia'] = pd.to_datetime(df_hist_copy['fecha']).dt.date
    
    # 🛡️ FILTRO TEMPORAL: Solo ver los juegos que pasaron ANTES de la fecha objetivo
    df_equipo = df_hist_copy[
        ((df_hist_copy['equipo_local'] == equipo) | (df_hist_copy['equipo_visitante'] == equipo)) & 
        (df_hist_copy['fecha_solo_dia'] < fecha_objetivo)
    ]
    
    if df_equipo.empty: return 0, 3 
    
    ultimo_juego = df_equipo.iloc[-1]
    fecha_ultimo = ultimo_juego['fecha_solo_dia']
    
    # Calculamos el descanso contra el día del partido, NO contra hoy
    descanso = (fecha_objetivo - fecha_ultimo).days
    
    if ultimo_juego['equipo_local'] == equipo:
        racha = ultimo_juego['racha_local']
        gano = ultimo_juego['marcador_local'] > ultimo_juego['marcador_visitante']
    else:
        racha = ultimo_juego['racha_visitante']
        gano = ultimo_juego['marcador_visitante'] > ultimo_juego['marcador_local']
        
    if gano:
        racha_actual = racha + 1 if racha > 0 else 1
    else:
        racha_actual = racha - 1 if racha < 0 else -1
        
    return racha_actual, descanso

# 🩺 Función para traer el reporte médico de hoy desde XAMPP
@st.cache_data(ttl=300)
def cargar_lesiones_hoy():
    try:
        conexion = conectar_bd()
        hoy = hoy_mx().strftime('%Y-%m-%d')
        query = f"SELECT equipo, impacto_total FROM factor_lesiones WHERE fecha = '{hoy}'"
        df_les = pd.read_sql(query, conexion)
        conexion.close()
        return df_les
    except Exception as e:
        return pd.DataFrame() # Si falla, regresa vacío para no romper el dashboard

# 🩺 El Filtro Médico que castiga la confianza
def aplicar_filtro_medico(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_lesiones):
    if df_lesiones.empty: return confianza_base
    
    # Buscamos cuántos puntos negativos tiene cada equipo (0 si están sanos)
    imp_l = df_lesiones.loc[df_lesiones['equipo'] == equipo_local, 'impacto_total'].values
    imp_v = df_lesiones.loc[df_lesiones['equipo'] == equipo_visitante, 'impacto_total'].values
    
    impacto_local = imp_l[0] if len(imp_l) > 0 else 0
    impacto_visita = imp_v[0] if len(imp_v) > 0 else 0
    
    # Calculamos la desventaja. 
    # Ej: Si Pick es Local (-5) y Visita tiene (0), la diferencia es -5.
    if equipo_elegido == equipo_local:
        ajuste = impacto_local - impacto_visita
    else:
        ajuste = impacto_visita - impacto_local
        
    # Aplicamos el castigo a la confianza (1 punto de lesión = 1% menos de confianza)
    confianza_final = confianza_base + ajuste
    
    # Evitamos que la IA enloquezca y de números ilógicos (mantenemos el % entre 50.1 y 99.9)
    if confianza_final > 99.0: confianza_final = 99.0
    if confianza_final < 50.1: confianza_final = 50.1
        
    return round(confianza_final, 1)

# ⚾ Función para traer los pitchers de hoy desde XAMPP
@st.cache_data(ttl=300)
def cargar_pitchers_hoy():
    try:
        conexion = conectar_bd()
        hoy = hoy_mx().strftime('%Y-%m-%d')
        query = f"SELECT equipo, nombre_pitcher, era FROM abridores WHERE fecha = '{hoy}'"
        df_pitchers = pd.read_sql(query, conexion)
        conexion.close()
        return df_pitchers
    except Exception as e:
        return pd.DataFrame()

# ⚾ El Filtro de Efectividad (ERA)
def aplicar_filtro_pitchers(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_pitchers):
    if df_pitchers.empty: return confianza_base, "TBD", "TBD"

    # Buscamos los ERAs
    era_l = df_pitchers.loc[df_pitchers['equipo'] == equipo_local, 'era'].values
    era_v = df_pitchers.loc[df_pitchers['equipo'] == equipo_visitante, 'era'].values
    
    # Si un equipo no tiene pitcher, usamos el 4.50 de salvavidas
    era_local = float(era_l[0]) if len(era_l) > 0 else 4.50
    era_visita = float(era_v[0]) if len(era_v) > 0 else 4.50

    # Extraemos los nombres
    nom_l = df_pitchers.loc[df_pitchers['equipo'] == equipo_local, 'nombre_pitcher'].values
    nom_v = df_pitchers.loc[df_pitchers['equipo'] == equipo_visitante, 'nombre_pitcher'].values
    pitcher_local = nom_l[0] if len(nom_l) > 0 else "Por anunciar"
    pitcher_visita = nom_v[0] if len(nom_v) > 0 else "Por anunciar"

    # Calculamos la ventaja (al ERA del rival le restamos el nuestro)
    if equipo_elegido == equipo_local:
        ventaja = era_visita - era_local
    else:
        ventaja = era_local - era_visita
        
    # Multiplicador: 1.00 de ventaja en ERA suma 2.5% de confianza
    ajuste = ventaja * 2.5
    confianza_final = confianza_base + ajuste
    
    # Límites lógicos para que el % no rompa la pantalla
    if confianza_final > 99.0: confianza_final = 99.0
    if confianza_final < 50.1: confianza_final = 50.1
        
    return round(confianza_final, 1), f"{pitcher_local} ({era_local})", f"{pitcher_visita} ({era_visita})"

# 🏟️ Función para traer el Park Factor desde XAMPP
@st.cache_data(ttl=86400) # Guardamos en caché por 24 horas para no saturar la BD
def cargar_park_factor():
    try:
        conexion = mysql.connector.connect(
            host="sports-analytics-rcabralrocha72-57db.h.aivencloud.com",
            port=26202,
            user="avnadmin",
            password="AVNS_rpZMsndwRZf6frZIM-w",
            database="defaultdb"
        )
        query = "SELECT equipo, factor FROM park_factor"
        df_estadios = pd.read_sql(query, conexion)
        conexion.close()
        return df_estadios
    except Exception as e:
        return pd.DataFrame()

# 🏟️ El Filtro del Estadio para los Totales (Over/Under)
def aplicar_filtro_estadio(pick_totales, confianza_base, equipo_local, df_estadios):
    if df_estadios.empty: return confianza_base
    
    # Buscamos el factor del estadio donde se juega (el local)
    factor_row = df_estadios.loc[df_estadios['equipo'] == equipo_local, 'factor'].values
    factor = int(factor_row[0]) if len(factor_row) > 0 else 100
    
    # Calculamos la diferencia respecto a un estadio neutral (100)
    # Ej: Colorado (114) -> +14. Seattle (91) -> -9.
    ventaja_ofensiva = factor - 100
    
    # Dividimos entre 2 para que el máximo bono sea +-7% (para no romper la matemática)
    ajuste = ventaja_ofensiva / 1.2
    
    # Verificamos si la IA eligió "Over" (Altas) o "Under" (Bajas)
    pick_upper = str(pick_totales).upper()
    
    if "OVER" in pick_upper or "ALTAS" in pick_upper:
        confianza_final = confianza_base + ajuste
    elif "UNDER" in pick_upper or "BAJAS" in pick_upper:
        confianza_final = confianza_base - ajuste # Restamos porque un estadio bateador arruina el Under
    else:
        confianza_final = confianza_base

    # Límites lógicos para que el % no rompa la pantalla
    if confianza_final > 99.0: confianza_final = 99.0
    if confianza_final < 50.1: confianza_final = 50.1
        
    return round(confianza_final, 1)

# 5. FUSIÓN DE MEMORIA: Unir el CSV viejo con los juegos nuevos de XAMPP
@st.cache_data(ttl=300)
def fusionar_historiales(df_csv, df_xampp):
    df_memoria = df_csv.copy()
    
    # Si la base de datos está vacía, regresamos el CSV intacto
    if df_xampp.empty:
        return df_memoria
        
    # Ordenamos los juegos de XAMPP del más viejo al más reciente
    df_xampp = df_xampp.sort_values(by='fecha').reset_index(drop=True)
    
    # Procesamos cada juego nuevo para calcularle su racha y sumarlo a la memoria
    for i in range(len(df_xampp)):
        local = df_xampp.loc[i, 'Equipo Local']
        visita = df_xampp.loc[i, 'Equipo Visitante']
        fecha_juego = df_xampp.loc[i, 'fecha']
        marcador_l = df_xampp.loc[i, 'marcador_local']
        marcador_v = df_xampp.loc[i, 'marcador_visitante']
        
        # Vemos cómo llegaban los equipos a ese juego específico
        racha_l, descanso_l = obtener_estado_actual(local, df_memoria, fecha_objetivo=fecha_juego)
        racha_v, descanso_v = obtener_estado_actual(visita, df_memoria, fecha_objetivo=fecha_juego)
        
        # Creamos la fila exactamente como la necesita la IA
        nueva_fila = pd.DataFrame([{
            'fecha': fecha_juego,
            'equipo_local': local,
            'equipo_visitante': visita,
            'marcador_local': marcador_l,
            'marcador_visitante': marcador_v,
            'racha_local': racha_l,
            'racha_visitante': racha_v
        }])
        
        # Inyectamos el juego a la memoria RAM
        df_memoria = pd.concat([df_memoria, nueva_fila], ignore_index=True)
        
    return df_memoria

@st.cache_data(ttl=300)
def cargar_historial_xampp():
    conexion = conectar_bd()
    consulta = """
        SELECT j.fecha, j.equipo_local AS 'Equipo Local', j.equipo_visitante AS 'Equipo Visitante',
               j.marcador_local, j.marcador_visitante,
               MAX(c.cuota_local) AS 'Paga Local', MAX(c.cuota_visitante) AS 'Paga Visitante'
        FROM juegos j
        JOIN cuotas_moneyline c ON j.id_juego = c.id_juego
        WHERE j.marcador_local IS NOT NULL 
          AND DATE(j.fecha) < %s  -- 🛡️ ESTO FILTRA Y EXCLUYE LOS PARTIDOS DE HOY Y DEL FUTURO
        GROUP BY j.id_juego
        ORDER BY j.fecha ASC
    """
    # 🔧 CORRECCIÓN: fecha de México en vez de CURDATE() del servidor MySQL.
    df = pd.read_sql(consulta, conexion, params=(hoy_mx(),))
    conexion.close()
    
    if not df.empty:
        df['solo_fecha'] = pd.to_datetime(df['fecha']).dt.date
        df = df.drop_duplicates(subset=['solo_fecha', 'Equipo Local', 'Equipo Visitante'], keep='last')
        df = df.drop(columns=['solo_fecha']).reset_index(drop=True)
        
    return df

# ---------------- FLUJO PRINCIPAL ----------------
df = cargar_datos_hoy()
# 🔧 CORRECCIÓN: se eliminó la llamada duplicada a cargar_oraculo() que
# desempaquetaba mal las variables (modelo, columnas, scaler) y terminaba
# asignando el ENCODER a la variable "scaler", rompiendo scaler.transform().
# Ya tenemos modelo, scaler y encoder cargados correctamente arriba.

# 🛡️ FILTRO ANTI-DUPLICADOS PARA HOY
if not df.empty:
    df = df.drop_duplicates(subset=['Equipo Local', 'Equipo Visitante']).reset_index(drop=True)

if not df.empty and modelo is not None:
    st.success("✅ Oráculo V2 Conectado. Analizando rachas y fatiga...")
    
    # 🧠 INICIALIZAR LA MEMORIA VIVA DE LA IA
    df_csv_estatico = pd.read_csv('mlb_dataset_ia.csv')
    df_pasado = cargar_historial_xampp() # Traemos el historial de XAMPP
    
    # Hacemos la fusión: CSV + XAMPP = Cerebro actualizado al día de hoy
    df_hist = fusionar_historiales(df_csv_estatico, df_pasado)
    df_lesiones_hoy = cargar_lesiones_hoy()
    
    # CREAMOS LAS PESTAÑAS
    tab1, tab2 = st.tabs(["🔮 Picks de Hoy", "💰 Tracker de ROI"])
    
    with tab1:
        resultados = []
        
        # 2. El ciclo que recorre los partidos de hoy y le pregunta a la IA
        for i in range(len(df)):
            local = df.loc[i, 'Equipo Local']
            visita = df.loc[i, 'Equipo Visitante']
            
            racha_l, descanso_l = obtener_estado_actual(local, df_hist)
            racha_v, descanso_v = obtener_estado_actual(visita, df_hist)

            # 🔧 CORRECCIÓN: normalizamos el nombre antes de pasarlo al encoder
            try:
                t_code = encoder.transform([normalizar_equipo(local)])[0]
                o_code = encoder.transform([normalizar_equipo(visita)])[0]
            except ValueError:
                st.warning(f"⚠️ Equipo no reconocido por el encoder: {local} / {visita}")
                continue

            cuota_l = df.loc[i, 'Paga Local']
            cuota_v = df.loc[i, 'Paga Visitante']

            fila_ia = pd.DataFrame([{
                'team_code': t_code,
                'opponent_code': o_code,
                'moneyLine': cuota_l,
                'oppMoneyLine': cuota_v,
                'dias_descanso': descanso_l,
                'racha_ultimos_5': racha_l
            }])

            vars_escaladas = scaler.transform(fila_ia)
            
            prob_local = modelo.predict(vars_escaladas, verbose=0)[0][0] * 100
            prob_visitante = 100 - prob_local
            
            fila_ia = pd.DataFrame([{
                'equipo_local': local, 'equipo_visitante': visita,
                'racha_local': racha_l, 'racha_visitante': racha_v,
                'descanso_local': descanso_l, 'descanso_visitante': descanso_v
            }])
            
            favorito = local if prob_local > 50 else visita
            confianza = max(prob_local, prob_visitante)
            paga = df.loc[i, 'Paga Local'] if prob_local > 50 else df.loc[i, 'Paga Visitante']

            # 🩺 CARGAMOS EL REPORTE MÉDICO DE HOY
            df_lesiones_hoy = cargar_lesiones_hoy()
            
            # ⚾ CARGAMOS LOS PITCHERS DE HOY
            df_pitchers_hoy = cargar_pitchers_hoy()
            df_estadios = cargar_park_factor()
            
            # 1. Pasamos la predicción por el departamento médico antes de guardarla
            confianza_filtrada = aplicar_filtro_medico(favorito, confianza, local, visita, df_lesiones_hoy)


            # 2. Filtro de Pitchers (Premia o castiga según el ERA)
            confianza_final, p_local, p_visita = aplicar_filtro_pitchers(favorito, confianza_filtrada, local, visita, df_pitchers_hoy)

            # ==========================================
            # ⚾ MÓDULO: PREDICCIÓN DE TOTALES (O/U)
            # ==========================================
            # Extraemos el ERA de los pitchers para sumar sus carreras esperadas
            era_l = df_pitchers_hoy.loc[df_pitchers_hoy['equipo'] == local, 'era'].values
            era_v = df_pitchers_hoy.loc[df_pitchers_hoy['equipo'] == visita, 'era'].values
            era_local = float(era_l[0]) if len(era_l) > 0 else 4.50
            era_visita = float(era_v[0]) if len(era_v) > 0 else 4.50
            
            carreras_esperadas = era_local + era_visita
            linea_promedio = 8.5 
            
            if carreras_esperadas > linea_promedio:
                pick_totales = "OVER (Altas)"
                confianza_t_cruda = 50.0 + ((carreras_esperadas - linea_promedio) * 8.5)
            else:
                pick_totales = "UNDER (Bajas)"
                confianza_t_cruda = 50.0 + ((linea_promedio - carreras_esperadas) * 8.5)
                
            if confianza_t_cruda > 95.0: confianza_t_cruda = 95.0
                
            # Filtro del Estadio
            confianza_totales_final = aplicar_filtro_estadio(pick_totales, confianza_t_cruda, local, df_estadios)

            # 3. GUARDADO FINAL UNIFICADO
            resultados.append({
                "Partido": f"{local} vs {visita}",
                "Abridores": f"{p_local} vs {p_visita}",
                "Pick de la IA": favorito,
                "Confianza (%)": confianza_final,
                "Pick Totales": pick_totales,
                "Confianza O/U (%)": confianza_totales_final,
                "Paga del Favorito": paga
            })
            
        # 3. Armamos el DataFrame de resultados ordenado por el Pick Ganador
        # 🔧 CORRECCIÓN: blindaje para no tronar si 'resultados' quedó vacío
        df_resultados = pd.DataFrame(resultados)
        if df_resultados.empty:
            st.warning("📭 No se pudo generar ningún pick hoy. Revisa que los nombres de equipo de la BD coincidan con el encoder (ver advertencias arriba).")
            st.stop()
        df_resultados = df_resultados.sort_values(by="Confianza (%)", ascending=False).reset_index(drop=True)
        
        # 4. Mostramos el Pick más fuerte
        st.markdown("---")
        st.markdown("### 🔥 El Pick Más Fuerte del Día")
        mejor_pick = df_resultados.loc[0]
        st.info(f"**{mejor_pick['Pick de la IA']}** ganando su partido de **{mejor_pick['Partido']}** (Confianza: {mejor_pick['Confianza (%)']:.1f}%) | Cuota: {mejor_pick['Paga del Favorito']:.2f}")
        
        # 5. Tabla general con su slider independiente de filtrado
        st.markdown("---")
        st.markdown("### 📊 Tabla de Predicciones Generales")
        
        filtro_hoy = st.slider(
            "Ocultar partidos basura. Mostrar solo confianza mayor a:", 
            min_value=50.0, max_value=90.0, value=74.0, step=1.0,
            key="slider_hoy"
        )
        
        df_filtrado = df_resultados[df_resultados['Confianza (%)'] >= filtro_hoy]
        
        if not df_filtrado.empty:
            # Pintamos las barras de ambas columnas de confianza
            st.dataframe(
                df_filtrado.style
                .bar(subset=['Confianza (%)', 'Confianza O/U (%)'], color='#4CAF50', vmin=50, vmax=100)
                .format({"Confianza (%)": "{:.1f}%", "Confianza O/U (%)": "{:.1f}%", "Paga del Favorito": "{:.2f}"}),
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("📉 El Oráculo ha hablado: Hoy no hay ningún partido que supere tu filtro de confianza. ¡Es mejor guardar el dinero y no apostar!")
            
    with tab2:
        st.markdown("### 💵 Rendimiento Histórico de la IA")
        
        # Slider de control de confianza
        filtro_confianza = st.slider(
            "Solo apostar si la confianza de la IA es mayor a:", 
            min_value=50.0, max_value=90.0, value=74.0, step=1.0,
            key="slider_roi"
        )
        
        df_pasado = cargar_historial_xampp()
        
        if not df_pasado.empty:
            apuestas_realizadas = 0   
            inversion_total = 0
            ganancia_neta = 0
            historial_banco = [0]
            registros_apuestas = []  
            
            # Leemos partido por partido del historial de XAMPP
            for i in range(len(df_pasado)):
                fecha_juego = df_pasado.loc[i, 'fecha']
                local = df_pasado.loc[i, 'Equipo Local']
                visita = df_pasado.loc[i, 'Equipo Visitante']
                cuota_l = df_pasado.loc[i, 'Paga Local']
                cuota_v = df_pasado.loc[i, 'Paga Visitante']
                
                # 1. Simular la predicción de la IA
                # 🔧 CORRECCIÓN CRÍTICA: ¡Le pasamos la fecha exacta del juego pasado!
                racha_l, descanso_l = obtener_estado_actual(local, df_hist, fecha_objetivo=fecha_juego)
                racha_v, descanso_v = obtener_estado_actual(visita, df_hist, fecha_objetivo=fecha_juego)

                # Normalizamos el nombre antes de pasarlo al encoder
                try:
                    t_code = encoder.transform([normalizar_equipo(local)])[0]
                    o_code = encoder.transform([normalizar_equipo(visita)])[0]
                except ValueError:
                    # 🚨 Aviso tipo pop-up si un equipo nos rompe la simulación
                    st.toast(f"Equipo ignorado en historial: {local} o {visita}")
                    continue

                fila_ia = pd.DataFrame([{
                    'team_code': t_code,
                    'opponent_code': o_code,
                    'moneyLine': cuota_l,
                    'oppMoneyLine': cuota_v,
                    'dias_descanso': descanso_l,
                    'racha_ultimos_5': racha_l
                }])

                vars_escaladas = scaler.transform(fila_ia)
                prob_local_val = modelo.predict(vars_escaladas, verbose=0)[0][0]
                
                prob_visitante_val = 1 - prob_local_val
                confianza = max(prob_local_val, prob_visitante_val) * 100
                
                ia_pick_local = prob_local_val > 0.50
                favorito = local if ia_pick_local else visita
                cuota_favorito = cuota_l if ia_pick_local else cuota_v
                
                gano_local_real = df_pasado.loc[i, 'marcador_local'] > df_pasado.loc[i, 'marcador_visitante']
                
                # 2. Aplicar el filtro del Slider
                if confianza >= filtro_confianza:
                    apuestas_realizadas += 1  
                    apuesta = 100
                    inversion_total += apuesta
                    
                    if ia_pick_local == gano_local_real:
                        ganancia = (apuesta * cuota_favorito) - apuesta
                        ganancia_neta += ganancia
                        resultado_txt = "✅ Ganada"
                    else:
                        ganancia = -apuesta
                        ganancia_neta += ganancia
                        resultado_txt = "❌ Perdida"
                        
                    historial_banco.append(ganancia_neta)
                    
                    # Guardamos los detalles de esta apuesta para la tabla
                    registros_apuestas.append({
                        "Fecha": fecha_juego,
                        "Partido": f"{local} vs {visita}",
                        "Pick de la IA": favorito,
                        "Confianza (%)": round(confianza, 1),
                        "Cuota": round(cuota_favorito, 2),
                        "Resultado": resultado_txt,
                        "Profit ($)": round(ganancia, 2)
                    })
            
            # 3. Mostrar Métricas Financieras Superiores
            roi = (ganancia_neta / inversion_total) * 100 if inversion_total > 0 else 0
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Apuestas Realizadas", f"{apuestas_realizadas} de {len(df_pasado)}") 
            col2.metric("Inversión Simulada", f"${inversion_total:,.2f}")
            col3.metric("Profit Neto", f"${ganancia_neta:,.2f}", f"ROI: {roi:.2f}%")
            
            st.markdown("#### 📈 Crecimiento del Bankroll")
            # 🛡️ PROTECCIÓN: Aseguramos que la gráfica exista validando los puntos de datos
            if apuestas_realizadas > 0:
                st.area_chart(historial_banco, color="#4CAF50")
            else:
                st.warning("📉 Ningún partido histórico alcanzó esa confianza. ¡Baja el filtro del slider para ver la gráfica!")
            
            # 4. TABLA HISTÓRICA DETALLADA DE APUESTAS
            st.markdown("---")
            st.markdown("#### 📋 Libro de Auditoría: Detalle de Apuestas Realizadas")
            if registros_apuestas:
                df_tabla_apuestas = pd.DataFrame(registros_apuestas)
                df_tabla_apuestas['Fecha'] = pd.to_datetime(df_tabla_apuestas['Fecha']).dt.date
                st.dataframe(df_tabla_apuestas, use_container_width=True, hide_index=True)
        else:
            # 🛡️ PROTECCIÓN: Por si la BD de XAMPP no nos arroja historiales aún
            st.info("⏳ Aún no hay partidos terminados en la base de datos para generar el ROI histórico.")
else:
    if df.empty:
        st.error("🚨 ERROR DE DATOS: La base de datos de XAMPP no tiene juegos nuevos registrados para hoy. El scraper no corrió o falló.")
    elif modelo is None:
        st.error("🚨 ERROR DE IA: No se encontraron los archivos 'cerebro_mlb_v2.keras' o los '.pkl' en esta carpeta.")
    else:
        st.error("🚨 Error desconocido.")