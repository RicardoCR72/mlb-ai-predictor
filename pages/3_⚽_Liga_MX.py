import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(
    page_title="Liga MX Oráculo",
    page_icon="⚽",
    layout="wide",
)

RAIZ = Path(__file__).resolve().parents[1]
RUTA_FUTBOL = RAIZ / "futbol_liga_mx"
RUTA_DATA = RUTA_FUTBOL / "data"
RUTA_MODELOS = RUTA_FUTBOL / "modelos"

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
    .soccer-shell {
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
    .soccer-brand {
        display: flex;
        align-items: center;
        gap: .65rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    .soccer-logo {
        width: 34px;
        height: 34px;
        display: inline-grid;
        place-items: center;
        border-radius: 10px;
        background: #b7ff3c;
        color: #071006;
        font-weight: 900;
    }
    .soccer-accent { color: #b7ff3c; }
    .soccer-status { color: #8e99a9; font-size: .78rem; font-weight: 700; }
    .soccer-view-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin: .9rem 0 1.25rem;
    }
    .soccer-eyebrow {
        color: #b7ff3c;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .12em;
    }
    .soccer-view-hero h1 {
        margin: .22rem 0 .15rem;
        color: #f5f8fb;
        font-size: clamp(1.75rem, 3vw, 2.45rem);
    }
    .soccer-subtitle { color: #8994a5; font-size: .88rem; }
    div[data-testid="stMetric"] {
        background: #111720;
        border: 1px solid #202938;
        border-radius: 11px;
        padding: .78rem .9rem;
    }
    div[data-testid="stMetric"] label { color: #8994a5; }
    div[data-testid="stMetricValue"] { color: #f4f7fb; }
    .match-card {
        padding: 1.15rem 1.3rem;
        border: 1px solid #253044;
        border-radius: 16px;
        background: linear-gradient(145deg, #111722, #0d131d);
        margin-bottom: 0.95rem;
    }
    .match-header {
        display: flex;
        justify-content: space-between;
        font-size: 0.78rem;
        color: #798699;
        margin-bottom: 0.7rem;
    }
    .match-teams {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 1.2rem;
        font-weight: 800;
        color: #f5f8fb;
        margin-bottom: 0.8rem;
    }
    .match-badge {
        padding: 0.25rem 0.6rem;
        border-radius: 999px;
        background: rgba(183, 255, 60, 0.08);
        border: 1px solid rgba(183, 255, 60, 0.3);
        color: #b7ff3c;
        font-size: 0.75rem;
        font-weight: 800;
    }
    .prob-bar {
        height: 6px;
        border-radius: 3px;
        background: #202938;
        overflow: hidden;
        margin-top: 0.5rem;
    }
    .prob-fill {
        height: 100%;
        background: #b7ff3c;
    }
    </style>
    <div class="soccer-shell">
        <div class="soccer-brand">
            <span class="soccer-logo">⚽</span>
            <span>ORÁCULO <span class="soccer-accent">LIGA MX</span></span>
        </div>
        <div class="soccer-status">MODELO CUANTITATIVO · TOTALES 2.5 · CONTINUIDAD 2025–26</div>
    </div>
    """,
    unsafe_allow_html=True,
)

vista = st.radio(
    "Sección Liga MX",
    ["🔮 Próximos Partidos", "⚽ Resultados Históricos", "📊 Métricas de Validación", "📋 Historial y Cobertura"],
    horizontal=True,
    label_visibility="collapsed",
    key="ligamx_vista",
)

@st.cache_data(ttl=300)
def cargar_datos_ligamx():
    partidos_csv = RUTA_DATA / "partidos.csv"
    if not partidos_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(partidos_csv)
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df

@st.cache_data(ttl=300)
def cargar_proximos_ligamx():
    proximos_csv = RUTA_DATA / "proximos.csv"
    if not proximos_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(proximos_csv)
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df

@st.cache_data(ttl=600)
def cargar_metricas_ligamx():
    metricas_path = RUTA_MODELOS / "metricas.json"
    if metricas_path.exists():
        return json.loads(metricas_path.read_text(encoding="utf-8"))
    return {}

@st.cache_data(ttl=600)
def cargar_modelo_portable():
    modelo_path = RUTA_MODELOS / "modelo_portable.json"
    if modelo_path.exists():
        return json.loads(modelo_path.read_text(encoding="utf-8"))
    return {}

@st.cache_data(ttl=600)
def calcular_estado_equipos(df_historico: pd.DataFrame) -> dict:
    """Calcula el estado rolling de cada equipo a partir del historial."""
    if df_historico.empty:
        return {}
    data = df_historico.sort_values('fecha').copy()
    league_gf = data['goles_local'].mean()
    league_ga = data['goles_visitante'].mean()
    state: dict = {}
    for _, row in data.iterrows():
        for equipo, gf, ga in [
            (row['local'], row['goles_local'], row['goles_visitante']),
            (row['visitante'], row['goles_visitante'], row['goles_local']),
        ]:
            if equipo not in state:
                state[equipo] = []
            puntos = 3 if gf > ga else (1 if gf == ga else 0)
            state[equipo].append({
                'fecha': row['fecha'], 'gf': gf, 'ga': ga, 'pts': puntos
            })
    return state

def get_team_features(equipo: str, state: dict, league_gf: float, league_ga: float, 
                      fecha_partido=None, es_local: bool = True):
    """Extrae las features del modelo para un equipo dado su historial."""
    historial = state.get(equipo, [])
    if fecha_partido is not None:
        historial = [r for r in historial if r['fecha'] < fecha_partido]
    ultimos = historial[-5:] if historial else []
    if not ultimos:
        gf_5 = league_gf if es_local else league_ga
        ga_5 = league_ga if es_local else league_gf
        pts_5 = 1.3 if es_local else 1.1
        descanso = 7
        n_juegos = 0
    else:
        prior_gf = league_gf if es_local else league_ga
        prior_ga = league_ga if es_local else league_gf
        gf_5 = (sum(r['gf'] for r in ultimos) + 5 * prior_gf) / (len(ultimos) + 5)
        ga_5 = (sum(r['ga'] for r in ultimos) + 5 * prior_ga) / (len(ultimos) + 5)
        prior_pts = 1.3 if es_local else 1.1
        pts_5 = (sum(r['pts'] for r in ultimos) + 5 * prior_pts) / (len(ultimos) + 5)
        ultima_fecha = historial[-1]['fecha'] if historial else None
        if ultima_fecha is not None and fecha_partido is not None:
            delta = (fecha_partido - ultima_fecha).days
            descanso = int(min(max(delta, 0), 30))
        else:
            descanso = 7
        n_juegos = min(len(historial), 25)
    return gf_5, ga_5, pts_5, descanso, n_juegos

def proyectar_partido(local: str, visitante: str, estado_equipos: dict, modelo_params: dict,
                      df_historico: pd.DataFrame, fecha_partido=None) -> float:
    """Proyecta la probabilidad Over 2.5 usando el modelo Poisson + calibración."""
    if not modelo_params or not estado_equipos:
        return 0.55  # Fallback: tasa histórica aproximada
    league_gf = df_historico['goles_local'].mean() if not df_historico.empty else 1.4
    league_ga = df_historico['goles_visitante'].mean() if not df_historico.empty else 1.2
    gf_loc, gc_loc, pts_loc, desc_loc, n_loc = get_team_features(
        local, estado_equipos, league_gf, league_ga, fecha_partido, es_local=True)
    gf_vis, gc_vis, pts_vis, desc_vis, n_vis = get_team_features(
        visitante, estado_equipos, league_gf, league_ga, fecha_partido, es_local=False)
    features_vals = [
        gf_loc, gc_loc, gf_vis, gc_vis,
        pts_loc, pts_vis,
        desc_loc, desc_vis,
        league_gf, league_ga,
        n_loc, n_vis,
    ]
    mean_v = np.array(modelo_params['mean'])
    scale_v = np.array(modelo_params['scale'])
    coef_v = np.array(modelo_params['coef'])
    intercept_v = float(modelo_params['intercept'])
    x = (np.array(features_vals) - mean_v) / scale_v
    log_mu = np.dot(coef_v, x) + intercept_v
    mu = float(np.exp(log_mu))
    mu = max(0.05, min(mu, 15.0))
    # Poisson CDF P(X <= 2) donde X = total goles
    p_under = math.exp(-mu) * (1 + mu + mu**2 / 2)
    p_over_raw = float(np.clip(1 - p_under, 1e-5, 1 - 1e-5))
    # Calibración logística
    cal = modelo_params.get('calibration', {})
    if cal and modelo_params.get('winner') == 'calibrada':
        logit_raw = math.log(p_over_raw / (1 - p_over_raw))
        cal_coef = float(cal.get('coef', 1.0))
        cal_int = float(cal.get('intercept', 0.0))
        logit_cal = cal_coef * logit_raw + cal_int
        p_over = float(1 / (1 + math.exp(-logit_cal)))
    else:
        p_over = p_over_raw
    return float(np.clip(p_over, 0.10, 0.90))

df_partidos = cargar_datos_ligamx()
df_proximos = cargar_proximos_ligamx()
metricas = cargar_metricas_ligamx()
modelo_params = cargar_modelo_portable()
estado_equipos = calcular_estado_equipos(df_partidos)

# ==========================================================
# VISTA 0: PRÓXIMOS PARTIDOS Y PROYECCIONES
# ==========================================================
if vista == "🔮 Próximos Partidos":
    st.markdown(
        """
        <div class="soccer-view-hero">
            <div>
                <div class="soccer-eyebrow">PROYECCIONES MODELO POISSON</div>
                <h1>Próximos Partidos Liga MX</h1>
                <div class="soccer-subtitle">Probabilidades calibradas de Over / Under 2.5 goles para la temporada 2025&ndash;26.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df_proximos.empty:
        st.info(
            "🔒 **Calendario 2025–26 no cargado.** "
            "Para ver los próximos partidos con proyecciones necesitas configurar `API_FOOTBALL_KEY` "
            "y ejecutar:\n\n"
            "```bash\n"
            "python -m futbol_liga_mx.proveedor_api\n"
            "```\n\n"
            "Esto genera `futbol_liga_mx/data/proximos.csv` con el calendario actual de Liga MX. "
            "Mientras tanto, puedes ver el historial en la pestaña **Resultados Históricos**."
        )
        if not df_partidos.empty and modelo_params:
            st.markdown("---")
            st.markdown("### 🧪 Proyección Manual")
            st.markdown("Puedes simular un partido usando el modelo entrenado:")
            equipos_conocidos = sorted(list(set(
                df_partidos['local'].unique().tolist() + df_partidos['visitante'].unique().tolist()
            )))
            col_a, col_b = st.columns(2)
            with col_a:
                local_sim = st.selectbox("🏠 Equipo Local", equipos_conocidos, index=0, key="sim_local")
            with col_b:
                idx_vis = 1 if len(equipos_conocidos) > 1 else 0
                visitante_sim = st.selectbox("✈️ Equipo Visitante", equipos_conocidos, index=idx_vis, key="sim_visitante")
            if local_sim != visitante_sim:
                p_over_sim = proyectar_partido(
                    local_sim, visitante_sim, estado_equipos, modelo_params, df_partidos
                )
                st.markdown(
                    f"""
                    <div class="match-card" style="margin-top:1rem;">
                        <div class="match-header">
                            <span>🧠 Proyección del Modelo</span>
                            <span class="match-badge">Simulación</span>
                        </div>
                        <div class="match-teams">
                            <span>{local_sim}</span>
                            <span style="color:#b7ff3c;">VS</span>
                            <span>{visitante_sim}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.84rem; color:#8994a5;">
                            <span>Prob. Over 2.5: <b style="color:#eef3f8;">{p_over_sim*100:.1f}%</b></span>
                            <span>Prob. Under 2.5: <b style="color:#eef3f8;">{(1-p_over_sim)*100:.1f}%</b></span>
                        </div>
                        <div class="prob-bar"><div class="prob-fill" style="width: {p_over_sim*100:.1f}%;"></div></div>
                        <div style="margin-top:0.6rem; font-size:0.78rem; color:#8994a5;">
                            ⚠️ Proyección basada en los últimos 5 partidos de cada equipo en el historial.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.warning("Selecciona dos equipos diferentes.")
    else:
        # Hay calendario disponible — mostrar partidos con proyecciones
        hoy = pd.Timestamp.now(tz='America/Mexico_City').normalize().tz_localize(None)
        proximos_futuros = df_proximos[df_proximos['fecha'] >= hoy].sort_values('fecha')

        if proximos_futuros.empty:
            st.warning("No hay partidos próximos en `futbol_liga_mx/data/proximos.csv`. Ejecuta `proveedor_api` para actualizar.")
        else:
            n_total = len(proximos_futuros)
            n_con_model = sum(1 for _, r in proximos_futuros.iterrows()
                              if r['local'] in estado_equipos and r['visitante'] in estado_equipos)
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Próximos Partidos", f"{n_total}")
            with m2:
                temporadas_prox = proximos_futuros['season'].unique() if 'season' in proximos_futuros.columns else ["2025-26"]
                st.metric("Temporada", temporadas_prox[0] if len(temporadas_prox) > 0 else "2025-26")
            with m3:
                st.metric("Con Proyección Modelo", f"{n_con_model}/{n_total}")

            st.markdown("### Partidos y Proyecciones Over/Under 2.5")
            for _, row in proximos_futuros.head(20).iterrows():
                fecha_str = row['fecha'].strftime("%d/%m/%Y")
                inicio_str = ""
                if 'inicio_utc' in row and pd.notna(row.get('inicio_utc')):
                    try:
                        utc_dt = pd.Timestamp(row['inicio_utc']).tz_convert('America/Mexico_City')
                        inicio_str = utc_dt.strftime("%H:%M CDMX")
                    except Exception:
                        pass
                ronda_str = row.get('ronda', '') if 'ronda' in row else ""
                fecha_partido_dt = row['fecha'].to_pydatetime() if hasattr(row['fecha'], 'to_pydatetime') else None
                p_over = proyectar_partido(
                    row['local'], row['visitante'], estado_equipos, modelo_params, df_partidos, fecha_partido_dt
                )
                p_over_pct = p_over * 100
                recomendacion = "OVER" if p_over >= 0.55 else ("UNDER" if p_over <= 0.45 else "NEUTRO")
                badge_color = "rgba(183,255,60,0.12)" if recomendacion == "OVER" else ("rgba(99,180,255,0.12)" if recomendacion == "UNDER" else "rgba(255,200,80,0.12)")
                badge_border = "rgba(183,255,60,0.4)" if recomendacion == "OVER" else ("rgba(99,180,255,0.4)" if recomendacion == "UNDER" else "rgba(255,200,80,0.4)")
                badge_text_color = "#b7ff3c" if recomendacion == "OVER" else ("#63b4ff" if recomendacion == "UNDER" else "#ffc850")
                st.markdown(
                    f"""
                    <div class="match-card">
                        <div class="match-header">
                            <span>🗓️ {fecha_str}{f' · {inicio_str}' if inicio_str else ''}{f' · {ronda_str}' if ronda_str else ''}</span>
                            <span style="padding:0.25rem 0.6rem; border-radius:999px; background:{badge_color}; border:1px solid {badge_border}; color:{badge_text_color}; font-size:0.75rem; font-weight:800;">{recomendacion} 2.5</span>
                        </div>
                        <div class="match-teams">
                            <span>{row['local']}</span>
                            <span style="color:#b7ff3c;">VS</span>
                            <span>{row['visitante']}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.84rem; color:#8994a5; margin-bottom:0.4rem;">
                            <span>Over 2.5: <b style="color:#eef3f8;">{p_over_pct:.1f}%</b></span>
                            <span>Under 2.5: <b style="color:#eef3f8;">{100 - p_over_pct:.1f}%</b></span>
                        </div>
                        <div class="prob-bar"><div class="prob-fill" style="width:{p_over_pct:.1f}%; background: {'#b7ff3c' if recomendacion=='OVER' else ('#63b4ff' if recomendacion=='UNDER' else '#ffc850')};"></div></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ==========================================================
# VISTA 1: RESULTADOS HISTÓRICOS
# ==========================================================
elif vista == "⚽ Resultados Históricos":
    st.markdown(
        """
        <div class="soccer-view-hero">
            <div>
                <div class="soccer-eyebrow">HISTORIAL 2018–2025</div>
                <h1>Resultados Históricos Liga MX</h1>
                <div class="soccer-subtitle">Resultados reales con probabilidad pre-partido Over/Under 2.5 según el modelo Poisson calibrado.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df_partidos.empty:
        st.warning("No se encontraron partidos en `futbol_liga_mx/data/partidos.csv`.")
    else:
        # Métricas generales arriba
        ultimos = df_partidos.sort_values(by="fecha", ascending=False)
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Partidos Registrados", f"{len(df_partidos):,}")
        with m2:
            prom_goles = (df_partidos['goles_local'] + df_partidos['goles_visitante']).mean()
            st.metric("Media Goles / Partido", f"{prom_goles:.2f}")
        with m3:
            over_rate = ((df_partidos['goles_local'] + df_partidos['goles_visitante']) > 2.5).mean()
            st.metric("Tasa Histórica Over 2.5", f"{over_rate * 100:.1f}%")
        with m4:
            st.metric("Temporada Activa", "2025–26 (Evaluada)")

        st.markdown("### Partidos Recientes y Proyecciones")
        temporadas_disponibles = sorted(df_partidos['season'].unique().tolist(), reverse=True)
        temporada_sel = st.selectbox("Filtrar por Temporada:", temporadas_disponibles, index=0)

        df_filtrado = df_partidos[df_partidos['season'] == temporada_sel].sort_values(by="fecha", ascending=False).reset_index(drop=True)

        # Mostrar los partidos
        for idx, row in df_filtrado.head(15).iterrows():
            total_goles = row['goles_local'] + row['goles_visitante']
            es_over = total_goles > 2.5
            fecha_str = row['fecha'].strftime("%d/%m/%Y")
            fecha_dt = row['fecha'].to_pydatetime() if hasattr(row['fecha'], 'to_pydatetime') else None
            # Probabilidad pre-partido usando el modelo (no los goles reales)
            p_over_val = proyectar_partido(
                row['local'], row['visitante'], estado_equipos, modelo_params, df_partidos, fecha_dt
            )
            p_over_pct = p_over_val * 100

            badge_text = f"REAL: {row['goles_local']} - {row['goles_visitante']} ({'OVER' if es_over else 'UNDER'})"
            resultado_color = "#b7ff3c" if es_over else "#63b4ff"
            st.markdown(
                f"""
                <div class="match-card">
                    <div class="match-header">
                        <span>🗓️ {fecha_str} · {row['ronda']}</span>
                        <span style="padding:0.25rem 0.6rem; border-radius:999px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.15); color:{resultado_color}; font-size:0.75rem; font-weight:800;">{badge_text}</span>
                    </div>
                    <div class="match-teams">
                        <span>{row['local']}</span>
                        <span style="color:#b7ff3c;">VS</span>
                        <span>{row['visitante']}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.84rem; color:#8994a5;">
                        <span>Prob. Over 2.5 (pre-partido): <b style="color:#eef3f8;">{p_over_pct:.1f}%</b></span>
                        <span>Prob. Under 2.5: <b style="color:#eef3f8;">{100 - p_over_pct:.1f}%</b></span>
                    </div>
                    <div class="prob-bar">
                        <div class="prob-fill" style="width: {p_over_pct:.1f}%; background:{resultado_color};"></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ==========================================================
# VISTA 2: MÉTRICAS DE VALIDACIÓN
# ==========================================================
elif vista == "📊 Métricas de Validación":
    st.markdown(
        """
        <div class="soccer-view-hero">
            <div>
                <div class="soccer-eyebrow">AUDITORÍA ESTADÍSTICA</div>
                <h1>Validación del Modelo Liga MX</h1>
                <div class="soccer-subtitle">Rendimiento riguroso medido por Brier Score y Log Loss frente al baseline de mercado.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if metricas:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### Confirmación 2024–25")
            conf = metricas.get("confirmation", {}).get("calibrated", {})
            st.metric("Brier Score", f"{conf.get('brier', 0):.4f}")
            st.metric("Log Loss", f"{conf.get('logloss', 0):.4f}")
            st.metric("Probabilidad Media", f"{conf.get('prob_media', 0)*100:.1f}%")
        with c2:
            st.markdown("#### Baseline de Comparación")
            base = metricas.get("confirmation", {}).get("baseline", {})
            st.metric("Brier Baseline", f"{base.get('brier', 0):.4f}")
            st.metric("Log Loss Baseline", f"{base.get('logloss', 0):.4f}")
            st.metric("Tasa Real Over", f"{base.get('real_over', 0)*100:.1f}%")
        with c3:
            st.markdown("#### Estado de Congelamiento")
            st.info(
                f"**Modelo:** Calibrado\n\n"
                f"**Muestra de entrenamiento:** {metricas.get('train_games', 0)} partidos\n\n"
                f"**Temporadas base:** 2018–19 a 2021–22\n\n"
                f"**Selección:** 2023–24\n\n"
                f"**Evaluación ciega:** 2024–25"
            )

        st.markdown("---")
        st.markdown("#### Cobertura Histórica de Partidos por Temporada")
        cobertura = metricas.get("coverage", {})
        if cobertura:
            df_cob = pd.DataFrame(list(cobertura.items()), columns=["Temporada", "Partidos"])
            st.dataframe(df_cob, use_container_width=True, hide_index=True)
    else:
        st.warning("No se encontró `futbol_liga_mx/modelos/metricas.json`.")

# ==========================================================
# VISTA 3: HISTORIAL Y COBERTURA
# ==========================================================
else:
    st.markdown(
        """
        <div class="soccer-view-hero">
            <div>
                <div class="soccer-eyebrow">BASE DE DATOS</div>
                <h1>Historial Completo Liga MX</h1>
                <div class="soccer-subtitle">Consulta de marcadores, goles totales y temporadas registradas.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not df_partidos.empty:
        col_filtro1, col_filtro2 = st.columns(2)
        with col_filtro1:
            equipos_todos = sorted(list(set(df_partidos['local'].unique().tolist() + df_partidos['visitante'].unique().tolist())))
            equipo_sel = st.selectbox("Filtrar por Equipo:", ["Todos"] + equipos_todos)
        with col_filtro2:
            ronda_filtro = st.text_input("Buscar por Ronda o Jornada (ej. Matchday 1, Final):")

        df_show = df_partidos.copy()
        if equipo_sel != "Todos":
            df_show = df_show[(df_show['local'] == equipo_sel) | (df_show['visitante'] == equipo_sel)]
        if ronda_filtro:
            df_show = df_show[df_show['ronda'].str.contains(ronda_filtro, case=False, na=False)]

        df_show['total_goles'] = df_show['goles_local'] + df_show['goles_visitante']
        df_show['over_25'] = np.where(df_show['total_goles'] > 2.5, "Over", "Under")

        columnas_ver = ['season', 'fecha', 'local', 'visitante', 'goles_local', 'goles_visitante', 'total_goles', 'over_25', 'ronda']
        st.dataframe(
            df_show[columnas_ver].sort_values(by="fecha", ascending=False),
            use_container_width=True,
            hide_index=True
        )
