import streamlit as st
import runpy
from pathlib import Path

st.set_page_config(page_title='Comparador de rendimiento',page_icon='📊',layout='wide')
view=runpy.run_path(str(Path(__file__).resolve().parents[1]/'core/ui_comparador.py'),run_name='comparador_ui')
view['render_comparison']()
