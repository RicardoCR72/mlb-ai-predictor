"""Lectura de candidatos locales para combinadas. No prepara tablas ni escribe apuestas."""
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from core.infrastructure.queries import rows
from core.domain.odds import decimal_odds
from core.combinadas import MARKETS

QUERIES={
'mlb_total':'''SELECT game_pk AS game_id,fecha_oficial AS fecha,equipo_local AS local,equipo_visitante AS visitante,
    seleccion,linea,start_utc AS inicio_utc,cuota_seleccion AS cuota,confianza AS probabilidad,
    quote_captured_utc AS captura FROM mlb_totales_predicciones
    WHERE start_utc>UTC_TIMESTAMP() AND candidato=1 AND LOWER(TRIM(casa_apuestas))='draftkings'
    ORDER BY recorded_utc DESC''',
'mlb_ml':'''SELECT j.id_juego AS game_id,p.fecha,p.equipo_local AS local,p.equipo_visitante AS visitante,
    p.pick_ia AS seleccion,p.cuota,p.confianza/100 AS probabilidad
    FROM registro_picks_ia p JOIN juegos j ON DATE(j.fecha)=p.fecha
    AND j.equipo_local=p.equipo_local AND j.equipo_visitante=p.equipo_visitante
    WHERE LOWER(j.estado)='programado' AND DATE(j.fecha)>=CURRENT_DATE()''',
'nfl_total':'''SELECT p.id_juego AS game_id,j.fecha,j.equipo_local AS local,j.equipo_visitante AS visitante,
    p.seleccion,p.linea_total AS linea,p.cuota_pick AS american,p.probabilidad_pick/100 AS probabilidad,
    p.estado_pick AS estado FROM nfl_predicciones_totales p JOIN nfl_juegos j ON j.id_juego=p.id_juego
    WHERE LOWER(j.estado)='programado' AND p.estado_pick='PICK'
    AND (p.resultado_pick IS NULL OR p.resultado_pick='PENDIENTE')
    ORDER BY p.actualizado_en DESC''',
'nfl_prop':'''SELECT p.id_juego AS game_id,p.id_jugador AS jugador_id,p.tipo_prop,j.fecha,
    j.equipo_local AS local,j.equipo_visitante AS visitante,u.nombre AS jugador,p.seleccion,p.linea,
    p.cuota_pick AS american,p.probabilidad_pick AS probabilidad,p.estado_pick AS estado,
    l.timestamp_captura AS captura,p.contexto_lesiones AS contexto
    FROM nfl_proyecciones_props p JOIN nfl_juegos j ON j.id_juego=p.id_juego
    JOIN nfl_jugadores u ON u.id_jugador=p.id_jugador JOIN nfl_lineas_props l ON l.id_linea=p.id_linea
    WHERE LOWER(j.estado)='programado' AND p.estado_pick IN ('CANDIDATO','REVISAR LESION')
    AND (p.resultado_pick IS NULL OR p.resultado_pick='PENDIENTE')
    AND LOWER(TRIM(l.casa_apuestas))='draftkings' ORDER BY p.actualizado_en DESC'''}


from nfl.persistence.calendar import nfl_starts


def read_candidates(conn,root,now=None):
    options=[];errors=[];starts=nfl_starts(root)
    if conn is None:errors.append('Los picks MLB y NFL no están disponibles en este momento.')
    else:
        for source,sql in QUERIES.items():
            try:
                data=rows(conn,sql)
                if data.empty:continue
                if source=='mlb_ml':data=data[~data.duplicated(['fecha','local','visitante'],keep=False)]
                # Una versión por jugador/mercado; ORDER BY conserva la más reciente.
                keys=['game_id']+(['jugador_id','tipo_prop'] if source=='nfl_prop' else [])
                data=data.drop_duplicates(keys)
                for row in data.to_dict('records'):
                    side=row['seleccion']
                    if source!='mlb_ml' and side not in ('OVER','UNDER','ANOTA'):continue
                    raw=row.get('american',row.get('cuota'))
                    try:odds=decimal_odds(raw) if 'american' in row else float(raw)
                    except (ValueError,TypeError):odds=None
                    label=side if source=='mlb_ml' else f"{row.get('jugador','')} {side}"+(' '+str(row['linea']) if side!='ANOTA' else '')
                    verified=source in ('mlb_total','nfl_prop')
                    options.append(dict(row,seleccion=label.strip(),deporte='MLB' if source.startswith('mlb') else 'NFL',
                        origen=source,mercado=MARKETS.get(row.get('tipo_prop'),MARKETS.get(source)),
                        cuota=odds,casa='DraftKings' if verified else 'Casa no verificada',casa_verificada=verified,
                        inicio_utc=row.get('inicio_utc') if source=='mlb_total' else starts.get(str(row['game_id'])) if source.startswith('nfl') else None,
                        cuota_capturada_utc=row.get('captura'),referencia={'game_id':str(row['game_id'])}))
            except Exception:errors.append('No se pudo leer '+MARKETS.get(source,'props NFL')+'.')
    try:
        from futbol_liga_mx.continuidad import frozen_model
        from futbol_liga_mx.inferencia import upcoming_probabilities
        folder=Path(root)/'futbol_liga_mx';params,report=frozen_model(folder/'modelos')
        future=upcoming_probabilities(pd.read_csv(folder/'data/partidos.csv'),pd.read_csv(folder/'data/proximos.csv'),params,report,now or datetime.now(timezone.utc))
        for row in future.to_dict('records'):
            # Ambas opciones aparecen en ranking; el selector de eventos impide juntarlas.
            for side in ['OVER','UNDER']:
                options.append(dict(fecha=row['fecha'],local=row['local'],visitante=row['visitante'],
                    deporte='Liga MX',origen='liga_mx',mercado='Total de goles',seleccion=side+' 2.5',
                    probabilidad=row['p_'+side.lower()+'25'],inicio_utc=row['inicio_utc'],cuota=None,
                    casa='Sin cuota guardada',casa_verificada=False,referencia={'side':side}))
    except Exception:errors.append('Los picks Liga MX no están disponibles en este momento.')
    # Moneyline solo hereda inicio si existe un único encuentro con hora verificada de esos equipos/día.
    times={}
    for pick in options:
        if pick['origen']=='mlb_total':
            key=(str(pd.Timestamp(pick['fecha']).date()),pick['local'],pick['visitante'])
            times.setdefault(key,set()).add(str(pick['inicio_utc']))
    for pick in options:
        if pick['origen']=='mlb_ml':
            known=times.get((str(pd.Timestamp(pick['fecha']).date()),pick['local'],pick['visitante']),set())
            if len(known)==1:pick['inicio_utc']=next(iter(known))
    return options,errors
