"""Script unificado para el pipeline automatizado de Fútbol Mundial (8 ligas) y Liga MX.
1. Liquida partidos terminados y audita resultados en MySQL y Parquet/CSV.
2. Descarga la jornada activa de ESPN y genera predicciones Poisson/Dixon-Coles calibradas.
3. Sincroniza datos en MySQL (futbol_registro_picks, ligamx_registro_picks) y almacenamiento local.
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
logger = logging.getLogger("futbol_pipeline_auto")


def ejecutar_pipeline_futbol():
    from futbol.predecir_jornada import liquidar_partidos_pendientes_futbol, predecir_futbol_mundial

    logger.info("⚽ [1/2] Liquidando partidos de fútbol concluidos en las 8 ligas...")
    res_liq = liquidar_partidos_pendientes_futbol()
    logger.info(f"Liquidación: {res_liq.get('mensaje')}")

    logger.info("⚽ [2/2] Generando predicciones actualizadas para la jornada...")
    preds = predecir_futbol_mundial(force_refresh=True, dias_adelante=3)
    logger.info(f"✅ Se generaron {len(preds)} predicciones activas para fútbol mundial y Liga MX.")

    return {
        "ok": True,
        "evaluados": res_liq.get("resueltas", res_liq.get("evaluados", 0)),
        "unidades_netas": res_liq.get("unidades_netas", 0.0),
        "predicciones_generadas": len(preds),
    }


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    resultado = ejecutar_pipeline_futbol()
    logger.info(f"🏁 Pipeline Fútbol completado con éxito: {resultado}")

