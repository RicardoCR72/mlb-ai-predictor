import streamlit as st
import pandas as pd
import mysql.connector
from tensorflow.keras.models import load_model
import joblib
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# 1. Configuración de la página web
st.set_page_config(page_title="MLB AI Dashboard V2", page_icon="🤖", layout="wide")
st.title("🤖 MLB Oráculo V2: Inteligencia Artificial")
st.markdown("Predicciones del mercado usando rachas y fatiga de la temporada 2026.")

# 2. Cargar la Inteligencia Artificial V2 (Nuevos archivos)
@st.cache_resource
def cargar_oraculo():
    try:
        modelo = load_model('cerebro_mlb_v2.keras')
        scaler = joblib.load('scaler_v2.pkl')
        columnas = joblib.load('columnas_entrenamiento_v2.pkl')
        return modelo, columnas, scaler
    except Exception as e:
        return None, None, None

def conectar_bd():
    return mysql.connector.connect(host="127.0.0.1", user="root", password="", database="sports_analytics")

# 3. Descargar cuotas de hoy y limpiar repetidos
@st.cache_data(ttl=60)
def cargar_datos_hoy():
    conexion = conectar_bd()
    consulta = """
        SELECT j.equipo_local AS 'Equipo Local', j.equipo_visitante AS 'Equipo Visitante',
               MAX(c.cuota_local) AS 'Paga Local', MAX(c.cuota_visitante) AS 'Paga Visitante'
        FROM juegos j
        JOIN cuotas_moneyline c ON j.id_juego = c.id_juego
        GROUP BY j.id_juego
    """
    df = pd.read_sql(consulta, conexion)
    conexion.close()
    
    if not df.empty:
        df = df.drop_duplicates(subset=['Equipo Local', 'Equipo Visitante'], keep='last').reset_index(drop=True)
    return df

# 4. EL MOTOR MATEMÁTICO: Calcular racha y fatiga en vivo
def obtener_estado_actual(equipo, df_hist):
    # Buscamos todos los juegos pasados de este equipo
    df_equipo = df_hist[(df_hist['equipo_local'] == equipo) | (df_hist['equipo_visitante'] == equipo)]
    if df_equipo.empty: return 0, 3 
    
    ultimo_juego = df_equipo.iloc[-1]
    fecha_ultimo = pd.to_datetime(ultimo_juego['fecha']).date()
    hoy = datetime.now().date()
    
    descanso = (hoy - fecha_ultimo).days
    
    # Ver si ganaron o perdieron su último partido
    if ultimo_juego['equipo_local'] == equipo:
        racha = ultimo_juego['racha_local']
        gano = ultimo_juego['marcador_local'] > ultimo_juego['marcador_visitante']
    else:
        racha = ultimo_juego['racha_visitante']
        gano = ultimo_juego['marcador_visitante'] > ultimo_juego['marcador_local']
        
    # Calcular nueva racha
    if gano:
        racha_actual = racha + 1 if racha > 0 else 1
    else:
        racha_actual = racha - 1 if racha < 0 else -1
        
    return racha_actual, descanso
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
          AND DATE(j.fecha) < CURDATE()  -- 🛡️ ESTO FILTRA Y EXCLUYE LOS PARTIDOS DE HOY Y DEL FUTURO
        GROUP BY j.id_juego
        ORDER BY j.fecha ASC
    """
    df = pd.read_sql(consulta, conexion)
    conexion.close()
    
    if not df.empty:
        df['solo_fecha'] = pd.to_datetime(df['fecha']).dt.date
        df = df.drop_duplicates(subset=['solo_fecha', 'Equipo Local', 'Equipo Visitante'], keep='last')
        df = df.drop(columns=['solo_fecha']).reset_index(drop=True)
        
    return df

# ---------------- FLUJO PRINCIPAL ----------------
df = cargar_datos_hoy()
modelo, columnas, scaler = cargar_oraculo()

if not df.empty and modelo is not None:
    st.success("✅ Oráculo V2 Conectado. Analizando rachas y fatiga...")
    
    # CREAMOS LAS PESTAÑAS AQUÍ
    tab1, tab2 = st.tabs(["🔮 Picks de Hoy", "💰 Tracker de ROI"])
    
    # Todo tu código de HOY va dentro de tab1
    with tab1:
        # 1. Cargamos la memoria y creamos la caja vacía 'resultados'
        df_hist = pd.read_csv('mlb_dataset_ia.csv')
        resultados = []
        
        # 2. El ciclo que recorre los partidos de hoy y le pregunta a la IA
        for i in range(len(df)):
            local = df.loc[i, 'Equipo Local']
            visita = df.loc[i, 'Equipo Visitante']
            
            racha_l, descanso_l = obtener_estado_actual(local, df_hist)
            racha_v, descanso_v = obtener_estado_actual(visita, df_hist)
            
            fila_ia = pd.DataFrame([{
                'equipo_local': local, 'equipo_visitante': visita,
                'racha_local': racha_l, 'racha_visitante': racha_v,
                'descanso_local': descanso_l, 'descanso_visitante': descanso_v
            }])
            
            equipos_encoded = pd.get_dummies(fila_ia[['equipo_local', 'equipo_visitante']])
            vars_escaladas = scaler.transform(fila_ia[['racha_local', 'racha_visitante', 'descanso_local', 'descanso_visitante']])
            df_num = pd.DataFrame(vars_escaladas, columns=['racha_local', 'racha_visitante', 'descanso_local', 'descanso_visitante'])
            
            X_hoy = pd.concat([equipos_encoded, df_num], axis=1)
            X_hoy = X_hoy.reindex(columns=columnas, fill_value=0)
            
            prob_local = modelo.predict(X_hoy, verbose=0)[0][0] * 100
            prob_visitante = 100 - prob_local
            
            favorito = local if prob_local > 50 else visita
            confianza = max(prob_local, prob_visitante)
            paga = df.loc[i, 'Paga Local'] if prob_local > 50 else df.loc[i, 'Paga Visitante']
            
            resultados.append({
                "Partido": f"{local} vs {visita}",
                "Pick de la IA": favorito,
                "Confianza (%)": round(confianza, 1),
                "Paga del Favorito": paga
            })
            
        # 3. Armamos el DataFrame de resultados ordenado
        df_resultados = pd.DataFrame(resultados).sort_values(by="Confianza (%)", ascending=False).reset_index(drop=True)
        
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
            st.dataframe(
                df_filtrado.style
                .bar(subset=['Confianza (%)'], color='#4CAF50', vmin=50, vmax=100)
                .format({"Confianza (%)": "{:.1f}%", "Paga del Favorito": "{:.2f}"}),
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
                registros_apuestas = []  # <--- CAJA NUEVA PARA GUARDAR EL HISTORIAL
                
                # Leemos partido por partido del historial de XAMPP
                for i in range(len(df_pasado)):
                    fecha_juego = df_pasado.loc[i, 'fecha']
                    local = df_pasado.loc[i, 'Equipo Local']
                    visita = df_pasado.loc[i, 'Equipo Visitante']
                    cuota_l = df_pasado.loc[i, 'Paga Local']
                    cuota_v = df_pasado.loc[i, 'Paga Visitante']
                    
                    # 1. Simular la predicción de la IA
                    racha_l, descanso_l = obtener_estado_actual(local, df_hist)
                    racha_v, descanso_v = obtener_estado_actual(visita, df_hist)
                    
                    fila_ia = pd.DataFrame([{'equipo_local': local, 'equipo_visitante': visita}])
                    equipos_encoded = pd.get_dummies(fila_ia)
                    
                    vars_escaladas = scaler.transform([[racha_l, racha_v, descanso_l, descanso_v]])
                    df_num = pd.DataFrame(vars_escaladas, columns=['racha_local', 'racha_visitante', 'descanso_local', 'descanso_visitante'])
                    
                    X_sim = pd.concat([equipos_encoded, df_num], axis=1).reindex(columns=columnas, fill_value=0)
                    prob_local = modelo.predict(X_sim, verbose=0)[0][0]
                    
                    prob_visitante = 1 - prob_local
                    confianza = max(prob_local, prob_visitante) * 100
                    
                    ia_pick_local = prob_local > 0.50
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
                st.area_chart(historial_banco, color="#4CAF50")
                
                # 4. TABLA HISTÓRICA DETALLADA DE APUESTAS
                st.markdown("---")
                st.markdown("#### 📋 Libro de Auditoría: Detalle de Apuestas Realizadas")
                if registros_apuestas:
                    df_tabla_apuestas = pd.DataFrame(registros_apuestas)
                    df_tabla_apuestas['Fecha'] = pd.to_datetime(df_tabla_apuestas['Fecha']).dt.date
                    st.dataframe(df_tabla_apuestas, use_container_width=True, hide_index=True)
                else:
                    st.info("Ningún partido supera el porcentaje de confianza seleccionado con el slider.")
                    
            else:
                st.info("Aún no hay suficientes juegos finalizados con cuotas guardadas en XAMPP para calcular el ROI.")
    
    # Procesar partido por partido
    for i in range(len(df)):
        local = df.loc[i, 'Equipo Local']
        visita = df.loc[i, 'Equipo Visitante']
        
        # 1. Preguntarle al motor matemático cómo vienen jugando
        racha_l, descanso_l = obtener_estado_actual(local, df_hist)
        racha_v, descanso_v = obtener_estado_actual(visita, df_hist)
        
        # 2. Armar el molde exacto para la IA
        fila_ia = pd.DataFrame([{
            'equipo_local': local, 'equipo_visitante': visita,
            'racha_local': racha_l, 'racha_visitante': racha_v,
            'descanso_local': descanso_l, 'descanso_visitante': descanso_v
        }])
        
        # Traducir equipos a 0s y 1s
        equipos_encoded = pd.get_dummies(fila_ia[['equipo_local', 'equipo_visitante']])
        
        # Escalar las rachas (comprimir entre 0 y 1 con el molde)
        vars_escaladas = scaler.transform(fila_ia[['racha_local', 'racha_visitante', 'descanso_local', 'descanso_visitante']])
        df_num = pd.DataFrame(vars_escaladas, columns=['racha_local', 'racha_visitante', 'descanso_local', 'descanso_visitante'])
        
        # Unir todo y asegurar que las columnas estén en el orden que la IA conoce
        X_hoy = pd.concat([equipos_encoded, df_num], axis=1)
        X_hoy = X_hoy.reindex(columns=columnas, fill_value=0)
        
        # 3. Lanzar la Predicción
        prob_local = modelo.predict(X_hoy, verbose=0)[0][0] * 100
        prob_visitante = 100 - prob_local
        
        favorito = local if prob_local > 50 else visita
        confianza = max(prob_local, prob_visitante)
        paga = df.loc[i, 'Paga Local'] if prob_local > 50 else df.loc[i, 'Paga Visitante']
        
        resultados.append({
            "Partido": f"{local} vs {visita}",
            "Pick de la IA": favorito,
            "Confianza (%)": round(confianza, 1),
            "Paga del Favorito": paga
        })
        
    df_resultados = pd.DataFrame(resultados).sort_values(by="Confianza (%)", ascending=False).reset_index(drop=True)
    
    st.markdown("---")
    st.markdown("### 🔥 El Pick Más Fuerte del Día")
    mejor_pick = df_resultados.loc[0]
    st.info(f"**{mejor_pick['Pick de la IA']}** ganando su partido de **{mejor_pick['Partido']}** (Confianza: {mejor_pick['Confianza (%)']:.1f}%) | Cuota: {mejor_pick['Paga del Favorito']:.2f}")
    
    st.markdown("---")
    st.markdown("### 📊 Tabla de Predicciones Generales")
    st.dataframe(
        df_resultados.style
        .bar(subset=['Confianza (%)'], color='#4CAF50', vmin=50, vmax=100)
        .format({"Confianza (%)": "{:.1f}%", "Paga del Favorito": "{:.2f}"}),
        use_container_width=True, hide_index=True
    )
else:
    st.error("⚠️ Faltan datos. Revisa XAMPP o los archivos del modelo.")
