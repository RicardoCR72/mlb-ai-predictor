"""Servicio de generacion Moneyline V5.0: Ensamble (LightGBM + Red Neuronal) + Sabermetria Nativa + Filtro Zona Muerta."""
from pathlib import Path
from datetime import datetime
import json
import pandas as pd
import numpy as np
import joblib
from core.constants import ZONA_MX, MLB_TEAMS_ABBR, MLB_STADIUM_TIMEZONES
from core.db import get_db_connection
from mlb.publicaciones_moneyline import prepare as prepare_moneyline, TODAY_SQL, save as save_moneyline, fingerprint

RAIZ = Path(__file__).resolve().parents[1]
RUTA_MODELOS_MLB = RAIZ / 'modelos_mlb'
RUTA_DATA_MLB = RAIZ / 'data/mlb'
MAPEO_EQUIPOS = MLB_TEAMS_ABBR
ZONAS_HORARIAS = MLB_STADIUM_TIMEZONES


def hoy_mx():
    return datetime.now(ZONA_MX).date()


class EnsambleMLBv5:
    """Ensamble Blended de LightGBM + Red Neuronal Densa + Calibracion Isotonica."""
    def __init__(self, modelo_nn, modelo_lgb, calibrador, scaler, columnas, peso_lgb=0.60, peso_nn=0.40):
        self.modelo_nn = modelo_nn
        self.modelo_lgb = modelo_lgb
        self.calibrador = calibrador
        self.scaler = scaler
        self.columnas = columnas
        self.peso_lgb = peso_lgb
        self.peso_nn = peso_nn
        self.version = "V5.0 Ensamble (LightGBM + DNN + Isotonic)"

    def get_weights(self):
        return self.modelo_nn.get_weights()

    def predict(self, vars_input, verbose=0):
        """Retorna probabilidades calibradas en formato shape (N, 1) para compatibilidad."""
        if isinstance(vars_input, pd.DataFrame):
            df_x = vars_input[self.columnas]
            vars_scaled = self.scaler.transform(df_x)
        else:
            df_x = pd.DataFrame(vars_input, columns=self.columnas)
            vars_scaled = vars_input

        # 1. Prediccion de arboles de gradiente LightGBM
        p_lgb = self.modelo_lgb.predict(df_x)
        if hasattr(p_lgb, 'ndim') and p_lgb.ndim > 1:
            p_lgb = p_lgb[:, 1]

        # 2. Prediccion de Red Neuronal Profunda
        p_nn = self.modelo_nn.predict(vars_scaled, verbose=0).flatten()

        # 3. Ensamble Ponderado Blended
        p_raw = (self.peso_lgb * p_lgb) + (self.peso_nn * p_nn)

        # 4. Calibracion Isotonica Post-Entrenamiento
        p_cal = self.calibrador.predict(p_raw)

        return np.array([[float(p)] for p in p_cal])


def cargar_oraculo():
    """Carga el Ensamble V5.0 de forma prioritaria con fallback de seguridad a V4."""
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Dense, Dropout, BatchNormalization, Input
    try:
        ruta_lgb_v5 = RUTA_MODELOS_MLB / 'modelo_lgb_v5.pkl'
        ruta_pesos_v5 = RUTA_MODELOS_MLB / 'pesos_mlb_v5.weights.h5'
        ruta_cal_v5 = RUTA_MODELOS_MLB / 'calibrador_v5.pkl'
        ruta_scaler_v5 = RUTA_MODELOS_MLB / 'scaler_v5.pkl'
        ruta_cols_v5 = RUTA_MODELOS_MLB / 'columnas_v5.pkl'

        if ruta_lgb_v5.exists() and ruta_pesos_v5.exists() and ruta_cal_v5.exists():
            columnas_v5 = joblib.load(ruta_cols_v5)
            scaler_v5 = joblib.load(ruta_scaler_v5)
            modelo_lgb = joblib.load(ruta_lgb_v5)
            calibrador_v5 = joblib.load(ruta_cal_v5)

            modelo_nn = Sequential([
                Input(shape=(len(columnas_v5),)),
                Dense(64, activation='relu'),
                Dropout(0.25),
                BatchNormalization(),
                Dense(32, activation='relu'),
                Dropout(0.20),
                Dense(16, activation='relu'),
                Dropout(0.15),
                Dense(1, activation='sigmoid')
            ])
            modelo_nn.load_weights(str(ruta_pesos_v5))

            ensamble = EnsambleMLBv5(modelo_nn, modelo_lgb, calibrador_v5, scaler_v5, columnas_v5)
            return (ensamble, scaler_v5, columnas_v5)

        # Fallback historico V4 si no se encuentran los artefactos V5
        modelo = Sequential([
            Input(shape=(18,)),
            Dense(64, activation='relu'),
            Dropout(0.3),
            Dense(32, activation='relu'),
            Dropout(0.2),
            Dense(16, activation='relu'),
            Dropout(0.2),
            Dense(1, activation='sigmoid')
        ])
        modelo.load_weights(str(RUTA_MODELOS_MLB / 'pesos_mlb_v4.weights.h5'))
        scaler = joblib.load(RUTA_MODELOS_MLB / 'scaler_v4.pkl')
        columnas_v4 = joblib.load(RUTA_MODELOS_MLB / 'columnas_v4.pkl')
        return (modelo, scaler, columnas_v4)
    except Exception:
        raise RuntimeError("El modelo Moneyline no esta disponible.") from None


def conectar_bd():
    return get_db_connection()


def normalizar_equipo(nombre):
    return MAPEO_EQUIPOS.get(nombre, nombre)


def cargar_datos_hoy():
    conexion = conectar_bd()
    try:
        prepare_moneyline(conexion)
        df = pd.read_sql(TODAY_SQL, conexion, params=(hoy_mx(),))
    finally:
        conexion.close()
    if not df.empty:
        df = df.drop_duplicates(subset=['id_juego'], keep='last').reset_index(drop=True)
    return df


def obtener_estado_actual(equipo, df_hist, fecha_objetivo=None):
    if fecha_objetivo is None:
        fecha_objetivo = hoy_mx()
    else:
        fecha_objetivo = pd.to_datetime(fecha_objetivo).date()
    df_hist_copy = df_hist.copy()
    df_hist_copy['fecha_solo_dia'] = pd.to_datetime(df_hist_copy['fecha']).dt.date
    df_equipo = df_hist_copy[((df_hist_copy['equipo_local'] == equipo) | (df_hist_copy['equipo_visitante'] == equipo)) & (df_hist_copy['fecha_solo_dia'] < fecha_objetivo)].sort_values('fecha_solo_dia')
    if df_equipo.empty:
        return (0.5, 0, 3, 0.5, equipo, 0)
    juegos_jugados = len(df_equipo)
    victorias = 0
    carreras_anotadas = 0
    carreras_recibidas = 0
    ultimos_5 = []
    juegos_ultimos_7d = 0
    for _, row in df_equipo.iterrows():
        es_local = row['equipo_local'] == equipo
        runs_fav = row['marcador_local'] if es_local else row['marcador_visitante']
        runs_con = row['marcador_visitante'] if es_local else row['marcador_local']
        carreras_anotadas += runs_fav
        carreras_recibidas += runs_con
        gano = 1 if runs_fav > runs_con else 0
        victorias += gano
        ultimos_5.append(gano)
        dias_dif = (fecha_objetivo - row['fecha_solo_dia']).days
        if dias_dif <= 7:
            juegos_ultimos_7d += 1

    win_pct = victorias / juegos_jugados
    run_diff = carreras_anotadas - carreras_recibidas
    racha_5 = np.mean(ultimos_5[-5:]) if len(ultimos_5) > 0 else 0.5
    fecha_ultimo = df_equipo.iloc[-1]['fecha_solo_dia']
    estadio_anterior = df_equipo.iloc[-1]['equipo_local']
    descanso = (fecha_objetivo - fecha_ultimo).days
    return (win_pct, run_diff, descanso, racha_5, estadio_anterior, juegos_ultimos_7d)


def limpiar_cuotas_v4(cuota_l_raw, cuota_v_raw):
    def to_decimal(val):
        if val <= -100:
            return 100 / abs(val) + 1
        elif val >= 100:
            return val / 100 + 1
        return val
    c_l = to_decimal(float(cuota_l_raw))
    c_v = to_decimal(float(cuota_v_raw))
    if c_l <= 1 or c_v <= 1:
        return (0.5, 0.5)
    prob_l_cruda = 1 / c_l
    prob_v_cruda = 1 / c_v
    overround = prob_l_cruda + prob_v_cruda
    return (prob_l_cruda / overround, prob_v_cruda / overround)


def cargar_metricas_avanzadas():
    conexion = conectar_bd()
    try:
        return pd.read_sql('SELECT equipo, ops_vs_zurdo, ops_vs_derecho, era_bullpen_7d FROM metricas_equipos WHERE fecha = (SELECT MAX(fecha) FROM metricas_equipos)', conexion)
    finally:
        conexion.close()


def cargar_lesiones_hoy():
    conexion = conectar_bd()
    try:
        return pd.read_sql('SELECT equipo, impacto_total FROM factor_lesiones WHERE fecha = (SELECT MAX(fecha) FROM factor_lesiones)', conexion)
    finally:
        conexion.close()


def aplicar_filtro_medico(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_lesiones):
    if df_lesiones.empty:
        return confianza_base
    imp_l = df_lesiones.loc[df_lesiones['equipo'] == equipo_local, 'impacto_total'].values
    imp_v = df_lesiones.loc[df_lesiones['equipo'] == equipo_visitante, 'impacto_total'].values
    impacto_local = imp_l[0] if len(imp_l) > 0 else 0
    impacto_visita = imp_v[0] if len(imp_v) > 0 else 0
    ajuste = impacto_local - impacto_visita if equipo_elegido == equipo_local else impacto_visita - impacto_local
    confianza_final = confianza_base + ajuste
    return max(50.1, min(99.0, round(confianza_final, 1)))


def cargar_pitchers_hoy():
    """Carga metricas sabermetricas completas V5 de abridores con fallback a V4."""
    conexion = conectar_bd()
    try:
        cursor = conexion.cursor()
        cursor.execute("SHOW COLUMNS FROM abridores")
        cols = {c[0].lower() for c in cursor.fetchall()}
        cursor.close()

        if 'fip' in cols and 'k_bb_pct' in cols:
            sql = """
                SELECT equipo, nombre_pitcher, era, era_ultimas_3,
                       COALESCE(whip_ultimas_3, 1.30) AS whip_ultimas_3,
                       COALESCE(fip, 4.20) AS fip,
                       COALESCE(xfip, 4.20) AS xfip,
                       COALESCE(k_bb_pct, 0.14) AS k_bb_pct,
                       COALESCE(mano, 'R') AS mano
                FROM abridores
                WHERE fecha = (SELECT MAX(fecha) FROM abridores)
            """
        else:
            sql = "SELECT equipo, nombre_pitcher, era, era_ultimas_3 FROM abridores WHERE fecha = (SELECT MAX(fecha) FROM abridores)"
        return pd.read_sql(sql, conexion)
    finally:
        conexion.close()


def aplicar_filtro_pitchers(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_pitchers, es_v5=True):
    """En V5, los pitchers estan integrados NATIVAMENTE en la IA (sin doble conteo manual)."""
    if df_pitchers.empty:
        return (confianza_base, 'TBD', 'TBD')

    def obtener_datos(equipo):
        row = df_pitchers[df_pitchers['equipo'] == equipo]
        if row.empty:
            return 4.20, 4.20, 0.14, 1.30, 'R', 'Por anunciar'
        era_3 = row['era_ultimas_3'].values[0] if 'era_ultimas_3' in row else 4.20
        era_g = row['era'].values[0] if 'era' in row else 4.20
        era_eff = float(era_3) if pd.notna(era_3) and float(era_3) > 0 else float(era_g)
        fip_v = float(row['fip'].values[0]) if 'fip' in row and pd.notna(row['fip'].values[0]) else 4.20
        kbb_v = float(row['k_bb_pct'].values[0]) if 'k_bb_pct' in row and pd.notna(row['k_bb_pct'].values[0]) else 0.14
        whip_v = float(row['whip_ultimas_3'].values[0]) if 'whip_ultimas_3' in row and pd.notna(row['whip_ultimas_3'].values[0]) else 1.30
        mano_v = str(row['mano'].values[0]) if 'mano' in row and pd.notna(row['mano'].values[0]) else 'R'
        nom = row['nombre_pitcher'].values[0] if 'nombre_pitcher' in row and pd.notna(row['nombre_pitcher'].values[0]) else 'Por anunciar'
        return era_eff, fip_v, kbb_v, whip_v, mano_v, nom

    era_l, fip_l, kbb_l, whip_l, mano_l, nom_l = obtener_datos(equipo_local)
    era_v, fip_v, kbb_v, whip_v, mano_v, nom_v = obtener_datos(equipo_visitante)

    if es_v5:
        # En V5, la red y LightGBM ya aprendieron la ventaja del pitcher de forma nativa
        confianza_final = confianza_base
    else:
        ventaja = era_v - era_l if equipo_elegido == equipo_local else era_l - era_v
        confianza_final = confianza_base + ventaja * 2.5

    p_local_desc = f"{nom_l} ({mano_l}HP | FIP {fip_l:.2f} | K-BB% {kbb_l:.1%})"
    p_visita_desc = f"{nom_v} ({mano_v}HP | FIP {fip_v:.2f} | K-BB% {kbb_v:.1%})"
    return (max(50.1, min(99.0, round(confianza_final, 1))), p_local_desc, p_visita_desc)


def fusionar_historiales(df_csv, df_xampp):
    df_memoria = df_csv.copy()
    if df_xampp.empty:
        return df_memoria
    df_xampp = df_xampp.sort_values(by='fecha').reset_index(drop=True)
    for i in range(len(df_xampp)):
        local = df_xampp.loc[i, 'Equipo Local']
        visita = df_xampp.loc[i, 'Equipo Visitante']
        fecha_juego = df_xampp.loc[i, 'fecha']
        marcador_l = df_xampp.loc[i, 'marcador_local']
        marcador_v = df_xampp.loc[i, 'marcador_visitante']
        nueva_fila = pd.DataFrame([{'fecha': fecha_juego, 'equipo_local': local, 'equipo_visitante': visita, 'marcador_local': marcador_l, 'marcador_visitante': marcador_v}])
        df_memoria = pd.concat([df_memoria, nueva_fila], ignore_index=True)
    return df_memoria


def cargar_historial_xampp():
    conexion = conectar_bd()
    consulta = "\n        SELECT j.fecha, j.equipo_local AS 'Equipo Local', j.equipo_visitante AS 'Equipo Visitante',\n               j.marcador_local, j.marcador_visitante,\n               MAX(c.cuota_local) AS 'Paga Local', MAX(c.cuota_visitante) AS 'Paga Visitante'\n        FROM juegos j\n        JOIN cuotas_moneyline c ON j.id_juego = c.id_juego\n        WHERE j.marcador_local IS NOT NULL AND j.marcador_visitante IS NOT NULL\n          AND DATE(j.fecha) <= %s\n        GROUP BY j.id_juego ORDER BY j.fecha ASC\n    "
    df = pd.read_sql(consulta, conexion, params=(hoy_mx(),))
    conexion.close()
    if not df.empty:
        df['solo_fecha'] = pd.to_datetime(df['fecha']).dt.date
        df = df.drop_duplicates(subset=['solo_fecha', 'Equipo Local', 'Equipo Visitante'], keep='last')
        df = df.drop(columns=['solo_fecha']).reset_index(drop=True)
    return df


def guardar_pick_ia(fecha, equipo_local, equipo_visitante, pick_ia, confianza, cuota, *, game_id, model_id, home_odds, away_odds):
    """Conserva el original verificable y mantiene el registro de compatibilidad."""
    conexion = None
    cursor = None
    try:
        conexion = conectar_bd()
        saved = save_moneyline(conexion, game_id=game_id, model_id=model_id, day=fecha, home=equipo_local, away=equipo_visitante, pick=pick_ia, confidence=confianza, home_odds=home_odds, away_odds=away_odds)
        if not saved:
            return
        cursor = conexion.cursor()
        cursor.execute('\n            INSERT INTO registro_picks_ia (fecha, equipo_local, equipo_visitante, pick_ia, confianza, cuota)\n            VALUES (%s, %s, %s, %s, %s, %s)\n            ON DUPLICATE KEY UPDATE fecha = registro_picks_ia.fecha\n        ', (fecha, equipo_local, equipo_visitante, pick_ia, float(confianza), float(cuota)))
        conexion.commit()
    except Exception:
        if conexion is not None:
            conexion.rollback()
        raise RuntimeError("No se pudo guardar la publicacion Moneyline.") from None
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None:
            conexion.close()


def generate():
    modelo, scaler, columnas_activas = cargar_oraculo()
    df = cargar_datos_hoy()
    if df.empty:
        return 0

    es_v5 = len(columnas_activas) > 18
    df_csv_estatico = pd.read_csv(RUTA_DATA_MLB / 'mlb_dataset_ia.csv')
    df_hist = fusionar_historiales(df_csv_estatico, cargar_historial_xampp())
    df_metricas_adv = cargar_metricas_avanzadas()
    version_moneyline = fingerprint(modelo, scaler, columnas_activas, [limpiar_cuotas_v4, aplicar_filtro_medico, aplicar_filtro_pitchers])
    df_lesiones_hoy = cargar_lesiones_hoy()
    df_pitchers_hoy = cargar_pitchers_hoy()

    resultados = []
    apuestas_publicadas = 0

    for i in range(len(df)):
        local_api = df.loc[i, 'Equipo Local']
        visita_api = df.loc[i, 'Equipo Visitante']

        local = normalizar_equipo(local_api)
        visita = normalizar_equipo(visita_api)

        # 1. Rendimiento Basico, Desgaste y Fatiga de Bullpen (7 dias)
        res_l = obtener_estado_actual(local, df_hist)
        res_v = obtener_estado_actual(visita, df_hist)
        w_l, d_l, desc_l, r5_l, est_ant_l, j7_l = res_l
        w_v, d_v, desc_v, r5_v, est_ant_v, j7_v = res_v

        # 2. Desgaste por Viaje (Jetlag)
        zona_estadio_hoy = ZONAS_HORARIAS.get(local, -5)
        zona_ant_l = ZONAS_HORARIAS.get(normalizar_equipo(est_ant_l), -5)
        zona_ant_v = ZONAS_HORARIAS.get(normalizar_equipo(est_ant_v), -5)
        jetlag_l = abs(zona_estadio_hoy - zona_ant_l)
        jetlag_v = abs(zona_estadio_hoy - zona_ant_v)

        # 3. Metricas Avanzadas de Bullpen y Splits de Bateo Reales
        met_l = df_metricas_adv[df_metricas_adv['equipo'] == local_api]
        met_v = df_metricas_adv[df_metricas_adv['equipo'] == visita_api]

        ops_l_t = float(met_l['ops_vs_zurdo'].values[0]) if not met_l.empty else 0.720
        ops_r_t = float(met_l['ops_vs_derecho'].values[0]) if not met_l.empty else 0.730
        era_bp_l = float(met_l['era_bullpen_7d'].values[0]) if not met_l.empty else 4.15

        ops_l_o = float(met_v['ops_vs_zurdo'].values[0]) if not met_v.empty else 0.720
        ops_r_o = float(met_v['ops_vs_derecho'].values[0]) if not met_v.empty else 0.730
        era_bp_v = float(met_v['era_bullpen_7d'].values[0]) if not met_v.empty else 4.15

        fatiga_bp_l = min(1.0, float(j7_l) / 7.0)
        fatiga_bp_v = min(1.0, float(j7_v) / 7.0)

        # 4. Metricas Sabermetricas de Abridores (FIP, xFIP, K-BB%, WHIP 3, ERA 3)
        row_p_l = df_pitchers_hoy[df_pitchers_hoy['equipo'] == local_api]
        row_p_v = df_pitchers_hoy[df_pitchers_hoy['equipo'] == visita_api]

        def extraer_pitcher_metrics(row_p):
            if row_p.empty:
                return {'era_3': 4.20, 'fip': 4.20, 'xfip': 4.20, 'k_bb': 0.14, 'whip_3': 1.30, 'mano': 'R'}
            return {
                'era_3': float(row_p['era_ultimas_3'].values[0]) if pd.notna(row_p['era_ultimas_3'].values[0]) and float(row_p['era_ultimas_3'].values[0]) > 0 else float(row_p['era'].values[0]),
                'fip': float(row_p['fip'].values[0]) if 'fip' in row_p and pd.notna(row_p['fip'].values[0]) else 4.20,
                'xfip': float(row_p['xfip'].values[0]) if 'xfip' in row_p and pd.notna(row_p['xfip'].values[0]) else 4.20,
                'k_bb': float(row_p['k_bb_pct'].values[0]) if 'k_bb_pct' in row_p and pd.notna(row_p['k_bb_pct'].values[0]) else 0.14,
                'whip_3': float(row_p['whip_ultimas_3'].values[0]) if 'whip_ultimas_3' in row_p and pd.notna(row_p['whip_ultimas_3'].values[0]) else 1.30,
                'mano': str(row_p['mano'].values[0]) if 'mano' in row_p and pd.notna(row_p['mano'].values[0]) else 'R'
            }

        sp_l = extraer_pitcher_metrics(row_p_l)
        sp_v = extraer_pitcher_metrics(row_p_v)

        # Split vs mano del abridor rival
        ops_vs_mano_team = ops_l_t if sp_v['mano'] == 'L' else ops_r_t
        ops_vs_mano_opp = ops_l_o if sp_l['mano'] == 'L' else ops_r_o

        # Ventajas de abridor
        ventaja_fip = sp_v['fip'] - sp_l['fip']
        ventaja_k_bb = sp_l['k_bb'] - sp_v['k_bb']
        ventaja_whip = sp_v['whip_3'] - sp_l['whip_3']

        # 5. Desparasitar Cuotas
        prob_p_l, prob_p_v = limpiar_cuotas_v4(df.loc[i, 'Paga Local'], df.loc[i, 'Paga Visitante'])

        if es_v5:
            fila_dic = {
                'win_pct_team': w_l, 'win_pct_opp': w_v,
                'run_diff_team': d_l, 'run_diff_opp': d_v,
                'dias_descanso_team': desc_l, 'dias_descanso_opp': desc_v,
                'racha_5_team': r5_l, 'racha_5_opp': r5_v,
                'jetlag_team': jetlag_l, 'jetlag_opp': jetlag_v,
                'ops_vs_mano_team': ops_vs_mano_team, 'ops_vs_mano_opp': ops_vs_mano_opp,
                'era_bullpen_team': era_bp_l, 'era_bullpen_opp': era_bp_v,
                'fatiga_bullpen_team': fatiga_bp_l, 'fatiga_bullpen_opp': fatiga_bp_v,
                'fip_team': sp_l['fip'], 'fip_opp': sp_v['fip'],
                'xfip_team': sp_l['xfip'], 'xfip_opp': sp_v['xfip'],
                'k_bb_team': sp_l['k_bb'], 'k_bb_opp': sp_v['k_bb'],
                'whip_reciente_team': sp_l['whip_3'], 'whip_reciente_opp': sp_v['whip_3'],
                'ventaja_fip': ventaja_fip, 'ventaja_k_bb': ventaja_k_bb,
                'ventaja_whip_reciente': ventaja_whip,
                'prob_pure_team': prob_p_l, 'prob_pure_opp': prob_p_v
            }
        else:
            fila_dic = {
                'win_pct_team': w_l, 'win_pct_opp': w_v,
                'run_diff_team': d_l, 'run_diff_opp': d_v,
                'dias_descanso_team': desc_l, 'dias_descanso_opp': desc_v,
                'racha_5_team': r5_l, 'racha_5_opp': r5_v,
                'jetlag_team': jetlag_l, 'jetlag_opp': jetlag_v,
                'ops_l_team': ops_l_t, 'ops_r_team': ops_r_t, 'era_bullpen_team': era_bp_l,
                'ops_l_opp': ops_l_o, 'ops_r_opp': ops_r_o, 'era_bullpen_opp': era_bp_v,
                'prob_pure_team': prob_p_l, 'prob_pure_opp': prob_p_v
            }

        fila_ia = pd.DataFrame([fila_dic])[columnas_activas]

        # 6. Prediccion de la Inteligencia Artificial
        if hasattr(modelo, 'predict'):
            if es_v5 and isinstance(modelo, EnsambleMLBv5):
                prob_local = float(modelo.predict(fila_ia, verbose=0)[0][0] * 100)
            else:
                vars_escaladas = scaler.transform(fila_ia)
                prob_local = float(modelo.predict(vars_escaladas, verbose=0)[0][0] * 100)
        else:
            prob_local = 50.0

        prob_visitante = 100.0 - prob_local
        favorito = local_api if prob_local > 50 else visita_api
        confianza_base = max(prob_local, prob_visitante)
        paga = df.loc[i, 'Paga Local'] if prob_local > 50 else df.loc[i, 'Paga Visitante']
        prob_justa_fav = prob_p_l if prob_local > 50 else prob_p_v

        # Filtros de ajuste contextual
        confianza_medica = aplicar_filtro_medico(favorito, confianza_base, local_api, visita_api, df_lesiones_hoy)
        confianza_final, p_local_desc, p_visita_desc = aplicar_filtro_pitchers(
            favorito, confianza_medica, local_api, visita_api, df_pitchers_hoy, es_v5=es_v5
        )

        # 7. POLITICA DE APUESTAS Y FILTRO DE LA ZONA MUERTA (55% - 65%)
        # En la zona media (55-65%), solo se apuesta si Edge >= +4.5% para evitar el margen de la casa (-6.6% ROI)
        edge_matematico = (confianza_final / 100.0) - prob_justa_fav
        es_zona_muerta = (55.0 <= confianza_final < 65.0)
        es_alta_confianza = (confianza_final >= 65.0)

        aprobado_apuesta = True
        motivo_filtro = "Aprobado (Alta Conviccion)" if es_alta_confianza else "Aprobado (Edge >= +4.5%)"

        if es_zona_muerta:
            if edge_matematico < 0.045:
                aprobado_apuesta = False
                motivo_filtro = f"Zona Muerta (55-65%) con Edge insuficiente ({edge_matematico*100:+.1f}% < +4.5%) - NO APOSTAR"
        elif not es_alta_confianza:
            aprobado_apuesta = False
            motivo_filtro = f"Confianza insuficiente ({confianza_final:.1f}% < 55%)"

        if aprobado_apuesta:
            guardar_pick_ia(
                pd.Timestamp(df.loc[i, "Fecha"]).date(), local_api, visita_api, favorito, confianza_final, paga,
                game_id=df.loc[i, "id_juego"], model_id=version_moneyline,
                home_odds=df.loc[i, "Paga Local"], away_odds=df.loc[i, "Paga Visitante"]
            )
            apuestas_publicadas += 1

        resultados.append({
            "id_juego": df.loc[i, "id_juego"],
            "Modelo": version_moneyline,
            "Fecha": df.loc[i, "Fecha"],
            "Partido": f"{local_api} vs {visita_api}",
            "Abridores": f"{p_local_desc} vs {p_visita_desc}",
            "Pick de la IA": favorito,
            "Confianza (%)": confianza_final,
            "Edge (%)": round(edge_matematico * 100, 1),
            "Paga del Favorito": paga,
            "Estado": "APROBADO" if aprobado_apuesta else "FILTRADO / ZONA MUERTA",
            "Detalle Filtro": motivo_filtro
        })

    return apuestas_publicadas
