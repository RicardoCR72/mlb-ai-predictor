"""Nombres visibles sin unir identidades o versiones distintas del modelo."""
import re
import pandas as pd

KNOWN={'MLB V4':'Moneyline MLB · V4', 'totales_v2_seleccion_automatica':'Totales NFL · V2',
       'props_nfl_v2':'Props NFL · V2'}


def model_names(frame):
    rows=frame[['deporte','modelo','mercado']].drop_duplicates().sort_values(['deporte','modelo','mercado'])
    names={};used={}
    for (sport,model), group in rows.groupby(['deporte','modelo'],dropna=False,sort=False):
        raw=str(model)
        if raw in KNOWN:label=KNOWN[raw]
        else:
            markets=set(group.mercado)
            family='Moneyline' if markets=={'Moneyline'} else 'Totales' if markets <= {'Totales','Totales V2'} else 'Props'
            version=re.search(r'(?:^|[_\s])v(\d+)(?:$|[_\s])',raw,re.I)
            label=f'{family} {sport}'+(f' · V{version.group(1)}' if version else '')
        used[label]=used.get(label,0)+1
        if raw not in KNOWN:label+=f' · edición {used[label]}'
        names[(str(sport),str(model))]=label
    return names


def label_models(frame, names):
    result=frame.copy()
    result['modelo_visible']=[names[(str(r.deporte),str(r.modelo))] for r in result.itertuples()]
    return result
