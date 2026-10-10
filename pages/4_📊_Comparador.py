import streamlit as st
from core.ui_comparador import render_comparison

st.set_page_config(page_title='Comparador de rendimiento',page_icon='📊',layout='wide')
render_comparison()
