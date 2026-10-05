import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(
    page_title="Gestión de Banca y Kelly",
    page_icon="💼",
    layout="wide",
)

RAIZ = Path(__file__).resolve().parents[1]
RUTA_BANKROLL = RAIZ / "data" / "bankroll_ledger.csv"

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

tab1, tab2, tab3 = st.tabs(["🧮 Calculadora Kelly & EV", "📈 Métricas de Portafolio", "📝 Registrar / Gestionar Apuesta"])

# Helper para cargar libro de apuestas
def cargar_ledger() -> pd.DataFrame:
    if RUTA_BANKROLL.exists():
        df = pd.read_csv(RUTA_BANKROLL)
        df['fecha'] = pd.to_datetime(df['fecha'])
        return df
    cols = ['fecha', 'deporte', 'partido', 'seleccion', 'casa', 'cuota', 'monto', 'estado', 'ganancia_neta']
    # Datos demostrativos iniciales
    df_init = pd.DataFrame([
        {'fecha': '2026-09-28', 'deporte': 'MLB', 'partido': 'LAD vs SF', 'seleccion': 'LAD ML', 'casa': 'DraftKings', 'cuota': 1.80, 'monto': 100.0, 'estado': 'Ganada', 'ganancia_neta': 80.0},
        {'fecha': '2026-09-29', 'deporte': 'NFL', 'partido': 'KC vs BAL', 'seleccion': 'Over 46.5', 'casa': 'DraftKings', 'cuota': 1.91, 'monto': 100.0, 'estado': 'Ganada', 'ganancia_neta': 91.0},
        {'fecha': '2026-09-30', 'deporte': 'Liga MX', 'partido': 'América vs Chivas', 'seleccion': 'Under 2.5', 'casa': 'Caliente', 'cuota': 1.85, 'monto': 100.0, 'estado': 'Perdida', 'ganancia_neta': -100.0},
    ])
    df_init.to_csv(RUTA_BANKROLL, index=False)
    df_init['fecha'] = pd.to_datetime(df_init['fecha'])
    return df_init

# ==========================================================
# TAB 1: CALCULADORA KELLY Y EXPECTED VALUE
# ==========================================================
with tab1:
    st.markdown("### Dimensionamiento Óptimo de Apuestas (Criterio de Kelly)")
    st.caption("Determina el tamaño exacto que debes arriesgar en base a la probabilidad de tu modelo y el precio del mercado.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown('<div class="kelly-box">', unsafe_allow_html=True)
        bankroll = st.number_input("Capital Total de Apuestas (Bankroll $):", min_value=100.0, value=10000.0, step=500.0)
        
        prob_modelo_pct = st.slider("Probabilidad estimada por la IA (%):", min_value=1.0, max_value=99.0, value=58.0, step=0.5)
        prob_modelo = prob_modelo_pct / 100.0

        tipo_cuota = st.selectbox("Formato de Cuota:", ["Decimal (ej. 1.91, 2.20)", "Americana (ej. -110, +135)"])
        
        if "Decimal" in tipo_cuota:
            cuota_dec = st.number_input("Cuota Decimal:", min_value=1.01, value=1.95, step=0.05)
        else:
            cuota_ame = st.number_input("Cuota Americana:", value=110, step=5)
            if cuota_ame > 0:
                cuota_dec = (cuota_ame / 100.0) + 1.0
            else:
                cuota_dec = (100.0 / abs(cuota_ame)) + 1.0

        fraccion_kelly = st.select_slider(
            "Fracción de Kelly (Ajuste de Riesgo):",
            options=[0.125, 0.25, 0.50, 1.0],
            value=0.25,
            format_func=lambda x: {0.125: "1/8 Kelly (Ultra Conservador)", 0.25: "1/4 Kelly (Recomendado)", 0.5: "1/2 Kelly (Moderado)", 1.0: "Full Kelly (Agresivo)"}[x]
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        # Cálculos matemáticos
        # b = ganancia neta por unidad apostada = cuota_dec - 1
        b = cuota_dec - 1.0
        p = prob_modelo
        q = 1.0 - p

        # Kelly f* = (b*p - q) / b
        kelly_full = (b * p - q) / b if b > 0 else 0.0
        kelly_ajustado = max(0.0, kelly_full * fraccion_kelly)

        # Expected Value = (P * cuota_dec) - 1
        ev = (p * cuota_dec) - 1.0
        prob_impl_mercado = 1.0 / cuota_dec

        monto_sugerido = bankroll * kelly_ajustado
        ganancia_esperada = monto_sugerido * ev

        st.markdown('<div class="kelly-box">', unsafe_allow_html=True)
        st.markdown("#### Resultado del Análisis Cuantitativo")

        if ev > 0:
            st.markdown(f'<span class="badge-pos">✅ APUESTA CON VALOR POSITIVO (+EV)</span>', unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="badge-neg">❌ VALOR NEGATIVO (-EV) · NO APOSTAR</span>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        r1, r2 = st.columns(2)
        with r1:
            st.metric("Edge sobre el Mercado", f"+{(prob_modelo - prob_impl_mercado)*100:.1f}%" if prob_modelo > prob_impl_mercado else f"{(prob_modelo - prob_impl_mercado)*100:.1f}%")
            st.metric("Valor Esperado (EV)", f"{ev*100:+.2f}%")
        with r2:
            st.metric("Stake Sugerido (%)", f"{kelly_ajustado*100:.2f}% de tu banca")
            st.metric("Monto a Apostar", f"${monto_sugerido:,.2f}")

        st.markdown("---")
        st.write(f"- **Probabilidad de la IA:** `{prob_modelo*100:.1f}%`")
        st.write(f"- **Probabilidad implícita en la cuota ({cuota_dec:.2f}):** `{prob_impl_mercado*100:.1f}%`")
        if ev > 0:
            st.success(f"Por cada ${monto_sugerido:,.2f} colocados a esta cuota, tu retorno esperado promedio a largo plazo es de **+${ganancia_esperada:,.2f}**.")
        else:
            st.error("La cuota de la casa de apuestas es menor a la probabilidad real estimada por el modelo. Apostar aquí destruye capital a largo plazo.")
        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================================
# TAB 2: MÉTRICAS DE PORTAFOLIO Y RENDIMIENTO
# ==========================================================
with tab2:
    df_ledger = cargar_ledger()

    st.markdown("### Auditoría Financiera y Métricas de Portafolio")
    
    total_apostado = df_ledger['monto'].sum()
    ganancia_neta_total = df_ledger['ganancia_neta'].sum()
    roi_global = (ganancia_neta_total / total_apostado) * 100 if total_apostado > 0 else 0.0
    
    apuestas_cerradas = df_ledger[df_ledger['estado'].isin(['Ganada', 'Perdida'])]
    ganadas = (apuestas_cerradas['estado'] == 'Ganada').sum()
    win_rate = (ganadas / len(apuestas_cerradas)) * 100 if len(apuestas_cerradas) > 0 else 0.0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Capital Invertido", f"${total_apostado:,.2f}")
    with k2:
        st.metric("Beneficio Neto (P&L)", f"${ganancia_neta_total:+,.2f}", delta=f"{roi_global:+.1f}% ROI")
    with k3:
        st.metric("Win Rate", f"{win_rate:.1f}%", f"{ganadas} de {len(apuestas_cerradas)}")
    with k4:
        st.metric("Apuestas Registradas", f"{len(df_ledger)}")

    st.markdown("---")
    st.markdown("#### Desglose de Rendimiento por Deporte")
    
    resumen_deporte = df_ledger.groupby('deporte').agg(
        Apuestas=('monto', 'count'),
        Apostado=('monto', 'sum'),
        Ganancia_Neta=('ganancia_neta', 'sum'),
    ).reset_index()
    resumen_deporte['ROI %'] = (resumen_deporte['Ganancia_Neta'] / resumen_deporte['Apostado']) * 100
    st.dataframe(resumen_deporte, use_container_width=True, hide_index=True)

    st.markdown("#### Historial Completo de Apuestas")
    st.dataframe(df_ledger.sort_values(by="fecha", ascending=False), use_container_width=True, hide_index=True)

# ==========================================================
# TAB 3: REGISTRAR NUEVA APUESTA
# ==========================================================
with tab3:
    st.markdown("### Añadir Nueva Operación al Libro de Apuestas")

    with st.form("form_nueva_apuesta"):
        c1, c2, c3 = st.columns(3)
        with c1:
            f_fecha = st.date_input("Fecha:", value=datetime.today())
            f_deporte = st.selectbox("Deporte:", ["MLB", "NFL", "Liga MX"])
            f_partido = st.text_input("Partido (ej. NYY vs BOS / DAL vs PHI):")
        with c2:
            f_seleccion = st.text_input("Selección (ej. NYY ML, Over 8.5, Ceedee Lamb Over 75.5 Yds):")
            f_casa = st.selectbox("Casa de Apuestas:", ["DraftKings", "Caliente", "Bet365", "Pinnacle", "Codere", "Otra"])
            f_cuota = st.number_input("Cuota Decimal Tomada:", min_value=1.01, value=1.90, step=0.05)
        with c3:
            f_monto = st.number_input("Monto Apostado ($):", min_value=1.0, value=100.0, step=10.0)
            f_estado = st.selectbox("Estado de la Apuesta:", ["Pendiente", "Ganada", "Perdida", "Push"])

        submit_btn = st.form_submit_button("💾 Guardar Apuesta en el Libro", use_container_width=True)

        if submit_btn:
            if not f_partido or not f_seleccion:
                st.error("Por favor completa el partido y la selección.")
            else:
                # Calcular ganancia neta
                if f_estado == "Ganada":
                    ganancia = f_monto * (f_cuota - 1.0)
                elif f_estado == "Perdida":
                    ganancia = -f_monto
                else:
                    ganancia = 0.0

                nuevo_registro = {
                    'fecha': f_fecha.strftime("%Y-%m-%d"),
                    'deporte': f_deporte,
                    'partido': f_partido,
                    'seleccion': f_seleccion,
                    'casa': f_casa,
                    'cuota': f_cuota,
                    'monto': f_monto,
                    'estado': f_estado,
                    'ganancia_neta': ganancia
                }

                df_curr = cargar_ledger()
                df_curr = pd.concat([df_curr, pd.DataFrame([nuevo_registro])], ignore_index=True)
                df_curr['fecha'] = df_curr['fecha'].dt.strftime("%Y-%m-%d")
                df_curr.to_csv(RUTA_BANKROLL, index=False)
                st.success("✅ ¡Apuesta guardada con éxito en el portafolio!")
                st.rerun()
