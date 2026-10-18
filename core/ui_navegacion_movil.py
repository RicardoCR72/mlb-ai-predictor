"""Ancla nativa para volver al inicio sin recargar la página."""
import streamlit as st


def install_navigation():
    from core.permisos import render_access
    render_access()
    st.markdown('''<style>
.oracle-page-top{height:0;scroll-margin-top:4rem}
.oracle-back-top{display:none}
@media(max-width:760px){
.oracle-back-top{display:inline-flex;position:fixed;right:.75rem;bottom:4.5rem;z-index:1000;align-items:center;gap:.35rem;min-height:44px;padding:.55rem .8rem;border:1px solid #b7ff3c;border-radius:12px;background:#111720;color:#b7ff3c!important;text-decoration:none;font-size:.82rem;font-weight:700;box-shadow:0 4px 18px #0006}
.oracle-back-top:focus-visible{outline:2px solid #b7ff3c;outline-offset:3px}
}
</style><div id="oracle-page-top" class="oracle-page-top"></div>
<a href="#oracle-page-top" target="_self" class="oracle-back-top" aria-label="Volver al inicio de esta página">↑ Volver arriba</a>''',unsafe_allow_html=True)
