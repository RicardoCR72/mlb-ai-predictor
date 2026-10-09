"""Selección estricta del día de México, independiente de la semana y del reloj UTC."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MEXICO = ZoneInfo('America/Mexico_City')
MERCADOS_PROPS = ('player_receptions', 'player_reception_yds', 'player_pass_yds',
                  'player_pass_tds', 'player_rush_yds', 'player_anytime_td')


def ahora_mexico(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('La hora actual requiere zona horaria.')
    return now.astimezone(MEXICO)


def inicio_evento(event):
    try:
        value = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))
        return value.astimezone(timezone.utc) if value.tzinfo is not None else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def eventos_hoy(events, now=None):
    now = ahora_mexico(now)
    valid = {}
    for event in events:
        start = inicio_evento(event)
        if (start and event.get('id') and start > now
                and start.astimezone(MEXICO).date() == now.date()):
            valid[event['id']] = event
    return sorted(valid.values(), key=lambda e: (inicio_evento(e), e['id']))


def limites_utc(day):
    start = datetime.combine(day, time.min, MEXICO)
    return (start.astimezone(timezone.utc).replace(tzinfo=None),
            (start + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None))


def calendario_hoy(frame, now=None):
    """nflverse publica gametime en Eastern; no inventar hora cuando falta."""
    import pandas as pd
    now = ahora_mexico(now)
    def eligible(row):
        try:
            if not row.get('gametime') or pd.isna(row.get('gametime')):
                return False
            day = pd.Timestamp(row['gameday']).date()
            start = datetime.fromisoformat(str(day)+'T'+str(row['gametime']))
            start = start.replace(tzinfo=ZoneInfo('America/New_York'))
            return start > now and start.astimezone(MEXICO).date() == now.date()
        except (TypeError, ValueError):
            return False
    if frame.empty:
        return frame.copy()
    return frame[frame.apply(eligible, axis=1)].copy()


def captura_programada(cron):
    """Decidir por el cron que disparó la ejecución, aunque el runner llegue tarde."""
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError('Programación NFL inválida.')
    return fields[4] in ('1', '4', '0')
