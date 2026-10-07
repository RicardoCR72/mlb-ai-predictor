"""Presentación adaptable: sin ocultar campos ni cambiar cálculos."""
import streamlit as st

CSS='''<style>
@media(max-width:760px){
 .block-container{padding-left:.8rem!important;padding-right:.8rem!important;padding-top:.8rem!important}
 [data-testid="stHorizontalBlock"]{flex-direction:column!important;gap:.7rem!important}
 [data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important;min-width:0!important}
 [data-testid="stMetricValue"]{font-size:1.6rem!important;overflow-wrap:anywhere;white-space:normal!important}
 [data-testid="stMetricLabel"]{white-space:normal!important}
 [data-testid="stButton"] button,[data-testid="stDownloadButton"] button,[data-testid="stFormSubmitButton"] button{width:100%;min-height:44px}
 [data-testid="stRadio"] [role="radiogroup"]{flex-wrap:wrap!important;gap:.5rem!important}
 [data-baseweb="tab-list"]{overflow-x:auto!important;gap:.6rem!important}
 [data-baseweb="tab"]{min-height:44px!important;white-space:nowrap}
 .bankroll-shell{flex-direction:column;align-items:flex-start!important}
 .bankroll-status{line-height:1.5;overflow-wrap:anywhere}
 .oracle-pick{padding:.85rem!important}.oracle-pick h3{font-size:1.05rem!important}
 .oracle-values{grid-template-columns:repeat(2,minmax(0,1fr))!important}
 .oracle-values strong{overflow-wrap:anywhere}.oracle-selection{flex-wrap:wrap}
}
</style>'''


def apply_mobile_layout():
    st.markdown(CSS,unsafe_allow_html=True)
