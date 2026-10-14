"""Validación reproducible desde CSV exportado, sin conexión ni modelos productivos."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from core.confianza import prepare,reliability,temporal_trial


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('csv',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    frame,excluded=prepare(pd.read_csv(args.csv))
    args.output.mkdir(parents=True,exist_ok=True)
    reliability(frame).to_csv(args.output/'rangos.csv',index=False)
    (args.output/'evaluacion.json').write_text(json.dumps({'excluidos':excluded,'pruebas':temporal_trial(frame)},ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
