"""Comparación de registros guardados; nunca reconstruye picks ni consulta cuotas actuales."""
import numpy as np
import pandas as pd
from core.bankroll import rows, decimal_odds
from mlb_totales import registro

COLUMNS=['fecha','deporte','mercado','modelo','procedencia','resultado','probabilidad','cuota','unidades','identidad','Temporada']
SAVED='Guardado · hora no verificable'
VERIFIED='Previo al inicio verificado'


def normalize(frame,*,sport,market,identity,american=False,verified=False):
    if frame.empty:return pd.DataFrame(columns=COLUMNS)
    out=frame.copy()
    out['deporte']=sport
    if market is not None:out['mercado']=market
    names={'receptions':'Recepciones','receiving_yards':'Yardas de recepción','passing_yards':'Yardas por pase',
           'passing_tds':'Pases de touchdown','rushing_yards':'Yardas terrestres','anytime_td':'Anota touchdown'}
    out['mercado']=out['mercado'].replace(names)
    out['procedencia']=VERIFIED if verified else SAVED
    out['resultado']=out['resultado'].astype(str).str.upper().str.strip()
    out['fecha']=pd.to_datetime(out['fecha'],errors='coerce')
    out['Temporada']=out['temporada'].astype(str) if 'temporada' in out else out['fecha'].dt.year.astype('Int64').astype(str)
    out['probabilidad']=pd.to_numeric(out['probabilidad'],errors='coerce')
    out['cuota']=pd.to_numeric(out['cuota'],errors='coerce')
    if american:
        def convert(v):
            if pd.isna(v):return np.nan
            try:return decimal_odds(v)
            except ValueError:return np.nan
        out['cuota']=out['cuota'].map(convert)
    valid=np.isfinite(out['cuota']) & out['cuota'].gt(1)
    # Push puede liquidarse sin cuota: beneficio conocido de cero.
    out['unidades']=np.where(out['resultado'].eq('PUSH'),0,
        np.where(out['resultado'].eq('PERDIDA'),-1,
        np.where(out['resultado'].eq('GANADA') & valid,out['cuota']-1,np.nan)))
    out['identidad']=out[identity].astype(str).agg('|'.join,axis=1)
    out=out.drop_duplicates(['modelo','identidad'],keep='first')
    return out.reindex(columns=COLUMNS)


def read_models(conn):
    frames=[];errors=[]
    queries=[('MLB Moneyline','MLB','Moneyline',False,['fecha','equipo_local','equipo_visitante'],'''
        SELECT r.fecha,r.equipo_local,r.equipo_visitante,'MLB V4' AS modelo,r.confianza/100 AS probabilidad,r.cuota,
          CASE WHEN j.marcador_local IS NULL OR j.marcador_visitante IS NULL THEN 'PENDIENTE'
               WHEN j.marcador_local=j.marcador_visitante THEN 'REVISAR'
               WHEN (r.pick_ia=j.equipo_local AND j.marcador_local>j.marcador_visitante)
                 OR (r.pick_ia=j.equipo_visitante AND j.marcador_visitante>j.marcador_local) THEN 'GANADA'
               ELSE 'PERDIDA' END AS resultado
        FROM registro_picks_ia r JOIN juegos j ON DATE(j.fecha)=DATE(r.fecha)
          AND j.equipo_local=r.equipo_local AND j.equipo_visitante=r.equipo_visitante
        WHERE r.pick_ia IN (j.equipo_local,j.equipo_visitante)
          AND 1=(SELECT COUNT(*) FROM juegos j2 WHERE DATE(j2.fecha)=DATE(r.fecha)
            AND j2.equipo_local=r.equipo_local AND j2.equipo_visitante=r.equipo_visitante)
        ORDER BY r.fecha DESC'''),
        ('NFL Totales','NFL','Totales',True,['id_juego'],'''
        SELECT j.fecha,j.temporada,p.id_juego,p.modelo_version AS modelo,p.probabilidad_pick AS probabilidad,
          p.cuota_pick AS cuota,p.resultado_pick AS resultado
        FROM nfl_predicciones_totales p JOIN nfl_juegos j ON j.id_juego=p.id_juego
        WHERE p.estado_pick='PICK' ORDER BY p.actualizado_en DESC,p.id_prediccion DESC'''),
        ('NFL Props','NFL',None,True,['id_juego','id_jugador','tipo_prop'],'''
        SELECT j.fecha,j.temporada,p.id_juego,p.id_jugador,p.tipo_prop,p.tipo_prop AS mercado,p.modelo_version AS modelo,
          p.probabilidad_pick AS probabilidad,p.cuota_pick AS cuota,p.resultado_pick AS resultado
        FROM nfl_proyecciones_props p JOIN nfl_juegos j ON j.id_juego=p.id_juego
        WHERE p.estado_pick IN ('CANDIDATO','REVISAR LESION')
        ORDER BY p.actualizado_en DESC,p.id_proyeccion DESC''')]
    for label,sport,market,american,identity,sql in queries:
        try:frames.append(normalize(rows(conn,sql),sport=sport,market=market,identity=identity,american=american))
        except Exception:errors.append(label)
    try:
        raw=registro.settle(registro.history(conn))
        if not raw.empty:
            raw=raw[raw.candidato.eq(1)].copy()
            registered=pd.to_datetime(raw.recorded_utc,errors='coerce',utc=True)
            quotes=pd.to_datetime(raw.quote_captured_utc,errors='coerce',utc=True)
            starts=pd.to_datetime(raw.start_utc,errors='coerce',utc=True)
            raw=raw[registered.lt(starts)&quotes.lt(starts)]
            raw=raw.rename(columns={'fecha_oficial':'fecha','model_id':'modelo','confianza':'probabilidad',
                                    'cuota_seleccion':'cuota'})
            frames.append(normalize(raw,sport='MLB',market='Totales V2',identity=['game_pk'],verified=True))
    except Exception:errors.append('MLB Totales V2')
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS),errors


def comparison(frame):
    output=[]
    settled=frame[frame.resultado.isin(['GANADA','PERDIDA','PUSH'])].copy()
    for keys,group in settled.groupby(['deporte','mercado','modelo','procedencia'],dropna=False):
        decided=group.resultado.isin(['GANADA','PERDIDA'])
        financial=group[np.isfinite(pd.to_numeric(group.unidades,errors='coerce'))]
        n=len(financial);units=float(financial.unidades.sum())
        output.append(dict(zip(['Deporte','Mercado','Modelo','Procedencia'],keys))|
                      {'Picks evaluados':len(group),'Picks con beneficio conocido':n,'Sin beneficio conocido':len(group)-n,
                       'Ganadas':int(group.resultado.eq('GANADA').sum()),'Perdidas':int(group.resultado.eq('PERDIDA').sum()),
                       'Push':int(group.resultado.eq('PUSH').sum()),
                       'Acierto (%)':100*group.resultado.eq('GANADA').sum()/decided.sum() if decided.sum() else np.nan,
                       'Unidades':units if n else np.nan,'ROI (%)':100*units/n if n else np.nan})
    return pd.DataFrame(output)
