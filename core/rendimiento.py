"""Calibración de snapshots previos al inicio y ROI con cuotas tomadas."""
import json
import numpy as np
import pandas as pd
from core.bankroll import metrics, rows

MARKETS = {'mlb_total':'Totales V2','mlb_ml':'Moneyline','nfl_total':'Totales',
           'nfl_prop':'Props','liga_mx':'Total 2.5'}


def prospective(reference):
    try:
        ref = json.loads(reference) if isinstance(reference,str) else reference
        registered, kickoff = pd.Timestamp(ref['registrado_utc']), pd.Timestamp(ref['inicio_utc'])
        # Una fecha sin hora o zona no permite demostrar registro antes del partido.
        if registered.tzinfo is None or kickoff.tzinfo is None: return False
        return registered < kickoff
    except (KeyError, TypeError, ValueError): return False


def calibration(probabilities, outcomes):
    p, y = np.asarray(probabilities,float), np.asarray(outcomes,float)
    valid = np.isfinite(p) & (p >= 0) & (p <= 1) & np.isin(y,[0,1])
    p,y = p[valid], y[valid]
    if not len(p): return dict(n_prob=0,brier=None,logloss=None,ece=None,prob_media=None,acierto=None)
    clipped = np.clip(p,1e-12,1-1e-12)
    bins = np.minimum((p*10).astype(int),9)
    ece = sum(float((bins==i).mean())*abs(float(p[bins==i].mean()-y[bins==i].mean()))
              for i in range(10) if (bins==i).any())
    return dict(n_prob=len(p),brier=float(np.mean((p-y)**2)),
                logloss=float(-np.mean(y*np.log(clipped)+(1-y)*np.log1p(-clipped))),
                ece=ece,prob_media=float(p.mean()),acierto=float(y.mean()))


def grouped_performance(ledger):
    if ledger.empty: return pd.DataFrame(),pd.DataFrame()
    model = ledger[ledger.origen.isin(MARKETS)].copy()
    model['Periodo'] = np.where(model.referencia.apply(prospective),'Registro previo al inicio','Histórico / hora no verificable')
    model['Mercado'] = model.origen.map(MARKETS)
    output, bins = [], []
    for (sport,market,period), frame in model.groupby(['deporte','Mercado','Periodo']):
        financial = metrics(frame)
        decided = frame[frame.estado.isin(['Ganada','Perdida'])]
        score = calibration(decided.probabilidad,decided.estado.eq('Ganada').astype(int))
        output.append({'Deporte':sport,'Mercado':market,'Periodo':period,
                       'Apuestas':len(frame),'Liquidadas':int(frame.estado.isin(['Ganada','Perdida','Push']).sum()),
                       'ROI (%)':financial['roi'] if financial['apostado'] else None,
                       'Beneficio':financial['beneficio'],**score})
        data = decided.copy()
        data['probabilidad'] = pd.to_numeric(data.probabilidad,errors='coerce')
        data = data[data.probabilidad.between(0,1)]
        data['grupo'] = np.minimum((data.probabilidad*10).astype(int),9)
        for bucket,subset in data.groupby('grupo'):
            bins.append({'Deporte':sport,'Mercado':market,'Periodo':period,'Rango':f'{bucket*10}–{(bucket+1)*10}%',
                         'n':len(subset),'Probabilidad media':subset.probabilidad.mean(),
                         'Frecuencia ganada':subset.estado.eq('Ganada').mean()})
    return pd.DataFrame(output),pd.DataFrame(bins)


def mlb_snapshot_performance(conn):
    """Todas las predicciones MLB V2 inmutables, independientemente de apostar."""
    data = rows(conn, """SELECT p.model_id,p.seleccion,p.linea,p.confianza,p.cuota_seleccion,
        r.home_runs+r.away_runs AS total
        FROM mlb_totales_predicciones p JOIN mlb_totales_resultados r ON r.game_pk=p.game_pk
        WHERE p.recorded_utc<p.start_utc AND p.quote_captured_utc<p.start_utc
        AND r.revision_reglas=0 AND LOWER(TRIM(p.casa_apuestas))='draftkings'""")
    output = []
    for model, frame in data.groupby('model_id') if not data.empty else []:
        for col in ('linea','confianza','cuota_seleccion','total'):
            frame[col] = pd.to_numeric(frame[col],errors='coerce')
        frame = frame[frame.seleccion.isin(['OVER','UNDER']) & frame.linea.notna() & frame.total.notna()]
        if frame.empty: continue
        pushes = frame.total.eq(frame.linea)
        win = np.where(frame.seleccion.eq('OVER'),frame.total>frame.linea,frame.total<frame.linea)
        profit = np.where(pushes,0,np.where(win,frame.cuota_seleccion-1,-1))
        # Confianza MLB incluye push; excluirlos exige convertir a probabilidad condicional.
        # Conservamos Brier/logloss solo en líneas sin posibilidad de push (media carrera).
        half = frame.linea.mod(1).eq(.5)
        score = calibration(frame.loc[half,'confianza'],np.asarray(win)[half])
        output.append({'Modelo':model,'Predicciones':len(frame),'Push':int(pushes.sum()),
                       'ROI teórico 1u (%)':100*float(profit.mean()),**score})
    return pd.DataFrame(output)
