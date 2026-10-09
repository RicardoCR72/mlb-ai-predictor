import argparse
import ast
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import pandas as pd
import yaml
from streamlit.testing.v1 import AppTest
from nfl import jornada, capturas
from core import nfl_creditos

ROOT = Path(__file__).resolve().parents[1]


def extracted(path, names, context):
    nodes = [n for n in ast.parse((ROOT/path).read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), context)
    return context


def event(id, kickoff, away='Arizona Cardinals', home='Seattle Seahawks'):
    return dict(id=id, commence_time=kickoff, away_team=away, home_team=home)


class DayTests(unittest.TestCase):
    def test_delayed_thursday_after_utc_midnight_is_still_tnf(self):
        now = datetime(2026,10,9,0,10,tzinfo=timezone.utc)
        events = [event('tnf','2026-10-09T00:20:00Z'), event('sun','2026-10-11T17:00:00Z'),
                  event('mnf','2026-10-13T00:20:00Z'), event('live','2026-10-08T23:00:00Z'),
                  event('missing',None), event('naive','2026-10-09T00:20:00')]
        self.assertEqual([e['id'] for e in jornada.eventos_hoy(events,now)],['tnf'])
        self.assertTrue(jornada.captura_programada('0 22 * 9-12,1-2 4'))
        self.assertFalse(jornada.captura_programada('0 14 * 9-12,1-2 5'))
        # La misma ejecución retrasada del incidente llega después del kickoff.
        self.assertEqual(jornada.eventos_hoy(events,datetime(2026,10,9,1,50,tzinfo=timezone.utc)),[])

    def test_sunday_keeps_snf_across_utc_date_but_excludes_monday(self):
        now = datetime(2026,10,11,15,tzinfo=timezone.utc)
        events=[event('early','2026-10-11T17:00:00Z'),event('late','2026-10-11T20:25:00Z'),
                event('snf','2026-10-12T00:20:00Z'),event('mnf','2026-10-13T00:20:00Z')]
        self.assertEqual([e['id'] for e in jornada.eventos_hoy(events,now)],['early','late','snf'])
        monday=datetime(2026,10,12,20,tzinfo=timezone.utc)
        self.assertEqual([e['id'] for e in jornada.eventos_hoy(events,monday)],['mnf'])
        self.assertEqual(jornada.limites_utc(date(2026,10,11)),
                         (datetime(2026,10,11,6),datetime(2026,10,12,6)))

    def test_calendar_uses_eastern_clock_and_never_guesses_missing_time(self):
        frame=pd.DataFrame([dict(game_id=id,gameday=day,gametime=hour) for id,day,hour in
            [('tnf','2026-10-08','20:20'),('sun','2026-10-11','13:00'),
             ('missing','2026-10-08',None),('started','2026-10-08','19:00')]])
        got=jornada.calendario_hoy(frame,datetime(2026,10,9,0,10,tzinfo=timezone.utc))
        self.assertEqual(got.game_id.tolist(),['tnf'])

    def test_totals_main_writes_only_today_and_preserves_weekly_csv(self):
        now=datetime(2026,10,8,20,tzinfo=timezone.utc)
        calendar=pd.DataFrame([dict(game_id=id,gameday=day,gametime='20:20',season=2026,
            game_type='REG',week=5,home_score=None,away_score=None) for id,day in
            [('tnf','2026-10-08'),('sun','2026-10-11'),('mnf','2026-10-12')]])
        prepare=Mock(side_effect=lambda c,w,game_ids:c[c.game_id.isin(game_ids)].copy())
        save=Mock(return_value=True)
        with tempfile.TemporaryDirectory() as folder:
            weekly=Path(folder)/'nfl_totales_2026_semana_5.csv';weekly.write_text('original')
            context=dict(argparse=argparse,TEMPORADA_ACTUAL=2026,DIRECTORIO_PREDICCIONES=Path(folder),
                calendario_hoy=lambda c:jornada.calendario_hoy(c,now),actualizar_calendario=lambda:calendar,
                actualizar_lesiones=Mock(),preparar_features=prepare,cargar_modelos=lambda:(None,None,None),
                generar_predicciones=lambda c,*m:c,guardar_predicciones_mysql=save,mostrar_resultados=Mock())
            extracted('nfl/predecir_semana_actual.py',['main'],context)
            with patch('sys.argv',['predictor','--solo-hoy']),redirect_stdout(StringIO()):
                context['main']()
            self.assertEqual(save.call_args.args[0].game_id.tolist(),['tnf'])
            self.assertEqual(prepare.call_args.kwargs['game_ids'],['tnf'])
            self.assertEqual(weekly.read_text(),'original')
            self.assertTrue((Path(folder)/'nfl_totales_2026_semana_5_hoy.csv').exists())


class CaptureTests(unittest.TestCase):
    def run_capture(self,now,events,args=(),previous=(),failure=False):
        import sys
        class Clock:
            @staticmethod
            def now(tz=None): return now
        teams={'Arizona Cardinals':'ARI','Seattle Seahawks':'SEA','Kansas City Chiefs':'KC',
               'Denver Broncos':'DEN','New England Patriots':'NE','New York Jets':'NYJ'}
        games=[dict(id_juego=e['id'],equipo_visitante=teams[e['away_team']],equipo_local=teams[e['home_team']],semana=5,
                    fecha=jornada.inicio_evento(e).astimezone(jornada.MEXICO).date())
               for e in events if jornada.inicio_evento(e)]
        conn=Mock();conn.is_connected.return_value=True
        count=0
        def api_get(route,key,**params):
            nonlocal count
            if route.endswith('/events'):return events,dict(restantes=500,costo=0)
            count+=1
            if failure:raise RuntimeError('No se pudo conectar a The Odds API.')
            return {'id':route.split('/')[-2]},dict(restantes=500-count*6,costo=6)
        api=Mock(side_effect=api_get)
        context=dict(argparse=argparse,json=json,datetime=Clock,timezone=timezone,pd=pd,
            TEMPORADA_ACTUAL=2026,SPORT='americanfootball_nfl',MARKETS=dict.fromkeys(jornada.MERCADOS_PROPS),
            EQUIPO_API_A_SIGLA=teams,
            ahora_mexico=lambda:jornada.ahora_mexico(now),eventos_hoy=lambda e:jornada.eventos_hoy(e,now),
            obtener_api_key=lambda:'test-key',conectar_mysql=lambda:conn,capturas=Mock(),
            sincronizar_catalogo_jugadores=lambda c:0,cargar_juegos_pendientes=Mock(return_value=games),
            api_get=api,filtrar_parejas_por_ventana=lambda p,h:p,
            juegos_con_captura=lambda c,p:set(previous),imprimir_cuota=lambda c:None,
            cargar_jugadores_por_equipo=lambda c,e:[],indice_jugadores=lambda j:{},
            cargar_cache_evento=lambda id:None,guardar_cache_evento=Mock(),
            extraer_lineas=lambda r,g,i:([{'id_juego':g['id_juego']}],set()),
            guardar_lineas=Mock(side_effect=lambda c,rows:len(rows)))
        context['capturas'].adquirir.return_value=True
        extracted('nfl/actualizar_lineas_props.py',['main','emparejar_eventos'],context)
        output=StringIO()
        with patch.dict(sys.modules,{'jornada':jornada}),redirect_stdout(output):
            try:context['main'](list(args))
            except RuntimeError:
                if not failure:raise
        report=json.loads(next(line.split('=',1)[1] for line in output.getvalue().splitlines()
                               if line.startswith('NFL_ODDS_REPORT=')))
        paid=[c for c in api.call_args_list if c.args[0].endswith('/odds')]
        return context,paid,report

    def test_thursday_default_without_window_never_buys_sunday(self):
        ctx,paid,report=self.run_capture(datetime(2026,10,8,20,tzinfo=timezone.utc),
            [event('tnf','2026-10-09T00:20:00Z'),event('sun','2026-10-11T17:00:00Z')])
        self.assertEqual(len(paid),1)
        self.assertIn('/tnf/odds',paid[0].args[0])
        self.assertEqual(paid[0].kwargs['bookmakers'],'draftkings')
        self.assertEqual(len(paid[0].kwargs['markets'].split(',')),6)
        self.assertEqual((report['creditos'],report['restantes']),(6,494))
        self.assertTrue(ctx['cargar_juegos_pendientes'].call_args.kwargs['solo_hoy'])

    def test_sunday_capture_and_budget_match_preview(self):
        events=[event('sun1','2026-10-11T17:00:00Z'),
                event('snf','2026-10-12T00:20:00Z',home='Seattle Seahawks'),
                event('mnf','2026-10-13T00:20:00Z')]
        # Equipos idénticos el mismo día son ambiguos: nunca asignar dos eventos a un juego.
        _,paid,_=self.run_capture(datetime(2026,10,11,15,tzinfo=timezone.utc),events)
        self.assertEqual(paid,[])
        events=[event('sun1','2026-10-11T17:00:00Z'),
                event('snf','2026-10-12T00:20:00Z','Kansas City Chiefs','Denver Broncos'),
                event('mnf','2026-10-13T00:20:00Z','New England Patriots','New York Jets')]
        _,paid,report=self.run_capture(datetime(2026,10,11,15,tzinfo=timezone.utc),events)
        self.assertEqual(len(paid),2);self.assertEqual(report['creditos'],12)
        self.assertTrue(all('/mnf/' not in c.args[0] for c in paid))
        _,paid,report=self.run_capture(datetime(2026,10,11,15,tzinfo=timezone.utc),events,
                                      ('--max-creditos','6'))
        self.assertEqual(len(paid),1);self.assertEqual(report['creditos'],6)
        self.assertFalse(report['completo'])
        _,paid,report=self.run_capture(datetime(2026,10,12,20,tzinfo=timezone.utc),events)
        self.assertEqual(len(paid),1);self.assertIn('/mnf/odds',paid[0].args[0])
        self.assertEqual(report['creditos'],6)
        events=[event('sun1','2026-10-11T17:00:00Z'),event('mnf','2026-10-13T00:20:00Z')]
        _,paid,report=self.run_capture(datetime(2026,10,11,15,tzinfo=timezone.utc),events,
            ('--max-creditos','0'))
        self.assertEqual(paid,[]);self.assertEqual(report['creditos'],0)
        _,paid,report=self.run_capture(datetime(2026,10,11,15,tzinfo=timezone.utc),events,
            ('--eventos','mnf','--max-creditos','6'))
        self.assertEqual(paid,[]);self.assertEqual(report['creditos'],0)

    def test_today_dedup_and_unknown_charge_on_network_failure(self):
        events=[event('tnf','2026-10-09T00:20:00Z')]
        _,paid,report=self.run_capture(datetime(2026,10,8,20,tzinfo=timezone.utc),events,
                                      ('--una-captura',),previous=('tnf',))
        self.assertEqual(paid,[]);self.assertEqual(report['omitidos'],1)
        _,paid,report=self.run_capture(datetime(2026,10,8,20,tzinfo=timezone.utc),events,failure=True)
        self.assertEqual(len(paid),1);self.assertIsNone(report['creditos'])

    def test_daily_dedup_query_does_not_block_old_thursday_lines(self):
        conn=Mock();conn.cursor.return_value.fetchall.return_value=[]
        now=datetime(2026,10,11,15,tzinfo=timezone.utc)
        context=dict(ahora_mexico=lambda:jornada.ahora_mexico(now),limites_utc=jornada.limites_utc)
        extracted('nfl/actualizar_lineas_props.py',['juegos_con_captura'],context)
        self.assertEqual(context['juegos_con_captura'](conn,[({'id_juego':'sun'}, {})]),set())
        sql,args=conn.cursor.return_value.execute.call_args.args
        self.assertIn('timestamp_captura >= %s',sql)
        self.assertIn('nfl_capturas_odds',sql)
        self.assertEqual(args[1:3],(datetime(2026,10,11,6),datetime(2026,10,12,6)))


class ManualTests(unittest.TestCase):
    def test_plan_only_uses_free_events_endpoint_and_six_markets(self):
        response=Mock(status_code=200,headers={'x-requests-remaining':'450'})
        response.json.return_value=[event('tnf','2026-10-09T00:20:00Z'),event('sun','2026-10-11T17:00:00Z')]
        with patch.object(nfl_creditos,'api_key',return_value='private'),patch.object(nfl_creditos.requests,'get',return_value=response) as get:
            plan=nfl_creditos.plan_hoy(datetime(2026,10,8,20,tzinfo=timezone.utc))
        self.assertTrue(get.call_args.args[0].endswith('/events'))
        self.assertEqual(plan['max_creditos'],6)
        self.assertEqual(plan['restantes'],450)

    def test_pipeline_spends_only_after_models_and_db_work_and_carries_budget(self):
        now=datetime(2026,10,8,20,tzinfo=timezone.utc)
        plan=dict(fecha='2026-10-08',eventos=[event('tnf','2026-10-09T00:20:00Z')],max_creditos=6,restantes=500)
        report=dict(fecha='2026-10-08',solicitados=1,creditos=6,restantes=494,insertadas=30,completo=True)
        def process(args,**kwargs):
            stdout='NFL_ODDS_REPORT='+json.dumps(report) if 'actualizar_lineas_props.py' in args[1] else 'MySQL actualizado: 1'
            return Mock(returncode=0,stdout=stdout)
        with tempfile.TemporaryDirectory() as folder,patch.object(nfl_creditos,'ahora_mexico',return_value=jornada.ahora_mexico(now)),\
             patch.object(nfl_creditos,'eventos_hoy',side_effect=lambda e:jornada.eventos_hoy(e,now)),\
             patch.object(nfl_creditos,'child_environment',return_value={}),patch.object(nfl_creditos,'api_key',return_value='private'),\
             patch.object(nfl_creditos.subprocess,'run',side_effect=process) as run:
            result=nfl_creditos.run_predictions(folder,plan)
            commands=[c.args[0] for c in run.call_args_list]
            paid=next(c for c in commands if 'actualizar_lineas_props.py' in c[1])
            self.assertEqual(paid[-4:],['--max-creditos','6','--eventos','tnf'])
            self.assertNotIn('--una-captura',paid)
            self.assertTrue(all('--solo-hoy' in c for c in commands if 'predecir_' in c[1]))
            self.assertTrue(result['ok']);self.assertEqual(result['reporte']['creditos'],6)
            run.reset_mock();run.return_value=Mock(returncode=1,stdout='');run.side_effect=None
            result=nfl_creditos.run_predictions(folder,plan)
            self.assertFalse(result['ok'])
            self.assertFalse(any('actualizar_lineas_props.py' in c.args[0][1] for c in run.call_args_list))

    def test_button_discloses_cost_and_does_not_run_on_page_load(self):
        plan=dict(fecha='2099-01-01',eventos=[event('tnf','2099-01-02T00:20:00Z')],max_creditos=6,restantes=500,reserva=120)
        with patch('core.ui_nfl_creditos.consultar',return_value=plan),\
             patch('core.ui_nfl_creditos.run_predictions',return_value=dict(ok=True,detalle='Actualizadas',reporte=None)) as run:
            at=AppTest.from_string('from core.ui_actualizacion import render_update_button\nfrom core.ui_nfl_creditos import render_prediction_button\nrender_update_button("nfl_props",compact=True)\nrender_prediction_button()').run()
            self.assertFalse(at.exception);run.assert_not_called()
            self.assertEqual(len(at.button),2)
            self.assertEqual(len(at.expander),0)
            self.assertEqual(len(at.caption),0)
            self.assertIn('6 créditos',at.button[1].label)
            at.button[1].click().run()
            self.assertFalse(at.exception);run.assert_called_once()
            self.assertEqual(run.call_args.args[1]['eventos'][0]['id'],'tnf')

    def test_workflow_decision_is_based_on_trigger_and_every_paid_step_is_today(self):
        w=yaml.safe_load((ROOT/'.github/workflows/bot_nfl_props.yml').read_text())
        steps=w['jobs']['props']['steps']
        decision=next(s for s in steps if s.get('id')=='ventana')
        self.assertIn('github.event.schedule',decision['env']['EVENT_SCHEDULE'])
        self.assertNotIn('date -u',decision['run'])
        self.assertIn('captura_programada',decision['run'])
        for name in ('bot_nfl_props.yml','nfl_props.yml'):
            doc=yaml.safe_load((ROOT/'.github/workflows'/name).read_text())
            for job in doc['jobs'].values():
                paid=[s for s in job['steps'] if 'actualizar_lineas_props.py' in s.get('run','')]
                self.assertTrue(paid)
                self.assertTrue(all('--solo-hoy' in s['run'] and '--una-captura' in s['run'] for s in paid))


if __name__ == '__main__': unittest.main()
