import streamlit as st
from core.ui_combinadas import render_combinations

st.set_page_config(page_title='Combinadas por confianza',page_icon='🎯',layout='wide')
render_combinations()
