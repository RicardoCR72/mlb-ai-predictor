from core.ui_resumen import render_home
import streamlit as st


st.set_page_config(
    page_title="Oráculo Sports AI",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 82% 0%, rgba(183,255,60,.08), transparent 30rem),
            #080c13;
        color: #eef3f8;
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container {
        max-width: 1450px;
        padding-top: 1.15rem;
        padding-bottom: 3rem;
    }
    [data-testid="stSidebar"] {
        background: #0d131d;
        border-right: 1px solid #202938;
    }
    .hub-topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .78rem .95rem;
        border: 1px solid #202938;
        border-radius: 13px;
        background: #111720;
        margin-bottom: 1.35rem;
    }
    .hub-brand {
        display: flex;
        align-items: center;
        gap: .7rem;
        color: #f5f8fb;
        font-weight: 850;
        letter-spacing: .02em;
    }
    .hub-logo {
        width: 36px;
        height: 36px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #b7ff3c;
        color: #071006;
        font-weight: 950;
    }
    .hub-brand-accent { color: #b7ff3c; }
    .hub-status {
        display: flex;
        align-items: center;
        gap: .45rem;
        color: #b7ff3c;
        font-size: .78rem;
        font-weight: 750;
    }
    .hub-status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #b7ff3c;
        box-shadow: 0 0 12px rgba(183,255,60,.75);
    }
    .hub-hero {
        position: relative;
        overflow: hidden;
        display: grid;
        grid-template-columns: minmax(0, 1.4fr) minmax(270px, .6fr);
        gap: 2rem;
        padding: 1.4rem;
        border: 1px solid #253044;
        border-radius: 24px;
        background: linear-gradient(135deg, #121925 0%, #0d131d 68%, #111b14 100%);
        box-shadow: 0 20px 60px rgba(0,0,0,.28);
        margin-bottom: 1.25rem;
    }
    .hub-hero::after {
        content: "";
        position: absolute;
        width: 260px;
        height: 260px;
        right: -95px;
        top: -115px;
        border-radius: 50%;
        border: 45px solid rgba(183,255,60,.055);
    }
    .hub-eyebrow {
        color: #b7ff3c;
        font-size: .75rem;
        font-weight: 850;
        letter-spacing: .17em;
        margin-bottom: .8rem;
    }
    .hub-hero h1 {
        color: #f7fafc;
        font-size: clamp(1.8rem, 3vw, 2.7rem);
        line-height: .98;
        letter-spacing: -.055em;
        margin: 0 0 1rem;
        max-width: 850px;
    }
    .hub-hero h1 span { color: #b7ff3c; }
    .hub-subtitle {
        color: #a5afbd;
        font-size: 1.02rem;
        line-height: 1.65;
        max-width: 720px;
    }
    .hub-signal {
        align-self: stretch;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: .65rem;
        padding: 1.2rem;
        border-left: 1px solid #2a3546;
    }
    .hub-signal-label {
        color: #788599;
        font-size: .68rem;
        letter-spacing: .14em;
        font-weight: 800;
    }
    .hub-signal-value {
        color: #f5f8fb;
        font-size: 1.15rem;
        font-weight: 850;
    }
    .hub-signal-value span { color: #b7ff3c; }
    .hub-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .85rem;
        margin: 1rem 0 1.6rem;
    }
    .hub-kpi {
        min-height: 105px;
        padding: 1rem 1.05rem;
        border: 1px solid #253044;
        border-radius: 15px;
        background: #111720;
    }
    .hub-kpi-label {
        color: #8190a5;
        font-size: .72rem;
        letter-spacing: .07em;
        text-transform: uppercase;
    }
    .hub-kpi-value {
        color: #f5f8fb;
        font-size: 1.12rem;
        font-weight: 850;
        margin-top: .45rem;
    }
    .hub-kpi-note { color: #b7ff3c; font-size: .72rem; margin-top: .3rem; }
    .hub-section-title {
        color: #f5f8fb;
        font-size: 1.25rem;
        font-weight: 850;
        margin: .3rem 0 .2rem;
    }
    .hub-section-note { color: #7f8b9d; font-size: .82rem; margin-bottom: .85rem; }
    .sport-card {
        min-height: 310px;
        padding: 1.35rem;
        border: 1px solid #273247;
        border-radius: 18px;
        background: linear-gradient(145deg, #121925, #0e141e);
        margin-bottom: .7rem;
    }
    .sport-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: .8rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #273247;
    }
    .sport-code { color: #77859a; font-size: .68rem; letter-spacing: .14em; }
    .sport-title { color: #f5f8fb; font-size: 1.45rem; font-weight: 900; margin-top: .2rem; }
    .sport-badge {
        border: 1px solid rgba(183,255,60,.35);
        border-radius: 999px;
        padding: .28rem .6rem;
        color: #b7ff3c;
        background: rgba(183,255,60,.07);
        font-size: .67rem;
        font-weight: 800;
    }
    .sport-copy { color: #939fb0; line-height: 1.55; margin: 1rem 0; min-height: 48px; }
    .sport-list { display: grid; gap: .55rem; }
    .sport-list-item {
        display: flex;
        align-items: center;
        gap: .55rem;
        color: #d7dee7;
        font-size: .83rem;
    }
    .sport-list-item::before {
        content: "";
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #b7ff3c;
        box-shadow: 0 0 8px rgba(183,255,60,.55);
    }
    div[data-testid="stPageLink"] a {
        min-height: 46px;
        justify-content: center;
        border: 1px solid #b7ff3c;
        border-radius: 11px;
        background: #b7ff3c;
        color: #071006 !important;
        font-weight: 850;
        text-decoration: none;
    }
    div[data-testid="stPageLink"] a:hover {
        background: #c5ff61;
        border-color: #c5ff61;
    }
    .hub-flow {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .7rem;
        margin-top: .8rem;
    }
    .hub-step {
        padding: .9rem 1rem;
        border: 1px solid #242f40;
        border-radius: 13px;
        background: #0f151f;
    }
    .hub-step-number { color: #b7ff3c; font-size: .68rem; font-weight: 900; }
    .hub-step-title { color: #f5f8fb; font-weight: 800; margin: .25rem 0; }
    .hub-step-note { color: #7f8b9d; font-size: .74rem; }
    .hub-footer {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        margin-top: 1.4rem;
        padding-top: 1rem;
        border-top: 1px solid #202938;
        color: #667387;
        font-size: .72rem;
    }
    @media (max-width: 900px) {
        .hub-hero { grid-template-columns: 1fr; padding: 1.5rem; }
        .hub-signal { border-left: 0; border-top: 1px solid #2a3546; }
        .hub-grid, .hub-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 560px) {
        .hub-grid, .hub-flow { grid-template-columns: 1fr; }
        .hub-topbar, .hub-footer { align-items: flex-start; flex-direction: column; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    """
    <div class="hub-topbar">
        <div class="hub-brand">
            <span class="hub-logo">O</span>
            <span>ORÁCULO <span class="hub-brand-accent">SPORTS AI</span></span>
        </div>
        <div class="hub-status"><span class="hub-status-dot"></span>RESUMEN DE DATOS</div>
    </div>
    <section class="hub-hero">
        <div>
            <div class="hub-eyebrow">INICIO · DATOS Y RESULTADOS</div>
            <h1>Tu centro deportivo.<br><span>El resumen de hoy.</span></h1>
            <div class="hub-subtitle">
                Consulta los partidos disponibles, revisa resultados pendientes
                y abre tu banca desde un solo lugar.
            </div>
        </div>
        <div class="hub-signal">
            <div class="hub-signal-label">COBERTURA ACTIVA</div>
            <div class="hub-signal-value"><span>MLB</span> · Totales + Moneyline</div>
            <div class="hub-signal-value"><span>NFL</span> · Totales + Props</div>
            <div class="hub-signal-value"><span>LIGA MX</span> · Totales 2.5</div>
        </div>
    </section>
    """,
    unsafe_allow_html=True,
)

render_home()

st.markdown('<div class="hub-section-title">Selecciona tu centro de análisis</div>', unsafe_allow_html=True)
st.markdown('<div class="hub-section-note">Cada módulo mantiene su propio modelo, controles y seguimiento de rendimiento.</div>', unsafe_allow_html=True)

mlb_col, nfl_col, ligamx_col = st.columns(3, gap="medium")

with mlb_col:
    st.markdown(
        """
        <div class="sport-card">
            <div class="sport-head">
                <div><div class="sport-code">BASEBALL ENGINE</div><div class="sport-title">⚾ MLB</div></div>
                <span class="sport-badge">ANÁLISIS</span>
            </div>
            <div class="sport-copy">Proyección de totales con probabilidades Over/Under, contexto del partido y auditoría histórica.</div>
            <div class="sport-list">
                <div class="sport-list-item">Probabilidades calibradas por línea</div>
                <div class="sport-list-item">Picks filtrados por confianza</div>
                <div class="sport-list-item">Resultados y ROI auditables</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/1_⚾_MLB.py",
        label="ABRIR CENTRO MLB",
        icon="⚾",
        use_container_width=True,
    )

with nfl_col:
    st.markdown(
        """
        <div class="sport-card">
            <div class="sport-head">
                <div><div class="sport-code">FOOTBALL ENGINE</div><div class="sport-title">🏈 NFL</div></div>
                <span class="sport-badge">ANÁLISIS</span>
            </div>
            <div class="sport-copy">Totales y seis mercados de jugadores con lesiones, valor esperado y liquidación automática.</div>
            <div class="sport-list">
                <div class="sport-list-item">Altas y bajas de puntos</div>
                <div class="sport-list-item">Recepción, pase, carrera y touchdown</div>
                <div class="sport-list-item">Unidades, ROI y equivalencia monetaria</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/2_🏈_NFL.py",
        label="ABRIR CENTRO NFL",
        icon="🏈",
        use_container_width=True,
    )

with ligamx_col:
    st.markdown(
        """
        <div class="sport-card">
            <div class="sport-head">
                <div><div class="sport-code">SOCCER ENGINE</div><div class="sport-title">⚽ LIGA MX</div></div>
                <span class="sport-badge">ANÁLISIS</span>
            </div>
            <div class="sport-copy">Modelos Poisson y regresión logística calibrada para el mercado de Over/Under 2.5 goles.</div>
            <div class="sport-list">
                <div class="sport-list-item">Proyección de goles esperados (xG)</div>
                <div class="sport-list-item">Probabilidad calibrada 2.5 goles</div>
                <div class="sport-list-item">Auditoría con Brier Score real</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/3_⚽_Liga_MX.py",
        label="ABRIR LIGA MX",
        icon="⚽",
        use_container_width=True,
    )

st.markdown('<div class="hub-section-title" style="margin-top:1.7rem">Flujo operativo</div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="hub-flow">
        <div class="hub-step"><div class="hub-step-number">01</div><div class="hub-step-title">Datos</div><div class="hub-step-note">Calendario, estadísticas, líneas y lesiones.</div></div>
        <div class="hub-step"><div class="hub-step-number">02</div><div class="hub-step-title">Modelos</div><div class="hub-step-note">Proyección y probabilidad calibrada.</div></div>
        <div class="hub-step"><div class="hub-step-number">03</div><div class="hub-step-title">Valor</div><div class="hub-step-note">Edge, EV y filtros de publicación.</div></div>
        <div class="hub-step"><div class="hub-step-number">04</div><div class="hub-step-title">Seguimiento</div><div class="hub-step-note">Resultados, simulaciones y apuestas realizadas.</div></div>
    </div>
    <div class="hub-footer">
        <span>ORÁCULO SPORTS AI · Centro de operaciones predictivas</span>
        <span>Las proyecciones son estimaciones, no garantías.</span>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Oráculo Sports AI")
    st.caption("Selecciona MLB, NFL, Liga MX, Comparador o Bankroll desde el menú de esta barra.")
    st.markdown("---")
    st.caption("Modelos, mercado, lesiones y rendimiento en un solo sistema.")
