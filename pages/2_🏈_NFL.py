from pathlib import Path
import runpy

import streamlit as st


st.set_page_config(
    page_title="NFL Oráculo",
    page_icon="🏈",
    layout="wide",
)

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 85% 0%, rgba(183,255,60,.055), transparent 28rem),
            #080c13;
        color: #eef3f8;
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container {
        max-width: 1480px;
        padding-top: 1.15rem;
        padding-bottom: 2.5rem;
    }
    [data-testid="stSidebar"] {
        background: #0d131d;
        border-right: 1px solid #202938;
    }
    .nfl-shell {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #202938;
        border-radius: 13px;
        background: #111720;
        margin-bottom: .75rem;
    }
    .nfl-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .nfl-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #b7ff3c;
        color: #071006;
        font-weight: 900;
    }
    .nfl-accent { color: #b7ff3c; }
    .nfl-status { color: #8e99a9; font-size: .78rem; }
    div[role="radiogroup"] {
        display: flex;
        gap: .4rem;
        padding: .35rem;
        margin-bottom: .9rem;
        border: 1px solid #202938;
        border-radius: 11px;
        background: #0d131d;
    }
    div[role="radiogroup"] label {
        flex: 1;
        justify-content: center;
        padding: .42rem .7rem;
        border-radius: 8px;
    }
    div[role="radiogroup"] label:has(input:checked) {
        background: #b7ff3c;
        color: #071006;
        font-weight: 800;
    }
    .nfl-view-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: .9rem 0 1rem;
    }
    .nfl-eyebrow {
        color: #b7ff3c;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .12em;
    }
    .nfl-view-hero h1 {
        margin: .22rem 0 .15rem;
        color: #f5f8fb;
        font-size: clamp(1.75rem, 3vw, 2.45rem);
    }
    .nfl-subtitle { color: #8994a5; font-size: .88rem; }
    div[data-testid="stMetric"] {
        background: #111720;
        border: 1px solid #202938;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8994a5; }
    div[data-testid="stMetricValue"] { color: #f4f7fb; }
    div[data-baseweb="tab-list"] {
        gap: .3rem;
        border-bottom: 1px solid #202938;
    }
    button[data-baseweb="tab"] {
        color: #8994a5;
        border-radius: 8px 8px 0 0;
        padding-left: .85rem;
        padding-right: .85rem;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #071006;
        background: #b7ff3c;
        font-weight: 800;
    }
    button[data-baseweb="tab"][aria-selected="true"] p { color: #071006; }
    .stTabs [data-baseweb="tab-list"] {
        width: fit-content;
        padding: .32rem;
        border: 1px solid #202938;
        border-radius: 11px;
        background: #111720;
    }
    .stTabs [data-baseweb="tab"] {
        min-height: 2.55rem;
        border-radius: 8px;
        border: 0 !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: #b7ff3c !important;
        color: #071006 !important;
    }
    .stTabs button[role="tab"][aria-selected="true"] {
        background: #b7ff3c !important;
        color: #071006 !important;
        box-shadow: none !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: transparent !important;
    }
    div[data-testid="stTabs"] div[role="tablist"],
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        display: flex !important;
        width: fit-content !important;
        gap: .4rem !important;
        padding: .35rem !important;
        margin-bottom: .8rem !important;
        border: 1px solid #263143 !important;
        border-radius: 11px !important;
        background: #111720 !important;
        box-shadow: none !important;
    }
    div[data-testid="stTabs"] button[role="tab"],
    div[data-testid="stTabs"] [data-baseweb="tab"] {
        min-height: 2.55rem !important;
        padding: .42rem .8rem !important;
        border: 0 !important;
        border-radius: 8px !important;
        background: transparent !important;
        color: #d9e1eb !important;
        box-shadow: none !important;
    }
    div[data-testid="stTabs"] button[role="tab"] p,
    div[data-testid="stTabs"] [data-baseweb="tab"] p {
        color: inherit !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"],
    div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
        background: #b7ff3c !important;
        color: #071006 !important;
        font-weight: 850 !important;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
    div[data-testid="stTabs"] [data-baseweb="tab-border"],
    div[data-testid="stTabs"] div[role="tablist"]::after {
        display: none !important;
        background: transparent !important;
    }
    div[data-testid="stTabs"] button[role="tab"]::after {
        display: none !important;
        content: none !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    div[data-baseweb="select"] > div {
        min-height: 3rem !important;
        border: 1px solid #b7ff3c !important;
        border-radius: 10px !important;
        background: #111720 !important;
        color: #eef3f8 !important;
        box-shadow: 0 0 0 1px rgba(183,255,60,.08) !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover,
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within,
    div[data-baseweb="select"] > div:hover,
    div[data-baseweb="select"] > div:focus-within {
        border-color: #b7ff3c !important;
        box-shadow: 0 0 0 2px rgba(183,255,60,.18) !important;
    }
    div[data-baseweb="select"] svg { fill: #b7ff3c !important; }
    div[data-baseweb="popover"] ul,
    ul[role="listbox"] {
        padding: .35rem !important;
        border: 1px solid #b7ff3c !important;
        border-radius: 10px !important;
        background: #111720 !important;
        box-shadow: 0 12px 30px rgba(0,0,0,.35) !important;
    }
    [role="option"] {
        margin: .12rem 0 !important;
        border-radius: 7px !important;
        color: #dce4ee !important;
        background: transparent !important;
    }
    [role="option"]:hover,
    [role="option"][aria-selected="true"],
    [data-baseweb="option"]:hover,
    [data-baseweb="option"][aria-selected="true"] {
        color: #071006 !important;
        background: #b7ff3c !important;
        font-weight: 800 !important;
    }
    [data-testid="stDataFrame"] {
        border: 1px solid #202938;
        border-radius: 12px;
        overflow: hidden;
    }
    .stDownloadButton button, .stFormSubmitButton button {
        border-color: #b7ff3c;
        color: #b7ff3c;
        background: #101720;
    }
    @media (max-width: 700px) {
        .nfl-status { display: none; }
        .nfl-view-hero { align-items: flex-start; flex-direction: column; }
    }
    </style>
    <div class="nfl-shell">
        <div class="nfl-brand">
            <span class="nfl-logo">O</span>
            <span>ORACLE <span class="nfl-accent">NFL</span></span>
        </div>
        <div class="nfl-status">TOTALES · PROPS · LESIONES · RENDIMIENTO</div>
    </div>
    """,
    unsafe_allow_html=True,
)

vista = st.radio(
    "Sección NFL",
    ["🏈 Totales", "📊 Props de jugadores"],
    horizontal=True,
    label_visibility="collapsed",
    key="nfl_vista_principal",
)

raiz = Path(__file__).resolve().parents[1]

if vista == "🏈 Totales":
    st.markdown(
        """
        <div class="nfl-view-hero">
            <div>
                <div class="nfl-eyebrow">MODELO DE PARTIDO</div>
                <h1>Totales NFL</h1>
                <div class="nfl-subtitle">Over/Under, probabilidad calibrada, edge y valor esperado.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    runpy.run_path(
        str(raiz / "nfl" / "ui_totales.py"),
        run_name="nfl_totales_ui",
    )
else:
    runpy.run_path(
        str(raiz / "nfl" / "ui_props.py"),
        run_name="nfl_props_ui",
    )
