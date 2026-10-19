"""Devolución con evidencia, sin confundir cero estadísticas con no participación."""
from datetime import datetime,timezone
from unittest import TestCase
from unittest.mock import Mock,patch
import pandas as pd
from core.devoluciones import apply_refunds,cancelled_mlb
from core.ui_historial_publicado import actual_result_details
from nfl.services.nonparticipation import nonparticipation_evidence
from core.actualizacion_manual import refresh_mlb_games


def pending(player='p'):
    return dict(id_juego='g',id_jugador=player,temporada=2026,semana=6,equipo_local='NYG',equipo_visitante='NO')


def empty_stats():
    return pd.DataFrame(index=pd.MultiIndex.from_tuples([],names=['game_id','player_id']))


class RefundTests(TestCase):
    def proof(self,stats=None,rosters=None,snaps=None,injuries=None,final=True):
        return nonparticipation_evidence([pending()],{'g'} if final else set(),
            empty_stats() if stats is None else stats,
            pd.DataFrame() if rosters is None else rosters,
            pd.DataFrame() if snaps is None else snaps,
            pd.DataFrame() if injuries is None else injuries)

    def test_missing_stats_alone_never_become_refund(self):
        self.assertEqual(self.proof(),{})

    def test_confirmed_out_only_after_game_finishes_and_only_matching_week(self):
        injury=pd.DataFrame([dict(season=2026,week=6,gsis_id='p',team='NYG',report_status='Out')])
        self.assertIn(('g','p'),self.proof(injuries=injury))
        self.assertEqual(self.proof(injuries=injury,final=False),{})
        self.assertEqual(self.proof(injuries=injury.assign(week=5)),{})
        self.assertEqual(self.proof(injuries=injury.assign(report_status='Questionable')),{})

    def test_zero_real_stats_are_participation_not_refund(self):
        stats=pd.DataFrame([dict(game_id='g',player_id='p',receiving_yards=0)]).set_index(['game_id','player_id'])
        injury=pd.DataFrame([dict(season=2026,week=6,gsis_id='p',team='NYG',report_status='Out')])
        self.assertEqual(self.proof(stats=stats,injuries=injury),{})

    def test_explicit_zero_snaps_and_positive_participation_override(self):
        roster=pd.DataFrame([dict(season=2026,week=6,gsis_id='p',team='NYG',pfr_id='PfrP',status='INA')])
        snaps=pd.DataFrame([dict(game_id='g',pfr_player_id='PfrP',offense_snaps=0,defense_snaps=0,st_snaps=0)])
        self.assertIn(('g','p'),self.proof(rosters=roster,snaps=snaps))
        self.assertEqual(self.proof(rosters=roster,snaps=snaps.assign(offense_snaps=1)),{})

    def test_postponed_and_live_games_never_treated_as_cancelled(self):
        for state in ['Postponed','Suspended','In Progress','Scheduled']:
            self.assertFalse(cancelled_mlb(dict(status=dict(abstractGameState='Final',detailedState=state))))
        self.assertTrue(cancelled_mlb(dict(status=dict(detailedState='Cancelled'))))
        self.assertFalse(cancelled_mlb(dict(status=dict(detailedState='Cancelled'),teams={'home':{'score':1}})))

    def test_matching_cancelled_game_is_audited_without_fake_score(self):
        frame=pd.DataFrame([dict(id_juego='odds-id',fecha='2026-10-16',equipo_local='H',equipo_visitante='A')])
        game=dict(gamePk=123,status={'abstractGameState':'Final','detailedState':'Cancelled'},
                  teams={'home':{'team':{'name':'H'}},'away':{'team':{'name':'A'}}})
        conn=Mock()
        with patch('core.bankroll.rows',return_value=frame),patch('mlb_totales.descargar_pitcheo.fetch_json',return_value={'dates':[{'games':[game]}]}), \
             patch('core.devoluciones.save_refund') as refund:
            msg=refresh_mlb_games(conn,datetime(2026,10,19,tzinfo=timezone.utc))
        self.assertEqual(refund.call_args.kwargs['game_id'],'odds-id')
        self.assertEqual(refund.call_args.kwargs['official_id'],123)
        self.assertEqual(refund.call_args.kwargs['legacy_key'],'2026-10-16|H|A')
        self.assertIn('1 partidos con devolución',msg)
        conn.cursor.return_value.execute.assert_not_called()

    def test_refund_applies_to_original_and_legacy_identities_without_resolving_other_rows(self):
        refund=dict(deporte='MLB',id_juego='odds-id',id_oficial='123',clave_legacy='2026-10-16|H|A',
                    id_jugador='',mercado='',motivo='Partido cancelado sin disputarse')
        frame=pd.DataFrame([dict(deporte='MLB',identidad=id,resultado='PENDIENTE',unidades=float('nan'))
                            for id in ['odds-id','123','2026-10-16|H|A','other']])
        settled=apply_refunds(frame,[refund])
        self.assertEqual(settled.resultado.tolist(),['PUSH','PUSH','PUSH','PENDIENTE'])
        self.assertEqual(settled.unidades.iloc[:3].tolist(),[0.,0.,0.])
        self.assertFalse(settled.resuelto.iloc[3])

    def test_player_refund_does_not_affect_teammate_or_total_and_never_invents_zero_yards(self):
        refund=dict(deporte='NFL',id_juego='g',id_jugador='p',mercado='receiving_yards',motivo='Jugador inactivo confirmado')
        frame=pd.DataFrame([dict(deporte='NFL',identidad=id,mercado='Yardas de recepción',resultado='PENDIENTE',valor_real=None)
                            for id in ['g|p|receiving_yards','g|other|receiving_yards','g']])
        settled=apply_refunds(frame,[refund])
        self.assertEqual(settled.resultado.tolist(),['PUSH','PENDIENTE','PENDIENTE'])
        self.assertIsNone(settled.valor_real.iloc[0])
        self.assertEqual(actual_result_details(settled.iloc[0]),[('Devolución','Jugador inactivo confirmado')])

    def test_evaluator_refunds_confirmed_absence_but_settles_played_zero_and_leaves_unknown_pending(self):
        with patch.dict('sys.modules',{'nflreadpy':Mock()}):
            from nfl import evaluar_resultados_props as evaluator
        rows=[pending(p)|dict(id_proyeccion=i,tipo_prop='receiving_yards',linea=20,seleccion='OVER',cuota_pick=-110,estado_pick='CANDIDATO')
              for i,p in enumerate(['inactive','played','unknown'],1)]
        stats=pd.DataFrame([dict(game_id='g',player_id='played',receiving_yards=0)]).set_index(['game_id','player_id'])
        proof={('g','inactive'):dict(reason='Jugador inactivo confirmado',source='fixture')}
        conn=Mock();cursor=conn.cursor.return_value;cursor.rowcount=1
        with patch.object(evaluator,'conectar_mysql',return_value=conn),patch.object(evaluator,'verificar_columnas'), \
             patch.object(evaluator,'cargar_pendientes',return_value=rows), \
             patch.object(evaluator,'cargar_resultados',return_value=({'g'},stats)), \
             patch('nfl.services.nonparticipation.load_nonparticipation',return_value=proof), \
             patch('core.infrastructure.migrations.ensure_schema'), \
             patch('core.devoluciones.save_refund') as refund:
            evaluator.main()
        params=[c.args[1] for c in cursor.execute.call_args_list]
        self.assertEqual(len(params),2)
        self.assertEqual(params[0][:3],(None,'PUSH',0.0))
        self.assertEqual(params[1][:3],(0.0,'PERDIDA',-1.0))
        self.assertEqual([p[-1] for p in params],[1,2])
        self.assertEqual(refund.call_args.kwargs['player_id'],'inactive')
        self.assertFalse(refund.call_args.kwargs['prepare'])
        cursor.rowcount=0
        with patch.object(evaluator,'conectar_mysql',return_value=conn),patch.object(evaluator,'verificar_columnas'), \
             patch.object(evaluator,'cargar_pendientes',return_value=rows[:1]), \
             patch.object(evaluator,'cargar_resultados',return_value=({'g'},stats)), \
             patch('nfl.services.nonparticipation.load_nonparticipation',return_value=proof), \
             patch('core.infrastructure.migrations.ensure_schema'), \
             patch('core.devoluciones.save_refund') as refund:
            evaluator.main()
        refund.assert_not_called()

    def test_refund_is_no_longer_pending_and_update_message_reports_it(self):
        from core.resumen import prediction_summary
        from core.ui_actualizacion import update_message
        frame=pd.DataFrame([dict(game_id='cancelled',fecha='2026-10-16',resultado='PUSH',resuelto=True),
                            dict(game_id='unknown',fecha='2026-10-16',resultado='PENDIENTE',resuelto=False)])
        _,count,_=prediction_summary(frame,datetime(2026,10,19,tzinfo=timezone.utc),keys=['game_id'],candidate=lambda r:True)
        self.assertEqual(count,1)
        message=update_message({'steps':[{'ok':True,'paso':'Marcadores MLB',
            'detalle':'0 partidos MLB actualizados. 1 partidos con devolución confirmada.'}]})
        self.assertIn('1 devoluciones registradas',message)
        self.assertNotIn('Sin cambios',message)
