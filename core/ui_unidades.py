"""Conversión ilustrativa de simulaciones; nunca modifica la banca real."""
import streamlit as st
from core import bankroll as bank
from core.db import get_db_connection


@st.cache_data(ttl=60)
def load_unit():
    conn = None
    try:
        conn = get_db_connection()
        return bank.unit_value(conn)
    except Exception:
        return None
    finally:
        if conn is not None:
            conn.close()


def render_model_equivalence(staked, profit):
    value = load_unit()
    if value is None:
        st.caption('Para ver la equivalencia en pesos, configura el valor de 1 unidad en Bankroll → Portafolio.')
        return
    cols = st.columns(2)
    cols[0].metric('Importe simulado', f'${staked*value:,.2f} MXN', f'{staked:,.2f} u', delta_color='off')
    cols[1].metric('Beneficio simulado en pesos', f'${profit*value:+,.2f} MXN', f'{profit:+.2f} u', delta_color='off')
    st.caption(f'Conversión ilustrativa con 1 u = ${value:,.2f} MXN, configurado en Bankroll. '
               'No representa dinero apostado ni modifica el ROI del modelo.')
