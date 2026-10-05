import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import streamlit as st
import uuid
from zoneinfo import ZoneInfo
from core import bankroll as bank
from core.db import get_db_connection

st.set_page_config(
    page_title="Gestión de Banca y Kelly",
    page_icon="💼",
    layout="wide",
)

RAIZ = Path(__file__).resolve().parents[1]

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
    .bankroll-shell {
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
    .bankroll-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .bankroll-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #b7ff3c;
        color: #071006;
        font-weight: 900;
    }
    .bankroll-accent { color: #b7ff3c; }
    .bankroll-status { color: #8e99a9; font-size: .78rem; font-weight: 700; }
    div[data-testid="stMetric"] {
        background: #111720;
        border: 1px solid #202938;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8994a5; }
    div[data-testid="stMetricValue"] { color: #f4f7fb; }
    .kelly-box {
        padding: 1.4rem;
        border: 1px solid #253044;
        border-radius: 16px;
        background: linear-gradient(145deg, #111722, #0d131d);
        margin-bottom: 1.2rem;
    }
    .badge-pos {
        background: rgba(183, 255, 60, 0.12);
        color: #b7ff3c;
        padding: 0.3rem 0.7rem;
        border-radius: 999px;
        border: 1px solid rgba(183, 255, 60, 0.4);
        font-weight: 800;
        font-size: 0.85rem;
    }
    .badge-neg {
        background: rgba(255, 75, 75, 0.12);
        color: #ff4b4b;
        padding: 0.3rem 0.7rem;
        border-radius: 999px;
        border: 1px solid rgba(255, 75, 75, 0.4);
        font-weight: 800;
        font-size: 0.85rem;
    }
    </style>
    <div class="bankroll-shell">
        <div class="bankroll-brand">
            <span class="bankroll-logo">💼</span>
            <span>PORTAFOLIO & <span class="bankroll-accent">GESTIÓN DE BANCA</span></span>
        </div>
        <div class="bankroll-status">CRITERIO DE KELLY · ROI AUDITADO · GESTIÓN DE RIESGO</div>
    </div>
    """,
    unsafe_allow_html=True,
)

def render_app(conn, ledger, initial):
    stats = bank.metrics(ledger, initial)
    tab1, tab2, tab3 = st.tabs(["🧮 Calculadora Kelly & EV", "📈 Portafolio", "📝 Registrar / Gestionar"])
    with tab1:
        bankroll = st.number_input("Banca disponible ($)", min_value=0.0,
                                  value=max(0.0, stats['disponible']), step=100.0)
        p = st.slider("Probabilidad estimada (%)", 1.0, 99.0, 58.0, 0.5) / 100
        format_odds = st.selectbox("Formato de cuota", ["Decimal", "Americana"])
        odds = 1.0
        if format_odds == "Decimal":
            odds = st.number_input("Cuota decimal", min_value=1.01, value=1.95, step=0.05)
        else:
            american = st.number_input("Momio americano", value=-110, step=5)
            try: odds = bank.decimal_odds(american)
            except ValueError as exc: st.warning(str(exc))
        fraction = st.select_slider("Fracción de Kelly", options=[0.125, 0.25, 0.5, 1.0], value=0.25)
        if odds > 1:
            ev = p * odds - 1
            kelly = max(0.0, (p * odds - 1) / (odds - 1)) * fraction
            cols = st.columns(3)
            cols[0].metric("EV", f"{ev:+.2%}")
            cols[1].metric("Stake sugerido", f"{kelly:.2%}")
            cols[2].metric("Monto sugerido", f"${bankroll*kelly:,.2f}")
            st.caption("La banca disponible descuenta las apuestas pendientes. La calculadora no registra apuestas.")
    with tab2:
        if conn is None:
            st.info("Conecta MySQL para consultar y guardar tu portafolio.")
        else:
            cols = st.columns(4)
            cols[0].metric("Saldo", f"${stats['saldo']:,.2f}")
            cols[1].metric("Disponible", f"${stats['disponible']:,.2f}")
            cols[2].metric("Beneficio neto", f"${stats['beneficio']:+,.2f}")
            cols[3].metric("ROI liquidado", f"{stats['roi']:+.2f}%")
            st.caption(f"Pendiente: ${stats['pendientes']:,.2f} · Apuestas: {stats['apuestas']} · Acierto: {stats['win_rate']:.1f}%")
            with st.form("capital_inicial"):
                value = st.number_input("Capital inicial de la banca ($)", min_value=0.0, value=initial, step=100.0)
                if st.form_submit_button("Guardar capital inicial"):
                    bank.capital(conn, value)
                    st.rerun()
            st.caption("El ROI incluye apuestas ganadas, perdidas y push. Pendientes y anuladas se muestran aparte.")
            if st.button("Actualizar liquidación"):
                changed, errors = bank.settle_pending(conn, RAIZ)
                st.success(f"{changed} apuestas actualizadas con los resultados disponibles.")
                for error in errors: st.warning(error)
                ledger = bank.load_ledger(conn)
            groups = []
            for sport, frame in ledger.groupby('deporte'):
                m = bank.metrics(frame)
                groups.append(dict(Deporte=sport, Apuestas=len(frame), Apostado=m['apostado'],
                                   Beneficio=m['beneficio'], ROI=m['roi'], Pendiente=m['pendientes']))
            st.dataframe(pd.DataFrame(groups), hide_index=True, use_container_width=True)
            st.dataframe(ledger.drop(columns=['referencia']), hide_index=True, use_container_width=True)
            st.download_button("Descargar historial", ledger.to_csv(index=False), "bankroll.csv", "text/csv")
    with tab3:
        if conn is None:
            st.info("No se guardan apuestas hasta recuperar la conexión con MySQL.")
        else:
            mode = st.radio("Origen de la apuesta", ["Manual", "Predicción del modelo"], horizontal=True)
            selected = None
            if mode == "Predicción del modelo":
                if st.button("Actualizar predicciones disponibles"):
                    st.session_state.pop('bankroll_predictions', None)
                if 'bankroll_predictions' not in st.session_state:
                    st.session_state['bankroll_predictions'] = bank.model_options(conn, RAIZ)
                options, errors = st.session_state['bankroll_predictions']
                for error in errors: st.caption(error)
                if options:
                    idx = st.selectbox("Selecciona una predicción", range(len(options)),
                        format_func=lambda i: f"{options[i]['deporte']} · {options[i]['partido']} · {options[i]['seleccion']}")
                    selected = options[idx]
                    if pd.notna(selected['probabilidad']):
                        st.metric("Confianza registrada", f"{float(selected['probabilidad']):.1%}")
                    st.caption("Registra únicamente una apuesta que realizaste. Confirma la cuota tomada y el monto.")
                else: st.info("No hay predicciones disponibles para registrar.")
            if mode == "Manual" or selected is not None:
                st.session_state.setdefault('bankroll_receipt', str(uuid.uuid4()))
                with st.form("registrar_apuesta"):
                    if selected is None:
                        fecha = st.date_input("Fecha", value=datetime.now(ZoneInfo('America/Mexico_City')).date())
                        sport = st.selectbox("Deporte", ["MLB", "NFL", "Liga MX"])
                        partido = st.text_input("Partido")
                        selection = st.text_input("Selección")
                        casa = st.text_input("Casa", value="DraftKings")
                        probability = st.number_input("Confianza (%) — opcional", 0.0, 100.0, 0.0) / 100 or None
                    else:
                        fecha, sport = selected['fecha'], selected['deporte']
                        partido, selection, casa = selected['partido'], selected['seleccion'], selected['casa']
                        probability = selected['probabilidad']
                        st.write(f"{partido} · {selection} · {casa}")
                    odds = st.number_input("Cuota decimal tomada", min_value=1.01,
                                           value=(float(selected['cuota']) if selected['cuota'] else None) if selected else 1.90,
                                           step=0.01, key=f"cuota_{mode}_{idx if selected else 'manual'}")
                    amount = st.number_input("Monto apostado ($)", min_value=1.0, value=100.0, step=10.0)
                    state = st.selectbox("Estado", bank.STATES)
                    if st.form_submit_button("Guardar apuesta realizada"):
                        bet = dict(fecha=fecha, deporte=sport, partido=partido, seleccion=selection,
                                   casa=casa, probabilidad=probability, cuota=odds, monto=amount, estado=state)
                        if selected: bet.update(origen=selected['origen'], referencia=selected['referencia'])
                        try:
                            if odds is None: raise ValueError("Introduce la cuota decimal que tomaste.")
                            bank.save_bet(conn, bet, st.session_state['bankroll_receipt'])
                            st.session_state['bankroll_receipt'] = str(uuid.uuid4())
                            st.rerun()
                        except ValueError as exc: st.error(str(exc))
            st.markdown("### Actualizar una apuesta registrada")
            if not ledger.empty:
                idx = st.selectbox("Apuesta", range(len(ledger)),
                    format_func=lambda i: f"{ledger.iloc[i]['fecha']:%d/%m/%Y} · {ledger.iloc[i]['partido']} · {ledger.iloc[i]['seleccion']} · {ledger.iloc[i]['estado']}")
                bet = ledger.iloc[idx]
                with st.form("actualizar_apuesta"):
                    state = st.selectbox("Nuevo estado", bank.STATES, index=bank.STATES.index(bet['estado']))
                    if st.form_submit_button("Actualizar estado"):
                        bank.update_state(conn, bet['id'], state)
                        st.rerun()


conn = None
try:
    ledger = pd.DataFrame(columns=bank.COLUMNS)
    initial = 10000.0
    try:
        conn = get_db_connection()
        bank.prepare(conn)
        _, errors = bank.settle_pending(conn, RAIZ)
        for error in errors: st.caption(f"Liquidación pendiente de revisión: {error}")
        ledger, initial = bank.load_ledger(conn), bank.capital(conn)
    except Exception as exc:
        st.warning(f"Bankroll no pudo conectar con MySQL ({type(exc).__name__}).")
        if conn is not None: conn.close()
        conn = None
    render_app(conn, ledger, initial)
finally:
    if conn is not None: conn.close()
