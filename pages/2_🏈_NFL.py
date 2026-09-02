import streamlit as st
import nfl_data_py as nfl
import pandas as pd

st.title("🏈 NFL Oráculo V1.0: Spreads & Props")
st.markdown("---")

st.subheader("📅 Calendario Semana 1 - Temporada 2026")

# Usamos caché para que no se tarde en cargar cada vez que cambias de página
@st.cache_data
def cargar_calendario():
    # Extraemos el calendario completo del 2026
    schedules = nfl.import_schedules([2026])
    
    # Filtramos para que solo nos traiga la Semana 1 de Temporada Regular ('REG')
    semana1 = schedules[(schedules['week'] == 1) & (schedules['game_type'] == 'REG')]
    
    # Nos quedamos con las columnas clave para no saturar la pantalla
    columnas_clave = ['game_id', 'gameday', 'gametime', 'away_team', 'home_team']
    df_limpio = semana1[columnas_clave].copy()
    
    # Renombramos las columnas al español para el dashboard
    df_limpio.columns = ['ID Juego', 'Fecha', 'Hora', 'Visita', 'Local']
    
    return df_limpio

# Agregamos un spinner visual mientras descarga los datos
with st.spinner("🏈 Descargando bases de datos de la NFL..."):
    df_semana1 = cargar_calendario()
    # Mostramos la tabla en toda la pantalla
    st.dataframe(df_semana1, use_container_width=True)

st.success(f"¡Conexión exitosa! Se encontraron {len(df_semana1)} partidos para la Semana 1.")