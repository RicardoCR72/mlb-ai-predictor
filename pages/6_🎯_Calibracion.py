import streamlit as st
from pathlib import Path

st.set_page_config(page_title='Calibración', page_icon='🎯', layout='wide')
from core.ui_navegacion_movil import install_navigation
install_navigation()
from core.ui_diseno import apply_design
apply_design()
from core.ui_calibracion_centro import render_center
render_center()

