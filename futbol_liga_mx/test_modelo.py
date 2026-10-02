import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from futbol_liga_mx.datos import read_season,read_csv_season,complete,audit
from futbol_liga_mx.modelo import build_features,fit


class TestLigaMX(unittest.TestCase):
    def test_fuente_descarta_playoffs_y_futuros_sin_inventar_marcadores(self):
        sample={'name':'Liga MX 2024/25','matches':[
            dict(round_name='unused',round='Apertura, Matchday 1',date='2024-07-05',
                 team1='Puebla FC',team2='Santos Laguna',score={'ft':[1,0]}),
            dict(round='Apertura Playoffs, Final',date='2024-12-15',
                 team1='Puebla FC',team2='Santos Laguna',score={'ft':[1,0]}),
            dict(round='Clausura, Matchday 2',date='2025-01-18',
                 team1='Santos Laguna',team2='Puebla FC')]
        }
        got,issues=read_season(sample,'2024-25','mx.1.json')
        self.assertEqual(len(got),1);self.assertEqual(len(issues),2)
        self.assertEqual(got.iloc[0].goles_local,1)

    def test_rechaza_duplicados(self):
        frame=pd.DataFrame([dict(fecha='2024-07-05',local='Puebla',visitante='Santos')]*2)
        with self.assertRaisesRegex(ValueError,'Duplicados'):audit(frame)

    def test_csv_excluye_liguilla_y_marcador_pendiente(self):
        payload='Stage,Round,Date,Team 1,FT,Team 2\nApertura,1,Fri Jul 1 2022,A,2-1,B\nClausura,3,Fri Jan 6 2023,B,,A\nClausura - Liguilla,Final,Sun May 28 2023,A,1-0,B\n'
        frame,issues=read_csv_season(payload,'2022-23','mx.1.csv')
        self.assertEqual(len(frame),1)
        self.assertEqual(len(issues),2)
        self.assertEqual(frame.iloc[0].goles_local,2)
        self.assertFalse(complete(frame))

    def test_no_usa_resultado_de_hoy(self):
        frame=pd.DataFrame([
            dict(season='2024-25',fecha='2024-07-01',local='A',visitante='B',goles_local=1,goles_visitante=0),
            dict(season='2024-25',fecha='2024-07-05',local='A',visitante='C',goles_local=2,goles_visitante=1),
            dict(season='2024-25',fecha='2024-07-05',local='B',visitante='D',goles_local=1,goles_visitante=1)])
        original=build_features(frame)
        changed=frame.copy();changed.loc[1,'goles_local']=25
        altered=build_features(changed)
        cols=['gf_local_5','gc_local_5','gf_visitante_5','media_liga_local','media_liga_visitante']
        pd.testing.assert_frame_equal(original.loc[original.fecha=='2024-07-05',cols].reset_index(drop=True),
                                      altered.loc[altered.fecha=='2024-07-05',cols].reset_index(drop=True))

    def test_split_y_baseline_reproducibles(self):
        rows=[]
        for year in range(2017,2024):
            season=f'{year}-{(year+1)%100:02d}'
            teams=list(range(18))
            for stage,month in [('Apertura',7),('Clausura',1)]:
                for week in range(17):
                    for i in range(9):
                        a,b=teams[i],teams[-i-1]
                        home,away=(a,b) if stage=='Apertura' else (b,a)
                        rows.append(dict(season=season,
                            fecha=f'{year+(stage=="Clausura")}-{month:02d}-{week+1:02d}',
                            local='T'+str(home),visitante='T'+str(away),
                            goles_local=(i+week)%4,goles_visitante=(i+2*week)%3,
                            ronda=f'{stage}, Matchday {week+1}'))
                    teams=[teams[0],teams[-1],*teams[1:-1]]
        frame=pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as temp:
            got=fit(frame,temp)
            self.assertEqual(got['seasons']['confirmacion'],'2023-24')
            self.assertEqual(got['train_games'],4*306)
            self.assertTrue(np.isfinite(got['confirmation']['raw']['logloss']))
            self.assertEqual(got['confirmation']['raw']['n'],306)
            model=json.loads((Path(temp)/'modelo_portable.json').read_text())
            self.assertEqual(len(model['features']),len(model['coef']))


if __name__=='__main__':unittest.main()
