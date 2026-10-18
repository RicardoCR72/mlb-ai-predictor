from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import tempfile
import unittest
from unittest.mock import patch,Mock
import pandas as pd
from core import actualizacion_manual as update
from core import bankroll as bank

ROOT=Path(__file__).resolve().parents[1]

class TestManualUpdates(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("core.permisos.require_admin"))
    def test_nfl_uses_fixed_evaluator_and_private_environment_without_notifications(self):
        creds={'host':'database','port':1234,'user':'user','password':'private','database':'sports','ssl_ca':'/tmp/ca.pem'}
        with patch.object(update,'get_db_credentials',return_value=creds),patch.dict(update.os.environ,{'ODDS_API_KEY':'secret','TELEGRAM_BOT_TOKEN':'secret'}),patch.object(update.subprocess,'run',return_value=Mock(returncode=0)) as run:
            update.run_script('nfl_props',ROOT)
        args,kwargs=run.call_args
        self.assertEqual(args[0],[update.sys.executable,str(ROOT/'nfl/evaluar_resultados_props.py')])
        self.assertNotIn('shell',kwargs)
        self.assertEqual(kwargs['env']['DB_PASSWORD'],'private')
        self.assertNotIn('ODDS_API_KEY',kwargs['env']);self.assertNotIn('TELEGRAM_BOT_TOKEN',kwargs['env'])
        self.assertEqual(kwargs['env']['TELEGRAM_REPORTE_UNIFICADO'],'1')

    def test_no_other_process_can_be_requested(self):
        with self.assertRaises(ValueError):update.run_update('odds',ROOT)
        with self.assertRaises(ValueError):update.run_script('odds',ROOT)

    def test_busy_service_does_not_start_or_settle_anything(self):
        update.LOCKS['mlb'].acquire()
        try:
            with patch.object(update,'get_db_connection') as connect:
                self.assertTrue(update.run_update('mlb',ROOT)['busy'])
            connect.assert_not_called()
        finally:update.LOCKS['mlb'].release()

    def test_partial_failure_is_visible_and_locks_are_released(self):
        conn=Mock()
        with patch.object(update,'get_db_connection',return_value=conn),patch.object(update,'run_script',side_effect=RuntimeError('Evaluador falló')),patch.object(update,'settle_bank',return_value='0 apuestas'):
            result=update.run_update('nfl_totales',ROOT)
        self.assertEqual([r['ok'] for r in result['steps']],[False])
        self.assertFalse(update.LOCKS['nfl_totales'].locked());conn.close.assert_not_called()

    def test_bankroll_fetches_only_sources_of_pending_model_bets(self):
        ledger=pd.DataFrame([{'estado':'Pendiente','origen':'nfl_prop'},{'estado':'Ganada','origen':'mlb_total'},{'estado':'Pendiente','origen':'manual'}])
        with patch.object(update,'get_db_connection',return_value=Mock()),patch.object(bank,'prepare'),patch.object(bank,'load_ledger',return_value=ledger),patch.object(update,'run_script',return_value='OK') as script,patch.object(update,'settle_bank',return_value='1 apuesta'):
            result=update.run_update('bankroll',ROOT)
        script.assert_called_once_with('nfl_props',ROOT)
        self.assertTrue(all(r['ok'] for r in result['steps']))

    def test_mlb_doubleheaders_never_apply_one_score_to_two_games(self):
        pending=pd.DataFrame([{'id_juego':'one','fecha':'2026-10-05','equipo_local':'H','equipo_visitante':'A'}])
        game={'gamePk':1,'status':{'abstractGameState':'Final'},'teams':{'home':{'team':{'name':'H'},'score':2},'away':{'team':{'name':'A'},'score':1}}}
        conn=Mock();conn.cursor.return_value.rowcount=1
        with patch.object(bank,'rows',return_value=pending),patch('mlb_totales.descargar_pitcheo.fetch_json',return_value={'dates':[{'games':[game,{**game,'gamePk':2}]}]}):
            message=update.refresh_mlb_games(conn,datetime(2026,10,6,tzinfo=ZoneInfo('America/Mexico_City')))
        conn.cursor.return_value.execute.assert_not_called()
        self.assertIn('ambiguas',message)

    def test_mlb_finished_game_is_settled_but_live_and_postponed_are_not(self):
        pending=pd.DataFrame([
            dict(id_juego='yesterday',fecha='2026-10-16',equipo_local='H',equipo_visitante='A'),
            dict(id_juego='today',fecha='2026-10-17',equipo_local='H',equipo_visitante='A'),
            dict(id_juego='rain',fecha='2026-10-15',equipo_local='H',equipo_visitante='A')])
        def official(endpoint,params):
            final=params['date']=='2026-10-16'
            if params['date']=='2026-10-15':
                return {'dates':[{'games':[dict(gamePk=3,status=dict(statusCode='DR',abstractGameState='Final',
                    detailedState='Postponed'),teams=dict(home=dict(team=dict(name='H')),away=dict(team=dict(name='A'))))]}]}
            return {'dates':[{'games':[dict(gamePk=1,status=dict(statusCode='O' if final else 'I',
                abstractGameState='Final' if final else 'Live'),teams=dict(
                home=dict(team=dict(name='H'),score=3),away=dict(team=dict(name='A'),score=2)))]}]}
        conn=Mock();conn.cursor.return_value.rowcount=1
        with patch.object(bank,'rows',return_value=pending), \
             patch('mlb_totales.descargar_pitcheo.fetch_json',side_effect=official):
            message=update.refresh_mlb_games(conn,datetime(2026,10,17,tzinfo=ZoneInfo('America/Mexico_City')))
        self.assertIn('1 partidos MLB actualizados',message)
        values=conn.cursor.return_value.execute.call_args.args[1]
        self.assertEqual(values,(3,2,'yesterday'))
        conn.cursor.return_value.execute.assert_called_once()

    def test_untracked_doubleheader_is_not_reported_as_ambiguous(self):
        pending=pd.DataFrame([dict(id_juego='one',fecha='2026-10-05',equipo_local='H',equipo_visitante='A')])
        game=dict(gamePk=1,status=dict(abstractGameState='Final'),teams=dict(
            home=dict(team=dict(name='Other H'),score=3),away=dict(team=dict(name='Other A'),score=1)))
        conn=Mock();report=Mock()
        with patch.object(bank,'rows',return_value=pending), \
             patch('mlb_totales.descargar_pitcheo.fetch_json',return_value={'dates':[{'games':[game,{**game,'gamePk':2}]}]}):
            message=update.refresh_mlb_games(conn,on_ambiguity=report)
        self.assertIn('0 coincidencias ambiguas',message)
        report.assert_not_called();conn.cursor.return_value.execute.assert_not_called()

    def test_real_ambiguity_is_reported_once_with_exact_pending_identity(self):
        pending=pd.DataFrame([dict(id_juego='one',fecha='2026-10-05',equipo_local='H',equipo_visitante='A')])
        game=dict(gamePk=1,status=dict(abstractGameState='Final'),teams=dict(
            home=dict(team=dict(name='H'),score=3),away=dict(team=dict(name='A'),score=1)))
        conn=Mock();report=Mock()
        with patch.object(bank,'rows',return_value=pending), \
             patch('mlb_totales.descargar_pitcheo.fetch_json',return_value={'dates':[{'games':[game,{**game,'gamePk':2}]}]}):
            message=update.refresh_mlb_games(conn,on_ambiguity=report)
        self.assertIn('1 coincidencias ambiguas',message)
        report.assert_called_once()
        self.assertEqual(report.call_args.args[0]['pendientes'],['one'])
        self.assertEqual([g['game_pk'] for g in report.call_args.args[0]['oficiales']],[1,2])
        conn.cursor.return_value.execute.assert_not_called()

    def test_doubleheader_uses_unique_nearby_starts_and_never_nearest_or_date_only(self):
        pending=pd.DataFrame([
            dict(id_juego='early',fecha='2026-09-22 11:05:00',equipo_local='H',equipo_visitante='A'),
            dict(id_juego='late',fecha='2026-09-22 17:05:00',equipo_local='H',equipo_visitante='A')])
        def game(pk,hour,score):return dict(gamePk=pk,gameDate=f'2026-09-22T{hour}:05:00Z',
            status=dict(abstractGameState='Final'),teams=dict(home=dict(team=dict(name='H'),score=score),
            away=dict(team=dict(name='A'),score=1)))
        games=[game(1,'17',2),game(2,'23',4)]
        self.assertEqual(update.verified_mlb_starts(pending,games),{'1':'early','2':'late'})
        date_only=pending.assign(fecha='2026-09-22')
        self.assertEqual(update.verified_mlb_starts(date_only,games),{})
        shifted=pending.copy();shifted['fecha']=pd.to_datetime(shifted.fecha)+pd.Timedelta(minutes=1)
        self.assertEqual(update.verified_mlb_starts(shifted,games),{'1':'early','2':'late'})
        shifted['fecha']+=pd.Timedelta(minutes=2)
        self.assertEqual(update.verified_mlb_starts(shifted,games),{})
        conflicting=[games[0],{**games[0],'gamePk':3,'gameDate':'2026-09-22T17:06:00Z'}]
        self.assertEqual(update.verified_mlb_starts(pending,conflicting),{})
        self.assertEqual(update.verified_mlb_starts(pd.concat([pending,pending]),games),{})
        conn=Mock();conn.cursor.return_value.rowcount=1;report=Mock()
        with patch.object(bank,'rows',return_value=pending), \
             patch('mlb_totales.descargar_pitcheo.fetch_json',return_value={'dates':[{'games':games}]}):
            message=update.refresh_mlb_games(conn,on_ambiguity=report)
        self.assertIn('2 partidos MLB actualizados',message)
        self.assertEqual([c.args[1] for c in conn.cursor.return_value.execute.call_args_list],[(2,1,'early'),(4,1,'late')])
        report.assert_not_called()

    def test_moneyline_history_includes_today_only_with_both_scores(self):
        import ast
        from datetime import date
        source=ast.parse((ROOT/'mlb/moneyline_service.py').read_text())
        fn=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='cargar_historial_xampp')
        fn.decorator_list=[]
        conn=Mock();read=Mock(return_value=pd.DataFrame())
        namespace=dict(conectar_bd=lambda:conn,hoy_mx=lambda:date(2026,10,17),pd=Mock(read_sql=read))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<history>','exec'),namespace)
        namespace['cargar_historial_xampp']()
        sql=read.call_args.args[0]
        self.assertIn('DATE(j.fecha) <= %s',sql)
        self.assertIn('j.marcador_visitante IS NOT NULL',sql)
        self.assertEqual(read.call_args.kwargs['params'],(date(2026,10,17),))
        conn.close.assert_called_once()

    def test_results_job_attempts_both_histories_and_reports_partial_failure(self):
        from scripts import actualizar_resultados_mlb as job
        conn=Mock()
        with patch.object(job,'get_db_connection',return_value=conn), \
             patch.object(job,'refresh_mlb_games',side_effect=ValueError('private')), \
             patch.object(job,'mlb_totals',return_value='2 resultados') as totals, \
             patch('builtins.print') as output:
            with self.assertRaises(RuntimeError):job.main()
        totals.assert_called_once_with(conn)
        conn.close.assert_called_once()
        self.assertNotIn('private',str(output.call_args_list))

    def test_hourly_results_workflow_has_no_odds_or_notifications(self):
        import yaml
        data=yaml.load((ROOT/'.github/workflows/mlb_resultados.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(data['on']['schedule'][0]['cron'],'25 * * * *')
        job=data['jobs']['resultados']
        self.assertEqual(job['steps'][-1]['run'],'python scripts/actualizar_resultados_mlb.py')
        self.assertFalse(any('ODDS' in key or 'TELEGRAM' in key for key in job['env']))

    def test_partial_today_coverage_expires_and_old_unresolved_games_block(self):
        from futbol_liga_mx import cobertura_actual as coverage
        from datetime import timedelta
        root=ROOT/'futbol_liga_mx/data'
        frame=pd.read_csv(root/'partidos.csv');frame=frame[frame.season.eq('2026-27')]
        now=datetime(2026,10,6,13,tzinfo=ZoneInfo('UTC'))
        # El CSV crece a diario: esta auditoría solo incluye el corte simulado.
        frame=frame[pd.to_datetime(frame.fecha).dt.date.le(now.date())]
        class Frozen(datetime):
            @classmethod
            def now(cls,tz=None):return now.astimezone(tz) if tz else now.replace(tzinfo=None)
        events=[dict(id=str(i),date=r.fecha+'T12:00:00Z',season={'slug':'torneo-apertura'},status={'type':{'name':'STATUS_FULL_TIME'}})
                for i,r in frame.iterrows()]
        events.append(dict(id='future_today',date='2026-10-06T23:00:00Z',season={'slug':'torneo-apertura'},status={'type':{'name':'STATUS_SCHEDULED'}}))
        with patch.object(coverage,'datetime',Frozen):
            report=coverage.scan_report(events,frame,datetime(2026,7,1).date(),now.date(),allow_current_day=True)
            self.assertTrue(report['audited'])
            self.assertTrue(coverage.verified_current(frame,now,report))
            self.assertFalse(coverage.verified_current(frame,now+timedelta(days=1),report))
            events[-1]['date']='2026-10-05T23:00:00Z'
            bad=coverage.scan_report(events,frame,datetime(2026,7,1).date(),now.date(),allow_current_day=True)
            self.assertFalse(bad['audited'])

    def test_button_refreshes_then_current_page_renders_and_shows_partial_result(self):
        from streamlit.testing.v1 import AppTest
        text='''import streamlit as st
from core.ui_actualizacion import render_update_button
render_update_button('nfl_totales')
st.write('Tabla actualizada')
'''
        result={'busy':False,'steps':[{'paso':'Resultados','ok':True,'detalle':'1 resultado'},{'paso':'Bankroll','ok':False,'detalle':'Sin conexión'}],'at':'2026-10-06T07:30:00-06:00'}
        from datetime import datetime
        job=dict(id='demo',estado='parcial',creado_utc=datetime(2026,10,1),iniciado_utc=None,terminado_utc=datetime(2026,10,1),resultado=result)
        with patch('core.ui_trabajos.session_token',return_value='test'),patch('core.ui_trabajos.submit',return_value='demo') as run, \
             patch('core.ui_trabajos.latest',return_value=job),patch('core.ui_trabajos.invalidate_readers'):
            app=AppTest.from_string(text).run()
            app.button[0].click().run()
        self.assertEqual(len(app.exception),0)
        run.assert_called_once()
        self.assertTrue(any('parcial' in c.value for c in app.caption))

class TestPublicationAudit(unittest.TestCase):
    def original(self):
        return dict(id_juego='g',modelo='v',probabilidad=.6,cuota=1.9,pick_ia='H',
            equipo_local='H',equipo_visitante='A',start_utc='2026-10-17 20:00:00',
            quote_utc='2026-10-17 17:00:00',captured_utc='2026-10-17 17:01:00',
            publicada_utc='2026-10-17 18:00:00')

    def test_new_publications_are_allowed_but_changed_or_deleted_originals_are_flagged(self):
        from core.auditoria_mlb import summarize,compare
        a={'Moneyline':summarize([self.original()],'Moneyline'),'Totales':summarize([],'Totales')}
        b={**a,'Moneyline':summarize([self.original(),{**self.original(),'id_juego':'new'}],'Moneyline')}
        self.assertEqual(compare(a,b)['Moneyline']['estado'],'OK')
        b['Moneyline']=summarize([{**self.original(),'probabilidad':.8}],'Moneyline')
        self.assertEqual(compare(a,b)['Moneyline']['modificados'],1)
        b['Moneyline']=summarize([],'Moneyline')
        self.assertEqual(compare(a,b)['Moneyline']['eliminados'],1)

    def test_bad_clock_probabilities_duplicates_and_missing_source_are_not_certified(self):
        from core.auditoria_mlb import summarize,compare
        bad={**self.original(),'publicada_utc':'2026-10-17 21:00:00','probabilidad':90}
        result=summarize([bad,bad],'Moneyline')
        self.assertEqual(result['invalidos'],2);self.assertEqual(result['duplicados'],1)
        a={'Moneyline':result,'Totales':dict(no_disponible='DatabaseError')}
        self.assertEqual(compare(a,a)['Moneyline']['estado'],'REVISAR')
        self.assertEqual(compare(a,a)['Totales']['estado'],'NO_VERIFICABLE')

    def test_capture_only_selects_and_never_returns_private_database_errors(self):
        from core.auditoria_mlb import capture
        conn=Mock();cur=conn.cursor.return_value;cur.fetchall.return_value=[]
        result=capture(conn)
        self.assertTrue(all(c.args[0].startswith('SELECT ') for c in cur.execute.call_args_list))
        cur.execute.side_effect=ValueError('private-host-password')
        result=capture(conn)
        self.assertNotIn('private',str(result))

if __name__=='__main__':unittest.main()
