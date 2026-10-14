"""Diagnóstico y recalibración temporal experimental; nunca modifica picks."""
import hashlib
import numpy as np
import pandas as pd
from scipy.special import expit,logit

KEYS=['deporte','mercado','modelo','procedencia']
VERIFIED='Previo al inicio verificado'


def prepare(frame):
    f=frame.copy();excluded={'entrada':len(f)}
    if f.empty:return f,excluded
    f['probabilidad']=pd.to_numeric(f.probabilidad,errors='coerce')
    valid=np.isfinite(f.probabilidad)&f.probabilidad.between(0,1)
    decided=f.resultado.isin(['GANADA','PERDIDA'])
    excluded['probabilidad_invalida']=int((~valid).sum())
    excluded['push_pendiente_o_revision']=int((~decided).sum())
    metadata=f[KEYS+['identidad']].notna().all(axis=1)
    excluded['identificacion_incompleta']=int((~metadata).sum())
    f=f[valid&decided&metadata].copy()
    def day(value):
        t=pd.to_datetime(value,errors='coerce')
        if pd.isna(t):return None
        return (t.tz_convert('America/Mexico_City') if t.tzinfo is not None else t).date()
    f['fecha']=f.fecha.map(day)
    excluded['sin_fecha']=int(f.fecha.isna().sum());f=f[f.fecha.notna()]
    before=len(f);f=f.drop_duplicates(KEYS+['identidad'])
    excluded['duplicados']=before-len(f)
    f['y']=f.resultado.eq('GANADA').astype(int)
    if 'evento' not in f:
        f['evento']=[str(r.identidad).split('|')[0] if r.deporte=='NFL' else str(r.identidad) for r in f.itertuples()]
    f['evento']=f.deporte.astype(str)+'|'+f.evento.astype(str)
    return f.reset_index(drop=True),excluded


def scores(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float);clipped=np.clip(p,1e-9,1-1e-9)
    return dict(brier=float(np.mean((p-y)**2)),logloss=float(-np.mean(y*np.log(clipped)+(1-y)*np.log1p(-clipped))))


def interval(values,events,seed=72,repetitions=400):
    values=np.asarray(values,float);events=np.asarray(events,str);unique=np.unique(events)
    if len(unique)<2:return (None,None)
    sums=np.array([values[events==e].sum() for e in unique]);sizes=np.array([(events==e).sum() for e in unique])
    rng=np.random.default_rng(seed);draw=rng.integers(0,len(unique),(repetitions,len(unique)))
    estimates=sums[draw].sum(axis=1)/sizes[draw].sum(axis=1)
    return tuple(float(x) for x in np.quantile(estimates,[.025,.975]))


def reliability(frame):
    records=[]
    if frame.empty:return pd.DataFrame()
    for key,g in frame.groupby(KEYS,dropna=False):
        bins=np.minimum((g.probabilidad*10).astype(int),9)
        for bucket,b in g.groupby(bins):
            n=len(b);games=b.evento.nunique();low,high=interval(b.y,b.evento)
            records.append(dict(zip(KEYS,key))|dict(rango=f'{bucket*10}–{(bucket+1)*10}%',picks=n,partidos=games,
                confianza=float(b.probabilidad.mean()),acierto=float(b.y.mean()),
                diferencia=float(b.y.mean()-b.probabilidad.mean()),intervalo_inferior=low,intervalo_superior=high,
                evidencia='Muestra limitada' if n<100 or games<30 else 'Muestra descriptiva amplia',
                **scores(b.y,b.probabilidad)))
    return pd.DataFrame(records)


def transform(p,model):
    p=np.asarray(p,float)
    if model['method']=='identity':return p
    z=logit(np.clip(p,1e-6,1-1e-6))
    return expit(z/model['temperature']) if model['method']=='temperature' else expit(model['slope']*z+model['intercept'])


def temporal_trial(frame):
    """Fit → selección → prueba, por fechas completas. Solo publicaciones verificadas."""
    reports=[]
    if frame.empty:return reports
    for keys,g in frame.groupby(['deporte','mercado','modelo'],dropna=False):
        report=dict(zip(['deporte','mercado','modelo'],keys))|{'production_changed':False,'status':'Datos insuficientes'}
        eligible=g.get('apto_ajuste',pd.Series(True,index=g.index)).map(lambda v:True if pd.isna(v) else str(v).casefold()=='true')
        verified=g[g.procedencia.eq(VERIFIED)&eligible].copy();dates=sorted(verified.fecha.unique())
        report.update(total=len(g),verificados=len(verified),partidos=int(verified.evento.nunique()))
        if len(dates)<10 or verified.groupby('evento').fecha.nunique().gt(1).any():reports.append(report);continue
        a=dates[int(len(dates)*.6)];b=dates[int(len(dates)*.8)]
        fit=verified[verified.fecha<a];selection=verified[(verified.fecha>=a)&(verified.fecha<b)];test=verified[verified.fecha>=b]
        report.update(corte_seleccion=str(a),corte_prueba=str(b),fit=len(fit),seleccion=len(selection),prueba=len(test))
        if (len(fit)<200 or len(selection)<100 or len(test)<100 or fit.evento.nunique()<30
            or selection.evento.nunique()<20 or test.evento.nunique()<20
            or any(min(block.y.value_counts().reindex([0,1],fill_value=0))<20 for block in [fit,selection,test])):reports.append(report);continue
        from sklearn.linear_model import LogisticRegression
        estimator=LogisticRegression(C=1,random_state=72).fit(logit(np.clip(fit.probabilidad.to_numpy(),1e-6,1-1e-6)).reshape(-1,1),fit.y)
        choices=[dict(method='identity')]+[dict(method='temperature',temperature=t) for t in [1.1,1.25,1.5,2.0]]
        if estimator.coef_[0,0]>0:choices.append(dict(method='platt',slope=float(estimator.coef_[0,0]),intercept=float(estimator.intercept_[0])))
        model=min(choices,key=lambda m:scores(selection.y,transform(selection.probabilidad,m))['logloss'])
        original=scores(test.y,test.probabilidad);adjusted=transform(test.probabilidad,model);after=scores(test.y,adjusted)
        delta=(adjusted-test.y.to_numpy())**2-(test.probabilidad.to_numpy()-test.y.to_numpy())**2
        lo,hi=interval(delta,test.evento)
        favorable=model['method']!='identity' and after['logloss']<original['logloss'] and hi is not None and hi<0
        report.update(status='Validación temporal favorable · experimental' if favorable else 'Sin mejora confirmada',
            transform=model,original=original,ajustado=after,delta_brier_intervalo=[lo,hi],
            prueba_hasta=str(test.fecha.max()),data_hash=hashlib.sha256(verified.to_json(default_handler=str).encode()).hexdigest())
        reports.append(report)
    return reports


def price_comparison(frame):
    f=frame.copy();odds=pd.to_numeric(f.cuota,errors='coerce');valid=np.isfinite(odds)&odds.gt(1)
    f['probabilidad_implicita']=(1/odds).where(valid)
    f['ventaja_estimacion']=f.probabilidad-f.probabilidad_implicita
    push=pd.to_numeric(f.get('p_push',pd.Series(0,index=f.index)),errors='coerce').fillna(0)
    f['ev_estimado']=((1-push)*(f.probabilidad*odds-1)).where(valid)
    return f
