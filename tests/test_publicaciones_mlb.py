from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
import numpy as np
import pandas as pd
from mlb import publicaciones_moneyline as pub


class MoneylinePublicationsTests(TestCase):
    def game(self):
        return dict(id='game1',commence_time='2099-01-02T01:00:00Z',home_team='A',away_team='B',
            bookmakers=[dict(key='draftkings',last_update='2099-01-01T18:00:00Z',markets=[dict(key='h2h',
                outcomes=[dict(name='A',price=1.9),dict(name='B',price=2.1)])])])

    def test_provider_clock_is_explicit_and_only_draftkings_pair_is_used(self):
        game=self.game();v=pub.market_values(game)
        self.assertEqual(v[0],'game1');self.assertEqual(v[4:6],(1.9,2.1))
        for change in ('unknown-clock','wrong-house','after-start','invalid-price'):
            g=deepcopy(game)
            if change=='unknown-clock':g['bookmakers'][0]['last_update']='2099-01-01 18:00'
            if change=='wrong-house':g['bookmakers'][0]['key']='other'
            if change=='after-start':g['bookmakers'][0]['last_update']=g['commence_time']
            if change=='invalid-price':g['bookmakers'][0]['markets'][0]['outcomes'][0]['price']=float('nan')
            self.assertIsNone(pub.market_values(g))

    def test_save_checks_exact_quote_and_game_and_never_updates_original(self):
        conn=Mock();cursor=conn.cursor.return_value;cursor.rowcount=1
        args=dict(game_id='game1',model_id='a'*64,day=date(2099,1,1),home='A',away='B',
                  pick='B',confidence=70,home_odds=1.9,away_odds=2.1)
        self.assertTrue(pub.save(conn,**args))
        sql,values=cursor.execute.call_args.args
        self.assertEqual(values[3],.7);self.assertEqual(values[4],2.1)
        self.assertIn('m.cuota_local=%s AND m.cuota_visitante=%s',sql)
        self.assertIn('m.start_utc>UTC_TIMESTAMP(6)',sql)
        self.assertEqual(sql.split('ON DUPLICATE KEY UPDATE')[1].strip(),'id=mlb_publicaciones_moneyline.id')
        cursor.rowcount=0;self.assertFalse(pub.save(conn,**args))
        cursor.execute.side_effect=RuntimeError('failure')
        with self.assertRaises(RuntimeError):pub.save(conn,**args)
        conn.rollback.assert_called_once()
        for value in (float('nan'),101,-1):
            with self.assertRaises(ValueError):pub.save(conn,**{**args,'confidence':value})

    def test_model_version_changes_with_loaded_weights_scaler_or_adjustment(self):
        model=Mock();model.get_weights.return_value=[np.array([1.,2.])]
        a=pub.fingerprint(model,{'scale':1},['x'],[pub.utc])
        self.assertEqual(a,pub.fingerprint(model,{'scale':1},['x'],[pub.utc]))
        self.assertNotEqual(a,pub.fingerprint(model,{'scale':2},['x'],[pub.utc]))
        self.assertNotEqual(a,pub.fingerprint(model,{'scale':1},['x'],[pub.market_values]))
        model.get_weights.return_value=[np.array([1.,3.])]
        self.assertNotEqual(a,pub.fingerprint(model,{'scale':1},['x'],[pub.utc]))

    def test_verified_moneyline_replaces_legacy_without_changing_other_history(self):
        from core.confianza_datos import read_confidence
        from core.comparador import normalize
        legacy=normalize(pd.DataFrame([
            dict(fecha='2099-01-01',equipo_local='A',equipo_visitante='B',modelo='MLB V4',probabilidad=.99,cuota=2,resultado='GANADA'),
            dict(fecha='2099-01-02',equipo_local='C',equipo_visitante='D',modelo='MLB V4',probabilidad=.8,cuota=2,resultado='PERDIDA')
        ]),sport='MLB',market='Moneyline',identity=['fecha','equipo_local','equipo_visitante'])
        raw=pd.DataFrame([dict(fecha=date(2099,1,1),equipo_local='A',equipo_visitante='B',id_juego='game1',
                              modelo='a'*64,probabilidad=.65,cuota=1.9,resultado='GANADA')])
        def query(conn,sql):return raw if 'mlb_publicaciones_moneyline' in sql else pd.DataFrame()
        with patch('core.confianza_datos.read_models',return_value=(legacy,[])),patch('core.confianza_datos.rows',side_effect=query), \
             patch('core.confianza_datos.registro.history',side_effect=RuntimeError('unavailable')):
            result,errors=read_confidence(Mock(),Path('/missing'))
        self.assertEqual(len(result),2)
        v=result[result.procedencia.eq('Previo al inicio verificado')].iloc[0]
        self.assertEqual(v.probabilidad,.65);self.assertEqual(v.evento,'MLB|game1')
        self.assertTrue(v.apto_ajuste)
        self.assertEqual(result[result.procedencia.eq('Guardado · hora no verificable')].probabilidad.iloc[0],.8)
