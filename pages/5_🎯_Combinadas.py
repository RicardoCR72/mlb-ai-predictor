import streamlit as st
from core.ui_combinadas_vista import render_combinations

st.set_page_config(page_title='Combinadas por confianza',page_icon='🎯',layout='wide')
from core.ui_diseno import apply_design
apply_design()

render_combinations()
