"""Auditoría del escaneo diario; no inventa jornadas para partidos aplazados."""
from datetime import date,datetime,timezone,timedelta
import hashlib,json
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

PATH = Path(__file__).resolve().parent/'data/cobertura_actual.json'

def results_hash(frame):
    from .inferencia import normalize_teams
    data=normalize_teams(frame)
    keys=['fecha','local','visitante','goles_local','goles_visitante']
    data=data[keys].sort_values(keys).copy()
    data['fecha']=pd.to_datetime(data.fecha).dt.strftime('%Y-%m-%d')
    for col in ('goles_local','goles_visitante'):data[col]=pd.to_numeric(data[col],errors='raise').astype(int)
    return hashlib.sha256(data.to_csv(index=False).encode()).hexdigest()

def scan_report(events,results,start,end,failures=(),allow_current_day=False):
    from .proveedor_espn import MX
    finals,unresolved=set(),set()
    today=datetime.now(MX).date()
    partial=end.isoformat() if allow_current_day and end==today else None
    for ev in events:
        if (ev.get('season') or {}).get('slug') not in ('torneo-apertura','torneo-clausura'):continue
        try:day=datetime.fromisoformat(ev['date'].replace('Z','+00:00')).astimezone(MX).date()
        except (KeyError,ValueError,TypeError):continue
        if not start<=day<=end:continue
        status=(ev.get('status') or {}).get('type',{}).get('name')
        if status in ('STATUS_FINAL','STATUS_FULL_TIME'):finals.add(ev['id'])
        elif status not in ('STATUS_CANCELED','STATUS_POSTPONED'):
            if not (partial and day==end):unresolved.add(ev['id'])
    valid = not failures and not unresolved and len(finals)==len(results) and bool(finals)
    return dict(scan_from=start.isoformat(),scan_until=end.isoformat(),verified_utc=datetime.now(timezone.utc).isoformat(),
                failed_days=list(failures),partial_day=partial,unresolved_events=sorted(unresolved),final_events=sorted(finals),
                final_count=len(finals),results_sha256=results_hash(results),audited=valid)

def verified_current(frame,now,report=None):
    try:
        report=report or json.loads(PATH.read_text())
        day=now.astimezone(timezone.utc).date()
        until=date.fromisoformat(report['scan_until'])
        start=date.fromisoformat(report['scan_from'])
        verified=pd.Timestamp(report['verified_utc'])
        if verified.tzinfo is None or verified>pd.Timestamp(now)+pd.Timedelta(hours=1):return False
        if report.get('partial_day') and report['partial_day'] != now.astimezone(ZoneInfo('America/Mexico_City')).date().isoformat():return False
        if start!=date(2026,7,1) or until<day-timedelta(days=2) or until>day:return False
        if not report['audited'] or report['failed_days'] or report['unresolved_events']:return False
        if len(frame)!=report['final_count'] or results_hash(frame)!=report['results_sha256']:return False
        pairs=frame.apply(lambda r:tuple(sorted((r.local,r.visitante))),axis=1)
        return not pairs.duplicated().any()
    except (OSError,KeyError,ValueError,TypeError):return False
