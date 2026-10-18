"""Diagnóstico de solo lectura: datos guardados, sin cuotas ni notificaciones."""
from pathlib import Path
import sys
import json
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from core.db import get_db_connection
from core.confianza_datos import read_confidence
from core.diagnostico_confianza import build_report


def main():
    conn=get_db_connection()
    try:
        raw,errors=read_confidence(conn,ROOT)
        report=build_report(raw,errors)
    finally:conn.close()
    report['generado_utc']=datetime.now(timezone.utc).isoformat()
    folder=ROOT/'diagnostico_confianza'
    folder.mkdir(exist_ok=True)
    (folder/'reporte.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2))
    for record in report['mercados']:
        print('MERCADO '+json.dumps(record,ensure_ascii=False,allow_nan=False))
    for record in report['pruebas_temporales']:
        print('PRUEBA '+json.dumps(record,ensure_ascii=False,allow_nan=False))
    print('FUENTES_NO_DISPONIBLES '+json.dumps(report['fuentes_no_disponibles'],ensure_ascii=False))
    print('EXCLUSIONES '+json.dumps(report['exclusiones'],ensure_ascii=False))
    print('Producción sin cambios. No se recalibró ningún pick.')


if __name__=='__main__':main()
