"""Presentación común; no modifica datos ni decisiones del modelo."""
import streamlit as st

CSS='''<style>
.stApp h1,.stApp .mlb-hero h1,.stApp .oracle-hero h1,.stApp .soccer-view-hero h1,.stApp .nfl-view-hero h1,.stApp .parlay-hero h1{
 font-size:2rem!important;line-height:1.2!important;font-weight:800!important;letter-spacing:-.035em!important;margin:.35rem 0!important;overflow-wrap:anywhere
}
.stApp .mlb-hero,.stApp .oracle-hero,.stApp .soccer-view-hero,.stApp .nfl-view-hero,.stApp .parlay-hero,.stApp .bankroll-hero{
 padding:1.15rem!important;border:1px solid #273245!important;border-radius:14px!important;background:#111720!important;margin:.6rem 0 1rem!important
}
.stApp .mlb-eyebrow,.stApp .oracle-eyebrow,.stApp .soccer-eyebrow,.stApp .nfl-eyebrow,.stApp .parlay-kicker,.stApp .bankroll-eyebrow{
 font-size:.72rem!important;letter-spacing:.12em!important;font-weight:800!important;color:#b7ff3c!important
}
.stApp .mlb-subtitle,.stApp .oracle-subtitle,.stApp .soccer-subtitle,.stApp .nfl-subtitle,.stApp .parlay-hero p,.stApp .bankroll-hero p{
 font-size:.94rem!important;line-height:1.5!important;color:#a8b4c5!important;margin:.4rem 0 0!important
}
.stApp [data-testid="stButton"] button,.stApp [data-testid="stDownloadButton"] button,.stApp [data-testid="stFormSubmitButton"] button,.stApp [data-testid="stPageLink"] a{
 background:#111720!important;color:#c6d1df!important;border:1px solid #45546a!important;border-radius:9px!important;min-height:44px; font-weight:650!important
}
.stApp [class*="st-key-actualizacion_manual_"] button,.stApp .st-key-nfl_predicciones_creditos button,.stApp .st-key-parlay_reload button,.stApp .st-key-comparison_refresh button,.stApp [data-testid="stButton"] button[kind="primary"],.stApp [data-testid="stFormSubmitButton"] button[kind="primary"]{
 background:#b7ff3c!important;color:#071006!important;border-color:#b7ff3c!important
}
.stApp [data-testid="stButton"] button:hover,.stApp [data-testid="stDownloadButton"] button:hover,.stApp [data-testid="stFormSubmitButton"] button:hover,.stApp [data-testid="stPageLink"] a:hover{
 background:#1a2535!important;color:#eef3f8!important;border-color:#b7ff3c!important
}
.stApp button:focus-visible,.stApp a:focus-visible{outline:2px solid #b7ff3c!important;outline-offset:3px}
.stApp [data-testid="stExpander"]{border-radius:12px!important;border-color:#273245!important}
.stApp .oracle-pick{min-height:19rem;background:#111720;border:1px solid #273245;border-top:3px solid #8994a5;border-radius:14px;padding:1rem;margin:.4rem 0;box-sizing:border-box}
.stApp .oracle-pick h3{min-height:2.8em;line-height:1.4}
.stApp .oracle-selection{min-height:3rem;align-items:flex-start}
.stApp .oracle-values{min-height:2.6rem}
.stApp .oracle-result{display:inline-flex;align-items:center;min-height:28px;padding:.2rem .6rem;border-radius:999px;background:#202b3b;color:#c6d1df;font-size:.76rem;max-width:100%;overflow-wrap:anywhere}
.stApp .oracle-result:empty{display:none}
.stApp .oracle-pick.won .oracle-result{background:#143529;color:#8aefb8}
.stApp .oracle-pick.lost .oracle-result{background:#3a2028;color:#ff9da5}
.stApp .oracle-pick.push .oracle-result{background:#352e1f;color:#f6d78e}
.stApp .oracle-pick.won{border-top-color:#6ee7a1}.stApp .oracle-pick.lost{border-top-color:#ff6b76}
.stApp .oracle-pick.pending{border-top-color:#8994a5}.stApp .oracle-pick.push{border-top-color:#f6c761}
@media(min-width:761px){
 .stApp [data-testid="stHorizontalBlock"]:has(.oracle-pick)>[data-testid="stColumn"]{display:flex;flex-direction:column}
 .stApp [data-testid="stColumn"]:has(.oracle-pick)>[data-testid="stVerticalBlock"]{height:100%}
 .stApp [data-testid="stColumn"] [data-testid="stElementContainer"]:has(.oracle-pick){flex:1;display:flex;flex-direction:column}
 .stApp [data-testid="stColumn"] [data-testid="stMarkdown"]:has(.oracle-pick),.stApp [data-testid="stColumn"] [data-testid="stMarkdownContainer"]:has(.oracle-pick){flex:1;display:flex;flex-direction:column}
 .stApp [data-testid="stColumn"] .oracle-pick{flex:1}
}
@media(max-width:760px){
 .stApp .block-container{padding:.65rem .8rem 1.4rem!important}
 .stApp [data-testid="stVerticalBlock"]{gap:.65rem!important}
 .stApp [data-testid="stHorizontalBlock"]{gap:.55rem!important}
 .stApp h1,.stApp .mlb-hero h1,.stApp .oracle-hero h1,.stApp .soccer-view-hero h1,.stApp .nfl-view-hero h1,.stApp .parlay-hero h1{font-size:1.65rem!important}
 .stApp h2{font-size:1.3rem!important;line-height:1.3!important;padding:.35rem 0!important}
 .stApp .mlb-hero,.stApp .oracle-hero,.stApp .soccer-view-hero,.stApp .nfl-view-hero,.stApp .parlay-hero,.stApp .bankroll-hero{padding:.85rem!important;margin:.4rem 0 .65rem!important}
 .stApp .oracle-pick{padding:.85rem!important;margin:.25rem 0;min-height:18rem}
 .stApp [data-testid="stRadio"] [role="radiogroup"]{margin-bottom:.5rem!important}
}
</style>'''


def apply_design():
    st.markdown(CSS,unsafe_allow_html=True)
