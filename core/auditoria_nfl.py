"""Auditoría descriptiva de picks publicados; no ajusta modelos ni cuotas."""
import numpy as np
import pandas as pd

KEYS = ['id_juego','id_jugador']
PUBLISHED = ['CANDIDATO','REVISAR LESION']


def numeric(frame, column):
    return pd.to_numeric(frame.get(column,pd.Series(np.nan,index=frame.index)),errors='coerce').replace([np.inf,-np.inf],np.nan)


def receiving_audit(picks, history):
    if picks.empty:
        return pd.DataFrame()
    frame = picks[picks.tipo_prop.eq('receiving_yards') & picks.estado_pick.isin(PUBLISHED) &
                  picks.resultado_pick.isin(['GANADA','PERDIDA','PUSH'])].copy()
    if frame.empty:
        return frame
    # La tabla de rendimiento ya identifica el pick; otras capturas no son apuestas nuevas.
    frame = frame.drop_duplicates(KEYS+['tipo_prop'])
    rec = history[history.tipo_prop.eq('receptions')].copy()
    if not rec.empty:
        rec = rec.sort_values('actualizado_en',ascending=False) if 'actualizado_en' in rec else rec
        rec = rec.drop_duplicates(KEYS)
        rec['recepciones_proyectadas'] = numeric(rec,'proyeccion')
        rec['recepciones_reales'] = numeric(rec,'valor_real')
        frame = frame.merge(rec[KEYS+['recepciones_proyectadas','recepciones_reales']],on=KEYS,how='left',validate='one_to_one')
    else:
        frame['recepciones_proyectadas'] = np.nan; frame['recepciones_reales'] = np.nan
    frame['Fuente'] = 'Histórico guardado · versión original no verificada'
    frame['dependencia_lesion'] = frame.get('contexto_lesiones',pd.Series('',index=frame.index)).fillna('').str.contains('Dependencia de lesión:',regex=False)
    # Un registro inmutable solo se utiliza si coincide con la línea y la versión del pick.
    if 'auditoria_payload' in frame:
        import json
        for index,row in frame.iterrows():
            raw = row.get('auditoria_payload')
            if not isinstance(raw,str): continue
            saved = json.loads(raw)
            for column in ['linea','proyeccion','seleccion','probabilidad_pick','cuota_pick','estado_lesion','contexto_lesiones','dependencia_lesion','recepciones_proyectadas']:
                if column in saved: frame.at[index,column] = saved[column]
            frame.at[index,'Fuente'] = 'Publicación conservada'
            actual = pd.to_numeric(row.get('valor_real'),errors='coerce')
            price = pd.to_numeric(saved.get('cuota_pick'),errors='coerce')
            line = pd.to_numeric(saved.get('linea'),errors='coerce')
            if pd.notna(actual) and pd.notna(line) and pd.notna(price) and np.isfinite([actual,line,price]).all() and price != 0:
                won = actual > line if saved['seleccion'] == 'OVER' else actual < line
                frame.at[index,'resultado_pick'] = 'PUSH' if actual == line else 'GANADA' if won else 'PERDIDA'
                frame.at[index,'beneficio_unidades'] = 0.0 if actual == line else (price/100 if price>0 else 100/abs(price)) if won else -1.0
            else:
                frame.at[index,'beneficio_unidades'] = np.nan
    frame['Error yardas'] = numeric(frame,'proyeccion')-numeric(frame,'valor_real')
    pred_rec = numeric(frame,'recepciones_proyectadas'); actual_rec = numeric(frame,'recepciones_reales')
    pred_ypr = (numeric(frame,'proyeccion')/pred_rec.where(pred_rec>0)).replace([np.inf,-np.inf],np.nan)
    real_ypr = (numeric(frame,'valor_real')/actual_rec.where(actual_rec>0)).replace([np.inf,-np.inf],np.nan)
    frame['Error recepciones'] = pred_rec-actual_rec
    frame['Error yardas/recepción'] = pred_ypr-real_ypr
    comparable = (pred_rec>0) & (actual_rec>0)
    frame['Error por volumen (yds)'] = ((pred_rec-actual_rec)*pred_ypr).where(comparable)
    frame['Error por eficiencia (yds)'] = (actual_rec*(pred_ypr-real_ypr)).where(comparable)
    own = frame.get('estado_lesion',pd.Series('',index=frame.index)).fillna('').str.lower()
    context = frame.get('contexto_lesiones',pd.Series('',index=frame.index)).fillna('')
    frame['Lesiones'] = np.select([frame.dependencia_lesion.astype(bool),own.isin(['questionable','doubtful','out']),
        context.str.contains(r'QUESTIONABLE|DOUBTFUL|OUT',case=False,regex=True)],
        ['Dependencia en escenarios','Lesión propia','Contexto de compañeros'],default='Sin alerta registrada')
    frame['Confianza'] = pd.cut(numeric(frame,'probabilidad_pick')*100,[0,60,65,100],right=False,
                               labels=['Menos de 60%','60–65%','65% o más']).astype('object').fillna('No disponible')
    frame.loc[numeric(frame,'probabilidad_pick').eq(1),'Confianza'] = '65% o más'
    frame['Unidades conocidas'] = numeric(frame,'beneficio_unidades')
    frame.loc[frame.resultado_pick.eq('PUSH'),'Unidades conocidas'] = 0.0
    frame['Ganada'] = frame.resultado_pick.eq('GANADA').astype(int)
    frame['Decidida'] = frame.resultado_pick.isin(['GANADA','PERDIDA']).astype(int)
    return frame


def summarize(frame, by):
    if frame.empty: return pd.DataFrame()
    result = frame.groupby(by,dropna=False,observed=True).agg(Picks=('id_juego','size'),
        Ganadas=('Ganada','sum'),Decididas=('Decidida','sum'),Muestra_ROI=('Unidades conocidas','count'),
        Unidades=('Unidades conocidas',lambda s:s.sum(min_count=1)),
        Sesgo_yardas=('Error yardas','mean'),MAE_yardas=('Error yardas',lambda s:s.abs().mean()),
        Pares_volumen_eficiencia=('Error por volumen (yds)','count'),
        Error_volumen=('Error por volumen (yds)','mean'),Error_eficiencia=('Error por eficiencia (yds)','mean')).reset_index()
    result['Acierto (%)'] = 100*result.Ganadas/result.Decididas.replace(0,np.nan)
    result['ROI (%)'] = 100*result.Unidades/result.Muestra_ROI.replace(0,np.nan)
    return result.drop(columns=['Ganadas','Decididas'])


def render_receiving_audit(picks, history):
    import streamlit as st
    with st.expander('Auditoría de yardas de recepción'):
        frame = receiving_audit(picks,history)
        if frame.empty:
            st.caption('No hay picks evaluados de yardas de recepción para los filtros seleccionados.')
            return
        st.caption('Usa los filtros de rendimiento actuales. Errores positivos indican sobreestimación. '
                   'Las proyecciones sin registro de publicación se distinguen; no se reconstruyen como si fueran originales.')
        st.dataframe(summarize(frame,['season','week','seleccion']),hide_index=True,use_container_width=True)
        st.dataframe(summarize(frame,['Lesiones','Confianza']),hide_index=True,use_container_width=True)
        st.caption('La descomposición requiere recepciones proyectadas y reales mayores que cero. '
                   'Error de yardas = error por volumen + error por eficiencia. Los datos faltantes no cuentan como cero. '
                   'Los picks de un mismo partido o jugador pueden estar relacionados; una diferencia no demuestra causalidad.')
        columns = [c for c in ['season','week','player_name','away_team','home_team','seleccion','linea','proyeccion',
            'valor_real','recepciones_proyectadas','recepciones_reales','Error yardas','Error recepciones',
            'Error yardas/recepción','Error por volumen (yds)','Error por eficiencia (yds)',
            'probabilidad_pick','cuota_pick','modelo_version','Lesiones','Fuente','timestamp_captura','contexto_lesiones','resultado_pick','Unidades conocidas'] if c in frame]
        st.dataframe(frame[columns],hide_index=True,use_container_width=True)
        st.download_button('Descargar auditoría de yardas',frame[columns].to_csv(index=False).encode('utf-8-sig'),
                           'auditoria_yardas_recepcion.csv','text/csv',key='nfl_receiving_audit_download')
