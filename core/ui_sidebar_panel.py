"""Componente unificado de alto diseño para la barra lateral (Sidebar)."""
from __future__ import annotations

import streamlit as st
from core.alerts import get_telegram_config, get_discord_config
from core.ui_boleta import render_widget_boleta


def render_sidebar_panel():
    """Renderiza las herramientas, boleta y centro de notificaciones con diseño premium."""
    st.markdown(
        """<div class="sidebar-header-box">
          <div class="sidebar-live-dot"></div>
          <div class="sidebar-header-title">CENTRO DE OPERACIONES</div>
        </div>""",
        unsafe_allow_html=True,
    )

    # 1. Boleta del Día
    render_widget_boleta(sidebar=True)

    # 2. Centro de Alertas (+EV)
    t_tok, t_chat = get_telegram_config()
    d_url = get_discord_config()

    titulo_alertas = "📢 Notificaciones (+EV) · Conectado" if (t_tok or d_url) else "📢 Notificaciones (+EV)"

    with st.expander(titulo_alertas, expanded=False):
        if t_tok:
            st.markdown(
                """<div class="sidebar-alert-card">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem;">
                    <span style="font-size:0.72rem; font-weight:800; color:#e2e8f0; letter-spacing:0.04em;">TELEGRAM BOT</span>
                    <span class="sidebar-status-pill">● EN VIVO</span>
                  </div>
                  <div style="font-size:0.75rem; color:#cbd5e1;">Destino: <b style="color:#00e5ff;">@DeportesAIbot</b></div>
                </div>""",
                unsafe_allow_html=True,
            )
        elif d_url:
            st.markdown(
                """<div class="sidebar-alert-card">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem;">
                    <span style="font-size:0.72rem; font-weight:800; color:#e2e8f0; letter-spacing:0.04em;">DISCORD WEBHOOK</span>
                    <span class="sidebar-status-pill">● ACTIVO</span>
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )
        else:
            st.info("Configura tu bot de Telegram o webhook en `.streamlit/secrets.toml`.")

        st.caption("Filtra y despacha las mayores ventajas estadísticas (+4.5% Edge) de la jornada.")

        if st.button("🚀 Despachar Alerta (+EV)", key="btn_alerta_sidebar", use_container_width=True, type="primary"):
            from scripts.notificar_picks_alto_ev import ejecutar_notificador
            with st.spinner("Escaneando cuotas y enviando..."):
                res = ejecutar_notificador()
            if res.get("ok"):
                st.success(f"¡Alerta enviada con éxito ({res.get('total_picks')} picks)!")
            else:
                st.warning(f"No se pudo enviar: {res.get('error', 'Revisa conexión')}")

    # 3. Pie de página estilizado
    st.markdown(
        """<div class="sidebar-footer-card">
          <div class="sidebar-sports-pills">
            <span class="sidebar-sport-tag">⚾ MLB</span>
            <span class="sidebar-sport-tag">🏈 NFL</span>
            <span class="sidebar-sport-tag">⚽ Fútbol (8 Ligas)</span>
            <span class="sidebar-sport-tag">🏀 NBA</span>
          </div>
          <div class="sidebar-footer-caption">ORÁCULO SPORTS AI · v2.5 PRO</div>
        </div>""",
        unsafe_allow_html=True,
    )
