"""Módulo unificado de 'Boleta del Día' (Bet Slip / Mi Selección) para deportes múltiples."""
from __future__ import annotations
import math
import streamlit as st


def parsear_cuota_decimal(cuota: str | float | None) -> float:
    """Convierte cualquier formato de momio (americano o decimal) a cuota decimal."""
    if cuota is None:
        return 1.91
    try:
        val = str(cuota).strip()
        # Si tiene paréntesis como "-110 (1.91)"
        if "(" in val and ")" in val:
            inner = val.split("(")[1].split(")")[0].strip()
            return float(inner)
        # Si es formato americano "+150" o "-110"
        if val.startswith("+"):
            return round(1.0 + float(val[1:]) / 100.0, 3)
        if val.startswith("-"):
            denom = float(val[1:])
            return round(1.0 + 100.0 / denom, 3) if denom > 0 else 1.91
        num = float(val)
        if num > 100:
            return round(1.0 + num / 100.0, 3)
        if num < -100:
            return round(1.0 + 100.0 / abs(num), 3)
        if num > 1.0:
            return round(num, 3)
        return 1.91
    except Exception:
        return 1.91


def formatear_decimal_a_americano(dec: float) -> str:
    """Convierte cuota decimal a formato americano (+150 / -110)."""
    if dec <= 1.0:
        return "-110"
    if dec >= 2.0:
        return f"+{int(round((dec - 1.0) * 100))}"
    denom = dec - 1.0
    return f"-{int(round(100.0 / denom))}" if denom > 0 else "-110"


def obtener_boleta() -> list[dict]:
    """Obtiene la lista actual de selecciones en la boleta."""
    if "mi_boleta" not in st.session_state or not isinstance(st.session_state["mi_boleta"], list):
        st.session_state["mi_boleta"] = []
    return st.session_state["mi_boleta"]


def esta_en_boleta(pick_id: str) -> bool:
    """Verifica si un pick ya está en la boleta."""
    return any(p.get("id") == pick_id for p in obtener_boleta())


def alternar_en_boleta(item: dict) -> None:
    """Añade o retira un pick de la boleta."""
    boleta = obtener_boleta()
    pick_id = item.get("id")
    existente = next((idx for idx, p in enumerate(boleta) if p.get("id") == pick_id), None)
    if existente is not None:
        boleta.pop(existente)
    else:
        # Asegurar cálculo decimal
        cuota_raw = item.get("cuota") or item.get("momio")
        cuota_dec = item.get("cuota_dec") or parsear_cuota_decimal(cuota_raw)
        nuevo = dict(item)
        nuevo["cuota_dec"] = cuota_dec
        nuevo["momio"] = str(cuota_raw or formatear_decimal_a_americano(cuota_dec))
        boleta.append(nuevo)
    st.session_state["mi_boleta"] = boleta


def limpiar_boleta() -> None:
    """Vacía la boleta."""
    st.session_state["mi_boleta"] = []


def render_boton_boleta(item: dict, key: str, help_text: str = "Añadir a mi selección del día") -> None:
    """Renderiza un botón compacto para añadir o quitar el pick de la boleta."""
    pick_id = item.get("id")
    en_boleta = esta_en_boleta(pick_id)
    label = "✅ En Boleta" if en_boleta else "🎟️ +Boleta"
    btn_type = "secondary" if en_boleta else "primary"
    if st.button(label, key=key, help=help_text, type=btn_type):
        alternar_en_boleta(item)
        st.rerun()


def render_widget_boleta(sidebar: bool = False) -> None:
    """Renderiza la tarjeta interactiva de la Boleta del Día."""
    boleta = obtener_boleta()
    n = len(boleta)

    titulo = f"🎟️ Mi Boleta del Día ({n} picks)" if n else "🎟️ Mi Boleta del Día"
    with st.expander(titulo, expanded=(n > 0 and not sidebar)):
        if n == 0:
            st.markdown(
                """<div style="text-align: center; padding: 1.2rem; color: #8fa0b5; font-size: 0.88rem;">
                <div style="font-size: 2rem; margin-bottom: 0.35rem;">🎟️</div>
                Tu boleta está vacía actualmente.<br>
                Navega por los deportes y pulsa <b>🎟️ +Boleta</b> para armar tu selección o parlay.
                </div>""",
                unsafe_allow_html=True,
            )
            return

        st.caption(f"Tienes {n} {'selección directa' if n == 1 else 'selecciones combinadas (Parlay)'}:")

        for idx, p in enumerate(boleta):
            c_dec = p.get("cuota_dec", 1.91)
            momio_txt = p.get("momio") or formatear_decimal_a_americano(c_dec)
            icono = p.get("icono", "🎯")
            deporte = p.get("deporte", "")

            b_col1, b_col2 = st.columns([4, 1], gap="small")
            with b_col1:
                st.markdown(
                    f"""<div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); 
                    border-radius: 8px; padding: 0.45rem 0.65rem; margin-bottom: 0.35rem;">
                    <div style="font-size: 0.72rem; color: #8fa0b5; font-weight: 700;">{icono} {deporte} · {p.get('mercado')}</div>
                    <div style="font-size: 0.88rem; font-weight: 850; color: #ffffff;">{p.get('seleccion')}</div>
                    <div style="font-size: 0.75rem; color: #00e5ff;">{p.get('partido')} · Momio: <b>{momio_txt}</b> ({c_dec:.2f})</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with b_col2:
                if st.button("❌", key=f"del_slip_{idx}_{sidebar}", help="Eliminar pick de la boleta"):
                    alternar_en_boleta(p)
                    st.rerun()

        # Resumen combinado
        parlay_dec = math.prod(p.get("cuota_dec", 1.91) for p in boleta)
        parlay_amer = formatear_decimal_a_americano(parlay_dec)

        st.markdown("<div style='margin-top: 0.6rem; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.6rem;'></div>", unsafe_allow_html=True)
        m1, m2 = st.columns(2)
        with m1:
            st.metric("Cuota Combinada", f"{parlay_amer} ({parlay_dec:.2f}x)")
        with m2:
            importe = st.number_input("Simular apuesta (MXN)", min_value=10.0, value=100.0, step=50.0, key=f"slip_amt_{sidebar}")

        pago_potencial = importe * parlay_dec
        ganancia_neta = pago_potencial - importe
        st.markdown(
            f"""<div style="background: rgba(34, 197, 94, 0.12); border: 1px solid rgba(34, 197, 94, 0.4); 
            border-radius: 8px; padding: 0.55rem 0.8rem; margin-top: 0.4rem; text-align: center;">
            <div style="font-size: 0.75rem; color: #86efac; font-weight: 700;">RETORNO POTENCIAL ESTIMADO</div>
            <div style="font-size: 1.15rem; font-weight: 900; color: #4ade80;">${pago_potencial:,.2f} MXN</div>
            <div style="font-size: 0.72rem; color: #cbd5e1;">Ganancia neta: +${ganancia_neta:,.2f} MXN</div>
            </div>""",
            unsafe_allow_html=True,
        )

        b_act1, b_act2 = st.columns(2)
        with b_act1:
            if st.button("🗑️ Vaciar Boleta", key=f"clear_slip_{sidebar}", use_container_width=True):
                limpiar_boleta()
                st.rerun()
        with b_act2:
            resumen_texto = "\\n".join([f"• [{p.get('deporte')}] {p.get('partido')}: {p.get('seleccion')} ({p.get('momio')})" for p in boleta])
            resumen_completo = f"🎟️ MI SELECCIÓN ORÁCULO AI ({parlay_amer}):\\n{resumen_texto}\\nCuota Total: {parlay_dec:.2f}x"
            st.download_button(
                "📋 Descargar Boleta",
                resumen_completo,
                file_name="boleta_oraculo.txt",
                mime="text/plain",
                key=f"dl_slip_{sidebar}",
                use_container_width=True,
            )
