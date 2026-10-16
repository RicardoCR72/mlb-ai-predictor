import streamlit as st
import runpy
from pathlib import Path

st.set_page_config(page_title='Rendimiento',page_icon='📊',layout='wide')
view=runpy.run_path(str(Path(__file__).resolve().parents[1]/'core/ui_rendimiento_centro.py'),run_name='rendimiento_centro')
view['render_center']()
