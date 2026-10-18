"""Servicio de generación Moneyline; solo se ejecuta por una acción explícita o CLI."""
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import joblib
from core.constants import ZONA_MX,MLB_TEAMS_ABBR,MLB_STADIUM_TIMEZONES
from core.db import get_db_connection
from mlb.publicaciones_moneyline import prepare as prepare_moneyline,TODAY_SQL,save as save_moneyline,fingerprint
RAIZ=Path(__file__).resolve().parents[1]
RUTA_MODELOS_MLB=RAIZ/'modelos_mlb'
RUTA_DATA_MLB=RAIZ/'data/mlb'
MAPEO_EQUIPOS=MLB_TEAMS_ABBR
ZONAS_HORARIAS=MLB_STADIUM_TIMEZONES


def hoy_mx():
    return datetime.now(ZONA_MX).date()

def cargar_oraculo():
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Dense, Dropout, Input
    try:
        modelo = Sequential([Input(shape=(18,)), Dense(64, activation='relu'), Dropout(0.3), Dense(32, activation='relu'), Dropout(0.2), Dense(16, activation='relu'), Dropout(0.2), Dense(1, activation='sigmoid')])
        modelo.load_weights(str(RUTA_MODELOS_MLB / 'pesos_mlb_v4.weights.h5'))
        scaler = joblib.load(RUTA_MODELOS_MLB / 'scaler_v4.pkl')
        columnas_v4 = joblib.load(RUTA_MODELOS_MLB / 'columnas_v4.pkl')
        return (modelo, scaler, columnas_v4)
    except Exception as e:
        raise RuntimeError("El modelo Moneyline no está disponible.") from None
        return (None, None, None)

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
        return (0.5, 0, 3, 0.5, equipo)
    juegos_jugados = len(df_equipo)
    victorias = 0
    carreras_anotadas = 0
    carreras_recibidas = 0
    ultimos_5 = []
    for _, row in df_equipo.iterrows():
        es_local = row['equipo_local'] == equipo
        runs_fav = row['marcador_local'] if es_local else row['marcador_visitante']
        runs_con = row['marcador_visitante'] if es_local else row['marcador_local']
        carreras_anotadas += runs_fav
        carreras_recibidas += runs_con
        gano = 1 if runs_fav > runs_con else 0
        victorias += gano
        ultimos_5.append(gano)
    win_pct = victorias / juegos_jugados
    run_diff = carreras_anotadas - carreras_recibidas
    racha_5 = np.mean(ultimos_5[-5:]) if len(ultimos_5) > 0 else 0.5
    fecha_ultimo = df_equipo.iloc[-1]['fecha_solo_dia']
    estadio_anterior = df_equipo.iloc[-1]['equipo_local']
    descanso = (fecha_objetivo - fecha_ultimo).days
    return (win_pct, run_diff, descanso, racha_5, estadio_anterior)

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
    conexion=conectar_bd()
    try:return pd.read_sql('SELECT equipo, ops_vs_zurdo, ops_vs_derecho, era_bullpen_7d FROM metricas_equipos WHERE fecha = (SELECT MAX(fecha) FROM metricas_equipos)',conexion)
    finally:conexion.close()

def cargar_lesiones_hoy():
    conexion=conectar_bd()
    try:return pd.read_sql('SELECT equipo, impacto_total FROM factor_lesiones WHERE fecha = (SELECT MAX(fecha) FROM factor_lesiones)',conexion)
    finally:conexion.close()

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
    conexion=conectar_bd()
    try:return pd.read_sql('SELECT equipo, nombre_pitcher, era, era_ultimas_3 FROM abridores WHERE fecha = (SELECT MAX(fecha) FROM abridores)',conexion)
    finally:conexion.close()

def aplicar_filtro_pitchers(equipo_elegido, confianza_base, equipo_local, equipo_visitante, df_pitchers):
    if df_pitchers.empty:
        return (confianza_base, 'TBD', 'TBD')

    def obtener_era_real(equipo):
        row = df_pitchers[df_pitchers['equipo'] == equipo]
        if row.empty:
            return 4.5
        era_3 = row['era_ultimas_3'].values[0]
        era_g = row['era'].values[0]
        return float(era_3) if pd.notna(era_3) and float(era_3) > 0 else float(era_g)
    era_local = obtener_era_real(equipo_local)
    era_visita = obtener_era_real(equipo_visitante)
    nom_l = df_pitchers.loc[df_pitchers['equipo'] == equipo_local, 'nombre_pitcher'].values
    nom_v = df_pitchers.loc[df_pitchers['equipo'] == equipo_visitante, 'nombre_pitcher'].values
    pitcher_local = nom_l[0] if len(nom_l) > 0 else 'Por anunciar'
    pitcher_visita = nom_v[0] if len(nom_v) > 0 else 'Por anunciar'
    ventaja = era_visita - era_local if equipo_elegido == equipo_local else era_local - era_visita
    confianza_final = confianza_base + ventaja * 2.5
    return (max(50.1, min(99.0, round(confianza_final, 1))), f'{pitcher_local} ({era_local:.2f})', f'{pitcher_visita} ({era_visita:.2f})')

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
        raise RuntimeError("No se pudo guardar la publicación Moneyline.") from None
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None:
            conexion.close()


def generate():
    modelo,scaler,columnas_v4=cargar_oraculo()
    df=cargar_datos_hoy()
    if df.empty:return 0
    df_csv_estatico=pd.read_csv(RUTA_DATA_MLB/'mlb_dataset_ia.csv')
    df_hist=fusionar_historiales(df_csv_estatico,cargar_historial_xampp())
    df_metricas_adv=cargar_metricas_avanzadas()
    version_moneyline=fingerprint(modelo,scaler,columnas_v4,[limpiar_cuotas_v4,aplicar_filtro_medico,aplicar_filtro_pitchers])
    df_lesiones_hoy=cargar_lesiones_hoy()
    df_pitchers_hoy=cargar_pitchers_hoy()
    resultados=[]
    for i in range(len(df)):
        local_api = df.loc[i, 'Equipo Local']
        visita_api = df.loc[i, 'Equipo Visitante']

        local = normalizar_equipo(local_api)
        visita = normalizar_equipo(visita_api)

        # 1. Rendimiento Básico y Estadio Anterior
        w_l, d_l, desc_l, r5_l, est_ant_l = obtener_estado_actual(local, df_hist)
        w_v, d_v, desc_v, r5_v, est_ant_v = obtener_estado_actual(visita, df_hist)

        # 2. Desgaste por Viaje (Jetlag)
        zona_estadio_hoy = ZONAS_HORARIAS.get(local, -5)
        zona_ant_l = ZONAS_HORARIAS.get(normalizar_equipo(est_ant_l), -5)
        zona_ant_v = ZONAS_HORARIAS.get(normalizar_equipo(est_ant_v), -5)
        jetlag_l = abs(zona_estadio_hoy - zona_ant_l)
        jetlag_v = abs(zona_estadio_hoy - zona_ant_v)

        # 3. Métricas Avanzadas (Splits y Bullpen)
        met_l = df_metricas_adv[df_metricas_adv['equipo'] == local_api]
        met_v = df_metricas_adv[df_metricas_adv['equipo'] == visita_api]

        ops_l_team = float(met_l['ops_vs_zurdo'].values[0]) if not met_l.empty else 0.700
        ops_r_team = float(met_l['ops_vs_derecho'].values[0]) if not met_l.empty else 0.700
        era_bp_team = float(met_l['era_bullpen_7d'].values[0]) if not met_l.empty else 4.50

        ops_l_opp = float(met_v['ops_vs_zurdo'].values[0]) if not met_v.empty else 0.700
        ops_r_opp = float(met_v['ops_vs_derecho'].values[0]) if not met_v.empty else 0.700
        era_bp_opp = float(met_v['era_bullpen_7d'].values[0]) if not met_v.empty else 4.50

        # 4. Desparasitar Cuotas
        prob_p_l, prob_p_v = limpiar_cuotas_v4(df.loc[i, 'Paga Local'], df.loc[i, 'Paga Visitante'])

        # 5. MATRIZ EXACTA V4.0 (18 Variables)
        fila_dic = {
            'win_pct_team': w_l, 'win_pct_opp': w_v,
            'run_diff_team': d_l, 'run_diff_opp': d_v,
            'dias_descanso_team': desc_l, 'dias_descanso_opp': desc_v,
            'racha_5_team': r5_l, 'racha_5_opp': r5_v,
            'jetlag_team': jetlag_l, 'jetlag_opp': jetlag_v,
            'ops_l_team': ops_l_team, 'ops_r_team': ops_r_team, 'era_bullpen_team': era_bp_team,
            'ops_l_opp': ops_l_opp, 'ops_r_opp': ops_r_opp, 'era_bullpen_opp': era_bp_opp,
            'prob_pure_team': prob_p_l, 'prob_pure_opp': prob_p_v
        }

        fila_ia = pd.DataFrame([fila_dic])
        fila_ia = fila_ia[columnas_v4]

        vars_escaladas = scaler.transform(fila_ia)
        prob_local = modelo.predict(vars_escaladas, verbose=0)[0][0] * 100
        prob_visitante = 100 - prob_local

        favorito = local_api if prob_local > 50 else visita_api
        confianza = max(prob_local, prob_visitante)
        paga = df.loc[i, 'Paga Local'] if prob_local > 50 else df.loc[i, 'Paga Visitante']


        confianza_filtrada = aplicar_filtro_medico(favorito, confianza, local_api, visita_api, df_lesiones_hoy)
        confianza_final, p_local, p_visita = aplicar_filtro_pitchers(favorito, confianza_filtrada, local_api, visita_api, df_pitchers_hoy)

        # NUEVO: persistimos el pick de moneyline en registro_picks_ia.
        # Esto es lo que Tab 2 va a leer más adelante cuando el juego termine,
        # en vez de recalcularlo con otra lógica.
        guardar_pick_ia(pd.Timestamp(df.loc[i, "Fecha"]).date(), local_api, visita_api, favorito, confianza_final, paga,
            game_id=df.loc[i, "id_juego"], model_id=version_moneyline,
            home_odds=df.loc[i, "Paga Local"], away_odds=df.loc[i, "Paga Visitante"])

        resultados.append({
            "id_juego": df.loc[i, "id_juego"],
            "Modelo": version_moneyline,
            "Fecha": df.loc[i, "Fecha"],
            "Partido": f"{local_api} vs {visita_api}",
            "Abridores": f"{p_local} vs {p_visita}",
            "Pick de la IA": favorito,
            "Confianza (%)": confianza_final,
            "Paga del Favorito": paga
        })


    return len(resultados)
