import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import pandas as pd
from mlb_totales.test_pitcheo import TestPitching as Fixtures
from mlb_totales.pitcheo_features import pitching_features
from mlb_totales.actualizar_pitcheo import update


class TestFechas(unittest.TestCase):
    def test_misma_prediccion_con_fechas_mixtas(self):
        h,p=Fixtures().data()
        expected=pitching_features(h,p)
        h.loc[h.game_id>=2,'fecha']=h.loc[h.game_id>=2,'fecha']+' 00:00:00'
        p.loc[p.game_id>=2,'fecha']=p.loc[p.game_id>=2,'fecha']+'T00:00:00'
        actual=pitching_features(h,p)
        pd.testing.assert_frame_equal(expected,actual)

    def test_actualizacion_escribe_fechas_uniformes_y_puede_repetirse(self):
        h,p=Fixtures().data()
        new_h=h[h.game_id==4].copy();new_p=p[p.game_id==4].copy()
        new_p['fecha']=pd.to_datetime(new_p.fecha)
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            h[h.game_id<4].to_csv(root/'historial_modelo.csv.gz',index=False)
            p[p.game_id<4].to_csv(root/'historial_pitcheo.csv.gz',index=False)
            (root/'historial_modelo.coverage.json').write_text(json.dumps({'hasta':'2024-04-02'}))
            with patch('mlb_totales.actualizar_pitcheo.download',return_value=(new_h,new_p)):
                update('2024-04-03',root,root)
                update('2024-04-03',root,root)
            got_h=pd.read_csv(root/'historial_modelo.csv.gz')
            got_p=pd.read_csv(root/'historial_pitcheo.csv.gz')
            self.assertEqual(len(got_h),len(h));self.assertEqual(len(got_p),len(p))
            self.assertTrue(got_p.fecha.str.fullmatch(r'\d{4}-\d{2}-\d{2}').all())
            self.assertTrue(got_h.fecha.str.fullmatch(r'\d{4}-\d{2}-\d{2}').all())
            pd.testing.assert_frame_equal(pitching_features(h,p),pitching_features(got_h,got_p))

    def test_fecha_invalida_sigue_fallando(self):
        h,p=Fixtures().data();p.loc[0,'fecha']='2024-99-99'
        with self.assertRaises(ValueError):pitching_features(h,p)


if __name__=='__main__':unittest.main()
