import streamlit as st
from core.ui_confianza import render
st.set_page_config(page_title='Calibración de confianza',page_icon='📐',layout='wide')
from core.ui_navegacion_movil import install_navigation
install_navigation()
render()
