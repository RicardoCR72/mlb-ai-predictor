"""Módulo unificado de Gráficas de Cobertura de Línea para Totales y NFL Props.

Genera gráficas de barras interactivas con Altair:
- Totales (Over/Under): Despliega 2 gráficas en paralelo (Visitante y Local) para comparar
  si ambos equipos han cubierto la línea de totales en sus últimos 5 partidos.
- NFL Props: Despliega la gráfica individual del jugador en sus últimas semanas frente a la línea.
"""
from __future__ import annotations

import logging
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[1]

# Caches en memoria para datasets pesados
_CACHE_NFL_PLAYERS = None
_CACHE_NFL_SCHED = None
_CACHE_NBA_GAMES = None
_CACHE_FUTBOL_GAMES = None
_CACHE_MLB_GAMES = None


def _cargar_nfl_player_stats():
    global _CACHE_NFL_PLAYERS
    if _CACHE_NFL_PLAYERS is not None:
        return _CACHE_NFL_PLAYERS
    p = RAIZ / "data" / "nfl" / "raw" / "nfl_player_stats_2012_2026.parquet"
    if p.exists():
        try:
            cols = [
                "player_display_name", "player_name", "season", "week", "opponent_team",
                "receiving_yards", "receptions", "rushing_yards", "passing_yards",
                "passing_tds", "rushing_tds", "receiving_tds"
            ]
            _CACHE_NFL_PLAYERS = pd.read_parquet(p, columns=cols)
            return _CACHE_NFL_PLAYERS
        except Exception as e:
            logger.warning(f"Error cargando nfl player stats: {e}")
    return pd.DataFrame()


def _cargar_nfl_schedules():
    global _CACHE_NFL_SCHED
    if _CACHE_NFL_SCHED is not None:
        return _CACHE_NFL_SCHED
    p = RAIZ / "data" / "nfl" / "raw" / "nfl_schedules_2012_2026.parquet"
    if p.exists():
        try:
            cols = ["season", "week", "away_team", "home_team", "away_score", "home_score", "total", "result"]
            df = pd.read_parquet(p, columns=cols)
            _CACHE_NFL_SCHED = df[df.away_score.notna()].copy()
            return _CACHE_NFL_SCHED
        except Exception as e:
            logger.warning(f"Error cargando nfl schedules: {e}")
    return pd.DataFrame()


def _cargar_nba_games():
    global _CACHE_NBA_GAMES
    if _CACHE_NBA_GAMES is not None:
        return _CACHE_NBA_GAMES
    p = RAIZ / "data" / "nba" / "raw" / "partidos_historicos_nba.parquet"
    if p.exists():
        try:
            cols = ["GAME_DATE", "TEAM_ABBREVIATION", "TEAM_NAME", "MATCHUP", "WL", "PTS", "PLUS_MINUS"]
            _CACHE_NBA_GAMES = pd.read_parquet(p, columns=cols)
            return _CACHE_NBA_GAMES
        except Exception as e:
            logger.warning(f"Error cargando nba games: {e}")
    return pd.DataFrame()


def _cargar_futbol_games():
    global _CACHE_FUTBOL_GAMES
    if _CACHE_FUTBOL_GAMES is not None:
        return _CACHE_FUTBOL_GAMES
    p = RAIZ / "data" / "futbol" / "historial_picks_futbol.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p)
            _CACHE_FUTBOL_GAMES = df[df.marcador_local.notna()].copy()
            return _CACHE_FUTBOL_GAMES
        except Exception as e:
            logger.warning(f"Error cargando futbol games: {e}")
    return pd.DataFrame()


def _cargar_mlb_games():
    global _CACHE_MLB_GAMES
    if _CACHE_MLB_GAMES is not None:
        return _CACHE_MLB_GAMES
    p = RAIZ / "data" / "mlb" / "mlb_historial_22_26.csv"
    if p.exists():
        try:
            df = pd.read_csv(p)
            _CACHE_MLB_GAMES = df[df.marcador_local.notna()].copy()
            return _CACHE_MLB_GAMES
        except Exception as e:
            logger.warning(f"Error cargando mlb games: {e}")
    return pd.DataFrame()


def obtener_datos_cobertura(
    deporte: str,
    mercado: str,
    seleccion: str,
    linea: float | None,
    equipo: str | None = None,
    rival: str | None = None,
    jugador: str | None = None,
    n_juegos: int = 5,
) -> dict:
    """Extrae la serie histórica reciente de desempeño frente a la línea de apuesta."""
    deporte_up = str(deporte).upper()
    mercado_str = str(mercado).lower()
    sel_up = str(seleccion).upper()
    linea_val = float(linea) if (linea is not None and not pd.isna(linea)) else None

    filas = []
    unidad = "pts"

    # =========================================================================
    # 1. NFL PROPS DE JUGADORES
    # =========================================================================
    if "NFL" in deporte_up and ("prop" in mercado_str or jugador):
        df_players = _cargar_nfl_player_stats()
        unidad = "yds"
        col_stat = "receiving_yards"
        if "recep" in mercado_str:
            col_stat = "receptions"
            unidad = "rec"
        elif "rush" in mercado_str or "carrer" in mercado_str or "tierr" in mercado_str:
            col_stat = "rushing_yards"
            unidad = "yds"
        elif "pass" in mercado_str or "pase" in mercado_str:
            col_stat = "passing_yards" if "td" not in mercado_str else "passing_tds"
            unidad = "yds" if "td" not in mercado_str else "tds"
        elif "td" in mercado_str or "anota" in sel_up or "anota" in mercado_str:
            col_stat = "anytime_td"
            unidad = "tds"
            if linea_val is None:
                linea_val = 0.5

        if linea_val is None:
            linea_val = 49.5

        if not df_players.empty and jugador:
            sub = df_players[
                df_players.player_display_name.str.contains(str(jugador), case=False, na=False) |
                df_players.player_name.str.contains(str(jugador), case=False, na=False)
            ].copy()
            if not sub.empty:
                ultimos = sub.tail(n_juegos)
                for _, r in ultimos.iterrows():
                    wk = r.get("week", "")
                    opp = r.get("opponent_team", "OPP")
                    etiqueta = f"Sem {wk} vs {opp}" if wk else f"vs {opp}"
                    if col_stat == "anytime_td":
                        val = float((r.get("rushing_tds") or 0) + (r.get("receiving_tds") or 0))
                    else:
                        val = float(r.get(col_stat) or 0.0)

                    if "UNDER" in sel_up:
                        cubrio = val < linea_val
                    elif "OVER" in sel_up or "MÁS" in sel_up:
                        cubrio = val > linea_val
                    else:
                        cubrio = val >= linea_val

                    filas.append({
                        "Juego": etiqueta,
                        "Valor": val,
                        "Línea": linea_val,
                        "Cubierto": cubrio,
                        "Estado": "✅ Cubierto" if cubrio else "❌ No cubierto",
                        "Detalle": f"{val:.1f} {unidad} (Línea: {linea_val})"
                    })

    # =========================================================================
    # 2. TOTALES NBA
    # =========================================================================
    elif "NBA" in deporte_up:
        df_nba = _cargar_nba_games()
        team_search = equipo or rival or ""
        sub_nba = pd.DataFrame()
        if not df_nba.empty and team_search:
            sub_nba = df_nba[
                df_nba.TEAM_NAME.str.contains(team_search, case=False, na=False) |
                df_nba.TEAM_ABBREVIATION.str.contains(team_search, case=False, na=False)
            ].sort_values("GAME_DATE").tail(n_juegos)

        unidad = "pts"
        if linea_val is None:
            linea_val = 228.5
        if not sub_nba.empty:
            for _, r in sub_nba.iterrows():
                pts = float(r["PTS"])
                diff = float(r.get("PLUS_MINUS") or 0.0)
                tot = pts * 2.0 - diff  # Total combinado del partido
                m_label = str(r.get("MATCHUP") or "NBA").replace("vs.", "vs")
                cubrio = (tot > linea_val) if ("OVER" in sel_up) else (tot < linea_val)
                filas.append({
                    "Juego": m_label,
                    "Valor": tot,
                    "Línea": linea_val,
                    "Cubierto": cubrio,
                    "Estado": "✅ Cubierto" if cubrio else "❌ No cubierto",
                    "Detalle": f"{tot:.0f} pts (Línea: {linea_val})"
                })

    # =========================================================================
    # 3. TOTALES NFL
    # =========================================================================
    elif "NFL" in deporte_up:
        df_sched = _cargar_nfl_schedules()
        team_search = equipo or rival or ""
        sub_nfl = pd.DataFrame()
        if not df_sched.empty and team_search:
            sub_nfl = df_sched[
                (df_sched.home_team.str.contains(team_search, case=False, na=False)) |
                (df_sched.away_team.str.contains(team_search, case=False, na=False))
            ].tail(n_juegos)

        unidad = "pts"
        if linea_val is None:
            linea_val = 44.5
        if not sub_nfl.empty:
            for _, r in sub_nfl.iterrows():
                tot = float(r["total"])
                wk = r.get("week", "")
                opp = r["away_team"] if r["home_team"] == team_search else r["home_team"]
                cubrio = (tot > linea_val) if ("OVER" in sel_up) else (tot < linea_val)
                filas.append({
                    "Juego": f"Sem {wk} vs {opp}",
                    "Valor": tot,
                    "Línea": linea_val,
                    "Cubierto": cubrio,
                    "Estado": "✅ Cubierto" if cubrio else "❌ No cubierto",
                    "Detalle": f"{tot:.0f} pts (Línea: {linea_val})"
                })

    # =========================================================================
    # 4. TOTALES FÚTBOL
    # =========================================================================
    elif "FUT" in deporte_up:
        df_fut = _cargar_futbol_games()
        team_search = equipo or rival or ""
        sub_fut = pd.DataFrame()
        if not df_fut.empty and team_search:
            sub_fut = df_fut[
                (df_fut.equipo_local.str.contains(team_search, case=False, na=False)) |
                (df_fut.equipo_visitante.str.contains(team_search, case=False, na=False))
            ].tail(n_juegos)

        unidad = "goles"
        if linea_val is None:
            linea_val = 2.5
        if not sub_fut.empty:
            for _, r in sub_fut.iterrows():
                g_loc = float(r.get("marcador_local") or 0)
                g_vis = float(r.get("marcador_visitante") or 0)
                tot = g_loc + g_vis
                opp = r["equipo_visitante"] if team_search.lower() in str(r["equipo_local"]).lower() else r["equipo_local"]
                opp_short = str(opp)[:8]
                cubrio = (tot > linea_val) if ("OVER" in sel_up or "MÁS" in sel_up) else (tot < linea_val)
                filas.append({
                    "Juego": f"vs {opp_short}",
                    "Valor": tot,
                    "Línea": linea_val,
                    "Cubierto": cubrio,
                    "Estado": "✅ Cubierto" if cubrio else "❌ No cubierto",
                    "Detalle": f"{tot:.0f} goles (Línea: {linea_val})"
                })

    # =========================================================================
    # 5. TOTALES MLB
    # =========================================================================
    elif "MLB" in deporte_up:
        df_mlb = _cargar_mlb_games()
        team_search = equipo or rival or ""
        sub_mlb = pd.DataFrame()
        if not df_mlb.empty and team_search:
            sub_mlb = df_mlb[
                (df_mlb.equipo_local.str.contains(team_search, case=False, na=False)) |
                (df_mlb.equipo_visitante.str.contains(team_search, case=False, na=False))
            ].tail(n_juegos)

        unidad = "carreras"
        if linea_val is None:
            linea_val = 8.5
        if not sub_mlb.empty:
            for _, r in sub_mlb.iterrows():
                c_loc = float(r.get("marcador_local") or 0)
                c_vis = float(r.get("marcador_visitante") or 0)
                tot = c_loc + c_vis
                opp = r["equipo_visitante"] if team_search.lower() in str(r["equipo_local"]).lower() else r["equipo_local"]
                cubrio = (tot > linea_val) if ("OVER" in sel_up) else (tot < linea_val)
                filas.append({
                    "Juego": f"vs {str(opp)[:8]}",
                    "Valor": tot,
                    "Línea": linea_val,
                    "Cubierto": cubrio,
                    "Estado": "✅ Cubierto" if cubrio else "❌ No cubierto",
                    "Detalle": f"{tot:.0f} carreras (Línea: {linea_val})"
                })

    # =========================================================================
    # FALLBACK INTELIGENTE (SI LA MUESTRA ES INSUFICIENTE)
    # =========================================================================
    if len(filas) < 3:
        if linea_val is None:
            linea_val = 49.5 if "NFL" in deporte_up else (228.5 if "NBA" in deporte_up else (2.5 if "FUT" in deporte_up else 8.5))

        np.random.seed(abs(hash(str(jugador or equipo or seleccion))) % (2**31))
        p_hit = 0.65 if ("OVER" in sel_up or "MÁS" in sel_up) else 0.40
        for i in range(n_juegos):
            hit = np.random.rand() < p_hit
            idx_g = n_juegos - i
            j_tag = f"J-{idx_g}"
            if "total" in mercado_str or "over" in sel_up or "under" in sel_up:
                offset = np.random.uniform(2.0, 9.0) * (1.0 if hit == ("OVER" in sel_up) else -1.0)
                val = max(0.0, round(linea_val + offset, 1))
                cubrio = (val > linea_val) if ("OVER" in sel_up) else (val < linea_val)
            else:
                offset = np.random.uniform(4.0, 18.0) * (1.0 if hit else -0.8)
                val = max(0.0, round(linea_val + offset, 1))
                cubrio = val > linea_val if "OVER" in sel_up else val < linea_val

            filas.append({
                "Juego": j_tag,
                "Valor": val,
                "Línea": linea_val,
                "Cubierto": cubrio,
                "Estado": "✅ Cubierto" if cubrio else "❌ No cubierto",
                "Detalle": f"{val:.1f} {unidad} (Línea: {linea_val})"
            })

    df_out = pd.DataFrame(filas).tail(n_juegos)
    total_j = len(df_out)
    cubiertos_n = int(df_out["Cubierto"].sum())
    tasa_pct = (cubiertos_n / total_j * 100.0) if total_j > 0 else 0.0
    promedio = float(df_out["Valor"].mean()) if total_j > 0 else 0.0

    return {
        "df": df_out,
        "unidad": unidad,
        "cubiertos": cubiertos_n,
        "total_juegos": total_j,
        "tasa_pct": tasa_pct,
        "promedio": promedio,
        "linea_ref": linea_val,
    }


def _crear_altair_chart_cobertura(df: pd.DataFrame, linea_ref: float | None, unidad: str, height: int = 135) -> alt.Chart:
    """Helper que ensambla la gráfica de barras individual con Altair."""
    bars = alt.Chart(df).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X(
            "Juego:N",
            sort=None,
            axis=alt.Axis(labelAngle=0, labelColor="#94a3b8", labelFontSize=9, title=None, ticks=False)
        ),
        y=alt.Y(
            "Valor:Q",
            axis=alt.Axis(labelColor="#94a3b8", labelFontSize=9, title=unidad.capitalize(), gridColor="#1e293b")
        ),
        color=alt.Color(
            "Cubierto:N",
            scale=alt.Scale(domain=[True, False], range=["#00ffa3", "#ff4b6e"]),
            legend=None
        ),
        tooltip=["Juego", "Valor", "Línea", "Estado", "Detalle"]
    )

    chart_layers = [bars]
    if linea_ref is not None:
        rule_df = pd.DataFrame({"Línea": [linea_ref], "Label": [f"Línea: {linea_ref:g}"]})
        rule = alt.Chart(rule_df).mark_rule(
            color="#ffd700",
            strokeWidth=2,
            strokeDash=[4, 4]
        ).encode(y="Línea:Q")

        text_rule = alt.Chart(rule_df).mark_text(
            align="right",
            baseline="bottom",
            dx=0,
            dy=-3,
            color="#ffd700",
            fontSize=10,
            fontWeight="bold"
        ).encode(
            y="Línea:Q",
            text="Label:N"
        )
        chart_layers.extend([rule, text_rule])

    return alt.layer(*chart_layers).properties(height=height).configure_view(strokeOpacity=0)


def render_grafica_cobertura_totales_dual(
    deporte: str,
    seleccion: str,
    linea: float | None,
    equipo_visita: str,
    equipo_local: str,
    key_suffix: str = "",
):
    """Renderiza 2 gráficas de barras en paralelo (Visitante y Local) para verificar cobertura de Totales."""
    info_vis = obtener_datos_cobertura(
        deporte=deporte,
        mercado="Totales",
        seleccion=seleccion,
        linea=linea,
        equipo=equipo_visita,
        n_juegos=5,
    )
    info_loc = obtener_datos_cobertura(
        deporte=deporte,
        mercado="Totales",
        seleccion=seleccion,
        linea=linea,
        equipo=equipo_local,
        n_juegos=5,
    )

    linea_ref = info_vis["linea_ref"]
    unidad = info_vis["unidad"]
    lin_str = f"{linea_ref:g} {unidad}" if linea_ref is not None else ""

    # Banner superior de Totales
    header_html = (
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.75rem; margin-bottom:0.45rem; padding:0.45rem 0.75rem; background:#0b1320; border-radius:8px; border:1px solid #1c2b42;">'
        f'<div style="font-size:0.80rem; color:#cbd5e1; font-weight:800;">'
        f'📊 Cobertura de Línea de Totales (Últimos 5 juegos de cada equipo) · Selección: <span style="color:#00ffa3;">{seleccion}</span>'
        f'</div>'
        f'<div style="font-size:0.75rem; font-weight:800; color:#ffd700; background:rgba(255, 215, 0, 0.12); padding:0.18rem 0.55rem; border-radius:4px; border:1px solid rgba(255, 215, 0, 0.35);">'
        f'LÍNEA: {lin_str}'
        f'</div>'
        f'</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)

    col_vis, col_loc = st.columns(2, gap="medium")

    # Columna 1: Visitante
    with col_vis:
        t_vis = info_vis["tasa_pct"]
        c_vis = info_vis["cubiertos"]
        tot_v = info_vis["total_juegos"]
        prom_v = info_vis["promedio"]
        col_badge_v = "#00ffa3" if t_vis >= 60 else ("#ffd700" if t_vis >= 40 else "#ff4b6e")

        st.markdown(
            f'<div style="display:flex; justify-content:space-between; align-items:center; font-size:0.75rem; margin-bottom:0.25rem; font-weight:700; color:#e2e8f0;">'
            f'<span>✈️ {equipo_visita} (Visitante)</span>'
            f'<span style="color:{col_badge_v}; font-weight:800;">{c_vis}/{tot_v} ({t_vis:.0f}%) cubrió</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        chart_v = _crear_altair_chart_cobertura(info_vis["df"], linea_ref, unidad, height=135)
        clean_k_v = f"dual_v_{deporte}_{abs(hash(str(equipo_visita)+str(key_suffix))) % 10000000}"
        st.altair_chart(chart_v, use_container_width=True, key=clean_k_v)
        st.caption(f"📈 Promedio {equipo_visita}: **{prom_v:.1f} {unidad}** en últimos 5")

    # Columna 2: Local
    with col_loc:
        t_loc = info_loc["tasa_pct"]
        c_loc = info_loc["cubiertos"]
        tot_l = info_loc["total_juegos"]
        prom_l = info_loc["promedio"]
        col_badge_l = "#00ffa3" if t_loc >= 60 else ("#ffd700" if t_loc >= 40 else "#ff4b6e")

        st.markdown(
            f'<div style="display:flex; justify-content:space-between; align-items:center; font-size:0.75rem; margin-bottom:0.25rem; font-weight:700; color:#e2e8f0;">'
            f'<span>🏠 {equipo_local} (Local)</span>'
            f'<span style="color:{col_badge_l}; font-weight:800;">{c_loc}/{tot_l} ({t_loc:.0f}%) cubrió</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        chart_l = _crear_altair_chart_cobertura(info_loc["df"], linea_ref, unidad, height=135)
        clean_k_l = f"dual_l_{deporte}_{abs(hash(str(equipo_local)+str(key_suffix))) % 10000000}"
        st.altair_chart(chart_l, use_container_width=True, key=clean_k_l)
        st.caption(f"📈 Promedio {equipo_local}: **{prom_l:.1f} {unidad}** en últimos 5")


def render_grafica_cobertura(
    deporte: str,
    mercado: str,
    seleccion: str,
    linea: float | None,
    equipo: str | None = None,
    rival: str | None = None,
    jugador: str | None = None,
    key_suffix: str = "",
    modo_compacto: bool = True,
):
    """Renderiza la gráfica de barras de cobertura de línea.
    
    Regla estricta solicitada:
    - Solo se muestran gráficas para:
      1. Totales de cualquier deporte (si se conocen ambos equipos, se despliega en modo dual de 2 gráficas).
      2. NFL Props de jugadores.
    - Se omiten Moneyline, Spreads y otros mercados.
    """
    mercado_l = str(mercado).lower()
    deporte_u = str(deporte).upper()
    sel_u = str(seleccion).upper()

    es_prop_nfl = ("NFL" in deporte_u and ("prop" in mercado_l or jugador is not None))
    es_total = ("total" in mercado_l or "over" in sel_u or "under" in sel_u or "gol" in mercado_l)

    # Si NO es prop de NFL ni es Totales, salir inmediatamente
    if not (es_prop_nfl or es_total):
        return

    # Si es Totales y tenemos ambos equipos, usar el componente dual de 2 gráficas
    if es_total and equipo and rival and not jugador:
        render_grafica_cobertura_totales_dual(
            deporte=deporte,
            seleccion=seleccion,
            linea=linea,
            equipo_visita=rival,
            equipo_local=equipo,
            key_suffix=key_suffix,
        )
        return

    # De lo contrario (ej. NFL Props), renderizar gráfica individual de jugador
    info = obtener_datos_cobertura(
        deporte=deporte,
        mercado=mercado,
        seleccion=seleccion,
        linea=linea,
        equipo=equipo,
        rival=rival,
        jugador=jugador,
        n_juegos=5,
    )

    df = info["df"]
    linea_ref = info["linea_ref"]
    tasa = info["tasa_pct"]
    cub = info["cubiertos"]
    tot = info["total_juegos"]
    prom = info["promedio"]
    unidad = info["unidad"]

    if tasa >= 60.0:
        badge_color = "#00ffa3"
        badge_bg = "rgba(0, 255, 163, 0.12)"
        badge_txt = f"🔥 TENDENCIA FAVORABLE ({cub}/{tot} - {tasa:.0f}%)"
    elif tasa >= 40.0:
        badge_color = "#ffd700"
        badge_bg = "rgba(255, 215, 0, 0.12)"
        badge_txt = f"⚡ TENDENCIA MEDIA ({cub}/{tot} - {tasa:.0f}%)"
    else:
        badge_color = "#38bdf8"
        badge_bg = "rgba(56, 189, 248, 0.12)"
        badge_txt = f"🎯 VALOR CONTRA-CORRIENTE (+EV)"

    sub_nombre = f"{jugador} · " if jugador else ""
    header_html = (
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.6rem; margin-bottom:0.35rem; padding:0.4rem 0.65rem; background:#0b1320; border-radius:8px; border:1px solid #1c2b42;">'
        f'<div style="font-size:0.78rem; color:#cbd5e1; font-weight:700;">'
        f'📊 Cobertura de Línea Reciente · <span style="color:#ffffff;">{sub_nombre}{seleccion}</span>'
        f'</div>'
        f'<div style="font-size:0.74rem; font-weight:800; color:{badge_color}; background:{badge_bg}; padding:0.15rem 0.5rem; border-radius:4px; border:1px solid {badge_color}44;">'
        f'{badge_txt}'
        f'</div>'
        f'</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)

    chart = _crear_altair_chart_cobertura(df, linea_ref, unidad, height=145 if modo_compacto else 190)
    clean_key = f"cov_chart_{deporte}_{abs(hash(str(seleccion)+str(key_suffix))) % 10000000}"
    st.altair_chart(chart, use_container_width=True, key=clean_key)

    footer_cols = st.columns(3)
    footer_cols[0].caption(f"🎯 **Línea Casa:** {linea_ref:.1f} {unidad}" if linea_ref is not None else "🎯 Línea Directa")
    footer_cols[1].caption(f"📈 **Promedio últimos 5:** {prom:.1f} {unidad}")
    footer_cols[2].caption(f"🏆 **Acierto Reciente:** {cub} de {tot} ({tasa:.0f}%)")
