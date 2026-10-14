import json
from datetime import datetime,timezone
from unittest import TestCase
from unittest.mock import Mock,patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from nfl.dependencia_lesiones import escenarios_companeros,marcar_dependencia
from nfl.publicaciones_props import publication_rows,save_publications,attach_publications
from core.auditoria_nfl import receiving_audit,summarize


class AuditTests(TestCase):
    def fixture(self):
        return pd.DataFrame([
            dict(id_juego='g',id_jugador='p',tipo_prop='receiving_yards',season=2026,week=5,
                 estado_pick='CANDIDATO',resultado_pick='PERDIDA',proyeccion=90,linea=75.5,
                 valor_real=60,probabilidad_pick=.65,beneficio_unidades=-1,seleccion='OVER',
                 estado_lesion='healthy_or_unlisted',contexto_lesiones='X (WR, QUESTIONABLE)'),
            dict(id_juego='g',id_jugador='p',tipo_prop='receptions',estado_pick='NO PICK',
                 resultado_pick='PERDIDA',proyeccion=6,valor_real=5)])

    def test_volume_and_efficiency_decompose_and_unknown_profit_stays_unknown(self):
        data=self.fixture();f=receiving_audit(data,data)
        self.assertEqual(len(f),1)
        self.assertEqual(f.iloc[0]['Error por volumen (yds)'],15)
        self.assertEqual(f.iloc[0]['Error por eficiencia (yds)'],15)
        self.assertEqual(f.iloc[0].Lesiones,'Contexto de compañeros')
        self.assertEqual(f.iloc[0].Confianza,'65% o más')
        table=summarize(f,['week','seleccion']);self.assertEqual(table.iloc[0]['ROI (%)'],-100)
        data.loc[0,'beneficio_unidades']=np.nan
        table=summarize(receiving_audit(data,data),['week'])
        self.assertTrue(pd.isna(table.iloc[0]['ROI (%)']))
        self.assertEqual(table.iloc[0].Muestra_ROI,0)

    def test_missing_or_zero_receptions_do_not_invent_efficiency(self):
        data=self.fixture();data.loc[1,'valor_real']=0
        f=receiving_audit(data,data)
        self.assertTrue(pd.isna(f.iloc[0]['Error por eficiencia (yds)']))
        f=receiving_audit(data,data.iloc[:1])
        self.assertTrue(pd.isna(f.iloc[0]['Error por volumen (yds)']))
        self.assertIn('no verificada',f.iloc[0].Fuente)
        self.assertTrue(receiving_audit(data.iloc[1:],data).empty)

    def test_original_publication_restores_values_and_recomputes_one_unit_settlement(self):
        data=self.fixture()
        data['auditoria_payload']=None
        data.loc[0,'auditoria_payload']=json.dumps(dict(linea=55.5,proyeccion=70,seleccion='OVER',
            probabilidad_pick=.61,cuota_pick=-110,recepciones_proyectadas=5,dependencia_lesion=True))
        f=receiving_audit(data,data)
        self.assertEqual(f.iloc[0].Fuente,'Publicación conservada')
        self.assertEqual(f.iloc[0].resultado_pick,'GANADA')
        self.assertAlmostEqual(f.iloc[0]['Unidades conocidas'],100/110)
        self.assertEqual(f.iloc[0].recepciones_proyectadas,5)
        self.assertEqual(f.iloc[0].Lesiones,'Dependencia en escenarios')

    def test_scenarios_exclude_self_and_other_teams_and_keep_confirmed_out(self):
        features=pd.DataFrame([dict(season=2026,week=5,team='MIN',player_id='h',
            teammate_skill_injury_score=1.35,team_skill_injury_score=1.7,team_skill_injury_count=3)])
        reports=pd.DataFrame([dict(season=2026,week=5,team=team,gsis_id=id,full_name=id,
            position='WR',report_status=status,practice_status='Limited') for team,id,status in
            [('MIN','j','Questionable'),('MIN','x','Out'),('MIN','h','Questionable'),('GB','z','Doubtful')]])
        active,absent,names=escenarios_companeros(features,reports)
        self.assertEqual(names.tolist(),['j'])
        self.assertAlmostEqual(active.iloc[0].teammate_skill_injury_score,1)
        self.assertAlmostEqual(absent.iloc[0].teammate_skill_injury_score,2)
        self.assertAlmostEqual(active.iloc[0].team_skill_injury_score,1.35)
        self.assertEqual(active.iloc[0].team_skill_injury_count,2)
        self.assertEqual(features.iloc[0].team_skill_injury_count,3)

    def test_side_or_eligibility_changes_flag_only_receiving_yards(self):
        base=pd.DataFrame([dict(game_id='g',player_id='h',tipo_prop=t,seleccion='OVER',
            proyeccion=85,estado_pick='CANDIDATO',companeros_en_duda='Jefferson',contexto_lesiones='')
            for t in ['receiving_yards','receptions','passing_yards']])
        active=base.iloc[:1].copy();active['proyeccion']=60;active['seleccion']='UNDER'
        absent=base.iloc[:1].copy()
        f=marcar_dependencia(base,active,absent)
        self.assertEqual(f.estado_pick.tolist(),['REVISAR LESION','CANDIDATO','CANDIDATO'])
        self.assertIn('Jefferson',f.iloc[0].contexto_lesiones)
        self.assertEqual(f.iloc[0].proyeccion,85)
        active['seleccion']='OVER';active['estado_pick']='NO PICK'
        self.assertEqual(marcar_dependencia(base,active,absent).iloc[0].estado_pick,'REVISAR LESION')
        active['estado_pick']='CANDIDATO'
        self.assertEqual(marcar_dependencia(base,active,absent).iloc[0].estado_pick,'CANDIDATO')

    def publication_fixture(self):
        data=pd.DataFrame([dict(game_id='g',player_id='p',tipo_prop=t,id_linea=1,
            proyeccion=n,linea=60,seleccion='OVER',probabilidad_pick=.65,cuota_pick=-110,
            estado_pick='CANDIDATO') for t,n in [('receiving_yards',90),('receptions',6)]])
        games=pd.DataFrame([dict(game_id='g',gameday='2026-10-11',gametime='13:00')])
        return data,games

    def test_publications_skip_started_unknown_time_and_no_line(self):
        data,games=self.publication_fixture();before=datetime(2026,10,11,16,tzinfo=timezone.utc)
        rows=publication_rows(data,games,'v',before)
        self.assertEqual(len(rows),2)
        self.assertEqual(json.loads(rows[0][-1])['recepciones_proyectadas'],6)
        self.assertEqual(publication_rows(data,games,'v',datetime(2026,10,11,18,tzinfo=timezone.utc)),[])
        games['gametime']=None;self.assertEqual(publication_rows(data,games,'v',before),[])

    def test_all_six_prop_markets_preserve_original_probabilities_with_unknown_injury(self):
        data,games=self.publication_fixture()
        markets=['receiving_yards','receptions','rushing_yards','passing_yards','passing_tds','anytime_td']
        records=[dict(data.iloc[0],tipo_prop=market,player_injury_status=np.nan) for market in markets]
        rows=publication_rows(pd.DataFrame(records),games,'v',datetime(2026,10,11,16,tzinfo=timezone.utc))
        self.assertEqual(len(rows),6)
        self.assertEqual({r[2] for r in rows},set(markets))
        for row in rows:
            payload=json.loads(row[-1])
            self.assertEqual(payload['probabilidad_pick'],.65)
            self.assertEqual(payload['estado_lesion'],'unknown')
            self.assertIs(payload['publicacion_utc'],True)

    def test_audit_ui_displays_breakdown_and_export(self):
        data=self.fixture()
        with patch('core.auditoria_nfl.receiving_audit',return_value=receiving_audit(data,data)):
            app=AppTest.from_string('from core.auditoria_nfl import render_receiving_audit\nrender_receiving_audit(None,None)').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe),3)
        self.assertEqual(len(app.get('download_button')),1)

    def test_prediction_pipeline_uses_frozen_model_and_existing_candidate_rules(self):
        import ast
        import tempfile
        from types import SimpleNamespace
        root=__import__('pathlib').Path(__file__).resolve().parents[1]
        nodes=[n for n in ast.parse((root/'nfl/predecir_props_semana_actual.py').read_text()).body
               if isinstance(n,ast.FunctionDef) and n.name in ['predecir_modelo','base_proyeccion',
                   'american_a_decimal','agregar_lineas_y_probabilidades','evaluar_dependencia_recepcion']]
        class FrozenModel:
            feature_names_in_=['teammate_skill_injury_score']
            def predict(self,frame):return 60+80*frame.teammate_skill_injury_score
        reports=pd.DataFrame([dict(season=2026,week=5,team='MIN',gsis_id='j',full_name='Jefferson',
                                   position='WR',report_status='Questionable',practice_status='Limited')])
        features=pd.DataFrame([dict(game_id='g',player_id='h',season=2026,week=5,team='MIN',
            position='TE',gameday='2026-10-11',player_name='Hockenson',player_injury_status='healthy_or_unlisted',
            contexto_lesiones='',teammate_skill_injury_score=.35,team_skill_injury_score=.35,
            team_skill_injury_count=1)])
        with tempfile.TemporaryDirectory() as folder:
            folder=__import__('pathlib').Path(folder)
            valid=folder/'validation.csv';config=folder/'config.json';resids=folder/'resids.npz'
            pd.DataFrame(dict(season=[2024]*100,objetivo=['receiving_yards']*100,position=['TE']*100,
                              error=np.arange(-50,50))).to_csv(valid,index=False)
            config.write_text('{}');np.savez(resids)
            context=dict(pd=pd,np=np,joblib=SimpleNamespace(load=lambda path:FrozenModel()),json=json,
                RUTA_MODELO_YARDAS='frozen',RUTA_VALIDACION=valid,RUTA_CALIBRACION_PC=config,RUTA_RESIDUOS_PC=resids,
                cargar_lesiones=lambda:reports)
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'pipeline','exec'),context)
            projections=context['base_proyeccion'](features)
            projections['tipo_prop']='receiving_yards';projections['proyeccion']=88
            projections['player_carries_avg_5']=0;projections['is_primary_rusher']=0
            lines=pd.DataFrame([dict(game_id='g',player_id='h',tipo_prop='receiving_yards',id_linea=1,
                                    linea=70,cuota_over=-110,cuota_under=-110,casa_apuestas='DraftKings')])
            base=context['agregar_lineas_y_probabilidades'](projections,lines)
            self.assertEqual(base.iloc[0].estado_pick,'CANDIDATO')
            final=context['evaluar_dependencia_recepcion'](base,features,lines)
            self.assertEqual(final.iloc[0].estado_pick,'REVISAR LESION')
            self.assertEqual(final.iloc[0].proyeccion,88)
            self.assertEqual(final.iloc[0].proyeccion_juegan,60)
            self.assertEqual(final.iloc[0].proyeccion_no_juegan,140)
