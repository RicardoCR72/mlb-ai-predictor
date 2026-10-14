"""Fuentes de solo lectura; diferencia capturas originales de reconstrucciones."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from core.comparador import read_models,normalize,COLUMNS,VERIFIED
from core.bankroll import rows
from mlb_totales import registro
from core.combinadas_datos import nfl_starts


def read_confidence(conn,root):
    frames=[];errors=[]
    if conn is not None:
        base,errors=read_models(conn)
        # Releer totales con su masa push; no usar confianza incondicional como binaria.
        base=base[~((base.deporte=='MLB')&base.mercado.eq('Totales V2'))].copy()
        frames.append(base)
        try:
            raw=registro.settle(registro.history(conn))
            if raw.empty:raw=pd.DataFrame(columns=['candidato','recorded_utc','quote_captured_utc','start_utc','p_push','confianza','fecha_oficial','model_id','cuota_seleccion','game_pk','resultado'])
            raw=raw[raw.candidato.eq(1)].copy()
            valid=pd.to_datetime(raw.recorded_utc,utc=True).lt(pd.to_datetime(raw.start_utc,utc=True)) & pd.to_datetime(raw.quote_captured_utc,utc=True).lt(pd.to_datetime(raw.start_utc,utc=True))
            raw=raw[valid & raw.p_push.between(0,1,inclusive='left')].copy()
            raw['probabilidad']=raw.confianza/(1-raw.p_push)
            raw=raw.rename(columns={'fecha_oficial':'fecha','model_id':'modelo','cuota_seleccion':'cuota'})
            prepared=normalize(raw,sport='MLB',market='Totales',identity=['game_pk'],verified=True)
            push=raw.drop_duplicates(['modelo','game_pk']).set_index(['modelo','game_pk']).p_push
            prepared['p_push']=[float(push.loc[(r.modelo,int(r.identidad))]) for r in prepared.itertuples()]
            prepared['tipo_probabilidad']='Condicional a no push'
            frames.append(prepared)
        except Exception:errors.append('Totales MLB: no se pudo leer la masa de push.')
        try:
            raw=rows(conn,'''SELECT p.id_juego,p.modelo_version AS modelo,p.linea_total,j.fecha,
                p.probabilidad_pick/100 AS probabilidad,p.cuota_pick AS cuota,p.resultado_pick AS resultado
                FROM nfl_predicciones_totales p JOIN nfl_juegos j ON j.id_juego=p.id_juego
                WHERE p.estado_pick='PICK' ORDER BY p.actualizado_en DESC,p.id_prediccion DESC''')
            if not raw.empty:
                line=pd.to_numeric(raw.linea_total,errors='coerce')
                raw=raw[np.isfinite(line)&line.mod(1).ne(0)]
            frames[0]=frames[0][~((frames[0].deporte=='NFL')&frames[0].mercado.eq('Totales'))]
            frames.append(normalize(raw,sport='NFL',market='Totales',identity=['id_juego'],american=True))
        except Exception:
            frames[0]=frames[0][~((frames[0].deporte=='NFL')&frames[0].mercado.eq('Totales'))]
            errors.append('Totales NFL: faltan líneas para excluir casos con push posible.')
        try:
            publications=rows(conn,'''SELECT s.id_juego,s.id_jugador,s.tipo_prop,s.modelo_version AS modelo,
                s.payload,s.publicada_en,j.fecha,p.valor_real
                FROM nfl_publicaciones_props s JOIN nfl_juegos j ON j.id_juego=s.id_juego
                JOIN nfl_proyecciones_props p ON p.id_juego=s.id_juego AND p.id_jugador=s.id_jugador
                AND p.tipo_prop=s.tipo_prop AND p.modelo_version=s.modelo_version
                ORDER BY s.publicada_en ASC''')
            starts=nfl_starts(root);records=[]
            for r in publications.to_dict('records'):
                start=starts.get(str(r['id_juego']));published=pd.Timestamp(r['publicada_en'])
                published=published.tz_localize('UTC') if published.tzinfo is None else published.tz_convert('UTC')
                if start is None or pd.isna(published) or published>=pd.Timestamp(start):continue
                saved=json.loads(r['payload']) if isinstance(r['payload'],str) else r['payload']
                real=float(r['valor_real']) if r['valor_real'] is not None else np.nan
                side=saved['seleccion'];line=float(saved.get('linea',.5)) if side=='ANOTA' else float(saved['linea'])
                if not np.isfinite(real) or side not in ('OVER','UNDER','ANOTA'):continue
                result=('GANADA' if real>0 else 'PERDIDA') if side=='ANOTA' else 'PUSH' if real==line else 'GANADA' if ((real>line)==(side=='OVER')) else 'PERDIDA'
                records.append(dict(r,mercado=r['tipo_prop'],probabilidad=saved['probabilidad_pick'],
                                    cuota=saved.get('cuota_pick'),resultado=result,estado_publicacion=saved.get('estado_pick','DESCONOCIDO')))
            verified=normalize(pd.DataFrame(records),sport='NFL',market=None,identity=['id_juego','id_jugador','tipo_prop'],american=True,verified=True)
            if not verified.empty:
                statuses={}
                for r in records:statuses.setdefault((r['modelo'],str(r['id_juego'])+'|'+str(r['id_jugador'])+'|'+r['tipo_prop']),r['estado_publicacion'])
                verified['estado_publicacion']=[statuses[(r.modelo,r.identidad)] for r in verified.itertuples()]
                verified['apto_ajuste']=verified.estado_publicacion.eq('CANDIDATO')
                ids=set(zip(verified.deporte,verified.mercado,verified.modelo,verified.identidad))
                frames[0]=frames[0][[tuple(r) not in ids for r in frames[0][['deporte','mercado','modelo','identidad']].itertuples(index=False,name=None)]]
                frames.append(verified)
        except Exception:errors.append('NFL: no se pudieron verificar las publicaciones originales de props.')
    else:errors.append('MLB y NFL no disponibles: falta conexión de datos.')
    try:
        folder=Path(root)/'futbol_liga_mx';raw=pd.read_csv(folder/'modelos/confirmacion.csv')
        raw['modelo']='Liga MX congelado · confirmación 2024-25'
        raw['probabilidad']=raw.p_calibrada;raw['cuota']=np.nan
        raw['resultado']=np.where(raw.over25.eq(1),'GANADA','PERDIDA')
        f=normalize(raw,sport='Liga MX',market='Over 2.5',identity=['fecha','local','visitante'])
        f['procedencia']='Confirmación histórica · reconstruida'
        frames.append(f)
    except Exception:errors.append('Liga MX: confirmación histórica no disponible.')
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS),errors
