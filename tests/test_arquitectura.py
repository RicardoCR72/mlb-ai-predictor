from pathlib import Path
from datetime import datetime,timezone
from unittest import TestCase
from unittest.mock import patch,Mock
import os
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.comparador import normalize,VERIFIED,SAVED

ROOT=Path(__file__).resolve().parents[1]


def history_fixture():
    return normalize(pd.DataFrame([dict(id='g1',fecha='2026-10-01',modelo='v1',seleccion='OVER',linea=45.5,
        equipo_local='H',equipo_visitante='A',resultado='GANADA',probabilidad=.7,cuota=1.9,
        start_utc='2026-10-01T20:00:00Z')]),sport='NFL',market='Totales',identity=['id'],verified=True)


def nfl_fixture(prop=False):
    row=dict(id_juego='g',id_prediccion=1,id_proyeccion=1,id_jugador='p',modelo_version='v',id_linea=1,
        season=2099,week=6,gameday=pd.Timestamp('2099-10-11'),away_team='Arizona Cardinals',home_team='Seattle Seahawks',
        actualizado_en=pd.Timestamp('2026-10-01'),generado_en=pd.Timestamp('2026-10-01'),evaluado_en=pd.NaT,
        timestamp_captura=pd.Timestamp('2026-10-01'),resultado_pick='PENDIENTE',beneficio_unidades=float('nan'),
        total_line=45.5,pred_total=48.,pred_total_base=47.,edge=2.5,edge_absoluto=2.5,pick='OVER',
        prob_pick=.7,prob_over=.7,prob_under=.3,odds_pick=-110,ev=.1,estado='PICK',total_real=float('nan'),
        away_score=float('nan'),home_score=float('nan'),game_type='REG',
        tipo_prop='receptions',linea=4.5,proyeccion=6.,seleccion='OVER',probabilidad_pick=.7,
        probabilidad_over=.7,probabilidad_under=.3,cuota_pick=-110,ev_estimado=.1,estado_pick='CANDIDATO',
        player_name='Jugador de prueba',position='WR',team='ARI',estado_lesion='healthy',
        impacto_lesiones_companeros=0,contexto_lesiones='',valor_real=float('nan'),
        cuota_over=-110,cuota_under=-110,casa_apuestas='DraftKings',mercado='Recepciones')
    return pd.DataFrame([row])


class ArchitectureTests(TestCase):
    def test_real_nfl_routes_switch_market_history_and_injuries_without_writes(self):
        with patch('nfl.repositorio.cargar_props_mysql',return_value=nfl_fixture(True)), \
             patch('nfl.repositorio.cargar_predicciones_mysql',return_value=nfl_fixture()), \
             patch('core.ui_historial_publicado.load_history',return_value=(history_fixture(),[])), \
             patch('core.ui_trabajos.latest',return_value=None), \
             patch('streamlit.secrets',{}),patch('subprocess.run') as child:
            app=AppTest.from_file(str(ROOT/'pages/2_🏈_NFL.py')).run()
            self.assertFalse(app.exception)
            next(r for r in app.radio if r.label=='Sección de totales').set_value('📈 Rendimiento').run()
            self.assertFalse(app.exception)
            next(r for r in app.radio if r.label=='Sección NFL').set_value('📊 Props de jugadores').run()
            self.assertFalse(app.exception)
            next(r for r in app.radio if r.label=='Sección de props').set_value('🏥 Lesiones').run()
            self.assertFalse(app.exception)
            next(r for r in app.radio if r.label=='Sección de props').set_value('📈 Rendimiento').run()
            self.assertFalse(app.exception)
            child.assert_not_called()

    def test_unknown_service_never_connects_or_spawns(self):
        from core import trabajos
        with patch.object(trabajos,'get_db_connection') as db, \
             patch.object(trabajos.EXECUTOR,'submit') as child:
            with self.assertRaises(ValueError):trabajos.submit('unknown')
            db.assert_not_called();child.assert_not_called()

    def test_update_button_submits_without_login_and_respects_disabled(self):
        with patch('core.ui_trabajos.submit',return_value='job') as submit, \
             patch('core.ui_trabajos.latest',return_value=None):
            app=AppTest.from_string("from core.ui_trabajos import action_button\naction_button('mlb','Actualizar resultados',key='update')\naction_button('nfl_predictions','Sin juegos',key='empty',disabled=True)").run()
            self.assertFalse(app.exception)
            self.assertFalse(app.button[0].disabled)
            self.assertTrue(app.button[1].disabled)
            submit.assert_not_called()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            submit.assert_called_once_with('mlb',payload=None)

    def test_history_and_calibration_share_original_but_keep_push_semantics(self):
        from core import confianza_datos as data
        base=normalize(pd.DataFrame(),sport='MLB',market='Moneyline',identity=['id'])
        totals=pd.DataFrame([dict(candidato=1,recorded_utc='2026-10-01T18:00Z',quote_captured_utc='2026-10-01T17:00Z',
            start_utc='2026-10-01T20:00Z',p_push=.1,confianza=.54,fecha_oficial='2026-10-01',model_id='m',
            cuota_seleccion=2,game_pk=1,resultado='GANADA',seleccion='OVER',linea=8.5)])
        with patch.object(data,'read_models',return_value=(base,[])),patch.object(data,'rows',return_value=pd.DataFrame()), \
             patch.object(data.registro,'history',return_value=totals),patch.object(data.registro,'settle',side_effect=lambda f:f):
            performance,_=data.read_history(Mock(),ROOT,include_liga=False)
            calibration,_=data.read_history(Mock(),ROOT,calibration=True,include_liga=False)
        self.assertAlmostEqual(performance.probabilidad.iloc[0],.54)
        self.assertAlmostEqual(calibration.probabilidad.iloc[0],.6)
        self.assertEqual(performance.identidad.tolist(),calibration.identidad.tolist())

    def test_original_props_replace_updated_line_and_result(self):
        from core import confianza_datos as data
        legacy=normalize(pd.DataFrame([dict(id_juego='g',id_jugador='p',tipo_prop='receiving_yards',
            mercado='receiving_yards',fecha='2026-10-01',modelo='v',probabilidad=.99,cuota=-110,resultado='GANADA')]),
            sport='NFL',market=None,identity=['id_juego','id_jugador','tipo_prop'],american=True)
        def query(conn,sql):
            if 'nfl_publicaciones_props' in sql:
                return pd.DataFrame([dict(id_juego='g',id_jugador='p',tipo_prop='receiving_yards',modelo='v',fecha='2026-10-01',
                    publicada_en='2026-10-01T18:00Z',valor_real=40,payload=dict(linea=50.5,seleccion='OVER',
                    probabilidad_pick=.7,cuota_pick=-110,estado_pick='CANDIDATO',publicacion_utc=True))])
            return pd.DataFrame()
        with patch.object(data,'read_models',return_value=(legacy,[])),patch.object(data,'rows',side_effect=query), \
             patch.object(data.registro,'history',return_value=pd.DataFrame()), \
             patch.object(data,'nfl_starts',return_value={'g':pd.Timestamp('2026-10-01T20:00Z')}):
            frame,_=data.read_history(Mock(),ROOT,include_liga=False)
        row=frame[frame.deporte.eq('NFL') & frame.mercado.eq('Yardas de recepción')].iloc[0]
        self.assertEqual(len(frame),1);self.assertEqual(row.resultado,'PERDIDA')
        self.assertEqual(row.linea,50.5);self.assertEqual(row.probabilidad,.7)
        self.assertEqual(row.valor_real,40)
        self.assertEqual(row.procedencia,VERIFIED)

    def test_readonly_history_does_not_import_tensorflow_and_empty_is_not_zero_roi(self):
        f=history_fixture();f['deporte']='MLB';f['mercado']='Moneyline'
        with patch('core.ui_historial_publicado.load_history',return_value=(f,[])), \
             patch('core.ui_trabajos.latest',return_value=None), \
             patch('subprocess.run') as child:
            app=AppTest.from_file(str(ROOT/'pages/1_⚾_MLB.py')).run()
            next(r for r in app.radio if r.label=='Sección MLB').set_value('Rendimiento').run()
            self.assertFalse(app.exception)
            self.assertEqual(next(m for m in app.metric if m.label=='Picks evaluados').value,'1')
            self.assertEqual(next(m for m in app.metric if m.label=='ROI').value,'+90.0%')
            self.assertTrue(all(not b.disabled for b in app.button if 'resultados' in b.label or 'Generar' in b.label))
            self.assertFalse(any(e.label=='Acceso administrativo' for e in app.expander))
            child.assert_not_called()
        with patch('core.ui_historial_publicado.load_history',return_value=(f.iloc[:0],[])):
            empty=AppTest.from_string("from core.ui_historial_publicado import render_history\nrender_history('MLB','Moneyline',key='empty')").run()
            self.assertFalse(empty.exception);self.assertFalse(empty.metric)

    def test_job_state_comes_from_persistent_record_after_session_reset(self):
        job=dict(id='job-1',estado='completada',creado_utc='2026-10-01 18:00:00',iniciado_utc=None,
            terminado_utc='2026-10-01 18:01:00',resultado=dict(detalle='Resultados guardados'))
        with patch('core.ui_trabajos.latest',return_value=job),patch('core.ui_trabajos.invalidate_readers'):
            app=AppTest.from_string("from core.ui_trabajos import render_job\nrender_job('mlb')").run()
            self.assertFalse(app.exception)
            self.assertTrue(any('completada' in c.value for c in app.caption))
            # Otra sesión sin ningún estado de la solicitud puede consultar la misma ejecución.
            other=AppTest.from_string("from core.ui_trabajos import render_job\nrender_job('mlb')").run()
            self.assertFalse(other.exception)
            self.assertTrue(any('Resultados guardados' in c.value for c in other.caption))

    def test_views_use_one_stylesheet_and_operational_day_is_cdmx(self):
        from core.constants import ZONA_MX,ZONA_CDMX
        from core.ui_diseno import CSS
        from core.ui_movil import CSS as mobile
        self.assertEqual(CSS,mobile)
        stamp=datetime(2026,10,18,6,30,tzinfo=timezone.utc)
        self.assertEqual(stamp.astimezone(ZONA_MX).date(),stamp.astimezone(ZONA_CDMX).date())
        for page in (ROOT/'pages').glob('*.py'):
            self.assertNotIn('<style>',page.read_text(encoding='utf-8', errors='replace'),str(page))
