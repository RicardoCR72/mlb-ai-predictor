from core.ui_actualizacion import render_update_button
from core.ui_nfl_creditos import render_prediction_button
from pathlib import Path
import runpy

import streamlit as st


st.set_page_config(
    page_title="NFL Oráculo",
    page_icon="🏈",
    layout="wide",
)
from core.ui_navegacion_movil import install_navigation
install_navigation()
from core.ui_diseno import apply_design
apply_design()


from core.ui_diseno import render_sport_header
render_sport_header('NFL','🏈','Totales y props de jugadores')

vista = st.radio(
    "Sección NFL",
    ["🏈 Totales", "📊 Props de jugadores"],
    horizontal=True,
    format_func=lambda value: value.lstrip("🏈📊 "),
    label_visibility="collapsed",
    key="nfl_vista_principal",
)

raiz = Path(__file__).resolve().parents[1]

result_action,prediction_action=st.columns(2)
with result_action:
    render_update_button("nfl_totales" if vista == "🏈 Totales" else "nfl_props", compact=True)
with prediction_action:
    render_prediction_button()

if vista == "🏈 Totales":
    st.subheader('Totales NFL')
    runpy.run_path(
        str(raiz / "nfl" / "ui_totales.py"),
        run_name="nfl_totales_ui",
    )
else:
    runpy.run_path(
        str(raiz / "nfl" / "ui_props.py"),
        run_name="nfl_props_ui",
    )

