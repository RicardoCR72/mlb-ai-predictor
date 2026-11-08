"""Utilidad compartida para visualización y consulta de lesiones NFL en tarjetas de pronóstico."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
RUTA_LESIONES = RAIZ / "data" / "nfl" / "raw" / "nfl_injuries_2012_2026.parquet"


@st.cache_data(ttl=1800, show_spinner=False)
def obtener_lesiones_partido(equipo_visita: str, equipo_local: str) -> Dict[str, List[Dict[str, str]]]:
    """Extrae las bajas y dudas recientes de ambos equipos para el encuentro."""
    res: Dict[str, List[Dict[str, str]]] = {"visita": [], "local": []}
    if not RUTA_LESIONES.exists():
        return res

    try:
        df = pd.read_parquet(RUTA_LESIONES)
        if df.empty:
            return res

        max_season = int(df["season"].max())
        df_season = df[df["season"] == max_season]

        for rol, code in [("visita", equipo_visita), ("local", equipo_local)]:
            if not code:
                continue
            df_team = df_season[df_season["team"].astype(str).str.upper() == str(code).upper()]
            if df_team.empty:
                continue

            # Buscar última semana con actividad reportada
            con_reporte = df_team[df_team["report_status"].notna() | df_team["practice_status"].notna()]
            if con_reporte.empty:
                con_reporte = df_team

            max_week = int(con_reporte["week"].max())
            df_semana = con_reporte[con_reporte["week"] == max_week]

            # Ordenar por criticidad (Out > Doubtful > Questionable > otros)
            prioridad = {"OUT": 0, "DOUBTFUL": 1, "QUESTIONABLE": 2, "DNP": 3, "LIMITED": 4}
            filas = []
            for _, r in df_semana.iterrows():
                st_raw = str(r.get("report_status") or r.get("practice_status") or "Duda").strip()
                prio = prioridad.get(st_raw.upper(), 5)
                filas.append((prio, {
                    "jugador": str(r.get("full_name") or f"{r.get('first_name', '')} {r.get('last_name', '')}").strip(),
                    "posicion": str(r.get("position") or "N/D").strip(),
                    "estado": st_raw,
                    "lesion": str(r.get("report_primary_injury") or r.get("practice_primary_injury") or "Reporte oficial").strip(),
                }))

            filas.sort(key=lambda x: x[0])
            res[rol] = [item[1] for item in filas[:7]]
    except Exception:
        pass

    return res


def crear_callback_lesiones_nfl(
    equipo_visita: str,
    equipo_local: str,
    extra_context: Optional[str] = None,
) -> Optional[Callable[[], None]]:
    """Genera la función callback para la pestaña de Lesiones dentro de la Tarjeta Universal."""
    info_inj = obtener_lesiones_partido(equipo_visita, equipo_local)
    vis = info_inj.get("visita", [])
    loc = info_inj.get("local", [])

    if not vis and not loc and not extra_context:
        return None

    def _render():
        c1, c2 = st.columns(2)
        with c1:
            st.caption(f"**{equipo_visita} ({len(vis)} reportes)**")
            if vis:
                for inj in vis:
                    st_u = inj["estado"].upper()
                    color_b = "#ff4d4d" if ("OUT" in st_u or "IR" in st_u or "DNP" in st_u) else "#ffaa00"
                    st.markdown(
                        f"<div style='margin-bottom: 0.25rem;'><span style='background: #2a1005; color: {color_b}; border: 1px solid {color_b}; padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.72rem; font-weight: 800;'>{inj['estado']}</span> "
                        f"<span style='color: #ffffff; font-weight: 700; font-size: 0.82rem;'>{inj['jugador']}</span> <span style='color: #a4978e; font-size: 0.78rem;'>({inj['posicion']}) · {inj['lesion']}</span></div>",
                        unsafe_allow_html=True
                    )
            else:
                st.caption("Sin bajas críticas reportadas.")

        with c2:
            st.caption(f"**{equipo_local} ({len(loc)} reportes)**")
            if loc:
                for inj in loc:
                    st_u = inj["estado"].upper()
                    color_b = "#ff4d4d" if ("OUT" in st_u or "IR" in st_u or "DNP" in st_u) else "#ffaa00"
                    st.markdown(
                        f"<div style='margin-bottom: 0.25rem;'><span style='background: #2a1005; color: {color_b}; border: 1px solid {color_b}; padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.72rem; font-weight: 800;'>{inj['estado']}</span> "
                        f"<span style='color: #ffffff; font-weight: 700; font-size: 0.82rem;'>{inj['jugador']}</span> <span style='color: #a4978e; font-size: 0.78rem;'>({inj['posicion']}) · {inj['lesion']}</span></div>",
                        unsafe_allow_html=True
                    )
            else:
                st.caption("Sin bajas críticas reportadas.")

        if extra_context:
            st.caption(extra_context)

    return _render
