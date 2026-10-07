"""Curva reconstruida y exposición de apuestas guardadas; sin escrituras."""
import json
import math
import pandas as pd


def balance_curve(ledger, initial):
    initial=float(initial)
    if not math.isfinite(initial) or initial<0: raise ValueError('Capital inicial inválido.')
    columns=['Fecha','Saldo','Pico','Caída (MXN)','Caída (%)']
    settled=ledger[ledger.estado.isin(['Ganada','Perdida','Push'])].copy()
    if settled.empty: return pd.DataFrame(columns=columns)
    settled['fecha']=pd.to_datetime(settled.fecha,errors='raise').dt.normalize()
    daily=settled.groupby('fecha',sort=True).ganancia_neta.sum().astype(float)
    if not daily.map(math.isfinite).all(): raise ValueError('Hay resultados no válidos.')
    first=daily.index[0]-pd.Timedelta(days=1)
    balances=pd.Series([initial]+(initial+daily.cumsum()).tolist(),index=[first]+daily.index.tolist())
    peaks=balances.cummax()
    drops=peaks-balances
    percentage=100*drops/peaks.where(peaks>0)
    return pd.DataFrame({'Fecha':balances.index,'Saldo':balances.values,'Pico':peaks.values,
                         'Caída (MXN)':drops.values,'Caída (%)':percentage.values})


def reference(value):
    if isinstance(value,dict): return value
    try:
        data=json.loads(value)
        return data if isinstance(data,dict) else {}
    except (ValueError,TypeError): return {}


def event_identity(row):
    ref=reference(row.get('referencia'))
    source=str(row.get('origen','manual'))
    sport=str(row['deporte'])
    if ref.get('game_id') is not None:
        family='nfl' if source in ('nfl_total','nfl_prop') else source
        return (sport,family,str(ref['game_id'])), 'Partido identificado'
    if source=='liga_mx' and all(ref.get(k) for k in ('fecha','local','visitante')):
        return (sport,'liga_mx',str(ref['fecha']),str(ref['local']),str(ref['visitante'])), 'Partido identificado'
    # Manuales sin id: agrupación visible aproximada, sin inferir alias ni dobles carteleras.
    date=pd.Timestamp(row['fecha']).date().isoformat()
    return (sport,'sin_id',date,str(row['partido']).strip().casefold()), 'Sin identificador: fecha y nombre'


def exposure(ledger, balance):
    pending=ledger[ledger.estado.eq('Pendiente')].copy()
    sport_cols=['Deporte','Apuestas','Comprometido (MXN)','% del pendiente','% del saldo']
    game_cols=['Fecha','Deporte','Partido','Agrupación','Apuestas','Comprometido (MXN)','% del pendiente','% del saldo']
    if pending.empty: return pd.DataFrame(columns=sport_cols),pd.DataFrame(columns=game_cols)
    pending['monto']=pd.to_numeric(pending.monto,errors='raise')
    if not pending.monto.map(lambda x:math.isfinite(float(x)) and x>0).all():
        raise ValueError('Hay montos pendientes no válidos.')
    total=float(pending.monto.sum())
    def percentages(frame):
        frame['% del pendiente']=100*frame['Comprometido (MXN)']/total
        frame['% del saldo']=100*frame['Comprometido (MXN)']/balance if balance>0 else float('nan')
        return frame.sort_values('Comprometido (MXN)',ascending=False).reset_index(drop=True)
    by_sport=pending.groupby('deporte',as_index=False).agg(Apuestas=('monto','size'),amount=('monto','sum'))
    by_sport=by_sport.rename(columns={'deporte':'Deporte','amount':'Comprometido (MXN)'})
    groups={}
    for row in pending.to_dict('records'):
        key,label=event_identity(row)
        item=groups.setdefault(key,{'Fecha':pd.Timestamp(row['fecha']).date().isoformat(),'Deporte':row['deporte'],
            'Partido':row['partido'],'Agrupación':label,'Apuestas':0,'Comprometido (MXN)':0.0})
        item['Apuestas']+=1
        item['Comprometido (MXN)']+=float(row['monto'])
    return percentages(by_sport)[sport_cols],percentages(pd.DataFrame(groups.values()))[game_cols]
