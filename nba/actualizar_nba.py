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

def ejecutar_pipeline_nba(force_refresh: bool = True):
    from nba.registro import liquidar_partidos_pendientes_nba
    from nba.predecir_hoy import predecir_partidos_hoy

    logger.info("🏀 [1/2] Liquidando partidos concluidos y actualizando marcadores finales...")
    res_liq = liquidar_partidos_pendientes_nba()
    logger.info(f"Liquidación: {res_liq.get('mensaje')}")

    logger.info("🏀 [2/2] Generando predicciones actualizadas de la jornada...")
    preds = predecir_partidos_hoy(force_refresh=force_refresh)
    logger.info(f"✅ Se generaron {len(preds)} predicciones para la cartelera activa.")

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

