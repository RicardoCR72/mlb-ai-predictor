"""Centro MLB; consultar una vista no genera ni guarda predicciones."""
import streamlit as st
from core.ui_diseno import apply_design,render_sport_header
from core.ui_navegacion_movil import install_navigation
from core.ui_actualizacion import render_update_button
from core.ui_historial_publicado import render_history
from core.ui_picks_guardados import render_mlb_today
st.set_page_config(page_title='MLB Oráculo',page_icon='⚾',layout='wide')
install_navigation();apply_design()
render_sport_header('MLB','⚾','Moneyline y totales')
view=st.radio('Sección MLB',['Picks de hoy','Totales','Rendimiento','Rendimiento Totales'],horizontal=True,key='mlb_section')
render_update_button('mlb')
from core.ui_trabajos import render_generate_mlb
render_generate_mlb()
if view=='Rendimiento':render_history('MLB','Moneyline',key='mlb_ml_perf')
elif view=='Rendimiento Totales':render_history('MLB','Totales',key='mlb_total_period')
else:render_mlb_today('Moneyline' if view=='Picks de hoy' else 'Totales')
