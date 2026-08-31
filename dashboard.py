import streamlit as st

st.set_page_config(
    page_title="Oráculo AI Hub",
    page_icon="🧠",
    layout="centered"
    
)



st.title("🧠 Bienvenido al Oráculo AI Hub")
st.markdown("---")

pg = st.navigation([
    st.Page("pages/1_⚾_MLB.py", title="MLB Oráculo", icon="⚾"),
    st.Page("pages/2_🏈_NFL.py", title="NFL Oráculo", icon="🏈"),
])

pg.run()

st.markdown("""
### Selecciona tu Mercado en el Menú Lateral 👈

Este es el panel central de operaciones predictivas.
*   **⚾ MLB (V4.0):** Modelo de predicción de béisbol activo. (En periodo de cuarentena validando ROI).
*   **🏈 NFL (V1.0):** [ EN DESARROLLO ] Construyendo el motor de Spreads, Totales y Player Props para la Semana 1.

*Sistema operando con bases de datos aisladas para máxima seguridad.*
""")