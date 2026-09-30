"""Correspondencia de juegos por IDs de equipos y hora; no colapsa dobles carteleras."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from mlb_totales.core import decimal_odds
from mlb_totales.predecir import IDS
from mlb_totales.descargar_pitcheo import fetch_json,TYPES

MX=ZoneInfo('America/Mexico_City')
ALIASES={'OAKLAND ATHLETICS':'ATH','ATHLETICS':'ATH','SACRAMENTO ATHLETICS':'ATH',
         'CLEVELAND INDIANS':'CLE','CHICAGO WHITE SOX':'CWS'}
NAMES={'Arizona Diamondbacks':'ARI','Atlanta Braves':'ATL','Baltimore Orioles':'BAL',
 'Boston Red Sox':'BOS','Chicago Cubs':'CHC','Chicago White Sox':'CWS',
 'Cincinnati Reds':'CIN','Cleveland Guardians':'CLE','Colorado Rockies':'COL',
 'Detroit Tigers':'DET','Houston Astros':'HOU','Kansas City Royals':'KC',
 'Los Angeles Angels':'LAA','Los Angeles Dodgers':'LAD','Miami Marlins':'MIA',
 'Milwaukee Brewers':'MIL','Minnesota Twins':'MIN','New York Mets':'NYM',
 'New York Yankees':'NYY','Philadelphia Phillies':'PHI','Pittsburgh Pirates':'PIT',
 'San Diego Padres':'SD','San Francisco Giants':'SF','Seattle Mariners':'SEA',
 'St. Louis Cardinals':'STL','Tampa Bay Rays':'TB','Texas Rangers':'TEX',
 'Toronto Blue Jays':'TOR','Washington Nationals':'WSH'}
ALIASES.update({k.upper():v for k,v in NAMES.items()})


def team_id(value):
    value=str(value).strip().upper()
    return IDS.get(ALIASES.get(value,value))


def utc(value,zone='UTC'):
    ts=pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError('Fecha ausente.')
    return ts.tz_localize(zone).tz_convert('UTC') if ts.tzinfo is None else ts.tz_convert('UTC')


def calendar(day):
    d=pd.Timestamp(day).date()
    data=fetch_json('schedule',{'sportId':1,'startDate':str(d-timedelta(days=1)),
        'endDate':str(d+timedelta(days=1)),'gameType':TYPES,'hydrate':'probablePitcher,linescore'})
    rows=[]
    for item in data.get('dates',[]):
        for g in item['games']:
            if g['status'].get('abstractGameState')!='Preview' or g.get('scheduledInnings',9)!=9:
                continue
            if any(g.get(k) for k in ('resumeDate','resumedFrom','resumedFromDate')):
                continue
            if any(x in g['status'].get('detailedState','').lower() for x in ('postponed','cancelled','suspended')):
                continue
            start=utc(g['gameDate'])
            if start.tz_convert(MX).date()!=d:
                continue
            h,a=g['teams']['home'],g['teams']['away']
            rows.append(dict(game_id=g['gamePk'],fecha=g.get('officialDate',item['date']),
                start_utc=start,local=h['team']['name'],visitante=a['team']['name'],
                home_id=h['team']['id'],away_id=a['team']['id'],game_type=g['gameType'],
                venue_id=g['venue']['id'],home_pitcher_id=h.get('probablePitcher',{}).get('id'),
                away_pitcher_id=a.get('probablePitcher',{}).get('id'),
                abridor_local=h.get('probablePitcher',{}).get('fullName','TBD'),
                abridor_visitante=a.get('probablePitcher',{}).get('fullName','TBD')))
    return pd.DataFrame(rows)


def match(fixtures,quotes,now=None,max_age_minutes=180,
          game_timezone='America/Mexico_City',quote_timezone='America/Mazatlan'):
    now=utc(now if now is not None else datetime.now(timezone.utc))
    if fixtures.empty:return pd.DataFrame()
    quotes=quotes.copy()
    if not quotes.empty:
        quotes['home_id']=quotes.equipo_local.map(team_id)
        quotes['away_id']=quotes.equipo_visitante.map(team_id)
        quotes['start_utc']=quotes.fecha.map(lambda v:utc(v,game_timezone))
        quotes['captured_utc']=quotes.timestamp_captura.map(lambda v:utc(v,quote_timezone))
    output=[]
    for _,game in fixtures.iterrows():
        if utc(game.start_utc)<=now:
            continue
        group=quotes[(quotes.home_id==game.home_id)&(quotes.away_id==game.away_id)] if not quotes.empty else quotes
        if group.empty:
            output.append(dict(game,estado_mercado='SIN_LINEA'))
            continue
        for house,q in group.groupby('casa_apuestas',sort=True):
            # Elegir la hora más cercana, nunca reutilizar una cuota de una doble cartelera ambigua.
            starts=q[['id_juego','start_utc']].drop_duplicates()
            starts['delta']=starts.start_utc.map(lambda v:abs((v-utc(game.start_utc)).total_seconds()))
            starts=starts.sort_values('delta')
            if starts.iloc[0].delta>3600 or (len(starts)>1 and starts.iloc[0].delta==starts.iloc[1].delta):
                output.append(dict(game,casa_apuestas=house,estado_mercado='HORARIO_NO_COINCIDE'))
                continue
            odds_id=starts.iloc[0].id_juego
            q=q[q.id_juego==odds_id]
            q=q[q.captured_utc==q.captured_utc.max()].drop_duplicates(
                ['linea','cuota_over','cuota_under'])
            if len(q)!=1:
                output.append(dict(game,casa_apuestas=house,estado_mercado='CUOTA_AMBIGUA'))
                continue
            quote=q.iloc[0]
            age=(now-quote.captured_utc).total_seconds()/60
            state='OK' if -5<=age<=max_age_minutes else 'CUOTA_ANTIGUA'
            try:
                line=float(quote.linea)
                if not np.isfinite(line) or line<=0:raise ValueError('Línea inválida.')
                over=decimal_odds(quote.cuota_over);under=decimal_odds(quote.cuota_under)
                if not np.isfinite(over) or not np.isfinite(under):raise ValueError('Cuotas incompletas.')
            except (ValueError,TypeError):
                output.append(dict(game,casa_apuestas=house,estado_mercado='CUOTA_INVALIDA'))
                continue
            output.append(dict(game,casa_apuestas=house,odds_game_id=str(odds_id),
                linea=line,cuota_over=over,cuota_under=under,
                captured_utc=quote.captured_utc,age_minutes=age,estado_mercado=state))
    result=pd.DataFrame(output)
    # Una fuente de cuotas no puede asignarse a dos juegos distintos de una doble cartelera.
    if 'odds_game_id' in result:
        ok=result.estado_mercado=='OK'
        reused=result[ok].groupby(['odds_game_id','casa_apuestas']).game_id.nunique()
        for (oid,house),n in reused.items():
            if n>1:
                result.loc[(result.odds_game_id==oid)&(result.casa_apuestas==house),'estado_mercado']='JUEGO_AMBIGUO'
    return result
