"""Presentación adaptable: sin ocultar campos ni cambiar cálculos."""
import streamlit as st

CSS='''<style>
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button,[data-testid="stFormSubmitButton"] button,[data-testid="stPageLink"] a{
 border:1px solid #b7ff3c!important;border-radius:9px!important;background:#111720!important;color:#b7ff3c!important;font-weight:800!important;min-height:44px
}
[data-testid="stButton"] button:hover,[data-testid="stDownloadButton"] button:hover,[data-testid="stFormSubmitButton"] button:hover,[data-testid="stPageLink"] a:hover{
 background:#b7ff3c!important;color:#071006!important
}
[data-testid="stButton"] button:focus-visible,[data-testid="stDownloadButton"] button:focus-visible,[data-testid="stFormSubmitButton"] button:focus-visible,[data-testid="stPageLink"] a:focus-visible{
 outline:2px solid #b7ff3c!important;outline-offset:3px
}
[data-testid="stButton"] button:disabled,[data-testid="stDownloadButton"] button:disabled,[data-testid="stFormSubmitButton"] button:disabled{opacity:.5}
.block-container{max-width:1450px;padding-bottom:2rem}
h1{letter-spacing:-.035em}h2,h3{letter-spacing:-.02em}
[data-testid="stMetric"]{border:1px solid #263143;border-radius:12px;padding:.65rem .8rem;background:#111720}
[data-testid="stRadio"] [role="radiogroup"]{display:flex;gap:.4rem;width:fit-content;max-width:100%;padding:.35rem;margin-bottom:1rem;border:1px solid #202938;border-radius:11px;background:#0d131d}
[data-testid="stRadio"] [role="radiogroup"] label{flex:1;justify-content:center;padding:.42rem .8rem;border-radius:8px}
[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked){background:#b7ff3c;color:#071006;font-weight:850}
@media(max-width:760px){
 .block-container{padding-left:.8rem!important;padding-right:.8rem!important;padding-top:.8rem!important}
 [data-testid="stHorizontalBlock"]{flex-direction:column!important;gap:.7rem!important}
 [data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important;min-width:0!important}
 [data-testid="stMetricValue"]{font-size:1.6rem!important;overflow-wrap:anywhere;white-space:normal!important}
 [data-testid="stMetricLabel"]{white-space:normal!important}
 [data-testid="stButton"] button,[data-testid="stDownloadButton"] button,[data-testid="stFormSubmitButton"] button,[data-testid="stPageLink"] a{width:100%;min-height:44px}
 [data-testid="stRadio"] [role="radiogroup"]{flex-wrap:wrap!important;gap:.5rem!important}
 [data-baseweb="tab-list"]{overflow-x:auto!important;gap:.6rem!important}
 [data-baseweb="tab"]{min-height:44px!important;white-space:nowrap}
 .bankroll-shell{flex-direction:column;align-items:flex-start!important}
 .bankroll-status{line-height:1.5;overflow-wrap:anywhere}
 .oracle-pick{padding:.85rem!important}.oracle-pick h3{font-size:1.05rem!important}
 .oracle-values{grid-template-columns:repeat(2,minmax(0,1fr))!important}
 [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]):not(:has([data-testid="stVerticalBlockBorderWrapper"])):not(:has([data-testid="stVerticalBlock"][data-border="true"])):not(:has([data-testid="stVerticalBlock"] [data-testid="stPageLink"])){display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem!important}
 [data-testid="stMetric"]{padding:.5rem .6rem}
 .oracle-details summary{min-height:44px;display:flex;align-items:center}
 .oracle-detail{flex-direction:column;gap:.15rem}.oracle-detail strong{text-align:left}
 .oracle-values strong{overflow-wrap:anywhere}.oracle-selection{flex-wrap:wrap}
}
</style>'''


def apply_mobile_layout():
    st.markdown(CSS,unsafe_allow_html=True)
