from unittest import TestCase
import numpy as np
import pandas as pd
from nfl.validar_yardas_recepcion import load_frames,select_configuration,alternative,select_calibration,clustered_interval


class ValidationTests(TestCase):
    def fixture(self):
        dataset=[];predictions=[]
        for season in [2023,2024,2025,2026]:
            for i in range(10):
                game=f'{season}_{i//2}'
                row=dict(game_id=game,player_id=f'p{i}',position='WR',season=season,team='A',
                    receptions=4,receiving_yards=30+i*5,player_receptions_avg_5=4,
                    player_receiving_yards_avg_5=40+i,team_receptions_avg_5=8,player_targets_avg_5=5,
                    player_injury_status='healthy_or_unlisted')
                dataset.append(row)
                if season==2023:continue
                for objective,pred in [('receptions',5),('receiving_yards',35+i*5)]:
                    predictions.append(dict(game_id=game,player_id=f'p{i}',position='WR',season=season,team='A',
                        gameday=f'{season}-10-{1+i//2:02}',objetivo=objective,prediccion=pred,receiving_yards=row['receiving_yards']))
        return pd.DataFrame(dataset),pd.DataFrame(predictions)

    def test_selection_ignores_confirmation_and_oos_results(self):
        dataset,pred=self.fixture();frame=load_frames(dataset,pred)
        first,_=select_configuration(frame)
        frame.loc[frame.season.isin([2025,2026]),'receiving_yards']=99999
        second,_=select_configuration(frame)
        self.assertEqual(first,second)

    def test_training_prior_ignores_later_labels_and_volume_cap_is_team_specific(self):
        dataset,pred=self.fixture();first=load_frames(dataset,pred)
        dataset.loc[dataset.season.ge(2024),'receiving_yards']=99999
        second=load_frames(dataset,pred)
        np.testing.assert_allclose(first.prior_ypr,second.prior_ypr)
        # Dos jugadores de 5 recepciones no superan el presupuesto previo de 8.
        out=alternative(first,alpha=0,cap=True)/first.prior_ypr
        sums=out.groupby([first.game_id,first.team]).sum()
        self.assertTrue((sums<=8+1e-9).all())

    def test_calibration_does_not_read_2025_or_2026_labels(self):
        dataset,pred=self.fixture();frame=load_frames(dataset,pred)
        mode,fitted,_,cutoff=select_calibration(frame,'prediccion')
        frame.loc[frame.season.ne(2024),'receiving_yards']=0
        other,new,_,other_cutoff=select_calibration(frame,'prediccion')
        self.assertEqual((mode,cutoff),(other,other_cutoff))
        np.testing.assert_allclose(fitted.coef_,new.coef_)
        np.testing.assert_allclose(fitted.intercept_,new.intercept_)

    def test_missing_pairs_and_duplicates_are_rejected(self):
        dataset,pred=self.fixture()
        with self.assertRaises(ValueError):load_frames(pd.concat([dataset,dataset.iloc[:1]]),pred)
        with self.assertRaises(ValueError):load_frames(dataset,pred.iloc[1:])

    def test_interval_uses_paired_errors_and_game_groups(self):
        dataset,pred=self.fixture();frame=load_frames(dataset,pred)
        interval=clustered_interval(frame,pd.Series(-1.0,index=frame.index),repetitions=100)
        np.testing.assert_allclose(interval,[-1,-1])

    def test_cli_exports_results_without_production_model_files(self):
        import tempfile
        import subprocess
        import sys
        import json
        from pathlib import Path
        dataset,pred=self.fixture()
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);data=folder/'data.parquet';csv=folder/'validation.csv';out=folder/'out'
            dataset.to_parquet(data,index=False);pred.to_csv(csv,index=False)
            process=subprocess.run([sys.executable,str(root/'nfl/validar_yardas_recepcion.py'),
                '--dataset',str(data),'--predictions',str(csv),'--output',str(out)],capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            report=json.loads((out/'decision.json').read_text())
            self.assertFalse(report['production_changed'])
            self.assertIsNone(report['historical_market_roi'])
            self.assertEqual(list(folder.rglob('*.joblib')),[])
            self.assertTrue((out/'point_metrics.csv').exists())
            self.assertTrue((out/'probability_metrics.csv').exists())
