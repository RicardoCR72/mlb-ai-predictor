import unittest
import numpy as np
import pandas as pd
from mlb_totales.core import FEATURES, features, probabilities, decimal_odds


class TestModel(unittest.TestCase):
    def history(self):
        return pd.DataFrame([dict(game_id=i, fecha=f'2024-04-0{d}', season=2024,
                       home_id=1,away_id=2,home_runs=h,away_runs=a,venue_id=10)
                    for i,d,h,a in [(1,1,2,3),(2,2,4,1),(3,2,8,9),(4,3,3,4)]])

    def test_no_future_or_same_day_leakage(self):
        hist = self.history()
        before = features(hist)
        hist.loc[hist.game_id == 2, 'home_runs'] = 40
        after = features(hist)
        np.testing.assert_allclose(before.loc[before.game_id.isin([1,2,3]),FEATURES],
                                  after.loc[after.game_id.isin([1,2,3]),FEATURES])
        self.assertNotEqual(before.loc[3,'home_scored_7'], after.loc[3,'home_scored_7'])

    def test_fixtures_do_not_update_state(self):
        hist = self.history()
        fixture = pd.DataFrame([dict(fecha='2024-04-03',home_id=1,away_id=2,venue_id=10)])
        built = features(hist, pd.concat([fixture, fixture]))
        np.testing.assert_allclose(built[built.is_fixture][FEATURES].iloc[0],
                                  built[built.is_fixture][FEATURES].iloc[1])

    def test_push_and_probability_mass(self):
        for alpha in (0, .2):
            over, under, push = probabilities([8,9], alpha, [8,8.5])
            np.testing.assert_allclose(over + under + push, 1, atol=1e-12)
            self.assertGreater(push[0],0)
            self.assertEqual(push[1],0)
            a = probabilities([8], alpha, [7.5])[0]
            b = probabilities([8], alpha, [9.5])[0]
            self.assertGreater(a[0], b[0])

    def test_odds(self):
        self.assertAlmostEqual(decimal_odds(-110), 1 + 100/110)
        self.assertEqual(decimal_odds(120), 2.2)
        self.assertEqual(decimal_odds(1.91), 1.91)
        with self.assertRaises(ValueError):
            decimal_odds(0)

    def test_season_reset(self):
        hist = self.history()
        next_year = hist.iloc[[0]].copy()
        next_year['fecha'] = '2025-04-01'
        next_year['game_id'] = 5
        built = features(pd.concat([hist, next_year], ignore_index=True))
        r = built[built.game_id == 5].iloc[0]
        self.assertEqual(r.home_games, 0)
        self.assertEqual(r.home_scored_season, 4.5)

if __name__ == '__main__':
    unittest.main()
