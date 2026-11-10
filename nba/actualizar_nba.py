"""Script automatizado para el pipeline diario de la NBA V2.
1. Liquida partidos concluidos y sincroniza marcadores en MySQL y Parquet/CSV.
2. Genera predicciones para la jornada del día y las guarda en JSON, MySQL y Parquet.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("nba_pipeline_auto")

def ejecutar_pipeline_nba(force_refresh: bool = True, sincronizar_boxscores: bool = True):
    from nba.registro import liquidar_partidos_pendientes_nba
    from nba.predecir_hoy import predecir_partidos_hoy
    from nba.servicio_jugadores_boxscores import sincronizar_boxscores_jugadores
    from nba.evaluar_props import sincronizar_y_liquidar_props_nba

    if sincronizar_boxscores:
        logger.info("🏀 [1/4] Sincronizando boxscores oficiales de jugadores (ESPN)...")
        try:
            sincronizar_boxscores_jugadores()
        except Exception as e_box:
            logger.warning(f"Error sincronizando boxscores de jugadores: {e_box}")

    logger.info("🏀 [2/4] Liquidando partidos concluidos y sincronizando marcadores finales...")
    res_liq = liquidar_partidos_pendientes_nba()
    logger.info(f"Liquidación partidos: {res_liq.get('mensaje')}")

    logger.info("🏀 [3/4] Liquidando Props de Jugadores concluidos...")
    try:
        res_props = sincronizar_y_liquidar_props_nba()
        logger.info(f"Liquidación props: {res_props.get('mensaje')}")
    except Exception as e_props:
        logger.warning(f"Error liquidando props: {e_props}")

    logger.info("🏀 [4/4] Generando predicciones actualizadas de la jornada...")
    preds = predecir_partidos_hoy(force_refresh=force_refresh)
    logger.info(f"✅ Se generaron {len(preds)} predicciones para la cartelera activa.")

    # Generar / actualizar props de hoy si hay líneas disponibles
    try:
        from nba.predecir_props import generar_predicciones_props_hoy
        df_p = generar_predicciones_props_hoy(usar_cache_bovada=False)
        logger.info(f"✅ Se generaron {len(df_p)} props de jugadores para la jornada.")
    except Exception as e_p_gen:
        logger.warning(f"No se pudieron generar props automáticamente: {e_p_gen}")

    return {
        "ok": True,
        "evaluados": res_liq.get("evaluados", 0),
        "predicciones_generadas": len(preds)
    }

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    resultado = ejecutar_pipeline_nba(force_refresh=True)
    logger.info(f"🏁 Pipeline NBA completado con éxito: {resultado}")

