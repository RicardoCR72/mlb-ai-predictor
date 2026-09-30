import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from mlb_totales.mercado import match,team_id
from mlb_totales.registro import snapshot_values,save_snapshots,settle,summary,parse_results,DDL
from mlb_totales.portable import load


class FakeCursor:
    def __init__(self,conn):self.conn=conn;self.rowcount=0
    def execute(self,sql,values):
        self.conn.sql.append(sql)
        self.conn.calls.append(values)
        key=(values[0],values[9],values[2])
        if key not in self.conn.rows:self.conn.rows[key]=values;self.rowcount=1
        else:self.rowcount=0
    def close(self):pass


class FakeConnection:
    def __init__(self):self.rows={};self.sql=[];self.calls=[];self.commits=0
    def cursor(self):return FakeCursor(self)
    def commit(self):self.commits+=1
    def rollback(self):pass


class TestIntegration(unittest.TestCase):
    def fixtures(self):
        return pd.DataFrame([dict(game_id=i,fecha='2026-09-30',local='New York Yankees',
            visitante='Boston Red Sox',home_id=147,away_id=111,
            start_utc=pd.Timestamp(f'2026-09-30T{hour}:00:00Z')) for i,hour in [(1,'19'),(2,'23')]])

    def quotes(self):
        return pd.DataFrame([dict(id_juego='odds_'+str(i),fecha=f'2026-09-30 {hour}:00:00',
            equipo_local='New York Yankees',equipo_visitante='Boston Red Sox',casa_apuestas='Casa A',
            linea=line,cuota_over=over,cuota_under=under,timestamp_captura='2026-09-30 10:50:00')
            for i,hour,line,over,under in [(1,'13',8.5,1.91,1.95),(2,'17',9.5,2.0,1.85)]])

    def snapshot(self):
        return dict(game_id=1,odds_game_id='odds_1',modelo='pitcheo_ridge',fecha='2026-09-30',
            start_utc='2026-09-30T19:00:00Z',local='NYY',visitante='BOS',game_type='R',
            casa_apuestas='DraftKings',linea=8.5,cuota_over=1.91,cuota_under=1.95,seleccion='OVER',
            total_proyectado=9.5,p_over=.6,p_under=.4,p_push=0,ev_over=.146,ev_under=-.22,
            edge_carreras=1,home_pitcher_id=1,away_pitcher_id=2,captured_utc='2026-09-30T17:50:00Z',
            estado='EXPERIMENTAL',estado_mercado='OK')

    def test_doubleheaders_preserve_game_and_line(self):
        got=match(self.fixtures(),self.quotes(),now='2026-09-30T18:00:00Z')
        self.assertEqual(got.estado_mercado.tolist(),['OK','OK'])
        self.assertEqual(got.odds_game_id.tolist(),['odds_1','odds_2'])
        self.assertEqual(got.linea.tolist(),[8.5,9.5])

    def test_never_mix_books_or_old_and_new_prices(self):
        q=self.quotes().iloc[[0]].copy()
        old=q.copy();old['timestamp_captura']='2026-09-30 10:00:00';old['cuota_over']=2.2
        other=q.copy();other['casa_apuestas']='Casa B';other['cuota_under']=2.1
        got=match(self.fixtures().iloc[[0]],pd.concat([q,old,other]),now='2026-09-30T18:00:00Z')
        a=got[got.casa_apuestas=='Casa A'].iloc[0]
        self.assertEqual(a.cuota_over,1.91);self.assertEqual(a.cuota_under,1.95)
        b=got[got.casa_apuestas=='Casa B'].iloc[0];self.assertEqual(b.cuota_under,2.1)

    def test_conflicting_latest_quote_blocks(self):
        q=self.quotes().iloc[[0]].copy();other=q.copy();other['linea']=7.5
        got=match(self.fixtures().iloc[[0]],pd.concat([q,other]),now='2026-09-30T18:00:00Z')
        self.assertEqual(got.iloc[0].estado_mercado,'CUOTA_AMBIGUA')

    def test_old_quote_and_started_game(self):
        q=self.quotes();q['timestamp_captura']='2026-09-30 01:00:00'
        got=match(self.fixtures(),q,now='2026-09-30T18:00:00Z')
        self.assertTrue((got.estado_mercado=='CUOTA_ANTIGUA').all())
        got=match(self.fixtures(),self.quotes(),now='2026-10-01T00:00:00Z')
        self.assertTrue(got.empty)

    def test_one_quote_cannot_represent_two_games(self):
        f=self.fixtures();f.loc[0,'start_utc']=pd.Timestamp('2026-09-30T19:00:00Z')
        f.loc[1,'start_utc']=pd.Timestamp('2026-09-30T20:00:00Z')
        q=self.quotes().iloc[[0]].copy();q['fecha']='2026-09-30 13:30:00'
        got=match(f,q,now='2026-09-30T18:00:00Z')
        self.assertTrue((got.estado_mercado=='JUEGO_AMBIGUO').all())

    def test_snapshot_is_before_start_and_immutable(self):
        c=FakeConnection();r=self.snapshot()
        self.assertEqual(save_snapshots(c,pd.DataFrame([r]),'a'*64,now='2026-09-30T18:00:00Z'),1)
        initial=list(c.rows.values())[0]
        r['p_over']=.8;r['p_under']=.2;r['linea']=7.5
        self.assertEqual(save_snapshots(c,pd.DataFrame([r]),'a'*64,now='2026-09-30T18:10:00Z'),0)
        self.assertEqual(list(c.rows.values())[0],initial)
        self.assertEqual(len(initial),28)
        self.assertIn('ON DUPLICATE KEY UPDATE id=mlb_totales_predicciones.id',c.sql[0])
        self.assertIsNone(snapshot_values(r,'a'*64,now='2026-09-30T19:00:00Z'))
        r['estado']='ACTUALIZAR_HISTORIAL'
        self.assertIsNone(snapshot_values(r,'a'*64,now='2026-09-30T18:00:00Z'))

    def test_probabilities_must_be_valid_to_save(self):
        r=self.snapshot();r['p_over']=.8
        self.assertIsNone(snapshot_values(r,'a'*64,now='2026-09-30T18:00:00Z'))

    def test_units_push_and_pending(self):
        frame=pd.DataFrame([dict(home_runs=h,away_runs=a,linea=line,seleccion=pick,
                    cuota_seleccion=1.95,confianza=.61,revision_reglas=review)
                    for h,a,line,pick,review in [(5,4,8.5,'OVER',0),(5,4,8.5,'UNDER',0),
                      (4,4,8,'OVER',0),(None,None,8.5,'OVER',0),(5,4,8.5,'OVER',1)]])
        got=settle(frame)
        self.assertEqual(got.resultado.tolist(),['GANADA','PERDIDA','PUSH','PENDIENTE','REVISAR_REGLAS'])
        np.testing.assert_allclose(got.unidades.iloc[:3],[.95,-1,0])
        self.assertTrue(got.unidades.iloc[3:].isna().all())
        self.assertTrue((got.confianza_pct==61).all())
        sums=summary(got)
        self.assertEqual(sums['apuestas'],3);self.assertAlmostEqual(sums['unidades'],-.05)
        self.assertEqual(sums['acierto'],50);self.assertAlmostEqual(sums['roi'],-.05/3*100)

    def test_early_final_requires_rules_review(self):
        games=[]
        for pk,inning,state in [(1,9,'Final'),(2,7,'Final'),(3,9,'In Progress')]:
            games.append(dict(gamePk=pk,status={'abstractGameState':state},
                teams={'home':{'score':5},'away':{'score':4}},linescore={'currentInning':inning},scheduledInnings=9))
        got=parse_results({'dates':[{'games':games}]})
        self.assertEqual(len(got),2);self.assertEqual(got[0][-1],0);self.assertEqual(got[1][-1],1)

    def test_portable_equals_saved_sklearn(self):
        import sklearn
        root=Path(__file__).resolve().parent/'modelos_pitcheo'
        portable=load(root)
        if sklearn.__version__!=portable['metadata']['sklearn_version']:
            self.skipTest('La inferencia portable funciona con otra versión; comparación exige entorno de entrenamiento.')
        import joblib
        saved=joblib.load(root/'modelo_totales.joblib')
        frame=pd.DataFrame(np.random.default_rng(42).normal(size=(30,len(saved['columns']))),columns=saved['columns'])
        np.testing.assert_allclose(portable['model'].predict(frame),saved['model'].predict(frame),rtol=1e-10,atol=1e-10)

    def test_alias_and_additive_schema(self):
        self.assertEqual(team_id('Oakland Athletics'),133)
        self.assertEqual(team_id('ATH'),133)
        self.assertTrue(all(s.lstrip().startswith('CREATE TABLE IF NOT EXISTS mlb_totales_') for s in DDL))
        self.assertTrue(all('DROP ' not in s and 'ALTER ' not in s for s in DDL))


if __name__=='__main__':unittest.main()
