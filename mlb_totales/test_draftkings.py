import unittest
from unittest.mock import patch
import pandas as pd
from mlb_totales.casa_base import only_base
from mlb_totales.registro import snapshot_values,settle,summary
from mlb_totales.tarjetas_totales import pick_html,performance_html
from mlb_totales import automatizar
from mlb_totales.test_integracion import TestIntegration as Samples


class TestDraftKings(unittest.TestCase):
    def test_normaliza_solo_la_casa_elegida(self):
        frame=pd.DataFrame({'casa_apuestas':['FanDuel',' DraftKings ','draftkings','BetMGM'],
                            'cuota_over':[2.4,1.91,1.93,2.1]})
        result=only_base(frame)
        self.assertEqual(result.cuota_over.tolist(),[1.91,1.93])
        self.assertEqual(result.casa_apuestas.tolist(),['DraftKings','DraftKings'])

    def test_registro_rechaza_otra_casa(self):
        r=Samples().snapshot();r['casa_apuestas']='FanDuel'
        self.assertIsNone(snapshot_values(r,'a'*64,now='2026-09-30T18:00:00Z'))

    def test_no_usa_otra_casa_si_falta_draftkings(self):
        games=pd.DataFrame([dict(game_id=1,home_id=147,away_id=111,
            fecha='2026-09-30',start_utc='2026-09-30T20:00:00Z')])
        quotes=pd.DataFrame([dict(casa_apuestas='FanDuel',cuota_over=2.9)])
        with patch('mlb_totales.mercado.calendar',return_value=games), \
             patch('mlb_totales.registro.quote_rows',return_value=quotes), \
             patch('mlb_totales.predecir_pitcheo.predict') as predict:
            with self.assertRaisesRegex(RuntimeError,'DraftKings'):
                automatizar.predict_today(object(),now=pd.Timestamp('2026-09-30T18:00:00Z'))
            predict.assert_not_called()

    def test_roi_excluye_otras_casas(self):
        rows=pd.DataFrame([dict(casa_apuestas=house,home_runs=5,away_runs=4,linea=8.5,
            seleccion=pick,cuota_seleccion=1.91,confianza=.6,revision_reglas=0)
            for house,pick in [('DraftKings','UNDER'),('FanDuel','OVER')]])
        sums=summary(settle(only_base(rows)))
        self.assertEqual(sums['apuestas'],1);self.assertEqual(sums['unidades'],-1)

    def test_tarjetas_muestran_confianza_cuota_y_estados(self):
        r=dict(prob_seleccion=.61,seleccion='OVER',cuota_over=1.91,ev_over=.1651,
            game_type='R',total_proyectado=9.2,visitante='<script>equipo</script>',local='Local',
            abridor_visitante='Uno',abridor_local='Dos',linea=8.5,p_over=.61,p_under=.39,
            p_push=0,age_minutes=8)
        card=pick_html(r)
        self.assertIn('mlb-pick-card',card);self.assertIn('61.0%',card)
        self.assertIn('1.91',card);self.assertNotIn('<script>',card)
        for result,units,css in [('GANADA',.91,'won'),('PERDIDA',-1,'lost'),
                ('PUSH',0,'push'),('PENDIENTE',None,'pending'),('REVISAR_REGLAS',None,'review')]:
            row=dict(resultado=result,unidades=units,confianza_pct=61,cuota_seleccion=1.91,
                fecha_oficial='2026-09-30',equipo_visitante='Visitante',equipo_local='Local',
                seleccion='OVER',linea=8.5,ev=.1651,recorded_utc='2026-09-30 10:00:00')
            card=performance_html(row)
            self.assertIn('mlb-total-card '+css,card);self.assertIn('61.0%',card)
            self.assertIn('CUOTA ORIGINAL',card)
            if units is None:self.assertNotIn('nan',card.lower())


if __name__=='__main__':unittest.main()
