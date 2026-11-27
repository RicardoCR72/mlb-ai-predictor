"""Interfaz interactiva para Spread (Línea de Hándicap / ATS) NFL en Streamlit.

Diseño Gridiron Turf Neon de alta gama con tarjetas de pronósticos,
probabilidades proyectadas de cobertura, métricas de edge (+EV) y módulo de backtest out-of-sample.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from nfl.predecir_spread import generar_predicciones_spread

ZONA_CDMX = ZoneInfo("America/Mexico_City")
RAIZ = Path(__file__).resolve().parents[1]
RUTA_PREDICCIONES = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_spread.json"
RUTA_REPORTE_BACKTEST = RAIZ / "modelos_nfl" / "reporte_backtest_spread.json"


def cargar_predicciones_spread(forzar: bool = False) -> list[dict]:
    """Carga o genera las predicciones de spread."""
    if forzar or not RUTA_PREDICCIONES.exists():
        with st.spinner("Ejecutando modelo Spread NFL V1 y calculando edges..."):
            return generar_predicciones_spread()

    try:
        with open(RUTA_PREDICCIONES, "r", encoding="utf-8") as f:
            preds = json.load(f)
        if not preds or not isinstance(preds, list):
            return generar_predicciones_spread()
        return preds
    except Exception:
        return generar_predicciones_spread()


def render():
    """Punto de entrada principal para la pestaña Spread de NFL."""
    st.markdown(
        """
        <div style="background:linear-gradient(135deg, #0d1e16 0%, #152c20 100%); padding:1.2rem 1.5rem; border-radius:12px; border:1px solid #1f4331; margin-bottom:1.5rem;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="background:#b7ff3c; color:#0b1911; font-weight:900; font-size:0.72rem; padding:0.2rem 0.6rem; border-radius:6px; letter-spacing:0.08em;">MODELO OFICIAL V1</span>
                    <h2 style="color:#ffffff; margin:0.35rem 0 0.15rem 0; font-size:1.5rem; font-weight:800;">Líneas de Hándicap (Spread / ATS)</h2>
                    <p style="color:#94a3b8; font-size:0.88rem; margin:0;">Ensamble Híbrido: Regresión Logística L2 + HistGradientBoosting · Validación en 682 partidos (2024-2026)</p>
                </div>
                <div style="text-align:right;">
                    <div style="color:#b7ff3c; font-size:1.4rem; font-weight:900;">55.24% WR</div>
                    <div style="color:#64748b; font-size:0.75rem; font-weight:700;">+5.34% ROI EN PRUEBA</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sub_vista = st.radio(
        "Subsección Spread",
        ["Partidos de la Semana", "Auditoría & Backtest Out-of-Sample"],
        horizontal=True,
        label_visibility="collapsed",
        key="nfl_spread_subvista",
    )

    if sub_vista == "Partidos de la Semana":
        render_cartelera()
    else:
        render_backtest_dashboard()


def render_cartelera():
    """Muestra los partidos evaluados para la jornada actual."""
    col_act, col_info = st.columns([1, 4])
    with col_act:
        if st.button("🔄 Actualizar Líneas", key="btn_refresh_spread"):
            predicciones = cargar_predicciones_spread(forzar=True)
            st.success("Líneas y pronósticos actualizados.")
        else:
            predicciones = cargar_predicciones_spread(forzar=False)

    if not predicciones:
        st.info("🏈 La cartelera de la semana se actualizará en cuanto las casas de apuestas publiquen las líneas de la próxima jornada.")
        return

    from core.filtro_top5 import TOP_N_PICKS, etiqueta_top

    picks_top5 = sorted(
        [
            p for p in predicciones
            if p.get("recomendar")
            and float(p.get("ev_esperado_pct") or 0.0) > 0.0
            and float(p.get("prob_seleccion") or 0.0) >= 0.53
        ],
        key=lambda x: (float(x.get("prob_seleccion") or 0.0), float(x.get("ev_esperado_pct") or 0.0)),
        reverse=True,
    )[:TOP_N_PICKS]

    # Métricas superiores
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Partidos Analizados", len(predicciones))
    with c2:
        st.metric("🏆 Top Picks (+EV)", f"{len(picks_top5)} / {TOP_N_PICKS}")
    with c3:
        st.metric("Punto Equilibrio (-110)", "52.38%")
    with c4:
        st.metric("Confianza Mínima", "P >= 53.0%")

    st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

    if not picks_top5:
        st.info("🛡️ Ningún partido de la semana supera el umbral estricto de seguridad (P >= 53.0% y +EV). No forzamos picks sin valor.")
        return

    st.caption(
        f"🏆 **Filtro Automático Top {TOP_N_PICKS}:** Mostrando únicamente los **{len(picks_top5)} spreads más seguros con +EV** (sin zona muerta ni picks sin valor)."
    )

    # Render exclusivo de tarjetas Top 5 con ventaja estadística
    for idx, p in enumerate(picks_top5):
        pick_txt = f"{p['pick']} {p['linea_pick']:+g}"
        prob_txt = f"{p['prob_seleccion']*100:.1f}%"
        ev_txt = f"{p['ev_esperado_pct']:+.1f}%"
        badge_txt = f"{etiqueta_top(idx + 1)} · +EV"

        card_html = f"""
        <div style="background:#101e17; border:1px solid #b7ff3c; border-radius:12px; padding:1.1rem 1.4rem; margin-bottom:1rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem;">
                <div>
                    <span style="font-size:0.75rem; font-weight:800; color:#64748b;">PARTIDO</span>
                    <h3 style="color:#ffffff; margin:0; font-size:1.2rem; font-weight:800;">{p['away_team']} @ {p['home_team']}</h3>
                </div>
                <div style="text-align:right;">
                    <span style="background:#b7ff3c; color:#000000; font-weight:900; font-size:0.72rem; padding:0.25rem 0.6rem; border-radius:6px;">
                        {badge_txt}
                    </span>
                    <div style="color:#94a3b8; font-size:0.78rem; margin-top:0.2rem;">Línea Local: {p['spread_line_raw']:+g}</div>
                </div>
            </div>
            <div style="display:grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap:0.75rem; background:#080f0c; padding:0.8rem 1rem; border-radius:8px; align-items:center;">
                <div>
                    <div style="font-size:0.72rem; color:#64748b; font-weight:700;">SELECCIÓN MODELO</div>
                    <div style="font-size:1.1rem; color:#b7ff3c; font-weight:900;">{pick_txt}</div>
                </div>
                <div>
                    <div style="font-size:0.72rem; color:#64748b; font-weight:700;">PROB COBERTURA</div>
                    <div style="font-size:1.05rem; color:#ffffff; font-weight:800;">{prob_txt}</div>
                </div>
                <div>
                    <div style="font-size:0.72rem; color:#64748b; font-weight:700;">VALOR ESPERADO (EV)</div>
                    <div style="font-size:1.05rem; color:#b7ff3c; font-weight:800;">{ev_txt}</div>
                </div>
                <div>
                    <div style="font-size:0.72rem; color:#64748b; font-weight:700;">ROL</div>
                    <div style="font-size:0.95rem; color:#cbd5e1; font-weight:700;">{p.get('rol', 'Neutral')}</div>
                </div>
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)


def render_backtest_dashboard():
    """Muestra el reporte detallado del backtest institucional."""
    if not RUTA_REPORTE_BACKTEST.exists():
        st.warning("⚠️ No se encontró el reporte JSON del backtest. Ejecute `python nfl/backtest_spread.py`.")
        return

    with open(RUTA_REPORTE_BACKTEST, "r", encoding="utf-8") as f:
        rep = json.load(f)

    resumen = rep.get("resumen_oficial", {})
    desglose_temporada = rep.get("desglose_temporada", {})
    desglose_rol = rep.get("desglose_rol", {})
    desglose_lado = rep.get("desglose_lado", {})
    desglose_clave = rep.get("desglose_clave", {})
    comparativa = rep.get("comparativa_umbrales", {})

    st.markdown("### 📊 Rendimiento Institucional Fuera de Muestra (Out-of-Sample)")
    st.caption("Validación estricta en 682 partidos de las temporadas 2024, 2025 y 2026 bajo cuota estándar -110.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Picks Oficiales", resumen.get("total_picks", 0))
    with c2:
        st.metric("Récord Global", resumen.get("record", ""))
    with c3:
        st.metric("Win Rate", f"{resumen.get('win_rate_pct', 0.0)}%", delta=f"{resumen.get('win_rate_pct', 0.0) - 52.38:+.2f}% vs BEP")
    with c4:
        st.metric("Ganancia Neta", f"{resumen.get('unidades', 0.0):+.2f} U", delta=f"{resumen.get('roi_pct', 0.0):+.2f}% ROI")

    st.markdown("---")

    # Tabla 1: Comparativa por Umbral
    st.markdown("#### 🎯 1. Desempeño según Umbral de Probabilidad / Confianza")
    rows_comp = []
    for u, m in comparativa.items():
        rows_comp.append({
            "Umbral P": f"P >= {float(u):.3f}",
            "Picks": m.get("total_picks", 0),
            "Récord": m.get("record", ""),
            "Win Rate (%)": f"{m.get('win_rate_pct', 0.0):.2f}%",
            "Unidades": f"{m.get('unidades', 0.0):+.2f} U",
            "ROI (%)": f"{m.get('roi_pct', 0.0):+.2f}%",
            "Max Drawdown": f"{m.get('max_drawdown', 0.0):.2f} U",
            "Profit Factor": m.get("profit_factor", 0.0),
        })
    st.dataframe(pd.DataFrame(rows_comp), hide_index=True, use_container_width=True)

    # Tabla 2: Desglose por Temporada
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown("#### 📅 2. Desglose por Temporada")
        rows_temp = []
        for yr, m in desglose_temporada.items():
            rows_temp.append({
                "Temporada": yr,
                "Picks": m.get("total_picks", 0),
                "Récord": m.get("record", ""),
                "Win Rate (%)": f"{m.get('win_rate_pct', 0.0):.2f}%",
                "Unidades": f"{m.get('unidades', 0.0):+.2f} U",
                "ROI (%)": f"{m.get('roi_pct', 0.0):+.2f}%",
            })
        st.dataframe(pd.DataFrame(rows_temp), hide_index=True, use_container_width=True)

    with col_t2:
        st.markdown("#### 🛡️ 3. Desglose por Rol de Mercado")
        rows_rol = []
        for r, m in desglose_rol.items():
            rows_rol.append({
                "Rol": r,
                "Picks": m.get("total_picks", 0),
                "Récord": m.get("record", ""),
                "Win Rate (%)": f"{m.get('win_rate_pct', 0.0):.2f}%",
                "Unidades": f"{m.get('unidades', 0.0):+.2f} U",
                "ROI (%)": f"{m.get('roi_pct', 0.0):+.2f}%",
            })
        st.dataframe(pd.DataFrame(rows_rol), hide_index=True, use_container_width=True)

    col_t3, col_t4 = st.columns(2)
    with col_t3:
        st.markdown("#### 🏟️ 4. Desglose por Condición (Local vs Visitante)")
        rows_lado = []
        for s, m in desglose_lado.items():
            rows_lado.append({
                "Lado": "Visitante (AWAY)" if s == "AWAY" else "Local (HOME)",
                "Picks": m.get("total_picks", 0),
                "Récord": m.get("record", ""),
                "Win Rate (%)": f"{m.get('win_rate_pct', 0.0):.2f}%",
                "Unidades": f"{m.get('unidades', 0.0):+.2f} U",
                "ROI (%)": f"{m.get('roi_pct', 0.0):+.2f}%",
            })
        st.dataframe(pd.DataFrame(rows_lado), hide_index=True, use_container_width=True)

    with col_t4:
        st.markdown("#### 🔑 5. Desglose por Números Clave de la NFL")
        rows_clave = []
        for k, m in desglose_clave.items():
            rows_clave.append({
                "Grupo de Línea": k,
                "Picks": m.get("total_picks", 0),
                "Récord": m.get("record", ""),
                "Win Rate (%)": f"{m.get('win_rate_pct', 0.0):.2f}%",
                "Unidades": f"{m.get('unidades', 0.0):+.2f} U",
                "ROI (%)": f"{m.get('roi_pct', 0.0):+.2f}%",
            })
        st.dataframe(pd.DataFrame(rows_clave), hide_index=True, use_container_width=True)
