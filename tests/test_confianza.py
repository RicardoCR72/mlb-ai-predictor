from datetime import date,timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch,Mock
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.confianza import prepare,reliability,temporal_trial,price_comparison,transform,VERIFIED


class ConfidenceTests(TestCase):
    def fixture(self,n=600):
        rng=np.random.default_rng(72);rows=[]
        for i in range(n):
            p=float(rng.uniform(.55,.9));actual=1/(1+np.exp(-np.log(p/(1-p))/2))
            rows.append(dict(fecha=date(2099,1,1)+timedelta(days=i//5),deporte='NFL',mercado='Yardas',modelo='v1',
                identidad=str(i),evento='game'+str(i//2),procedencia=VERIFIED,probabilidad=p,cuota=1.9,
                resultado='GANADA' if rng.random()<actual else 'PERDIDA'))
        # Un evento no debe abarcar dos días en el ensayo.
        for i,row in enumerate(rows):row['evento']='game'+str(i)
        return pd.DataFrame(rows)

    def test_bins_endpoints_exclusions_and_sources_are_not_mixed(self):
        raw=self.fixture(6);raw.probabilidad=[0,.7,.7,1,70,float('nan')]
        raw.loc[2,'procedencia']='Hora desconocida';raw.loc[3,'resultado']='PUSH'
        raw=pd.concat([raw,raw.iloc[[1]]],ignore_index=True)
        f,excluded=prepare(raw)
        self.assertEqual(len(f),3)
        self.assertEqual(excluded['probabilidad_invalida'],2)
        self.assertEqual(excluded['duplicados'],1)
        bins=reliability(f)
        self.assertEqual(len(bins),3)
        self.assertTrue(bins.evidencia.eq('Muestra limitada').all())
        self.assertEqual(f.fecha.iloc[0],date(2099,1,1))
        raw=self.fixture(1);raw.loc[0,'fecha']='2099-01-02T02:00:00Z'
        self.assertEqual(prepare(raw)[0].fecha.iloc[0],date(2099,1,1))

    def test_small_or_unverified_data_never_fits_and_no_production_mutation(self):
        f,_=prepare(self.fixture(30));reports=temporal_trial(f)
        self.assertEqual(reports[0]['status'],'Datos insuficientes')
        f,_=prepare(self.fixture());f['procedencia']='Sin hora'
        reports=temporal_trial(f)
        self.assertEqual(reports[0]['verificados'],0)
        self.assertFalse(reports[0]['production_changed'])
        f['procedencia']=VERIFIED;f['apto_ajuste']='False'
        self.assertEqual(temporal_trial(f)[0]['verificados'],0)

    def test_chronological_selection_does_not_use_test_outcomes(self):
        f,_=prepare(self.fixture());report=temporal_trial(f)[0]
        self.assertIn('transform',report)
        self.assertLess(report['corte_seleccion'],report['corte_prueba'])
        changed=f.copy();mask=changed.fecha.ge(date.fromisoformat(report['corte_prueba']))
        changed.loc[mask,'y']=1-changed.loc[mask,'y']
        later=temporal_trial(changed)[0]
        self.assertEqual(report['transform'],later['transform'])
        self.assertEqual(report['fit'],later['fit'])
        self.assertFalse(later['production_changed'])
        p=transform(np.array([.5,.7,.9]),report['transform'])
        self.assertTrue(np.all(np.diff(p)>=0))

    def test_events_cannot_cross_fit_and_test_dates(self):
        f,_=prepare(self.fixture());f['evento']='same-game'
        self.assertNotIn('transform',temporal_trial(f)[0])

    def test_quotes_missing_and_push_refunds_use_correct_ev(self):
        f,_=prepare(self.fixture(2));f['probabilidad']=.6;f['cuota']=[2,None];f['p_push']=.1
        prices=price_comparison(f)
        self.assertAlmostEqual(prices.probabilidad_implicita.iloc[0],.5)
        self.assertAlmostEqual(prices.ev_estimado.iloc[0],.18)
        self.assertTrue(pd.isna(prices.ev_estimado.iloc[1]))

    def test_reader_normalizes_mlb_push_and_uses_immutable_nfl_probability(self):
        from core.confianza_datos import read_confidence
        from core.comparador import COLUMNS
        raw=pd.DataFrame([dict(candidato=1,recorded_utc='2099-01-01T20:00Z',quote_captured_utc='2099-01-01T19:00Z',
            start_utc='2099-01-02T01:00Z',p_push=.1,confianza=.54,fecha_oficial='2099-01-01',model_id='m',
            cuota_seleccion=2,game_pk=1,resultado='GANADA')])
        def query(conn,sql):
            self.assertTrue(sql.strip().startswith('SELECT'))
            if 'nfl_publicaciones_props' in sql:return pd.DataFrame([dict(id_juego='g',id_jugador='p',tipo_prop='receiving_yards',
                modelo='m',publicada_en='2099-01-01T18:00Z',fecha='2099-01-01',valor_real=40,
                payload='{"linea":30.5,"seleccion":"OVER","probabilidad_pick":0.7,"cuota_pick":-110,"estado_pick":"CANDIDATO","publicacion_utc":true}')])
            return pd.DataFrame(columns=['linea_total'])
        with patch('core.confianza_datos.read_models',return_value=(pd.DataFrame(columns=COLUMNS),[])), \
             patch('core.confianza_datos.registro.history',return_value=raw),patch('core.confianza_datos.registro.settle',side_effect=lambda f:f), \
             patch('core.confianza_datos.rows',side_effect=query),patch('core.confianza_datos.nfl_starts',return_value={'g':pd.Timestamp('2099-01-02T01:00Z')}):
            result,errors=read_confidence(Mock(),Path('/missing'))
        self.assertEqual(len(result),2)
        self.assertAlmostEqual(result[result.deporte.eq('MLB')].probabilidad.iloc[0],.6)
        self.assertAlmostEqual(result[result.deporte.eq('NFL')].probabilidad.iloc[0],.7)
        self.assertTrue(result.procedencia.eq(VERIFIED).all())

    def test_page_uses_all_results_with_limited_evidence_and_no_adjustment(self):
        with patch('core.ui_confianza.load',return_value=(self.fixture(20),[])):
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'pages/6_📐_Calibracion.py')).run()
            self.assertFalse(app.exception)
            table=next(t.value for t in app.dataframe if 'evidencia' in t.value)
            self.assertTrue(table.evidencia.eq('Muestra limitada').all())
            self.assertEqual(len(app.selectbox),3)
            self.assertTrue(any('No cambia' in c.value for c in app.caption))

    def test_mixed_sources_fill_missing_game_ids_and_prepare_is_idempotent(self):
        raw=self.fixture(4)
        raw['probabilidad']=.7
        raw['identidad']=['g1|p1|receiving_yards','g1|p2|receiving_yards','g2|p3|receiving_yards','mlb1']
        raw['evento']=[None,np.nan,'','MLB|mlb1']
        raw.loc[3,'deporte']='MLB'
        f,_=prepare(raw)
        self.assertEqual(f.evento.tolist(),['NFL|g1','NFL|g1','NFL|g2','MLB|mlb1'])
        self.assertEqual(prepare(f)[0].evento.tolist(),f.evento.tolist())
        self.assertEqual(reliability(f[f.deporte.eq('NFL')]).partidos.sum(),2)

    def test_market_diagnosis_preserves_versions_and_sources_and_json_is_strict(self):
        from core.diagnostico_confianza import build_report
        import json
        raw=self.fixture(6)
        raw['probabilidad']=.9;raw['resultado']=['GANADA','PERDIDA']*3
        raw.loc[2:3,'modelo']='v2';raw.loc[4:,'procedencia']='Sin hora'
        report=build_report(raw,['Fuente ausente'])
        self.assertEqual(len(report['mercados']),3)
        self.assertTrue(all(r['muestra']=='Limitada' for r in report['mercados']))
        self.assertTrue(all(abs(r['diferencia']+.4)<1e-9 for r in report['mercados']))
        self.assertFalse(report['production_changed'])
        self.assertEqual(report['fuentes_no_disponibles'],['Fuente ausente'])
        json.dumps(report,allow_nan=False)
        self.assertTrue(all('motivo' in r for r in report['pruebas_temporales']))
