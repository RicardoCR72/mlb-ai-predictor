"""Evidencia explícita de ausencia; un registro estadístico faltante no es un DNP."""
import pandas as pd


def _matching(frame, season, week, player, teams, game_type=None):
    required={'season','week','gsis_id','team'}
    if frame.empty or not required.issubset(frame.columns):return pd.DataFrame()
    aliases={'LA':'LAR','JAC':'JAX','WSH':'WAS','OAK':'LV','SD':'LAC'}
    teams={aliases.get(t,t) for t in teams}
    team_values=frame.team.astype(str).replace(aliases)
    frame=frame[team_values.isin(teams)]
    if game_type and 'game_type' in frame:
        kind='REG' if game_type=='REG' else 'POST'
        frame=frame[frame.game_type.eq(kind)]
    return frame[pd.to_numeric(frame.season,errors='coerce').eq(int(season)) &
                 pd.to_numeric(frame.week,errors='coerce').eq(int(week)) &
                 frame.gsis_id.astype(str).eq(player)]


def nonparticipation_evidence(pending, final_ids, stats, rosters, snaps, injuries):
    proofs={}
    for row in pending:
        game=str(row['id_juego']);player=str(row['id_jugador']);key=(game,player)
        if game not in final_ids or key in stats.index or key in proofs:continue
        teams={row.get('equipo_local'),row.get('equipo_visitante')} - {None}
        roster=_matching(rosters,row['temporada'],row['semana'],player,teams,row.get('tipo_juego'))
        injury=_matching(injuries,row['temporada'],row['semana'],player,teams,row.get('tipo_juego'))
        proof={'game_id':game,'player_id':player,'season':int(row['temporada']),'week':int(row['semana'])}
        # La identidad GSIS/PFR es estable aunque el roster semanal llegue tarde.
        # Reusar solo esa correspondencia; nunca el estatus de otra semana.
        identity_roster=rosters
        required={'season','gsis_id','pfr_id'}
        if required.issubset(rosters.columns):
            identity_roster=rosters[
                pd.to_numeric(rosters.season,errors='coerce').eq(int(row['temporada'])) &
                rosters.gsis_id.astype(str).eq(player)]
        else:
            identity_roster=pd.DataFrame()
        pfr_ids=identity_roster.pfr_id.dropna().astype(str).unique() if 'pfr_id' in identity_roster else []
        snap=pd.DataFrame()
        if len(pfr_ids)==1 and {'game_id','pfr_player_id'}.issubset(snaps.columns):
            snap=snaps[snaps.game_id.astype(str).eq(game)&snaps.pfr_player_id.astype(str).eq(pfr_ids[0])]
        counts=['offense_snaps','defense_snaps','st_snaps']
        if not snap.empty and set(counts).issubset(snap.columns):
            values=snap[counts].apply(pd.to_numeric,errors='coerce')
            # Participation overrides a stale inactive/injury designation.
            if values.gt(0).any().any():continue
            if values.notna().all().all() and values.eq(0).all().all():
                proofs[key]=dict(proof,reason='Jugador sin participación confirmada',source='nflverse/PFR snap counts',snaps=values.to_dict('records'))
                continue
        if not injury.empty and 'report_status' in injury:
            states=injury.report_status.fillna('').astype(str).str.lower().str.strip()
            if states.eq('out').all():
                proofs[key]=dict(proof,reason='Jugador inactivo (Out)',source='nflverse injury report',report_status='Out')
                continue
        if not roster.empty and 'status' in roster:
            states=roster.status.fillna('').astype(str).str.upper().str.strip()
            if states.isin(['INA','PUP','RES','SUS']).all():
                proofs[key]=dict(proof,reason='Jugador inactivo confirmado',source='nflverse weekly roster',roster_status=sorted(states.unique()))
    return proofs


def load_nonparticipation(seasons,pending,final_ids,stats,provider):
    frames=[]
    for name in ('load_rosters_weekly','load_snap_counts','load_injuries'):
        try:
            frames.append(getattr(provider,name)(seasons).to_pandas())
        except Exception:
            # Missing/delayed optional data leaves ambiguous props pending.
            frames.append(pd.DataFrame())
            print('Evidencia de participación no disponible:',name)
    return nonparticipation_evidence(pending,final_ids,stats,*frames)
