import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import numpy as np
import pandas as pd
from mlb_totales.pitcheo_features import PITCH_FEATURES,pitching_features,audit,sp_features
from mlb_totales.descargar_pitcheo import innings_outs,parse_people
from mlb_totales.crear_partidos import create


class TestPitching(unittest.TestCase):
    def data(self):
        games=[];pitch=[]
        for gid,day in [(1,1),(2,2),(3,2),(4,3)]:
            games.append(dict(game_id=gid,fecha=f'2024-04-0{day}',season=2024,
                home_id=1,away_id=2,home='Uno',away='Dos',home_runs=2,away_runs=3,
                venue_id=10,scheduled_innings=9,game_type='R'))
            for team,starter,runs in [(1,10,3),(2,20,2)]:
                for pid,started,outs,er,pitches in [(starter,1,15,runs,85),(starter+1,0,12,0,55)]:
                    pitch.append(dict(game_id=gid,fecha=f'2024-04-0{day}',team_id=team,
                        pitcher_id=pid,started=started,outs=outs,earned_runs=er,runs=er,
                        hits=5,walks=1,strikeouts=4,home_runs=1,pitches=pitches))
        return pd.DataFrame(games),pd.DataFrame(pitch)

    def test_no_current_or_same_day_pitching(self):
        games,pitch=self.data()
        original=pitching_features(games,pitch)
        altered=pitch.copy()
        altered.loc[altered.game_id==2,['earned_runs','pitches','hits']]=[25,200,30]
        updated=pitching_features(games,altered)
        idx=original.game_id.isin([1,2,3])
        np.testing.assert_allclose(original.loc[idx,PITCH_FEATURES],updated.loc[idx,PITCH_FEATURES])
        self.assertNotEqual(original.iloc[3].home_sp_era_365,updated.iloc[3].home_sp_era_365)
        self.assertNotEqual(original.iloc[3].home_bp_pitches_3d,updated.iloc[3].home_bp_pitches_3d)

    def test_future_stats_do_not_change_prior_fixtures(self):
        games,pitch=self.data()
        fixture=pd.DataFrame([dict(fecha='2024-04-02',local='Uno',visitante='Dos',
                    home_id=1,away_id=2,home_pitcher_id=10,away_pitcher_id=20,venue_id=10,game_type='R')])
        before=pitching_features(games,pitch,fixture)
        pitch.loc[pitch.game_id>=2,'earned_runs']=40
        after=pitching_features(games,pitch,fixture)
        np.testing.assert_allclose(before[before.is_fixture][PITCH_FEATURES],after[after.is_fixture][PITCH_FEATURES])

    def test_fast_prediction_equals_full_history(self):
        games,pitch=self.data()
        original=pitching_features(games,pitch)
        fixture=games.iloc[[3]].drop(columns=['home_runs','away_runs']).copy()
        fixture['home_pitcher_id']=10;fixture['away_pitcher_id']=20
        fast=pitching_features(games,pitch,fixture)
        np.testing.assert_allclose(original[original.game_id==4][PITCH_FEATURES].to_numpy(),
                                  fast[fast.is_fixture][PITCH_FEATURES].to_numpy())

    def test_audit_and_duplicate_guard(self):
        games,pitch=self.data()
        self.assertTrue(audit(games,pitch).empty)
        broken=pitch.copy();broken.loc[0,'runs']=99
        self.assertIn('carreras_no_concilian',audit(games,broken).reason.tolist())
        with self.assertRaises(ValueError):
            pitching_features(games,pd.concat([pitch,pitch.iloc[[0]]]))
        broken=pitch[pitch.pitcher_id!=10]
        self.assertIn('abridor_ambiguo',audit(games,broken).reason.tolist())

    def test_outs_are_not_decimal_innings(self):
        self.assertEqual(innings_outs('5.2'),17)
        self.assertEqual(innings_outs('0.1'),1)
        with self.assertRaises(ValueError):
            innings_outs('5.3')

    def test_empty_starter_prior(self):
        f=sp_features([],pd.Timestamp('2024-04-01'),unknown=True)
        self.assertEqual(f['sp_missing'],1)
        self.assertEqual(f['sp_ip_365'],0)
        self.assertEqual(f['sp_era_365'],4.3)

    def test_zero_outs_appearance_kept(self):
        stat=dict(gamesStarted=0,inningsPitched='0.0',earnedRuns=2,runs=2,
                  hits=1,baseOnBalls=1,strikeOuts=0,homeRuns=0,numberOfPitches=10)
        obj={'people':[{'id':10,'fullName':'Pitcher','stats':[{'group':{'displayName':'pitching'},
              'splits':[{'stat':stat,'season':'2024','date':'2024-04-01','gameType':'R',
                         'game':{'gamePk':1},'team':{'id':1}}]}]}]}
        got=parse_people(obj)
        self.assertEqual(len(got),1);self.assertEqual(got.iloc[0].outs,0)

    def test_calendar_only_pending_and_no_overwrite(self):
        g=dict(gamePk=1,officialDate='2026-09-30',gameDate='2026-09-30T20:00:00Z',
              gameType='F',venue={'id':10},status={'abstractGameState':'Preview'},
              teams={'home':{'team':{'id':1,'name':'Uno'}},'away':{'team':{'id':2,'name':'Dos'}}})
        data={'dates':[{'date':'2026-09-30','games':[g,dict(g,status={'abstractGameState':'Final'})]}]}
        with TemporaryDirectory() as d,patch('mlb_totales.crear_partidos.fetch_json',return_value=data):
            path=Path(d)/'partidos.csv'
            got=create('2026-09-30',path)
            self.assertEqual(len(got),1)
            self.assertTrue(pd.isna(got.home_pitcher_id.iloc[0]))
            with self.assertRaises(FileExistsError):
                create('2026-09-30',path)


if __name__=='__main__':
    unittest.main()
