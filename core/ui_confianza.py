"""Calibración visible, CLV institucional, fiabilidad probabilística y gestión de riesgo."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import streamlit as st

from core.db import get_db_connection
from core.infrastructure.database import query_df
from core.confianza_datos import read_confidence
from core.confianza import prepare, reliability, temporal_trial, price_comparison
from core.diagnostico_confianza import market_summary
from core.ui_diseno import apply_design
from core.ui_controles import state_message
from core.ui_movil import apply_mobile_layout
from core.ui_rendimiento_diseno import safe_select

# Nuevos módulos cuantitativos institucionales
from core.clv import (
    calcular_metricas_clv_resumen,
    validar_mercado_dos_lados,
    auditar_balance_diario,
    calcular_vig
)
from core.calibracion_evaluador import (
    calcular_tabla_calibracion,
    generar_figura_diagrama_fiabilidad,
    CalibradorIsotonicoWalkForward
)
from core.gestion_riesgo import (
    calcular_kelly_fraccional,
    asignar_stakes_con_tope_de_partido
)

ROOT = Path(__file__).resolve().parents[1]


@st.cache_data(ttl=300, show_spinner=False)
def load():
    conn = None
    try:
        try:
            conn = get_db_connection()
        except Exception:
            pass
        return read_confidence(conn, ROOT)
    finally:
        if conn is not None:
            conn.close()


@st.cache_data(ttl=120, show_spinner=False)
def cargar_props_calibracion(deporte: str = "NBA") -> pd.DataFrame:
    """Carga los props liquidados desde MySQL para calibración y CLV."""
    try:
        if deporte == "NBA":
            sql = """
            SELECT fecha, jugador, mercado, seleccion, linea, cuota, probabilidad, 
                   resultado, valor_real, ev_pct, id_juego, clv_cuota, clv_linea, linea_cierre, cuota_cierre
            FROM nba_registro_props
            ORDER BY id DESC
            """
            return query_df(sql)
        elif deporte == "NFL":
            sql = """
            SELECT p.id_proyeccion, p.tipo_prop, p.linea, p.cuota_pick as cuota, 
                   p.probabilidad_pick as probabilidad, p.resultado_pick as resultado, 
                   p.valor_real, p.ev_estimado as ev_pct, p.id_juego, p.clv_cuota, p.clv_linea
            FROM nfl_proyecciones_props p
            ORDER BY p.id_proyeccion DESC
            """
            return query_df(sql)
    except Exception as err:
        st.warning(f"No se pudieron cargar datos de {deporte} desde MySQL: {err}")
    return pd.DataFrame()


def render():
    apply_mobile_layout()
    apply_design()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    hora_cdmx = datetime.now(ZoneInfo('America/Mexico_City')).strftime('%H:%M')

    st.markdown(
        '<div class="calib-shell">'
        '<div class="calib-brand">'
        '<span class="calib-logo">📐</span>'
        '<div>'
        '<div>OVERDOG <span class="calib-accent">CALIBRACIÓN AI & CLV</span></div>'
        '<div class="calib-status">Reliability Deciles · Brier Score & ECE · Closing Line Value · Kelly Fraccional</div>'
        '</div>'
        '</div>'
        f'<div style="text-align:right;">'
        f'<span style="background:#1f132e;color:#c084fc;padding:.3rem .75rem;border-radius:8px;font-size:.78rem;font-weight:800;border:1px solid #3b2057;">'
        f'🕒 {hora_cdmx} CDMX'
        f'</span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )

    pestana_calib, pestana_clv, pestana_riesgo, pestana_legacy = st.tabs([
        "🎯 Curva de Fiabilidad (ECE)",
        "📈 CLV & Eficiencia de Mercado",
        "🛡️ Gestión de Riesgo (Kelly)",
        "📊 Diagnóstico Legacy por Mercado"
    ])

    # =========================================================================
    # PESTAÑA 1: CURVA DE FIABILIDAD Y EVALUACIÓN POR BUCKETS
    # =========================================================================
    with pestana_calib:
        st.markdown("### 🎯 Fiabilidad Probabilística y Curva de Calibración")
        st.caption("Si el modelo dice **60%**, debe acertar el **60%** en la realidad. Brier Score y Expected Calibration Error (ECE) miden la veracidad matemática sin autoengaños de EV.")

        dep_sel = st.radio("Deporte a evaluar:", ["NBA Props", "NFL Props"], horizontal=True, key="calib_dep_sel")
        dep_clave = "NBA" if "NBA" in dep_sel else "NFL"
        df_props = cargar_props_calibracion(dep_clave)

        if not df_props.empty and "resultado" in df_props.columns:
            # Filtrar picks decididos
            df_decididos = df_props[df_props["resultado"].isin(["GANADA", "PERDIDA"])].copy()

            if not df_decididos.empty:
                p = df_decididos["probabilidad"]
                y = (df_decididos["resultado"] == "GANADA").astype(int)

                df_bins, metricas = calcular_tabla_calibracion(p, y, n_bins=5, prob_min=0.50, prob_max=0.75)

                # Tarjetas de Métricas Institucionales
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("Total Picks Evaluados", f"{metricas['n_muestras']}")
                with c2:
                    st.metric("Acierto Global Real", f"{metricas['acierto_global']*100:.1f}%")
                with c3:
                    ece_val = metricas['ece'] * 100.0
                    st.metric("Expected Calibration Error (ECE)", f"{ece_val:.2f}%", delta="Excelente (< 3%)" if ece_val < 3.0 else "Requiere calibración", delta_color="normal")
                with c4:
                    st.metric("Brier Score", f"{metricas['brier_score']:.4f}", help="0.0 es predicción perfecta; 0.25 es azar puro.")

                # Gráfica interactiva de fiabilidad Plotly
                fig_calib = generar_figura_diagrama_fiabilidad(df_bins, metricas)
                if fig_calib is not None:
                    st.plotly_chart(fig_calib, use_container_width=True)

                # Tabla por intervalos
                st.markdown("#### 📋 Desglose por Intervalos de Confianza")
                st.dataframe(
                    df_bins[[
                        "etiqueta", "picks_en_bucket", "probabilidad_media", "frecuencia_real", "error_calibracion", "sesgo"
                    ]],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "etiqueta": st.column_config.TextColumn("Rango de Probabilidad"),
                        "picks_en_bucket": st.column_config.NumberColumn("Volumen de Picks"),
                        "probabilidad_media": st.column_config.ProgressColumn("Prob. Media Modelo", format="%.1%", min_value=0.0, max_value=1.0),
                        "frecuencia_real": st.column_config.ProgressColumn("Acierto Real Observado", format="%.1%", min_value=0.0, max_value=1.0),
                        "error_calibracion": st.column_config.NumberColumn("Error Absoluto", format="%.2%"),
                        "sesgo": st.column_config.TextColumn("Diagnóstico del Sesgo")
                    }
                )
            else:
                st.info(f"Aún no hay suficientes picks decididos (GANADA/PERDIDA) en {dep_clave} para calcular la curva.")
        else:
            st.info(f"No hay datos registrados disponibles para {dep_clave}.")

    # =========================================================================
    # PESTAÑA 2: CLV (CLOSING LINE VALUE) Y AUDITORÍA DE MERCADO
    # =========================================================================
    with pestana_clv:
        st.markdown("### 📈 CLV (Closing Line Value) & Eficiencia de Mercado")
        st.caption("El CLV mide si tomaste mejor precio o mejor línea que el cierre del mercado. Bajar el precio de cierre de forma consistente es la prueba irrefutable de ventaja matemática a largo plazo.")

        col_clv1, col_clv2 = st.columns([1.5, 1])
        with col_clv1:
            st.markdown("#### 🏆 Resumen Institucional de CLV")
            df_clv_data = cargar_props_calibracion("NBA")
            res_clv = calcular_metricas_clv_resumen(df_clv_data)

            m_c1, m_c2, m_c3 = st.columns(3)
            with m_c1:
                st.metric("% Picks con +CLV", f"{res_clv['pct_beat_clv']}%", help="Porcentaje de selecciones que vencieron la cuota de cierre.")
            with m_c2:
                st.metric("CLV Cuota Promedio", f"+{res_clv['clv_cuota_promedio']}%", help="Ventaja porcentual de precio frente a la línea de cierre.")
            with m_c3:
                st.metric("ROI Esperado (vía CLV)", f"+{res_clv['roi_esperado_clv']}%")

        with col_clv2:
            st.markdown("#### 🛡️ Filtro de Vig Automático")
            st.caption("En mercados balanceados de dos lados, el overround o vig de la casa debe oscilar estrictamente entre **1.02 y 1.15**.")
            c_ov = st.number_input("Cuota Over:", value=1.91, step=0.05, format="%.2f")
            c_un = st.number_input("Cuota Under:", value=1.91, step=0.05, format="%.2f")
            es_val, v_calc, v_msg = validar_mercado_dos_lados(c_ov, c_un)
            if es_val:
                st.success(f"✅ Mercado Válido | Vig: **{v_calc:.4f}** ({((v_calc or 1)-1)*100:.2f}% comisión)")
            else:
                st.error(f"⚠️ {v_msg}")

        # Auditoría de Sesgo Direccional
        st.markdown("---")
        st.markdown("#### ⚖️ Auditoría de Sesgo Diario (Overs vs Unders)")
        st.caption("Regla de tolerancia de sobreexposición: Alerta si más del 70% de los picks del día van orientados al mismo lado.")
        if not df_clv_data.empty:
            fecha_max = df_clv_data["fecha"].max()
            df_hoy = df_clv_data[df_clv_data["fecha"] == fecha_max]
            ok_sesgo, msg_sesgo, stats_sesgo = auditar_balance_diario(df_hoy.to_dict(orient="records"), umbral_sesgo=0.70)
            b1, b2, b3 = st.columns(3)
            with b1:
                st.metric("Picks Jornada Reciente", f"{stats_sesgo['total']}")
            with b2:
                st.metric("Overs", f"{stats_sesgo['overs']} ({stats_sesgo['pct_overs']*100:.1f}%)")
            with b3:
                st.metric("Unders", f"{stats_sesgo['unders']} ({stats_sesgo['pct_unders']*100:.1f}%)")

            if ok_sesgo:
                st.success(f"✅ {msg_sesgo}")
            else:
                st.warning(f"{msg_sesgo}")

    # =========================================================================
    # PESTAÑA 3: GESTIÓN DE RIESGO Y KELLY FRACCIONAL
    # =========================================================================
    with pestana_riesgo:
        st.markdown("### 🛡️ Gestión de Riesgo Cuantitativo: Kelly Fraccional y Correlación")
        st.caption("Asignación matemática de capital basada en **Quarter Kelly (1/4)** con candado de correlación por partido (máximo 6.0% del bankroll acumulado por juego).")

        c_k1, c_k2 = st.columns(2)
        with c_k1:
            st.markdown("#### 🧮 Calculadora de Kelly Fraccional Individual")
            prob_in = st.slider("Probabilidad Calibrada de la Selección:", 0.50, 0.75, 0.58, step=0.01)
            cuota_in = st.number_input("Cuota Decimal del Pick:", value=1.91, step=0.05, format="%.2f")
            frac_sel = st.selectbox("Fracción de Kelly:", ["1/4 Kelly (Recomendado)", "1/8 Kelly (Conservador)", "Full Kelly (Peligro: Alta Varianza)"])
            alpha = 0.25 if "1/4" in frac_sel else (0.125 if "1/8" in frac_sel else 1.0)

            k_calc = calcular_kelly_fraccional(prob_in, cuota_in, fraccion=alpha)
            st.markdown(f"**Stake Recomendado:** `{k_calc['stake_recomendado_pct']*100:.2f}%` del bankroll")
            st.markdown(f"**Valor Esperado (+EV):** `+{k_calc['ev_esperado_pct']}%`")

        with c_k2:
            st.markdown("#### 🔒 Candado de Correlación por Partido")
            st.info(
                "**¿Por qué limitar por partido?**\n\n"
                "Si seleccionas el Over de puntos de Tatum, el Over de asistencias de Brown y el Under de un rival en el mismo juego, "
                "los 3 picks están fuertemente correlacionados (si hay blowout o prórroga, ganan o pierden juntos). "
                "El motor aplica un **factor de escala automático** para asegurar que ningún partido concentre más del **6.0% de tu capital**."
            )

    # =========================================================================
    # PESTAÑA 4: DIAGNÓSTICO LEGACY POR MERCADO
    # =========================================================================
    with pestana_legacy:
        st.caption('Compara probabilidades proyectadas con resultados históricos reales para evaluar la fiabilidad matemática del modelo.')
        if st.button('Recargar historial guardado', key='confidence_refresh', type='primary'):
            load.clear()
            st.rerun()
        raw, errors = load()
        for error in errors:
            st.caption(error)
        clean, excluded = prepare(raw)
        if clean.empty:
            state_message('Aún no hay resultados decididos con probabilidades válidas para evaluar.')
            return

        with st.expander('Diagnóstico por mercado y versión', expanded=True):
            overview = pd.DataFrame(market_summary(clean))
            st.caption('Cada fila mantiene separados deporte, mercado, versión y procedencia. Diferencia = acierto real menos confianza; un valor negativo indica que la confianza fue mayor que el acierto observado.')
            over_cfg = {
                'deporte': st.column_config.TextColumn('Deporte', width='small'),
                'mercado': st.column_config.TextColumn('Mercado', width='medium'),
                'modelo': st.column_config.TextColumn('Modelo', width='medium'),
                'procedencia': st.column_config.TextColumn('Procedencia', width='medium'),
                'picks': st.column_config.NumberColumn('Picks', format='%d'),
                'confianza': st.column_config.ProgressColumn('Confianza Estimada', format='%.1%', min_value=0.0, max_value=1.0),
                'acierto': st.column_config.ProgressColumn('Acierto Real', format='%.1%', min_value=0.0, max_value=1.0),
                'diferencia': st.column_config.NumberColumn('Diferencia (pp)', format='%+.1%'),
                'brier': st.column_config.NumberColumn('Brier Score', format='%.4f'),
                'logloss': st.column_config.NumberColumn('Log-Loss', format='%.4f'),
            }
            st.dataframe(overview, hide_index=True, width='stretch', column_config=over_cfg)

        sport = safe_select('Deporte', sorted(clean.deporte.unique()), key='confidence_sport')
        f = clean[clean.deporte.eq(sport)]
        market = safe_select('Mercado', sorted(f.mercado.unique()), key='confidence_market')
        f = f[f.mercado.eq(market)]
        model = safe_select('Versión del modelo', sorted(f.modelo.unique()), key='confidence_model')
        f = f[f.modelo.eq(model)]
        table = reliability(f)
        st.subheader('Confianza frente a acierto real')
        rel_cfg = {
            'rango': st.column_config.TextColumn('Rango de Confianza', width='medium'),
            'picks': st.column_config.NumberColumn('Picks', format='%d'),
            'partidos': st.column_config.NumberColumn('Partidos', format='%d'),
            'confianza': st.column_config.ProgressColumn('Confianza Media', format='%.1%', min_value=0.0, max_value=1.0),
            'acierto': st.column_config.ProgressColumn('Acierto Observado', format='%.1%', min_value=0.0, max_value=1.0),
            'diferencia': st.column_config.NumberColumn('Diferencia', format='%+.1%'),
            'evidencia': st.column_config.TextColumn('Evidencia Muestra', width='medium'),
        }
        st.dataframe(table, hide_index=True, width='stretch', column_config=rel_cfg)
