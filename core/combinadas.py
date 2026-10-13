"""Combinadas por confianza a partir de picks guardados; sin consultas de cuotas."""
from datetime import datetime,timezone
import hashlib
import json
import math
import unicodedata
import pandas as pd

MARKETS={'mlb_ml':'Moneyline','mlb_total':'Total de carreras','nfl_total':'Total del partido',
         'receptions':'Recepciones','receiving_yards':'Yardas de recepción','passing_yards':'Yardas por pase',
         'passing_tds':'Pases de touchdown','rushing_yards':'Yardas terrestres','anytime_td':'Anota touchdown',
         'liga_mx':'Total de goles'}


def stamp(value):
    try:
        result=pd.Timestamp(value)
        if pd.isna(result):return None
        return result.tz_localize('UTC') if result.tzinfo is None else result.tz_convert('UTC')
    except (TypeError,ValueError):return None


def finite(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (TypeError,ValueError):return None


def normalized(value):
    text=unicodedata.normalize('NFKD',str(value)).casefold()
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).split())


def prepare_candidates(options, now=None, days=1):
    now=stamp(now or datetime.now(timezone.utc)); today=now.tz_convert('America/Mexico_City').date()
    unique={}
    for option in options:
        pick=dict(option);p=finite(pick.get('probabilidad'))
        if p is None or not 0<p<1:continue
        start=stamp(pick.get('inicio_utc'))
        try:day=start.tz_convert('America/Mexico_City').date() if start is not None else pd.Timestamp(pick['fecha']).date()
        except (TypeError,ValueError,KeyError):continue
        if not 0<=(day-today).days<days or (start is not None and start<=now):continue
        captured=stamp(pick.get('cuota_capturada_utc'))
        odds=finite(pick.get('cuota'));odds=odds if odds is not None and odds>1 else None
        match=(normalized(pick['deporte']),str(day),*sorted([normalized(pick['local']),normalized(pick['visitante'])]))
        identity=match+(pick['origen'],str(pick.get('jugador_id','')),
                        normalized(pick.get('tipo_prop',pick.get('mercado',''))),normalized(pick['seleccion']))
        key=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:20]
        problems=[]
        if start is None:problems.append('Hora de inicio por confirmar')
        if pick.get('estado')=='REVISAR LESION':problems.append('Revisar lesión')
        if captured is not None and (captured>now+pd.Timedelta(minutes=5) or now-captured>pd.Timedelta(hours=24)):
            problems.append('Cuota antigua o fecha por revisar')
        pick['referencia']=dict(pick.get('referencia',{}))
        if start is not None:pick['referencia']['inicio_utc']=start.isoformat()
        pick.update(id=key,event=match,probabilidad=p,cuota=odds,inicio_utc=start,
            cuota_capturada_utc=captured,fecha=str(day),automatic=not problems,notes=problems,
            partido=f"{pick['visitante']} @ {pick['local']}")
        previous=unique.get(key)
        order=captured.value if captured is not None else -1
        if previous is None or order>previous['_capture_order']:
            pick['_capture_order']=order;unique[key]=pick
    return sorted(unique.values(),key=lambda p:(-p['probabilidad'],p['id']))


def recommend(candidates, count=3, min_probability=0):
    chosen=[];seen=set()
    for pick in candidates:
        if pick['automatic'] and pick['probabilidad']>=min_probability and pick['event'] not in seen:
            chosen.append(pick);seen.add(pick['event'])
            if len(chosen)==count:break
    return chosen


def combination(selected, now=None):
    now=stamp(now or datetime.now(timezone.utc))
    if len(selected)<2:return dict(ok=False,reason='Elige al menos dos selecciones de partidos distintos.')
    if len({p['event'] for p in selected})!=len(selected):
        return dict(ok=False,reason='Hay selecciones del mismo partido. Conserva solo una por encuentro.')
    if any(not p['automatic'] or p['inicio_utc'] is None or p['inicio_utc']<=now for p in selected):
        return dict(ok=False,reason='Hay selecciones con inicio o lesión por revisar; no se calcula la combinada.')
    houses={normalized(p.get('casa','')) for p in selected}
    quoted=all(p['cuota'] is not None and p.get('casa_verificada',False) for p in selected) and len(houses)==1
    return dict(ok=True,probability=math.prod(p['probabilidad'] for p in selected),
        odds=math.prod(p['cuota'] for p in selected) if quoted else None,
        quote_pending=not quoted)
