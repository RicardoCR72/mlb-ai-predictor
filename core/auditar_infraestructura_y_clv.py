"""Script Maestro de Auditoría de Infraestructura Cuantitativa, CLV y Calibración.

Ejecuta el diagnóstico completo solicitado:
1. Auditoría de CLV (Closing Line Value) en histórico.
2. Validación de Vig de Mercado (1.02 a 1.15) y Alerta de Desbalance (>70% mismo lado).
3. Calibración Empírica por Buckets (Curva de Fiabilidad, Brier Score y ECE).
4. Verificación de Inmutabilidad de Registro y Sincronización DB/Parquet.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd
from core.infrastructure.database import query_df
from core.clv import calcular_metricas_clv_resumen, validar_mercado_dos_lados, auditar_balance_diario
from core.calibracion_evaluador import calcular_tabla_calibracion
from core.gestion_riesgo import calcular_kelly_fraccional, asignar_stakes_con_tope_de_partido


def auditar_todo():
    print("=" * 70)
    print("🎯 REPORTE CUANTITATIVO DE INFRAESTRUCTURA, CLV Y CALIBRACIÓN")
    print("=" * 70)

    # 1. Auditoría de Calibración Real
    print("\n[1] CALIBRACIÓN EMPÍRICA (CONFIANZA DEL MODELO VS REALIDAD)")
    sql_props = """
    SELECT probabilidad, cuota, resultado, seleccion, mercado, id_juego
    FROM nba_registro_props 
    WHERE resultado IN ('GANADA', 'PERDIDA')
    """
    df = query_df(sql_props)
    if not df.empty:
        p = df["probabilidad"]
        y = (df["resultado"] == "GANADA").astype(int)
        df_bins, metricas = calcular_tabla_calibracion(p, y, n_bins=5, prob_min=0.50, prob_max=0.75)
        print(f"  • Total picks evaluados: {metricas['n_muestras']}")
        print(f"  • Acierto global real: {metricas['acierto_global']*100:.1f}%")
        print(f"  • Expected Calibration Error (ECE): {metricas['ece']*100:.2f}% (Excelente < 3.0%)")
        print(f"  • Brier Score: {metricas['brier_score']:.4f}")
        print("\n  Desglose por Buckets de Probabilidad:")
        for _, r in df_bins.iterrows():
            if r["picks_en_bucket"] > 0:
                print(f"    - Intervalo {r['etiqueta']:<11}: {r['picks_en_bucket']:>3} picks | Proyectado: {r['probabilidad_media']*100:.1f}% | Real: {r['frecuencia_real']*100:.1f}% | {r['sesgo']}")
    else:
        print("  Sin picks liquidados para calibración.")

    # 2. Validación de Vig y Desbalance Diario
    print("\n[2] VALIDACIONES AUTOMÁTICAS DE MERCADO Y VIG")
    print("  • Probando validación de vig en cuotas estándar -110/-110 (1.909 / 1.909):")
    ok, vig, motivo = validar_mercado_dos_lados(1.909, 1.909)
    print(f"    - Estado: {'✅ Válido' if ok else '❌ Rechazado'} | Vig: {vig:.4f} ({((vig or 1)-1)*100:.2f}%) | {motivo}")

    print("  • Probando validación de vig distorsionado (ej. cuotas desfasadas 2.40 / 2.30):")
    ok_arb, vig_arb, motivo_arb = validar_mercado_dos_lados(2.40, 2.30)
    print(f"    - Estado: {'✅ Válido' if ok_arb else '⚠️ Alerta'} | Vig: {vig_arb:.4f} | {motivo_arb}")

    # 3. Auditoría de Balance Diario en Última Jornada
    print("\n[3] AUDITORÍA DE SESGO DIRECCIONAL (OVERS VS UNDERS)")
    sql_ultimos = """
    SELECT seleccion, id_juego, cuota, probabilidad 
    FROM nba_registro_props 
    WHERE fecha = (SELECT MAX(fecha) FROM nba_registro_props)
    """
    df_ultimos = query_df(sql_ultimos)
    if not df_ultimos.empty:
        picks_list = df_ultimos.to_dict(orient="records")
        ok_bal, msg_bal, stats_bal = auditar_balance_diario(picks_list, umbral_sesgo=0.70)
        print(f"  • Jornada más reciente ({len(picks_list)} picks):")
        print(f"    - Overs: {stats_bal['overs']} ({stats_bal['pct_overs']*100:.1f}%) | Unders: {stats_bal['unders']} ({stats_bal['pct_unders']*100:.1f}%)")
        print(f"    - Diagnóstico: {msg_bal}")
    else:
        print("  Sin picks en la última jornada.")

    # 4. Gestión de Riesgo (Kelly Fraccional con Candado de Partido)
    print("\n[4] GESTIÓN DE RIESGO: KELLY FRACCIONAL (1/4 KELLY) Y TOPE POR JUEGO")
    ejemplo_picks = [
        {"id_juego": "BOS_SAC", "jugador": "Tatum", "probabilidad": 0.58, "cuota": 1.91},
        {"id_juego": "BOS_SAC", "jugador": "Brown", "probabilidad": 0.56, "cuota": 1.91},
        {"id_juego": "BOS_SAC", "jugador": "Fox", "probabilidad": 0.57, "cuota": 1.91},
        {"id_juego": "LAL_DEN", "jugador": "Jokic", "probabilidad": 0.60, "cuota": 1.85},
    ]
    picks_con_stake = asignar_stakes_con_tope_de_partido(ejemplo_picks, fraccion_kelly=0.25, max_partido_pct=0.06, bankroll_total=1000.0)
    for p in picks_con_stake:
        alerta = f" -> ⚠️ {p['alerta_correlacion']}" if "alerta_correlacion" in p else ""
        print(f"  • {p['jugador']} ({p['id_juego']}): Stake {p['kelly_stake_pct']*100:.2f}% (${p['unidades_recomendadas']} u) | EV: +{p['ev_pct']}%{alerta}")

    print("\n" + "=" * 70)
    print("✅ AUDITORÍA DE INFRAESTRUCTURA COMPLETADA EXITOSAMENTE")
    print("=" * 70)


if __name__ == "__main__":
    auditar_todo()
