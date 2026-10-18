"""Resumen descriptivo por mercado, modelo y procedencia; sin aplicar ajustes."""
from core.confianza import KEYS,prepare,reliability,temporal_trial,scores,interval


def market_summary(clean):
    records=[]
    if clean.empty:return records
    for key,g in clean.groupby(KEYS,dropna=False):
        n,games=len(g),g.evento.nunique()
        estimated,actual=float(g.probabilidad.mean()),float(g.y.mean())
        low,high=interval(g.y,g.evento)
        records.append(dict(zip(KEYS,key))|dict(picks=n,partidos=int(games),
            confianza=estimated,acierto=actual,diferencia=actual-estimated,
            intervalo_inferior=low,intervalo_superior=high,
            muestra='Limitada' if n<100 or games<30 else 'Descriptiva amplia',
            senal='Confianza mayor que acierto observado' if estimated>actual else
                'Confianza menor que acierto observado' if estimated<actual else 'Coinciden en esta muestra',
            **scores(g.y,g.probabilidad)))
    return records


def build_report(raw,errors=()):
    clean,excluded=prepare(raw)
    ranges=reliability(clean)
    # to_json convierte NaN a null; el reporte descargable debe ser JSON estricto.
    import json
    return dict(production_changed=False,fuentes_no_disponibles=list(errors),exclusiones=excluded,
        mercados=market_summary(clean),rangos=json.loads(ranges.to_json(orient='records')),
        pruebas_temporales=temporal_trial(clean))
