import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from datetime import datetime
import pandas as pd
from mlb_totales import automatizar as a


class TestActions(unittest.TestCase):
    def test_secretos_con_caracteres_especiales(self):
        env=dict(DB_HOST='localhost',DB_PORT='3306',DB_USER='u',
                 DB_PASS='comillas\" y \' y \\ y $() y 🦊',DB_NAME='base')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,env):
            dest=Path(tmp)/'secrets.toml'
            a.create_secrets(dest)
            got=tomllib.loads(dest.read_text())
            self.assertEqual(got['password'],env['DB_PASS'])
            self.assertEqual(got['port'],3306)

    def test_no_avanza_con_partido_en_curso(self):
        with self.assertRaises(RuntimeError):
            a.complete_days({'dates':[{'games':[{'gamePk':1,'status':{
                'abstractGameState':'Live','detailedState':'In Progress'}}]}]})
        a.complete_days({'dates':[{'games':[{'gamePk':1,'status':{
            'abstractGameState':'Preview','detailedState':'Postponed'}}]}]})

    def test_ayer_se_calcula_en_mexico_y_no_repite_descarga(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'historial_modelo.coverage.json').write_text(json.dumps({'hasta':'2026-09-28'}))
            with patch('mlb_totales.descargar_pitcheo.fetch_json') as fetch:
                a.update_history(tmp,datetime.fromisoformat('2026-09-30T05:00:00+00:00'))
                fetch.assert_not_called()

    def test_actualiza_solo_dia_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'historial_modelo.coverage.json').write_text(json.dumps({'hasta':'2026-09-28'}))
            with patch('mlb_totales.descargar_pitcheo.fetch_json',return_value={'dates':[]}), \
                 patch('mlb_totales.actualizar_pitcheo.update') as update:
                a.update_history(tmp,datetime.fromisoformat('2026-09-30T11:00:00+00:00'))
                self.assertEqual(update.call_args.args[0],'2026-09-29')

    def predictions(self,state='EXPERIMENTAL'):
        rows=pd.DataFrame([dict(game_id=1,casa_apuestas=house,odds_game_id='x',
            start_utc='2026-09-30T20:00:00Z',captured_utc='2026-09-30T17:00:00Z',
            estado_mercado='OK',estado=state,p_over=.60) for house in ['A','B']])
        return rows

    def run_prediction(self,rows):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for target,value in [('mlb_totales.mercado.calendar',rows),
                ('mlb_totales.registro.quote_rows',rows),('mlb_totales.mercado.match',rows),
                ('mlb_totales.predecir_pitcheo.predict',rows.copy()),
                ('mlb_totales.portable.load',{'model_id':'a'*64})]:
                stack.enter_context(patch(target,return_value=value))
            save=stack.enter_context(patch('mlb_totales.registro.save_snapshots',return_value=2))
            if (rows.estado=='ACTUALIZAR_HISTORIAL').any():
                with self.assertRaises(RuntimeError):a.predict_today(object())
                save.assert_not_called()
            else:
                self.assertEqual(a.predict_today(object()),2)
                self.assertEqual(save.call_args.args[1].casa_apuestas.tolist(),['A','B'])

    def test_registra_todas_las_casas(self):self.run_prediction(self.predictions())
    def test_historial_atrasado_no_guarda(self):self.run_prediction(self.predictions('ACTUALIZAR_HISTORIAL'))

    def test_sin_cuotas_no_reporta_exito(self):
        rows=self.predictions().assign(estado_mercado='SIN_LINEA')
        with patch('mlb_totales.mercado.calendar',return_value=rows), \
             patch('mlb_totales.registro.quote_rows',return_value=rows), \
             patch('mlb_totales.mercado.match',return_value=rows):
            with self.assertRaises(RuntimeError):a.predict_today(object())


if __name__=='__main__':unittest.main()
