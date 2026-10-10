import streamlit as st
from core.ui_inicio import render_home

st.set_page_config(page_title='Oráculo Sports AI', page_icon='◉', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
[data-testid="stAppViewContainer"]{background:radial-gradient(circle at 85% 0%,rgba(183,255,60,.06),transparent 30rem),#080c13;color:#eef3f8}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{background:#0d131d;border-right:1px solid #202938}
.oracle-brand{color:#b7ff3c;font-size:.75rem;letter-spacing:.15em;font-weight:800;margin-bottom:.5rem}
</style><div class="oracle-brand">ORÁCULO SPORTS AI</div>''', unsafe_allow_html=True)
st.title('Tu día deportivo')
render_home()
with st.sidebar:
    st.caption('MLB, NFL, Liga MX, Comparador y Bankroll')
