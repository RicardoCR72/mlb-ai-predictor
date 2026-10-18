"""Fuentes de solo lectura; diferencia capturas originales de reconstrucciones."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from core.comparador import read_legacy_models as read_models,normalize,COLUMNS,VERIFIED
from core.bankroll import rows
from mlb_totales import registro
from core.combinadas_datos import nfl_starts
from mlb.publicaciones_moneyline import HISTORY_SQL


def read_history(conn,root,*,calibration=False,include_liga=True,only_candidates=True):
    frames=[];errors=[]
    if conn is not None:
        base,errors=read_models(conn)
        # Releer totales con su masa push; no usar confianza incondicional como binaria.
        base=base[~((base.deporte=='MLB')&base.mercado.eq('Totales V2'))].copy()
        frames.append(base)
        try:
            raw=rows(conn,HISTORY_SQL)
            verified=normalize(raw,sport='MLB',market='Moneyline',identity=['id_juego'],verified=True)
            if not verified.empty:
                # Retirar solo el duplicado legacy del mismo partido; no certificar el resto.
                legacy_ids=set(pd.to_datetime(raw.fecha).dt.strftime('%Y-%m-%d')+'|'+raw.equipo_local+'|'+raw.equipo_visitante)
                legacy=frames[0]
                mask=legacy.deporte.eq('MLB')&legacy.mercado.eq('Moneyline')&legacy.identidad.isin(legacy_ids)
                frames[0]=legacy[~mask].copy()
                verified['evento']='MLB|'+verified.identidad
                verified['apto_ajuste']=True
                frames.append(verified)
        except Exception:errors.append('Moneyline MLB: todavía no hay publicaciones originales verificables disponibles.')

        try:
            raw=registro.settle(registro.history(conn))
            if raw.empty:raw=pd.DataFrame(columns=['candidato','recorded_utc','quote_captured_utc','start_utc','p_push','confianza','fecha_oficial','model_id','cuota_seleccion','game_pk','resultado'])
            if calibration or only_candidates:raw=raw[raw.candidato.eq(1)].copy()
            valid=pd.to_datetime(raw.recorded_utc,utc=True).lt(pd.to_datetime(raw.start_utc,utc=True)) & pd.to_datetime(raw.quote_captured_utc,utc=True).le(pd.to_datetime(raw.recorded_utc,utc=True))
            raw=raw[valid & raw.p_push.between(0,1,inclusive='left')].copy()
            raw['probabilidad']=raw.confianza/(1-raw.p_push) if calibration else raw.confianza
            raw=raw.rename(columns={'fecha_oficial':'fecha','model_id':'modelo','cuota_seleccion':'cuota','quote_captured_utc':'quote_utc','recorded_utc':'publicada_utc'})
            prepared=normalize(raw,sport='MLB',market='Totales',identity=['game_pk'],verified=True)
            push=raw.drop_duplicates(['modelo','game_pk']).set_index(['modelo','game_pk']).p_push
            prepared['p_push']=[float(push.loc[(r.modelo,int(r.identidad))]) for r in prepared.itertuples()]
            prepared['tipo_probabilidad']='Condicional a no push' if calibration else 'Probabilidad original'
            frames.append(prepared)
        except Exception:errors.append('Totales MLB: no se pudo leer la masa de push.')
        try:
            raw=rows(conn,'''SELECT p.id_juego,p.modelo_version AS modelo,p.linea_total,p.seleccion,j.fecha,j.equipo_local,j.equipo_visitante,
                p.probabilidad_pick/100 AS probabilidad,p.cuota_pick AS cuota,p.resultado_pick AS resultado
                FROM nfl_predicciones_totales p JOIN nfl_juegos j ON j.id_juego=p.id_juego
                WHERE p.estado_pick='PICK' ORDER BY p.actualizado_en DESC,p.id_prediccion DESC''')
            if calibration and not raw.empty:
                line=pd.to_numeric(raw.linea_total,errors='coerce')
                raw=raw[np.isfinite(line)&line.mod(1).ne(0)]
            frames[0]=frames[0][~((frames[0].deporte=='NFL')&frames[0].mercado.eq('Totales'))]
            frames.append(normalize(raw,sport='NFL',market='Totales',identity=['id_juego'],american=True))
        except Exception:
            frames[0]=frames[0][~((frames[0].deporte=='NFL')&frames[0].mercado.eq('Totales'))]
            errors.append('Totales NFL: faltan líneas para excluir casos con push posible.')
        try:
            publications=rows(conn,'''SELECT s.id_juego,s.id_jugador,s.tipo_prop,s.modelo_version AS modelo,
                s.payload,s.publicada_en,j.fecha,j.equipo_local,j.equipo_visitante,u.nombre AS jugador,p.valor_real
                FROM nfl_publicaciones_props s JOIN nfl_juegos j ON j.id_juego=s.id_juego
                JOIN nfl_proyecciones_props p ON p.id_juego=s.id_juego AND p.id_jugador=s.id_jugador
                AND p.tipo_prop=s.tipo_prop AND p.modelo_version=s.modelo_version
                AND p.id_proyeccion=(SELECT p2.id_proyeccion FROM nfl_proyecciones_props p2
                    WHERE p2.id_juego=s.id_juego AND p2.id_jugador=s.id_jugador
                    AND p2.tipo_prop=s.tipo_prop AND p2.modelo_version=s.modelo_version
                    ORDER BY (p2.valor_real IS NOT NULL) DESC,p2.evaluado_en DESC,p2.actualizado_en DESC,p2.id_proyeccion DESC LIMIT 1)
                LEFT JOIN nfl_jugadores u ON u.id_jugador=s.id_jugador
                ORDER BY s.publicada_en ASC''')
            starts=nfl_starts(root);records=[]
            for r in publications.to_dict('records'):
                start=starts.get(str(r['id_juego']));published=pd.Timestamp(r['publicada_en'])
                published=published.tz_localize('UTC') if published.tzinfo is None else published.tz_convert('UTC')
                saved=json.loads(r['payload']) if isinstance(r['payload'],str) else r['payload']
                clock_known=saved.get('publicacion_utc') is True
                if clock_known and start is not None and pd.notna(published) and published>=pd.Timestamp(start):continue
                clock_verified=clock_known and start is not None and pd.notna(published) and published<pd.Timestamp(start)
                real=float(r['valor_real']) if r['valor_real'] is not None else np.nan
                side=saved['seleccion'];line=float(saved.get('linea',.5)) if side=='ANOTA' else float(saved['linea'])
                if side not in ('OVER','UNDER','ANOTA'):continue
                result='PENDIENTE' if not np.isfinite(real) else ('GANADA' if real>0 else 'PERDIDA') if side=='ANOTA' else 'PUSH' if real==line else 'GANADA' if ((real>line)==(side=='OVER')) else 'PERDIDA'
                records.append(dict(r,seleccion=side,linea=line,mercado=r['tipo_prop'],probabilidad=saved['probabilidad_pick'],
                                    cuota=saved.get('cuota_pick'),resultado=result,estado_publicacion=saved.get('estado_pick','DESCONOCIDO'),clock_verified=bool(clock_verified)))
            verified=normalize(pd.DataFrame(records),sport='NFL',market=None,identity=['id_juego','id_jugador','tipo_prop'],american=True,verified=True)
            if not verified.empty:
                statuses={};clocks={}
                for r in records:
                    key=(r['modelo'],str(r['id_juego'])+'|'+str(r['id_jugador'])+'|'+r['tipo_prop'])
                    statuses.setdefault(key,r['estado_publicacion']);clocks.setdefault(key,r['clock_verified'])
                verified['estado_publicacion']=[statuses[(r.modelo,r.identidad)] for r in verified.itertuples()]
                verified['apto_ajuste']=verified.estado_publicacion.eq('CANDIDATO')
                verified['procedencia']=[VERIFIED if clocks[(r.modelo,r.identidad)] else 'Publicación inmutable · hora no certificada' for r in verified.itertuples()]
                ids=set(zip(verified.deporte,verified.mercado,verified.modelo,verified.identidad))
                frames[0]=frames[0][[tuple(r) not in ids for r in frames[0][['deporte','mercado','modelo','identidad']].itertuples(index=False,name=None)]]
                frames.append(verified)
        except Exception:errors.append('NFL: no se pudieron verificar las publicaciones originales de props.')
        try:
            raw=rows(conn,"""SELECT s.*,j.fecha,j.equipo_local,j.equipo_visitante,j.marcador_local,j.marcador_visitante,j.estado FROM nfl_publicaciones_totales s
                JOIN nfl_juegos j ON CAST(j.id_juego AS BINARY)=CAST(s.id_juego AS BINARY)
                WHERE s.publicada_utc<s.start_utc ORDER BY s.publicada_utc ASC""")
            if not raw.empty:
                score=(pd.to_numeric(raw.marcador_local,errors='coerce')+pd.to_numeric(raw.marcador_visitante,errors='coerce')).where(raw.estado.str.lower().eq('finalizado'))
                raw['resultado']=np.where(score.isna(),'PENDIENTE',np.where(score.eq(raw.linea),'PUSH',
                    np.where((score.gt(raw.linea))==raw.seleccion.eq('OVER'),'GANADA','PERDIDA')))
                if calibration:raw=raw[pd.to_numeric(raw.linea).mod(1).ne(0)].copy()
                original=normalize(raw,sport='NFL',market='Totales',identity=['id_juego'],american=True,verified=True)
                original['apto_ajuste']=True
                keys=set(zip(original.modelo,original.identidad))
                frames=[f[~(f.deporte.eq('NFL')&f.mercado.eq('Totales')&pd.Series([(r.modelo,r.identidad) in keys for r in f.itertuples()],index=f.index))] for f in frames]
                frames.append(original)
        except Exception:errors.append('Totales NFL: publicaciones originales no disponibles; históricos sin certificar.')
    else:errors.append('MLB y NFL no disponibles: falta conexión de datos.')
    if not include_liga:
        return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS),errors
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


def read_confidence(conn,root):
    return read_history(conn,root,calibration=True)
