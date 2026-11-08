import unittest
import pandas as pd
import numpy as np
from pathlib import Path
from nfl.services.calendar_updates import cargar_mapeo_depth_chart
from nfl.predecir_props_semana_actual import (
    calibrar_team_share_rushing,
    aplicar_inercia_volumen_elite,
    seleccionar_candidatos,
)

class TestDepthChartHierarchyAndZeroSum(unittest.TestCase):
    def test_depth_chart_ranks_hall_above_allen(self):
        dc = cargar_mapeo_depth_chart()
        self.assertFalse(dc.empty)
        
        # NYJ RB Depth Chart
        nyj_rbs = dc[(dc["team"] == "NYJ") & (dc["position"] == "RB")]
        hall = nyj_rbs[nyj_rbs["player_name"].str.contains("Hall", case=False)]
        allen = nyj_rbs[nyj_rbs["player_name"].str.contains("Allen", case=False)]
        
        self.assertFalse(hall.empty)
        self.assertFalse(allen.empty)
        self.assertEqual(hall.iloc[0]["depth_rank"], 1)
        self.assertEqual(allen.iloc[0]["depth_rank"], 2)

    def test_backup_rb_cannot_be_over_candidate(self):
        # Simular caso de Braelon Allen con cuota favorable pero siendo suplente (is_primary_rusher=0, depth_rank=2)
        sample = pd.DataFrame([
            {
                "game_id": "2026_10_NYJ_BUF",
                "player_id": "00-0039794",
                "player_name": "Braelon Allen",
                "position": "RB",
                "team": "NYJ",
                "opponent_team": "BUF",
                "tipo_prop": "rushing_yards",
                "linea": 33.5,
                "proyeccion": 78.0,  # Proyección sin calibrar inflada
                "edge": 44.5,
                "seleccion": "OVER",
                "probabilidad_over": 0.65,
                "probabilidad_under": 0.35,
                "probabilidad_pick": 0.65,
                "cuota_over": -110,
                "cuota_under": -110,
                "cuota_pick": -110,
                "ev_estimado": 0.24,
                "player_injury_status": "healthy_or_unlisted",
                "player_carries_avg_5": 18.6,
                "is_primary_rusher": 0,  # SUPLENTE
                "depth_rank": 2,         # RB2 en Depth Chart oficial
            }
        ])
        res = seleccionar_candidatos(sample)
        # NUNCA debe ser CANDIDATO a un OVER siendo suplente detrás del titular activo
        self.assertEqual(res.iloc[0]["estado_pick"], "NO PICK")

    def test_starter_rb_can_be_candidate(self):
        # Simular caso de Breece Hall como titular (is_primary_rusher=1, depth_rank=1) con alta confianza
        sample = pd.DataFrame([
            {
                "game_id": "2026_10_NYJ_BUF",
                "player_id": "00-0038120",
                "player_name": "Breece Hall",
                "position": "RB",
                "team": "NYJ",
                "opponent_team": "BUF",
                "tipo_prop": "rushing_yards",
                "linea": 37.5,
                "proyeccion": 62.5,
                "edge": 25.0,
                "seleccion": "OVER",
                "probabilidad_over": 0.78,
                "probabilidad_under": 0.22,
                "probabilidad_pick": 0.78,
                "cuota_over": -110,
                "cuota_under": -110,
                "cuota_pick": -110,
                "ev_estimado": 0.24,
                "player_injury_status": "healthy_or_unlisted",
                "player_carries_avg_5": 16.2,
                "is_primary_rusher": 1,  # TITULAR
                "depth_rank": 1,         # RB1
            }
        ])
        res = seleccionar_candidatos(sample)
        self.assertEqual(res.iloc[0]["estado_pick"], "CANDIDATO")

    def test_zero_sum_team_share_calibration(self):
        # Verificar que el backfield de Jets suma razonablemente (<110 yds) y que Allen se deflacta
        backfield = pd.DataFrame([
            {
                "game_id": "g1", "team": "NYJ", "player_id": "p1",
                "player_name": "B.Hall", "position": "RB", "is_primary_rusher": 1,
                "depth_rank": 1, "proyeccion": 58.5, "player_carries_avg_5": 16.2
            },
            {
                "game_id": "g1", "team": "NYJ", "player_id": "p2",
                "player_name": "B.Allen", "position": "RB", "is_primary_rusher": 0,
                "depth_rank": 2, "proyeccion": 78.0, "player_carries_avg_5": 18.6
            },
            {
                "game_id": "g1", "team": "NYJ", "player_id": "p3",
                "player_name": "I.Davis", "position": "RB", "is_primary_rusher": 0,
                "depth_rank": 3, "proyeccion": 14.6, "player_carries_avg_5": 3.0
            },
        ])
        cal = calibrar_team_share_rushing(backfield)
        allen_proj = cal.loc[cal["player_name"] == "B.Allen", "proyeccion"].iloc[0]
        hall_proj = cal.loc[cal["player_name"] == "B.Hall", "proyeccion"].iloc[0]
        total_rb = cal["proyeccion"].sum()

        self.assertLess(allen_proj, 25.0)
        self.assertGreater(hall_proj, 50.0)
        self.assertLess(total_rb, 110.0)

    def test_volume_inertia_only_applies_to_primaries(self):
        # Suplente no debe recibir ajuste alcista de inercia
        raw = np.array([40.0])
        df_backup = pd.DataFrame([{
            "is_primary_rusher": 0,
            "player_carries_avg_5": 18.0,
            "player_rushing_yards_avg_5": 80.0
        }])
        ajuste_backup = aplicar_inercia_volumen_elite(raw, df_backup, "rushing_yards")
        self.assertEqual(ajuste_backup[0], 40.0)

        # Titular sí recibe ajuste alcista
        df_starter = pd.DataFrame([{
            "is_primary_rusher": 1,
            "player_carries_avg_5": 18.0,
            "player_rushing_yards_avg_5": 80.0
        }])
        ajuste_starter = aplicar_inercia_volumen_elite(raw, df_starter, "rushing_yards")
        self.assertGreater(ajuste_starter[0], 40.0)

if __name__ == "__main__":
    unittest.main()
