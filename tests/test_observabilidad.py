from datetime import datetime,timezone
from pathlib import Path
import json
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from core.rendimiento import calibration,prospective,grouped_performance
from core.observabilidad import age_status,workflow_status
from core.bankroll import fingerprint, net_profit
from futbol_liga_mx.recuperar_historial import read_espn_history,strict_regular_coverage

class TestMetrics(unittest.TestCase):
    def test_prospective_requires_zoned_kickoff_and_registration(self):
        self.assertFalse(prospective({'inicio_utc':'2026-10-05','registrado_utc':'2026-10-04T23:00:00Z'}))
        self.assertFalse(prospective({'inicio_utc':'2026-10-05T01:00:00Z','registrado_utc':'2026-10-05T02:00:00Z'}))
        self.assertTrue(prospective({'inicio_utc':'2026-10-05T01:00:00Z','registrado_utc':'2026-10-04T23:00:00Z'}))
    def test_brier_logloss_and_empty_are_not_zero_success(self):
        result=calibration([.8,.2],[1,0])
        self.assertAlmostEqual(result['brier'],.04);self.assertAlmostEqual(result['logloss'],-np.log(.8))
        self.assertAlmostEqual(result['ece'],.2)
        self.assertIsNone(calibration([],[])['brier'])
    def test_groups_exclude_manual_and_separate_unverified_records(self):
        ref=json.dumps({'inicio_utc':'2026-10-05T01:00:00Z','registrado_utc':'2026-10-04T23:00:00Z'})
        frame=pd.DataFrame([dict(deporte='NFL',origen=o,referencia=r,estado=s,monto=100,ganancia_neta=g,probabilidad=p)
                            for o,r,s,g,p in [('nfl_total',ref,'Ganada',90,.6),('nfl_total',None,'Perdida',-100,.6),('manual',ref,'Ganada',100,.8),('nfl_total',ref,'Push',0,.6)]])
        report,bins=grouped_performance(frame)
        self.assertEqual(len(report),2);self.assertEqual(report.n_prob.sum(),2)
        prior=report[report.Periodo.eq('Registro previo al inicio')].iloc[0]
        self.assertEqual(prior['ROI (%)'],45);self.assertEqual(prior.n_prob,1)
    def test_duplicate_fingerprint_and_ticket(self):
        bet=dict(fecha='2026-10-05',deporte='NFL',partido='A @ B',seleccion='OVER 45.5',casa='DraftKings',monto=100,cuota=1.91)
        self.assertEqual(fingerprint(bet),fingerprint({**bet,'partido':' a @ b '}))
        self.assertNotEqual(fingerprint(bet),fingerprint({**bet,'ticket':'two'}))
        self.assertEqual(net_profit('Ganada',100,1.91),91)
    def test_status_no_data_stale_and_success_not_latest_failure(self):
        now=datetime(2026,10,5,tzinfo=timezone.utc)
        self.assertEqual(age_status(None,now=now),'Sin datos')
        self.assertIn('antiguos',age_status('2026-10-01',now=now))
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'workflow_runs':[{'conclusion':'failure','created_at':'2026-10-05','html_url':'failure'}, {'conclusion':'success','updated_at':'2026-10-04'}]}).encode()
        status=workflow_status('bot_diario.yml',opener=lambda *args,**kwargs:Response())
        self.assertEqual(status['resultado'],'failure');self.assertEqual(status['ultimo_exito'],'2026-10-04')

class TestHistoricalCoverage(unittest.TestCase):
    def event(self,slug='torneo-clausura',status='STATUS_FULL_TIME',score='2'):
        return dict(id='1',date='2026-01-11T01:00:00Z',season={'year':2026,'slug':slug},status={'type':{'name':status}},
                    competitions=[{'competitors':[{'homeAway':'home','team':{'displayName':'América'},'score':score},
                                                  {'homeAway':'away','team':{'displayName':'Chivas'},'score':'1'}]}])
    def test_phase_year_scores_and_duplicates(self):
        data=read_espn_history([self.event(),self.event(),self.event('clausura---finals'),self.event(score=None)])
        self.assertEqual(len(data),1);self.assertEqual(data.iloc[0].season,'2025-26')
        self.assertFalse(strict_regular_coverage(data))
    def test_real_recovered_season_strict_coverage_and_missing_game(self):
        path=Path(__file__).resolve().parents[1]/'futbol_liga_mx/data/partidos.csv'
        data=pd.read_csv(path);data=data[data.season.eq('2025-26')]
        self.assertTrue(strict_regular_coverage(data));self.assertFalse(strict_regular_coverage(data.iloc[1:]))
    def test_current_scan_rejects_stale_or_modified_results(self):
        from futbol_liga_mx.cobertura_actual import verified_current
        root=Path(__file__).resolve().parents[1]/'futbol_liga_mx/data'
        frame=pd.read_csv(root/'partidos.csv');frame=frame[frame.season.eq('2026-27')]
        report=json.loads((root/'cobertura_actual.json').read_text())
        now=pd.Timestamp(report['verified_utc']).to_pydatetime()
        self.assertTrue(verified_current(frame,now,report))
        self.assertFalse(verified_current(frame.iloc[1:],now,report))
        changed=frame.copy();changed.iloc[0,changed.columns.get_loc('goles_local')]+=1
        self.assertFalse(verified_current(changed,now,report))
        self.assertFalse(verified_current(frame,now+pd.Timedelta(days=10),report))
        self.assertFalse(verified_current(frame,now,{**report,'unresolved_events':['pending']}))

if __name__=='__main__':unittest.main()
