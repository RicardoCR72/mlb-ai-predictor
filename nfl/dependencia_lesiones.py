"""Escenarios de disponibilidad para yardas de recepción, sin cambiar el modelo."""
import numpy as np
import pandas as pd
from nfl.features_lesiones import normalizar_lesiones


def escenarios_companeros(features, lesiones):
    reports = normalizar_lesiones(lesiones)
    reports = reports[reports.position.isin(['WR','TE','RB','FB']) &
                      reports.report_status_norm.isin(['questionable','doubtful'])]
    active = features.copy(); absent = features.copy(); names = []
    for index, row in features.iterrows():
        others = reports[(reports.season == row.season) & (reports.week == row.week) &
                         (reports.team == row.team) & (reports.gsis_id.astype(str) != str(row.player_id))]
        weight = float(others.injury_weight.sum()); number = len(others)
        names.append('; '.join(others.get('full_name', others.gsis_id).astype(str).tolist()))
        for frame, replacement, count_delta in [(active, 0.0, -number), (absent, float(number), 0)]:
            for column in ['teammate_skill_injury_score','team_skill_injury_score']:
                frame.loc[index,column] = max(0.0, float(row[column])-weight+replacement)
            frame.loc[index,'team_skill_injury_count'] = max(0.0,float(row.team_skill_injury_count)+count_delta)
    return active, absent, pd.Series(names,index=features.index)


def marcar_dependencia(base, active, absent):
    """Retiene la predicción base; alerta si cambia el lado o deja de ser candidato."""
    keys = ['game_id','player_id','tipo_prop']
    result = base.copy()
    if active.empty or absent.empty:
        return result
    for label, scenario in [('juegan',active),('no_juegan',absent)]:
        fields = ['proyeccion','seleccion','estado_pick']
        result = result.merge(scenario[keys+fields].rename(columns={f:f+'_'+label for f in fields}),
                              on=keys,how='left',validate='one_to_one')
    names = result.get('companeros_en_duda',pd.Series('',index=result.index)).fillna('')
    eligible = result.tipo_prop.eq('receiving_yards') & result.estado_pick.isin(['CANDIDATO','REVISAR LESION']) & names.ne('')
    changed = pd.Series(False,index=result.index)
    for label in ['juegan','no_juegan']:
        changed |= result['seleccion_'+label].ne(result.seleccion) | ~result['estado_pick_'+label].isin(['CANDIDATO','REVISAR LESION'])
    flag = eligible & changed
    result.loc[flag,'estado_pick'] = 'REVISAR LESION'
    result['dependencia_lesion'] = flag
    for index in result.index[flag]:
        row = result.loc[index]
        note = (f"Dependencia de lesión: {names.loc[index]}. Si juegan: {row.proyeccion_juegan:.1f} yds "
                f"({row.seleccion_juegan}, {row.estado_pick_juegan}); si no juegan: {row.proyeccion_no_juegan:.1f} yds "
                f"({row.seleccion_no_juegan}, {row.estado_pick_no_juegan}). Confirmar disponibilidad.")
        result.loc[index,'contexto_lesiones'] = str(row.get('contexto_lesiones','') or '')+' | '+note
    return result
