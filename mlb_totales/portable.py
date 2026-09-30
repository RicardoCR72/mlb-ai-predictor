"""Inferencia Ridge en NumPy, independiente de la versión de sklearn/NFL."""
import hashlib
import json
from pathlib import Path
import numpy as np


class PortableRidge:
    def __init__(self,payload):
        self.columns=payload['columns']
        self.mean=np.asarray(payload['mean'],dtype=float)
        self.scale=np.asarray(payload['scale'],dtype=float)
        self.coef=np.asarray(payload['coef'],dtype=float)
        self.intercept=float(payload['intercept'])
        if (not(len(self.columns)==len(self.mean)==len(self.scale)==len(self.coef))
            or not np.isfinite(self.mean).all() or not np.isfinite(self.coef).all()
            or not np.isfinite(self.scale).all() or np.any(self.scale<=0)):
            raise ValueError('Modelo portable inválido.')

    def predict(self,frame):
        x=frame[self.columns].to_numpy(dtype=float)
        if not np.isfinite(x).all():
            raise ValueError('Variables no finitas.')
        return ((x-self.mean)/self.scale)@self.coef+self.intercept


def load(directory):
    payload=json.loads((Path(directory)/'modelo_portable.json').read_text(encoding='utf-8'))
    return dict(model=PortableRidge(payload),alpha=payload['alpha'],columns=payload['columns'],
                metadata=payload['metadata'],model_id=payload['model_id'])


def export(bundle,path):
    steps=getattr(bundle['model'],'named_steps',{})
    if 'standardscaler' not in steps or 'ridge' not in steps:
        raise ValueError('Exportación portable admite el ganador Ridge; no sustituir por otro modelo.')
    scaler,ridge=steps['standardscaler'],steps['ridge']
    payload=dict(format='ridge_numpy_v1',columns=bundle['columns'],alpha=float(bundle['alpha']),
                 mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),
                 coef=ridge.coef_.tolist(),intercept=float(ridge.intercept_))
    payload['model_id']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    payload['metadata']=bundle['metadata']
    Path(path).write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return payload


if __name__=='__main__':
    import argparse
    import joblib
    p=argparse.ArgumentParser()
    p.add_argument('--modelos',default='mlb_totales/modelos_pitcheo')
    a=p.parse_args()
    root=Path(a.modelos)
    export(joblib.load(root/'modelo_totales.joblib'),root/'modelo_portable.json')
    print('Modelo Ridge exportado para inferencia NumPy.')
