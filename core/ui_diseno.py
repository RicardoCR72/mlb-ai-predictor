"""Tokens y componentes comunes: assets/ui.css es la fuente visual única."""
from pathlib import Path
from html import escape
import streamlit as st
def get_css():
    return '<style>'+(Path(__file__).resolve().parents[1]/'assets/ui.css').read_text(encoding='utf-8', errors='replace')+'</style>'

CSS = get_css()

def apply_design():
    st.markdown(get_css(), unsafe_allow_html=True)

def render_sport_header(name,icon,description):
    st.markdown(f'<div class="oracle-sport-header"><h1>{escape(icon)} {escape(name)}</h1><p>{escape(description)}</p></div>',unsafe_allow_html=True)
