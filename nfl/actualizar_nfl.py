"""Script maestro de actualización y liquidación automática de la NFL V2.
1. Liquida partidos concluidos (Moneyline, Totales y Props de Jugadores) usando la API en vivo de ESPN.
2. Sincroniza predicciones y resultados en MySQL y archivos Parquet locales.
"""
from __future__ import annotations

import json
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
logger = logging.getLogger("nfl_pipeline_auto")

def ejecutar_pipeline_nfl():
    from nfl.liquidar_nfl import liquidar_todo_nfl
    import pandas as pd

    logger.info("🏈 [1/2] Liquidando partidos y props de la NFL concluidos con ESPN...")
    res = liquidar_todo_nfl()
    logger.info(f"Liquidación: {res.get('mensaje')}")

    logger.info("🏈 [2/2] Sincronizando archivos Parquet locales de predicciones...")
    p_json = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_moneyline.json"
    p_parquet = RAIZ / "data" / "nfl" / "predictions" / "predicciones_nfl_moneyline.parquet"
    if p_json.exists():
        try:
            with open(p_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            df = pd.DataFrame(data)
            df.to_parquet(p_parquet, index=False)
            logger.info("✅ Parquet local de Moneyline NFL sincronizado.")
        except Exception as exc:
            logger.warning(f"Error sincronizando parquet Moneyline: {exc}")

    return res

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    resultado = ejecutar_pipeline_nfl()
    logger.info(f"🏁 Pipeline NFL completado: {resultado}")
