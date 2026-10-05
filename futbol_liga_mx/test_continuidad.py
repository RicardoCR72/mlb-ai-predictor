import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import date,datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from futbol_liga_mx.proveedor_api import parse_fixtures,merge_results,canonical,league_id,run
from futbol_liga_mx.continuidad import portable_probability,fetch_draftkings,quote_for_fixture,predict
from futbol_liga_mx.modelo import build_features


def fixture(fid,day,stage='Apertura - 1',status='FT',goals=(2,1)):
    return {'fixture':{'id':fid,'date':day+'T23:00:00+00:00','status':{'short':status}},
            'league':{'name':'Liga MX','round':stage},
            'teams':{'home':{'name':'Club America'},'away':{'name':'Puebla'}},
            'score':{'fulltime':{'home':goals[0],'away':goals[1]}}}


class TestContinuidad(unittest.TestCase):
    def test_no_consume_odds_if_2025_26_incomplete(self):
        games=pd.DataFrame([dict(season='2026-27',fecha='2026-10-01',
                                 ronda='Apertura, Matchday 12')])
        fixtures=pd.DataFrame(columns=['season','inicio_utc'])
        loader=Mock(side_effect=AssertionError('No se deben pedir momios'))
        with self.assertRaisesRegex(ValueError,'2025-26 incompleta'):
            predict(games,fixtures,{}, {'seasons':{'confirmacion':'2024-25'}},
                    now=datetime(2026,10,2,tzinfo=timezone.utc),quote_loader=loader)
        loader.assert_not_called()

    def test_no_consume_odds_if_no_upcoming_games(self):
        games=pd.DataFrame([dict(season='2025-26',fecha='2026-05-01',
                                 ronda='Clausura, Matchday 17'),
                            dict(season='2026-27',fecha='2026-10-01',
                                 ronda='Apertura, Matchday 1')])
        fixtures=pd.DataFrame(columns=['season','inicio_utc'])
        loader=Mock(side_effect=AssertionError('No se deben pedir momios'))
        with tempfile.TemporaryDirectory() as tmp, patch('futbol_liga_mx.continuidad.complete',return_value=True):
            output=Path(tmp)/'predicciones.csv'
            result=predict(games,fixtures,{}, {'seasons':{'confirmacion':'2024-25'}},
                           now=datetime(2026,10,2,tzinfo=timezone.utc),
                           output=output,quote_loader=loader)
            self.assertTrue(result.empty)
            self.assertIn('p_over25',pd.read_csv(output).columns)
        loader.assert_not_called()

    def test_consume_odds_once_after_computing_probabilities(self):
        now=datetime(2026,10,2,tzinfo=timezone.utc)
        fixtures=pd.DataFrame([dict(season='2026-27',fecha='2026-10-03',
                                    inicio_utc='2026-10-03T23:00:00+00:00',
                                    local='CF América',visitante='Puebla FC',
                                    ronda='Apertura, Matchday 12',fixture_id=101)])
        games=pd.DataFrame([dict(fecha='2026-10-01')])
        loader=Mock(return_value=pd.DataFrame())
        with tempfile.TemporaryDirectory() as tmp, \
             patch('futbol_liga_mx.continuidad.upcoming_ready',return_value=fixtures), \
             patch('futbol_liga_mx.continuidad.upcoming_features',return_value=pd.DataFrame()), \
             patch('futbol_liga_mx.continuidad.portable_probability',return_value=[.55]):
            result=predict(games,fixtures,{}, {},now=now,
                           output=Path(tmp)/'predicciones.csv',quote_loader=loader)
        self.assertEqual(len(result),1)
        self.assertAlmostEqual(result.iloc[0].p_under25,.45)
        loader.assert_called_once_with()

    def test_resultados_futuros_liguilla_y_nombres(self):
        data=[fixture(1,'2025-07-12'),fixture(2,'2025-12-15','Apertura - Final'),
              fixture(3,'2026-09-27','Apertura - 11'),
              fixture(4,'2026-10-02','Apertura - 12','NS',(None,None))]
        done,upcoming=parse_fixtures(data,date(2026,9,30))
        self.assertEqual(done.season.tolist(),['2025-26','2026-27'])
        self.assertEqual(upcoming.season.tolist(),['2026-27'])
        self.assertEqual(done.iloc[0].local,'CF América')
        with self.assertRaisesRegex(ValueError,'desconocido'):
            canonical('Equipo equivocado')

    def test_una_respuesta_parcial_no_borra_historial(self):
        old=pd.DataFrame([dict(season='2026-27',fecha='2026-07-17',local='A',visitante='B',
                               goles_local=1,goles_visitante=0,ronda='Apertura, Matchday 1',source_file='api')])
        newer=old.assign(season='2025-26',fecha='2025-07-17')
        with self.assertRaisesRegex(ValueError,'No sobrescribí'):
            merge_results(old,newer)

    def test_cuotas_solo_draftkings_y_linea_25(self):
        payload=[{'id':'odds-1','home_team':'Club America','away_team':'Puebla',
                  'commence_time':'2026-10-02T23:00:00Z',
                  'bookmakers':[{'key':'other','markets':[{'key':'totals','outcomes':[]}]},
                                {'key':'draftkings','markets':[{'key':'totals','outcomes':[
                                    {'name':'Over','point':2.5,'price':1.93},
                                    {'name':'Under','point':2.5,'price':1.89},
                                    {'name':'Over','point':3.5,'price':2.7}]}]}]}]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return None
            def read(self,*args):return json.dumps(payload).encode()
        odds=fetch_draftkings('test',opener=lambda *args,**kwargs:Response())
        self.assertEqual(len(odds),1)
        self.assertEqual(odds.iloc[0].precio_over,1.93)
        self.assertIsNotNone(quote_for_fixture(dict(local='CF América',visitante='Puebla FC',
                inicio_utc='2026-10-02T23:00:00+00:00'),odds))

    def test_portable_reproduce_confirmacion_2024(self):
        root=Path(__file__).resolve().parent
        data=root/'data/partidos.csv';params=root/'modelos/modelo_portable.json'
        reference=root/'modelos/confirmacion.csv'
        if not all(p.exists() for p in (data,params,reference)):
            self.skipTest('Artefactos reales locales opcionales no disponibles.')
        frame=build_features(pd.read_csv(data))
        test=frame[frame.season=='2024-25']
        p=portable_probability(test,json.loads(params.read_text()))
        expected=pd.read_csv(reference).p_calibrada.to_numpy()
        np.testing.assert_allclose(p,expected,rtol=0,atol=1e-10)


if __name__=='__main__':unittest.main()
