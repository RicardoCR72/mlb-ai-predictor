import os
import streamlit as st
import pandas as pd
import numpy as np
import mysql.connector
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Input
import joblib
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo

warnings.filterwarnings('ignore')

ZONA_MX = ZoneInfo("America/Mazatlan")

def hoy_mx():
    return datetime.now(ZONA_MX).date()

st.set_page_config(page_title="MLB AI Dashboard V3.0", page_icon="🤖", layout="wide")
st.title("🤖 MLB Oráculo V3.0: Edge Matemático")
st.markdown("Predicciones del mercado usando rendimiento real, diferencial de carreras y cuotas desparasitadas.")

# ==========================================================
# 2. CARGAR LA INTELIGENCIA ARTIFICIAL V3.0
# ==========================================================
@st.cache_resource
def cargar_oraculo():
    try:
        # Arquitectura V3: Ahora recibe 10 variables continuas
        modelo = Sequential([
            Input(shape=(10,)), 
            Dense(32, activation='relu'),
            Dropout(0.2),
            Dense(16, activation='relu'),
            Dropout(0.2),
            Dense(1, activation='sigmoid')
        ])
        
        # Cargamos los nuevos pesos, scaler y la lista exacta de columnas
        modelo.load_weights('pesos_mlb_v3.weights.h5')
        scaler = joblib.load('scaler_v3.pkl')
        columnas_v3 = joblib.load('columnas_v3.pkl')
        
        return modelo, scaler, columnas_v3
    except Exception as e:
        st.error(f"Error cargando la IA V3.0: {e}")
        return None, None, None

def conectar_bd():
    return mysql.connector.connect(
        host=st.secrets["host"],
        port=st.secrets["port"],
        user=st.secrets["user"],
        password=st.secrets["password"],
        database=st.secrets["database"]
    )

MAPEO_EQUIPOS = {
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

def normalizar_equipo(nombre):
    return MAPEO_EQUIPOS.get(nombre, nombre)

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
    df = pd.read_sql(consulta, conexion, params=(hoy_mx(),))
    conexion.close()
    
    if not df.empty:
        df = df.drop_duplicates(subset=['Equipo Local', 'Equipo Visitante'], keep='last').reset_index(drop=True)
    return df

modelo, scaler, columnas_v3 = cargar_oraculo()

# 🌍 Diccionario de Zonas Horarias de la MLB (Diferencia respecto a UTC)
ZONAS_HORARIAS = {
    'ARI': -7, 'ATL': -5, 'BAL': -5, 'BOS': -5,
    'CHC': -6, 'CWS': -6, 'CIN': -5, 'CLE': -5,
    'COL': -7, 'DET': -5, 'HOU': -6, 'KC': -6,
    'LAA': -8, 'LAD': -8, 'MIA': -5, 'MIL': -6,
    'MIN': -6, 'NYM': -5, 'NYY': -5, 'OAK': -8,
    'PHI': -5, 'PIT': -5, 'SD': -8, 'SF': -8,
    'SEA': -8, 'STL': -6, 'TB': -5, 'TEX': -6,
    'TOR': -5, 'WSH': -5
}

def calcular_desgaste_viaje(equipo, fecha_actual, df_hist):
    """Calcula cuántas horas de huso horario cruzó el equipo en su juego más reciente."""
    df_equipo = df_hist[
        (df_hist['equipo_local'] == equipo) | (df_hist['equipo_visitante'] == equipo)
    ].sort_values('fecha', ascending=False)
    
    if df_equipo.empty:
        return 0 # Sin jetlag si no hay registro previo
        
    ultimo_juego = df_equipo.iloc[0]
    # Identificamos en qué estadio fue el juego anterior
    estadio_anterior = ultimo_juego['equipo_local']
    
    zona_anterior = ZONAS_HORARIAS.get(estadio_anterior, -5)
    zona_actual = ZONAS_HORARIAS.get(equipo, -5)
    
    # La diferencia absoluta de horas entre el viaje
    return abs(zona_actual - zona_anterior)

# ==========================================================
# 4. MOTOR MATEMÁTICO V3: Diferencial, Win% y Fatiga
# ==========================================================
def obtener_estado_actual(equipo, df_hist, fecha_objetivo=None):
    if fecha_objetivo is None:
        fecha_objetivo = hoy_mx()
    else:
        fecha_objetivo = pd.to_datetime(fecha_objetivo).date()
        
    df_hist_copy = df_hist.copy()
    df_hist_copy['fecha_solo_dia'] = pd.to_datetime(df_hist_copy['fecha']).dt.date
    
    # Filtramos la historia del equipo estrictamente ANTES del partido
    df_equipo = df_hist_copy[
        ((df_hist_copy['equipo_local'] == equipo) | (df_hist_copy['equipo_visitante'] == equipo)) & 
        (df_hist_copy['fecha_solo_dia'] < fecha_objetivo)
    ].sort_values('fecha_solo_dia')
    
    # Si es inicio de temporada y no hay historial, devolvemos valores neutrales
    if df_equipo.empty: 
        return 0.500, 0, 3, 0.5
    
    juegos_jugados = len(df_equipo)
    victorias = 0
    carreras_anotadas = 0
    carreras_recibidas = 0
    ultimos_5 = []
    
    for _, row in df_equipo.iterrows():
        es_local = row['equipo_local'] == equipo
        runs_fav = row['marcador_local'] if es_local else row['marcador_visitante']
        runs_con = row['marcador_visitante'] if es_local else row['marcador_local']
        
        carreras_anotadas += runs_fav
        carreras_recibidas += runs_con
        gano = 1 if runs_fav > runs_con else 0
        victorias += gano
        ultimos_5.append(gano)
        
    win_pct = victorias / juegos_jugados
    run_diff = carreras_anotadas - carreras_recibidas
    racha_5 = np.mean(ultimos_5[-5:]) if len(ultimos_5) > 0 else 0.5
    
    fecha_ultimo = df_equipo.iloc[-1]['fecha_solo_dia']
    descanso = (fecha_objetivo - fecha_ultimo).days
        
    return win_pct, run_diff, descanso, racha_5

def limpiar_cuotas_v3(cuota_l_raw, cuota_v_raw):
    """Convierte el formato de cuotas y remueve el overround de Las Vegas."""
    def to_decimal(val):
        if val <= -100: return (100 / abs(val)) + 1
        elif val >= 100: return (val / 100) + 1
        return val

    c_l = to_decimal(float(cuota_l_raw))
    c_v = to_decimal(float(cuota_v_raw))

    if c_l <= 1 or c_v <= 1:
        return 0.5, 0.5

    prob_l_cruda = 1 / c_l
    prob_v_cruda = 1 / c_v
    overround = prob_l_cruda + prob_v_cruda

    return prob_l_cruda / overround, prob_v_cruda / overround

@st.cache_data(ttl=300)
def cargar_lesiones_hoy():
    try:
        conexion = conectar_bd()
        hoy = hoy_mx().strftime('%Y-%m-%d')
        query = f"SELECT equipo, impacto_total FROM factor_lesiones WHERE fecha = '{hoy}'"
        df_les = pd.read_sql(query, conexion)
        conexion.close()
        return df_les
    except: return pd.DataFrame()

def aplicar_filtro_medico(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_lesiones):
    if df_lesiones.empty: return confianza_base
    imp_l = df_lesiones.loc[df_lesiones['equipo'] == equipo_local, 'impacto_total'].values
    imp_v = df_lesiones.loc[df_lesiones['equipo'] == equipo_visitante, 'impacto_total'].values
    impacto_local = imp_l[0] if len(imp_l) > 0 else 0
    impacto_visita = imp_v[0] if len(imp_v) > 0 else 0
    
    if equipo_elegido == equipo_local: ajuste = impacto_local - impacto_visita
    else: ajuste = impacto_visita - impacto_local
        
    confianza_final = confianza_base + ajuste
    if confianza_final > 99.0: confianza_final = 99.0
    if confianza_final < 50.1: confianza_final = 50.1
    return round(confianza_final, 1)

@st.cache_data(ttl=300)
def cargar_pitchers_hoy():
    try:
        conexion = conectar_bd()
        hoy = hoy_mx().strftime('%Y-%m-%d')
        query = f"SELECT equipo, nombre_pitcher, era FROM abridores WHERE fecha = '{hoy}'"
        df_pitchers = pd.read_sql(query, conexion)
        conexion.close()
        return df_pitchers
    except: return pd.DataFrame()

def aplicar_filtro_pitchers(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_pitchers):
    if df_pitchers.empty: return confianza_base, "TBD", "TBD"

    era_l = df_pitchers.loc[df_pitchers['equipo'] == equipo_local, 'era'].values
    era_v = df_pitchers.loc[df_pitchers['equipo'] == equipo_visitante, 'era'].values
    era_local = float(era_l[0]) if len(era_l) > 0 else 4.50
    era_visita = float(era_v[0]) if len(era_v) > 0 else 4.50

    nom_l = df_pitchers.loc[df_pitchers['equipo'] == equipo_local, 'nombre_pitcher'].values
    nom_v = df_pitchers.loc[df_pitchers['equipo'] == equipo_visitante, 'nombre_pitcher'].values
    pitcher_local = nom_l[0] if len(nom_l) > 0 else "Por anunciar"
    pitcher_visita = nom_v[0] if len(nom_v) > 0 else "Por anunciar"

    if equipo_elegido == equipo_local: ventaja = era_visita - era_local
    else: ventaja = era_local - era_visita
        
    ajuste = ventaja * 2.5
    confianza_final = confianza_base + ajuste
    
    if confianza_final > 99.0: confianza_final = 99.0
    if confianza_final < 50.1: confianza_final = 50.1
    return round(confianza_final, 1), f"{pitcher_local} ({era_local})", f"{pitcher_visita} ({era_visita})"

@st.cache_data(ttl=86400) 
def cargar_park_factor():
    try:
        conexion = conectar_bd()
        query = "SELECT equipo, factor FROM park_factor"
        df_estadios = pd.read_sql(query, conexion)
        conexion.close()
        return df_estadios
    except: return pd.DataFrame()

def aplicar_filtro_estadio(pick_totales, confianza_base, equipo_local, df_estadios):
    if df_estadios.empty: return confianza_base
    factor_row = df_estadios.loc[df_estadios['equipo'] == equipo_local, 'factor'].values
    factor = int(factor_row[0]) if len(factor_row) > 0 else 100
    ventaja_ofensiva = factor - 100
    ajuste = ventaja_ofensiva / 1.2
    
    pick_upper = str(pick_totales).upper()
    if "OVER" in pick_upper or "ALTAS" in pick_upper: confianza_final = confianza_base + ajuste
    elif "UNDER" in pick_upper or "BAJAS" in pick_upper: confianza_final = confianza_base - ajuste 
    else: confianza_final = confianza_base

    if confianza_final > 99.0: confianza_final = 99.0
    if confianza_final < 50.1: confianza_final = 50.1
    return round(confianza_final, 1)

@st.cache_data(ttl=300)
def fusionar_historiales(df_csv, df_xampp):
    df_memoria = df_csv.copy()
    if df_xampp.empty: return df_memoria
        
    df_xampp = df_xampp.sort_values(by='fecha').reset_index(drop=True)
    
    for i in range(len(df_xampp)):
        local = df_xampp.loc[i, 'Equipo Local']
        visita = df_xampp.loc[i, 'Equipo Visitante']
        fecha_juego = df_xampp.loc[i, 'fecha']
        marcador_l = df_xampp.loc[i, 'marcador_local']
        marcador_v = df_xampp.loc[i, 'marcador_visitante']
        
        nueva_fila = pd.DataFrame([{
            'fecha': fecha_juego, 'equipo_local': local, 'equipo_visitante': visita,
            'marcador_local': marcador_l, 'marcador_visitante': marcador_v,
        }])
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
        WHERE j.marcador_local IS NOT NULL AND DATE(j.fecha) < %s  
        GROUP BY j.id_juego ORDER BY j.fecha ASC
    """
    df = pd.read_sql(consulta, conexion, params=(hoy_mx(),))
    conexion.close()
    
    if not df.empty:
        df['solo_fecha'] = pd.to_datetime(df['fecha']).dt.date
        df = df.drop_duplicates(subset=['solo_fecha', 'Equipo Local', 'Equipo Visitante'], keep='last')
        df = df.drop(columns=['solo_fecha']).reset_index(drop=True)
    return df

# ---------------- FLUJO PRINCIPAL ----------------
df = cargar_datos_hoy()
if not df.empty:
    df = df.drop_duplicates(subset=['Equipo Local', 'Equipo Visitante']).reset_index(drop=True)

if not df.empty and modelo is not None:
    st.success("✅ Oráculo V3.0 Conectado. Analizando Diferencial de Carreras y Edge del Mercado...")
    
    df_csv_estatico = pd.read_csv('mlb_dataset_ia.csv')
    df_pasado = cargar_historial_xampp() 
    df_hist = fusionar_historiales(df_csv_estatico, df_pasado)
    df_lesiones_hoy = cargar_lesiones_hoy()
    
    tab1, tab2 = st.tabs(["🔮 Picks de Hoy", "💰 Tracker de ROI"])
    
    with tab1:
        resultados = []
        for i in range(len(df)):
            local_api = df.loc[i, 'Equipo Local']
            visita_api = df.loc[i, 'Equipo Visitante']
            
            # Normalizamos nombres para cruzar con el historial
            local = normalizar_equipo(local_api)
            visita = normalizar_equipo(visita_api)
            
            # 1. Traemos la matemática pura del historial
            w_l, d_l, desc_l, r5_l = obtener_estado_actual(local, df_hist)
            w_v, d_v, desc_v, r5_v = obtener_estado_actual(visita, df_hist)

            cuota_l_raw = df.loc[i, 'Paga Local']
            cuota_v_raw = df.loc[i, 'Paga Visitante']
            
            # 2. Desparasitamos las cuotas
            prob_p_l, prob_p_v = limpiar_cuotas_v3(cuota_l_raw, cuota_v_raw)

            # 3. Armamos la fila exactamente como la espera la IA V3
            fila_dic = {
                'win_pct_team': w_l, 'win_pct_opp': w_v,
                'run_diff_team': d_l, 'run_diff_opp': d_v,
                'dias_descanso_team': desc_l, 'dias_descanso_opp': desc_v,
                'racha_5_team': r5_l, 'racha_5_opp': r5_v,
                'prob_pure_team': prob_p_l, 'prob_pure_opp': prob_p_v
            }
            
            fila_ia = pd.DataFrame([fila_dic])
            fila_ia = fila_ia[columnas_v3] # Garantiza el orden de columnas exacto
            
            vars_escaladas = scaler.transform(fila_ia)
            prob_local = modelo.predict(vars_escaladas, verbose=0)[0][0] * 100
            prob_visitante = 100 - prob_local
            
            favorito = local_api if prob_local > 50 else visita_api
            confianza = max(prob_local, prob_visitante)
            paga = df.loc[i, 'Paga Local'] if prob_local > 50 else df.loc[i, 'Paga Visitante']

            df_lesiones_hoy = cargar_lesiones_hoy()
            df_pitchers_hoy = cargar_pitchers_hoy()
            df_estadios = cargar_park_factor()
            
            confianza_filtrada = aplicar_filtro_medico(favorito, confianza, local_api, visita_api, df_lesiones_hoy)
            confianza_final, p_local, p_visita = aplicar_filtro_pitchers(favorito, confianza_filtrada, local_api, visita_api, df_pitchers_hoy)

            # MÓDULO O/U
            era_l = df_pitchers_hoy.loc[df_pitchers_hoy['equipo'] == local_api, 'era'].values
            era_v = df_pitchers_hoy.loc[df_pitchers_hoy['equipo'] == visita_api, 'era'].values
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
            confianza_totales_final = aplicar_filtro_estadio(pick_totales, confianza_t_cruda, local_api, df_estadios)

            resultados.append({
                "Partido": f"{local_api} vs {visita_api}",
                "Abridores": f"{p_local} vs {p_visita}",
                "Pick de la IA": favorito,
                "Confianza (%)": confianza_final,
                "Pick Totales": pick_totales,
                "Confianza O/U (%)": confianza_totales_final,
                "Paga del Favorito": paga
            })
            
        df_resultados = pd.DataFrame(resultados)
        if df_resultados.empty:
            st.warning("📭 No se pudo generar ningún pick hoy.")
            st.stop()
            
        df_resultados = df_resultados.sort_values(by="Confianza (%)", ascending=False).reset_index(drop=True)
        
        st.markdown("---")
        st.markdown("### 🔥 El Pick Más Fuerte del Día")
        mejor_pick = df_resultados.loc[0]
        st.info(f"**{mejor_pick['Pick de la IA']}** ganando su partido de **{mejor_pick['Partido']}** (Confianza: {mejor_pick['Confianza (%)']:.1f}%) | Cuota: {mejor_pick['Paga del Favorito']:.2f}")
        
        st.markdown("---")
        st.markdown("### 📊 Tabla de Predicciones Generales")
        
        filtro_hoy = st.slider("Ocultar partidos basura. Mostrar solo confianza mayor a:", 50.0, 90.0, 74.0, 1.0, key="slider_hoy")
        df_filtrado = df_resultados[df_resultados['Confianza (%)'] >= filtro_hoy]
        
        if not df_filtrado.empty:
            st.dataframe(
                df_filtrado.style
                .bar(subset=['Confianza (%)', 'Confianza O/U (%)'], color='#4CAF50', vmin=50, vmax=100)
                .format({"Confianza (%)": "{:.1f}%", "Confianza O/U (%)": "{:.1f}%", "Paga del Favorito": "{:.2f}"}),
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("📉 El Oráculo ha hablado: Hoy no hay ningún partido que supere tu filtro de confianza.")
            
    with tab2:
        st.markdown("### 💵 Rendimiento Histórico de la IA (V3.0)")
        
        filtro_confianza = st.slider("Solo apostar si la confianza de la IA es mayor a:", 50.0, 90.0, 74.0, 1.0, key="slider_roi")
        df_pasado = cargar_historial_xampp()
        
        if not df_pasado.empty:
            apuestas_realizadas = 0   
            inversion_total = 0
            ganancia_neta = 0
            historial_banco = [0]
            registros_apuestas = []  
            
            for i in range(len(df_pasado)):
                fecha_juego = df_pasado.loc[i, 'fecha']
                local_api = df_pasado.loc[i, 'Equipo Local']
                visita_api = df_pasado.loc[i, 'Equipo Visitante']
                cuota_l_raw = df_pasado.loc[i, 'Paga Local']
                cuota_v_raw = df_pasado.loc[i, 'Paga Visitante']
                
                local = normalizar_equipo(local_api)
                visita = normalizar_equipo(visita_api)
                
                w_l, d_l, desc_l, r5_l = obtener_estado_actual(local, df_hist, fecha_objetivo=fecha_juego)
                w_v, d_v, desc_v, r5_v = obtener_estado_actual(visita, df_hist, fecha_objetivo=fecha_juego)
                
                prob_p_l, prob_p_v = limpiar_cuotas_v3(cuota_l_raw, cuota_v_raw)

                fila_dic = {
                    'win_pct_team': w_l, 'win_pct_opp': w_v,
                    'run_diff_team': d_l, 'run_diff_opp': d_v,
                    'dias_descanso_team': desc_l, 'dias_descanso_opp': desc_v,
                    'racha_5_team': r5_l, 'racha_5_opp': r5_v,
                    'prob_pure_team': prob_p_l, 'prob_pure_opp': prob_p_v
                }
                
                fila_ia = pd.DataFrame([fila_dic])
                fila_ia = fila_ia[columnas_v3]
                
                vars_escaladas = scaler.transform(fila_ia)
                prob_local_val = modelo.predict(vars_escaladas, verbose=0)[0][0]
                
                prob_visitante_val = 1 - prob_local_val
                confianza = max(prob_local_val, prob_visitante_val) * 100
                
                ia_pick_local = prob_local_val > 0.50
                favorito = local_api if ia_pick_local else visita_api
                cuota_favorito = cuota_l_raw if ia_pick_local else cuota_v_raw
                
                gano_local_real = df_pasado.loc[i, 'marcador_local'] > df_pasado.loc[i, 'marcador_visitante']
                
                if confianza >= filtro_confianza:
                    apuestas_realizadas += 1  
                    apuesta = 100
                    inversion_total += apuesta
                    
                    if ia_pick_local == gano_local_real:
                        ganancia = (apuesta * float(cuota_favorito)) - apuesta
                        ganancia_neta += ganancia
                        resultado_txt = "✅ Ganada"
                    else:
                        ganancia = -apuesta
                        ganancia_neta += ganancia
                        resultado_txt = "❌ Perdida"
                        
                    historial_banco.append(ganancia_neta)
                    
                    registros_apuestas.append({
                        "Fecha": fecha_juego,
                        "Partido": f"{local_api} vs {visita_api}",
                        "Pick de la IA": favorito,
                        "Confianza (%)": round(confianza, 1),
                        "Cuota": round(float(cuota_favorito), 2),
                        "Resultado": resultado_txt,
                        "Profit ($)": round(ganancia, 2)
                    })
            
            roi = (ganancia_neta / inversion_total) * 100 if inversion_total > 0 else 0
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Apuestas Realizadas", f"{apuestas_realizadas} de {len(df_pasado)}") 
            col2.metric("Inversión Simulada", f"${inversion_total:,.2f}")
            col3.metric("Profit Neto", f"${ganancia_neta:,.2f}", f"ROI: {roi:.2f}%")
            
            st.markdown("#### 📈 Crecimiento del Bankroll")
            if apuestas_realizadas > 0:
                st.area_chart(historial_banco, color="#4CAF50")
            else:
                st.warning("📉 Ningún partido histórico alcanzó esa confianza.")
            
            st.markdown("---")
            st.markdown("#### 📋 Libro de Auditoría: Detalle de Apuestas Realizadas")
            if registros_apuestas:
                df_tabla_apuestas = pd.DataFrame(registros_apuestas)
                df_tabla_apuestas['Fecha'] = pd.to_datetime(df_tabla_apuestas['Fecha']).dt.date
                st.dataframe(df_tabla_apuestas, use_container_width=True, hide_index=True)
        else:
            st.info("⏳ Aún no hay partidos terminados en la base de datos para generar el ROI histórico.")
else:
    if df.empty:
        st.error("🚨 ERROR DE DATOS: La base de datos de XAMPP no tiene juegos nuevos registrados para hoy.")
    elif modelo is None:
        st.error("🚨 ERROR DE IA: Faltan archivos de la V3.0.")