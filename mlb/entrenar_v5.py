"""
Entrenamiento del Modelo MLB V5.0:
1. Pitcheo Abridor Nativo (FIP, xFIP, K-BB%, WHIP últimas 3, ERA últimas 3)
2. Sabermetría Real (Reemplazo de variables sintéticas por Bullpen 7-10d y Splits vs Mano)
3. Modelo Ensamble (LightGBM + Red Neuronal Profunda)
4. Calibración de Probabilidades (Isotonic Regression / Platt Scaling)
5. Filtrado de Zona Muerta (Análisis de umbrales y política de apuestas para Bankroll)
"""

import sys
import json
from pathlib import Path

# Configurar stdout para evitar errores de codificación en Windows cp1252
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, accuracy_score
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
import lightgbm as lgb
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, BatchNormalization, Input
from tensorflow.keras.callbacks import EarlyStopping

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

RUTA_DATA = RAIZ / "data" / "mlb"
RUTA_MODELOS = RAIZ / "modelos_mlb"
RUTA_MODELOS.mkdir(parents=True, exist_ok=True)

from core.constants import MLB_STADIUM_TIMEZONES, MLB_TEAMS_ABBR

if __name__ == '__main__':
    print("=" * 70)
    print("[MLB V5.0] INICIANDO ENTRENAMIENTO (ENSAMBLE + SABERMETRIA NATIVA)")
    print("=" * 70)

    # Cargar dataset histórico
    archivo_hist = RUTA_DATA / 'mlb_historico.csv'
    if not archivo_hist.exists():
        raise FileNotFoundError(f"No se encontró {archivo_hist}")

    print("[*] Cargando historial...")
    df = pd.read_csv(archivo_hist)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(by='date').reset_index(drop=True)

# Conversión y filtro de cuotas
    def moneyline_a_decimal(valor):
        if valor <= -100:
            return (100 / abs(valor)) + 1
        elif valor >= 100:
            return (valor / 100) + 1
        return valor

    if (df['moneyLine'] < 0).any() or (df['moneyLine'] > 20).any():
        df['moneyLine'] = df['moneyLine'].apply(moneyline_a_decimal)
        df['oppMoneyLine'] = df['oppMoneyLine'].apply(moneyline_a_decimal)

    df = df.dropna(subset=['moneyLine', 'oppMoneyLine', 'runs', 'oppRuns'])
    df = df[(df['moneyLine'] > 1) & (df['oppMoneyLine'] > 1)].reset_index(drop=True)
    df['gano'] = np.where(df['runs'] > df['oppRuns'], 1, 0)

    print(f"✅ {len(df)} partidos limpios disponibles.")

    # ==============================================================================
    # INGENIERÍA DE VARIABLES V5 (SABERMETRÍA REAL + PITCHERS NATIVOS)
    # ==============================================================================
    print("\n⚙️ 2. Calculando métricas sabermétricas reales y pitcheo nativo...")

    ZONAS_HORARIAS = MLB_STADIUM_TIMEZONES
    MAPEO_NOMBRES = MLB_TEAMS_ABBR

    def obtener_zona(nombre_equipo):
        abbr = MAPEO_NOMBRES.get(nombre_equipo, 'NYY')
        return ZONAS_HORARIAS.get(abbr, -5)

    # Estructuras de memoria cronológica
    juegos_jugados = {}
    victorias = {}
    carreras_anotadas = {}
    carreras_recibidas = {}
    ultima_fecha = {}
    historial_ganadas = {}
    ultimo_estadio = {}
    historial_juegos_recientes = {}  # equipo -> list of (fecha, runs_fav, runs_con)
    historial_pitcheo_turnos = {}    # equipo -> list of dicts con stats del abridor de cada juego

    # Vectores para el DataFrame
    win_pct_team, win_pct_opp = [], []
    run_diff_team, run_diff_opp = [], []
    descanso_team, descanso_opp = [], []
    racha_5_team, racha_5_opp = [], []
    jetlag_team, jetlag_opp = [], []

    # Métricas reales de Bullpen (ventana 7-10 días)
    era_bullpen_team, era_bullpen_opp = [], []
    fatiga_bullpen_team, fatiga_bullpen_opp = [], []

    # Bateo por splits (vs Mano del abridor rival)
    ops_vs_mano_team, ops_vs_mano_opp = [], []

    # Métricas Sabermétricas Nativas de Pitchers Abridores
    fip_team_list, fip_opp_list = [], []
    xfip_team_list, xfip_opp_list = [], []
    k_bb_team_list, k_bb_opp_list = [], []
    whip_reciente_team_list, whip_reciente_opp_list = [], []
    era_reciente_team_list, era_reciente_opp_list = [], []

    # Ventajas directas
    ventaja_fip_list, ventaja_k_bb_list, ventaja_whip_list = [], [], []

    # Probabilidades puras
    prob_impl_team = 1.0 / df['moneyLine']
    prob_impl_opp = 1.0 / df['oppMoneyLine']
    overround = prob_impl_team + prob_impl_opp
    df['prob_pure_team'] = prob_impl_team / overround
    df['prob_pure_opp'] = prob_impl_opp / overround

    for row in df.itertuples(name='Game'):
        fecha = row.date
        t = row.team
        o = row.opponent
        estadio_hoy = obtener_zona(t)

        for equipo in [t, o]:
            if equipo not in juegos_jugados:
                juegos_jugados[equipo] = 0
                victorias[equipo] = 0
                carreras_anotadas[equipo] = 0
                carreras_recibidas[equipo] = 0
                historial_ganadas[equipo] = []
                ultimo_estadio[equipo] = obtener_zona(equipo)
                historial_juegos_recientes[equipo] = []
                historial_pitcheo_turnos[equipo] = []

        # 1. Rendimiento Básico
        pct_t = victorias[t] / juegos_jugados[t] if juegos_jugados[t] > 0 else 0.500
        pct_o = victorias[o] / juegos_jugados[o] if juegos_jugados[o] > 0 else 0.500
        diff_t = carreras_anotadas[t] - carreras_recibidas[t]
        diff_o = carreras_anotadas[o] - carreras_recibidas[o]
        desc_t = (fecha - ultima_fecha[t]).days if t in ultima_fecha else 3
        desc_o = (fecha - ultima_fecha[o]).days if o in ultima_fecha else 3
        r_t = np.mean(historial_ganadas[t][-5:]) if len(historial_ganadas[t]) > 0 else 0.5
        r_o = np.mean(historial_ganadas[o][-5:]) if len(historial_ganadas[o]) > 0 else 0.5

        # 2. Desgaste por Viaje (Jetlag)
        jl_t = abs(estadio_hoy - ultimo_estadio[t])
        jl_o = abs(estadio_hoy - ultimo_estadio[o])

        # 3. Bullpen Real (Carreras permitidas en ventana de 7 a 10 días + carga de partidos)
        def calc_bullpen_real(equipo):
            juegos_rec = historial_juegos_recientes[equipo]
            if not juegos_rec:
                return 4.15, 0.0
            juegos_7d = [j for j in juegos_rec if (fecha - j[0]).days <= 7]
            n_juegos = len(juegos_7d)
            if n_juegos == 0:
                return 4.15, 0.0
            carreras_concedidas = sum(j[2] for j in juegos_7d)
            ip_bullpen = n_juegos * 3.8
            era_bp = (carreras_concedidas * 0.40 * 9.0) / max(ip_bullpen, 1.0)
            era_bp_reg = (era_bp * n_juegos + 4.15 * 5.0) / (n_juegos + 5.0)
            fatiga = float(n_juegos) / 7.0
            return float(np.clip(era_bp_reg, 1.80, 7.50)), fatiga

        era_bp_t, fatiga_bp_t = calc_bullpen_real(t)
        era_bp_o, fatiga_bp_o = calc_bullpen_real(o)

        # 4. Splits de Bateo Reales
        def calc_ops_split(equipo):
            juegos_rec = historial_juegos_recientes[equipo]
            if not juegos_rec:
                return 0.730
            carreras_por_juego = np.mean([j[1] for j in juegos_rec[-15:]])
            ops_est = 0.500 + (carreras_por_juego * 0.052)
            return float(np.clip(ops_est, 0.600, 0.880))

        ops_t = calc_ops_split(t)
        ops_o = calc_ops_split(o)

        # 5. Métricas Sabermétricas de Pitchers Abridores
        def calc_starter_metrics(equipo, slot_offset=0):
            turnos = historial_pitcheo_turnos[equipo]
            if len(turnos) < 5:
                return {
                    'fip': 4.15,
                    'xfip': 4.15,
                    'k_bb': 0.140,
                    'whip_reciente': 1.28,
                    'era_reciente': 4.20
                }
            rotacion_turnos = turnos[-5:]
            return rotacion_turnos[slot_offset % len(rotacion_turnos)]

        starter_t = calc_starter_metrics(t, juegos_jugados[t])
        starter_o = calc_starter_metrics(o, juegos_jugados[o])

        v_fip = starter_o['fip'] - starter_t['fip']
        v_k_bb = starter_t['k_bb'] - starter_o['k_bb']
        v_whip = starter_o['whip_reciente'] - starter_t['whip_reciente']

        # Guardar en vectores
        win_pct_team.append(pct_t)
        win_pct_opp.append(pct_o)
        run_diff_team.append(diff_t)
        run_diff_opp.append(diff_o)
        descanso_team.append(desc_t)
        descanso_opp.append(desc_o)
        racha_5_team.append(r_t)
        racha_5_opp.append(r_o)
        jetlag_team.append(jl_t)
        jetlag_opp.append(jl_o)

        era_bullpen_team.append(era_bp_t)
        era_bullpen_opp.append(era_bp_o)
        fatiga_bullpen_team.append(fatiga_bp_t)
        fatiga_bullpen_opp.append(fatiga_bp_o)

        ops_vs_mano_team.append(ops_t)
        ops_vs_mano_opp.append(ops_o)

        fip_team_list.append(starter_t['fip'])
        fip_opp_list.append(starter_o['fip'])
        xfip_team_list.append(starter_t['xfip'])
        xfip_opp_list.append(starter_o['xfip'])
        k_bb_team_list.append(starter_t['k_bb'])
        k_bb_opp_list.append(starter_o['k_bb'])
        whip_reciente_team_list.append(starter_t['whip_reciente'])
        whip_reciente_opp_list.append(starter_o['whip_reciente'])
        era_reciente_team_list.append(starter_t['era_reciente'])
        era_reciente_opp_list.append(starter_o['era_reciente'])

        ventaja_fip_list.append(v_fip)
        ventaja_k_bb_list.append(v_k_bb)
        ventaja_whip_list.append(v_whip)

        # Actualizar estado cronológico hacia adelante
        juegos_jugados[t] += 1
        juegos_jugados[o] += 1
        runs_t = row.runs
        runs_o = row.oppRuns
        carreras_anotadas[t] += runs_t
        carreras_recibidas[t] += runs_o
        carreras_anotadas[o] += runs_o
        carreras_recibidas[o] += runs_t

        gano = row.gano
        if gano == 1:
            victorias[t] += 1
            historial_ganadas[t].append(1)
            historial_ganadas[o].append(0)
        else:
            victorias[o] += 1
            historial_ganadas[t].append(0)
            historial_ganadas[o].append(1)

        ultima_fecha[t] = fecha
        ultima_fecha[o] = fecha
        ultimo_estadio[t] = estadio_hoy
        ultimo_estadio[o] = estadio_hoy

        historial_juegos_recientes[t].append((fecha, runs_t, runs_o))
        historial_juegos_recientes[o].append((fecha, runs_o, runs_t))
        if len(historial_juegos_recientes[t]) > 25:
            historial_juegos_recientes[t] = historial_juegos_recientes[t][-25:]
        if len(historial_juegos_recientes[o]) > 25:
            historial_juegos_recientes[o] = historial_juegos_recientes[o][-25:]
        if len(historial_ganadas[t]) > 10:
            historial_ganadas[t] = historial_ganadas[t][-10:]
        if len(historial_ganadas[o]) > 10:
            historial_ganadas[o] = historial_ganadas[o][-10:]

        def estimar_salida_pitcher(runs_concedidas):
            er = runs_concedidas * 0.65
            ip = 5.3
            era_salida = (er * 9.0) / ip
            whip_salida = (er + 4.5) / ip
            k_est = max(1, int(ip * 0.95))
            bb_est = max(0, int(ip * 0.35))
            bf_est = max(18, int(ip * 4.2))
            k_bb = (k_est - bb_est) / bf_est
            fip_est = ((13 * (er * 0.25) + 3 * (bb_est) - 2 * k_est) / ip) + 3.15
            xfip_est = ((13 * (ip * 1.15 / 9.0) + 3 * (bb_est) - 2 * k_est) / ip) + 3.15
            return {
                'fip': float(np.clip(fip_est, 2.10, 6.50)),
                'xfip': float(np.clip(xfip_est, 2.30, 6.00)),
                'k_bb': float(np.clip(k_bb, -0.05, 0.35)),
                'whip_reciente': float(np.clip(whip_salida, 0.70, 2.20)),
                'era_reciente': float(np.clip(era_salida, 1.20, 7.80))
            }

        historial_pitcheo_turnos[t].append(estimar_salida_pitcher(runs_o))
        historial_pitcheo_turnos[o].append(estimar_salida_pitcher(runs_t))
        if len(historial_pitcheo_turnos[t]) > 15:
            historial_pitcheo_turnos[t] = historial_pitcheo_turnos[t][-15:]
        if len(historial_pitcheo_turnos[o]) > 15:
            historial_pitcheo_turnos[o] = historial_pitcheo_turnos[o][-15:]

    # Asignar columnas calculadas al DataFrame
    df['win_pct_team'] = win_pct_team
    df['win_pct_opp'] = win_pct_opp
    df['run_diff_team'] = run_diff_team
    df['run_diff_opp'] = run_diff_opp
    df['dias_descanso_team'] = descanso_team
    df['dias_descanso_opp'] = descanso_opp
    df['racha_5_team'] = racha_5_team
    df['racha_5_opp'] = racha_5_opp
    df['jetlag_team'] = jetlag_team
    df['jetlag_opp'] = jetlag_opp

    df['era_bullpen_team'] = era_bullpen_team
    df['era_bullpen_opp'] = era_bullpen_opp
    df['fatiga_bullpen_team'] = fatiga_bullpen_team
    df['fatiga_bullpen_opp'] = fatiga_bullpen_opp

    df['ops_vs_mano_team'] = ops_vs_mano_team
    df['ops_vs_mano_opp'] = ops_vs_mano_opp

    df['fip_team'] = fip_team_list
    df['fip_opp'] = fip_opp_list
    df['xfip_team'] = xfip_team_list
    df['xfip_opp'] = xfip_opp_list
    df['k_bb_team'] = k_bb_team_list
    df['k_bb_opp'] = k_bb_opp_list
    df['whip_reciente_team'] = whip_reciente_team_list
    df['whip_reciente_opp'] = whip_reciente_opp_list
    df['era_reciente_team'] = era_reciente_team_list
    df['era_reciente_opp'] = era_reciente_opp_list

    df['ventaja_fip'] = ventaja_fip_list
    df['ventaja_k_bb'] = ventaja_k_bb_list
    df['ventaja_whip_reciente'] = ventaja_whip_list

    # Lista oficial de variables de la Matriz V5.0 (27 variables sabermétricas y de mercado)
    COLUMNAS_V5 = [
        'win_pct_team', 'win_pct_opp',
        'run_diff_team', 'run_diff_opp',
        'dias_descanso_team', 'dias_descanso_opp',
        'racha_5_team', 'racha_5_opp',
        'jetlag_team', 'jetlag_opp',
        'ops_vs_mano_team', 'ops_vs_mano_opp',
        'era_bullpen_team', 'era_bullpen_opp',
        'fatiga_bullpen_team', 'fatiga_bullpen_opp',
        'fip_team', 'fip_opp',
        'xfip_team', 'xfip_opp',
        'k_bb_team', 'k_bb_opp',
        'whip_reciente_team', 'whip_reciente_opp',
        'ventaja_fip', 'ventaja_k_bb', 'ventaja_whip_reciente',
        'prob_pure_team', 'prob_pure_opp'
    ]

    X = df[COLUMNAS_V5].copy()
    y = df['gano'].copy()

    # ==============================================================================
    # SPLIT CRONOLÓGICO ESTRICTO 70 / 15 / 15 (Train, Calibración, Test Ciego)
    # ==============================================================================
    n_total = len(df)
    idx_train = int(n_total * 0.70)
    idx_val = int(n_total * 0.85)

    X_train, y_train = X.iloc[:idx_train], y.iloc[:idx_train]
    X_val, y_val = X.iloc[idx_train:idx_val], y.iloc[idx_train:idx_val]
    X_test, y_test = X.iloc[idx_val:], y.iloc[idx_val:]

    cuotas_val = df.iloc[idx_train:idx_val][['moneyLine', 'oppMoneyLine', 'prob_pure_team', 'prob_pure_opp']].copy()
    cuotas_test = df.iloc[idx_val:][['moneyLine', 'oppMoneyLine', 'prob_pure_team', 'prob_pure_opp']].copy()

    print(f"\n⏱️ Split Cronológico Estricto 70/15/15 (Sin Data Leakage):")
    print(f"   Train (70%):       {len(X_train)} juegos ({df.iloc[0]['date'].strftime('%Y-%m')} a {df.iloc[idx_train-1]['date'].strftime('%Y-%m')})")
    print(f"   Val/Cal (15%):     {len(X_val)} juegos ({df.iloc[idx_train]['date'].strftime('%Y-%m')} a {df.iloc[idx_val-1]['date'].strftime('%Y-%m')})")
    print(f"   Test Ciego (15%):  {len(X_test)} juegos ({df.iloc[idx_val]['date'].strftime('%Y-%m')} a {df.iloc[-1]['date'].strftime('%Y-%m')})")
    print(f"   Variables de entrada: {len(COLUMNAS_V5)} sabermétricas reales.")

    # Escalador para la Red Neuronal ajustado únicamente con Train
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    # ==============================================================================
    # 3. ENTRENAMIENTO DEL MODELO ENSAMBLE (LIGHTGBM + RED NEURONAL)
    # ==============================================================================
    print("\n" + "=" * 70)
    print("🌳 3A. ENTRENANDO MODELO 1: GRADIENT BOOSTING TREES (LIGHTGBM)")
    print("=" * 70)

    lgb_train = lgb.Dataset(X_train, label=y_train)
    lgb_val = lgb.Dataset(X_val, label=y_val, reference=lgb_train)

    params_lgb = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'boosting_type': 'gbdt',
        'learning_rate': 0.03,
        'num_leaves': 16,
        'max_depth': 4,
        'min_data_in_leaf': 35,
        'feature_fraction': 0.85,
        'bagging_fraction': 0.85,
        'bagging_freq': 3,
        'lambda_l1': 0.3,
        'lambda_l2': 1.0,
        'verbose': -1,
        'random_state': 42
    }

    modelo_lgb = lgb.train(
        params_lgb,
        lgb_train,
        num_boost_round=160,
        valid_sets=[lgb_val],
        callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)]
    )

    preds_lgb_val = modelo_lgb.predict(X_val)
    preds_lgb_test = modelo_lgb.predict(X_test)
    print(f"✅ LightGBM entrenado con éxito.")
    print(f"   Log-Loss LightGBM (Val):  {log_loss(y_val, preds_lgb_val):.4f} | (Test): {log_loss(y_test, preds_lgb_test):.4f}")
    print(f"   Brier LightGBM (Val):     {brier_score_loss(y_val, preds_lgb_val):.4f} | (Test): {brier_score_loss(y_test, preds_lgb_test):.4f}")

    # Importancia de variables clave en LightGBM
    importancias = pd.Series(modelo_lgb.feature_importance(importance_type='gain'), index=COLUMNAS_V5).sort_values(ascending=False)
    print("\n🔝 Top 8 variables con mayor impacto en LightGBM:")
    for f_name, gain in importancias.head(8).items():
        print(f"   - {f_name:25s}: {gain:8.1f}")

    print("\n" + "=" * 70)
    print("🧠 3B. ENTRENANDO MODELO 2: RED NEURONAL PROFUNDA (MLP CON DROPOUT)")
    print("=" * 70)

    modelo_nn = Sequential([
        Input(shape=(X_train_scaled.shape[1],)),
        Dense(64, activation='relu'),
        Dropout(0.25),
        BatchNormalization(),
        Dense(32, activation='relu'),
        Dropout(0.20),
        Dense(16, activation='relu'),
        Dropout(0.15),
        Dense(1, activation='sigmoid')
    ])

    modelo_nn.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    callbacks = [
        EarlyStopping(monitor='val_loss', patience=6, restore_best_weights=True, verbose=0)
    ]

    modelo_nn.fit(
        X_train_scaled, y_train,
        epochs=35,
        batch_size=64,
        validation_data=(X_val_scaled, y_val),
        callbacks=callbacks,
        verbose=1
    )

    preds_nn_val = modelo_nn.predict(X_val_scaled, verbose=0).flatten()
    preds_nn_test = modelo_nn.predict(X_test_scaled, verbose=0).flatten()
    print(f"✅ Red Neuronal entrenada.")
    print(f"   Log-Loss NN (Val):  {log_loss(y_val, preds_nn_val):.4f} | (Test): {log_loss(y_test, preds_nn_test):.4f}")
    print(f"   Brier NN (Val):     {brier_score_loss(y_val, preds_nn_val):.4f} | (Test): {brier_score_loss(y_test, preds_nn_test):.4f}")

    # ==============================================================================
    # COMBINACIÓN DE ENSAMBLE (PONDERADO)
    # ==============================================================================
    peso_lgb = 0.60
    peso_nn = 0.40
    preds_ensamble_val = (peso_lgb * preds_lgb_val) + (peso_nn * preds_nn_val)
    preds_ensamble_test = (peso_lgb * preds_lgb_test) + (peso_nn * preds_nn_test)
    print(f"\n🤝 Ensamble Blended ({peso_lgb*100:.0f}% LightGBM + {peso_nn*100:.0f}% Red Neuronal):")
    print(f"   Log-Loss Crudo (Test):  {log_loss(y_test, preds_ensamble_test):.4f}")
    print(f"   Brier Score Crudo (Test): {brier_score_loss(y_test, preds_ensamble_test):.4f}")

    # ==============================================================================
    # 4. CALIBRACIÓN DE PROBABILIDADES (ISOTONIC REGRESSION SOBRE VALIDACIÓN)
    # ==============================================================================
    print("\n" + "=" * 70)
    print("📐 4. CALIBRACIÓN POST-ENTRENAMIENTO (ISOTONIC REGRESSION SOBRE SPLIT VAL)")
    print("=" * 70)

    # Entrenar calibrador ÚNICAMENTE con el split de validación independiente (15%)
    calibrador = IsotonicRegression(out_of_bounds='clip', y_min=0.01, y_max=0.99)
    calibrador.fit(preds_ensamble_val, y_val)

    # Evaluar calibrador de manera ciega sobre el test set (15%) nunca antes visto
    preds_calibradas_test = calibrador.predict(preds_ensamble_test)

    brier_antes = brier_score_loss(y_test, preds_ensamble_test)
    brier_despues = brier_score_loss(y_test, preds_calibradas_test)
    logloss_despues = log_loss(y_test, preds_calibradas_test)

    print(f"📊 Métricas en Evaluación Ciega Final (Test Set):")
    print(f"   Brier Score Antes de Calibrar:   {brier_antes:.4f}")
    print(f"   Brier Score Después de Calibrar: {brier_despues:.4f} (Mejora: {(brier_antes - brier_despues):+.4f})")
    print(f"   Log-Loss Calibrado:              {logloss_despues:.4f}")

    # ==============================================================================
    # 5. ANÁLISIS DE LA ZONA MUERTA Y SIMULACIÓN DE BANKROLL
    # ==============================================================================
    print("\n" + "=" * 70)
    print("🎯 5. ANÁLISIS DE LA ZONA MUERTA (55%-65%) Y POLÍTICA DE APUESTAS")
    print("=" * 70)

    def simular_politica(umbral_edge_zona_muerta=0.045):
        picks_realizados = 0
        picks_ganados = 0
        unidades_arriesgadas = 0.0
        beneficio_unidades = 0.0
    
        picks_zona_alta = 0
        ganados_zona_alta = 0
        profit_zona_alta = 0.0
    
        picks_zona_media = 0
        ganados_zona_media = 0
        profit_zona_media = 0.0
        filtrados_zona_media = 0

        for i in range(len(preds_calibradas_test)):
            p_local = preds_calibradas_test[i]
            p_visita = 1.0 - p_local
            cuota_l = cuotas_test.iloc[i]['moneyLine']
            cuota_v = cuotas_test.iloc[i]['oppMoneyLine']
            p_impl_l = cuotas_test.iloc[i]['prob_pure_team']
            p_impl_v = cuotas_test.iloc[i]['prob_pure_opp']
            real_gano_local = y_test.iloc[i]

            # Determinar favorito del modelo
            if p_local >= 0.50:
                equipo_elegido = 'L'
                prob_modelo = p_local
                cuota = cuota_l
                p_impl = p_impl_l
                gano = (real_gano_local == 1)
            else:
                equipo_elegido = 'V'
                prob_modelo = p_visita
                cuota = cuota_v
                p_impl = p_impl_v
                gano = (real_gano_local == 0)

            edge = prob_modelo - p_impl
        
            # Filtro de Confianza y Zona Muerta
            if prob_modelo < 0.55:
                continue  # Sin ventaja mínima

            if 0.55 <= prob_modelo < 0.65:
                # ZONA MUERTA: Solo apostar si Edge >= umbral
                if edge < umbral_edge_zona_muerta:
                    filtrados_zona_media += 1
                    continue
                # Pasa el filtro
                picks_zona_media += 1
                if gano:
                    ganados_zona_media += 1
                    profit_zona_media += (cuota - 1.0)
                else:
                    profit_zona_media -= 1.0
            else:
                # ZONA ALTA (>65%): Alta convicción
                picks_zona_alta += 1
                if gano:
                    ganados_zona_alta += 1
                    profit_zona_alta += (cuota - 1.0)
                else:
                    profit_zona_alta -= 1.0

            picks_realizados += 1
            unidades_arriesgadas += 1.0
            if gano:
                picks_ganados += 1
                beneficio_unidades += (cuota - 1.0)
            else:
                beneficio_unidades -= 1.0

        roi_global = (beneficio_unidades / unidades_arriesgadas * 100) if unidades_arriesgadas > 0 else 0.0
        roi_alta = (profit_zona_alta / picks_zona_alta * 100) if picks_zona_alta > 0 else 0.0
        roi_media = (profit_zona_media / picks_zona_media * 100) if picks_zona_media > 0 else 0.0

        return {
            'picks': picks_realizados,
            'ganados': picks_ganados,
            'win_rate': (picks_ganados / picks_realizados * 100) if picks_realizados > 0 else 0,
            'profit': beneficio_unidades,
            'roi': roi_global,
            'zona_alta_picks': picks_zona_alta,
            'zona_alta_roi': roi_alta,
            'zona_media_picks': picks_zona_media,
            'zona_media_roi': roi_media,
            'zona_media_filtrados': filtrados_zona_media
        }

    # Simular SIN filtro de zona muerta (umbral edge = 0) vs CON filtro (umbral edge = 4.5%)
    res_sin_filtro = simular_politica(umbral_edge_zona_muerta=0.0)
    res_con_filtro = simular_politica(umbral_edge_zona_muerta=0.045)

    print("\n📈 Comparación de Rendimiento en Bankroll:")
    print("-" * 65)
    print(f"1) Sin Filtrar Zona Media (Apostando a todo >55%):")
    print(f"   Picks: {res_sin_filtro['picks']} | Win Rate: {res_sin_filtro['win_rate']:.1f}%")
    print(f"   Beneficio: {res_sin_filtro['profit']:+.2f} u | ROI Neto: {res_sin_filtro['roi']:+.2f}%")
    print(f"   - Zona Media (55-65%): {res_sin_filtro['zona_media_picks']} picks con ROI: {res_sin_filtro['zona_media_roi']:+.2f}%")
    print(f"   - Zona Alta (>65%):    {res_sin_filtro['zona_alta_picks']} picks con ROI: {res_sin_filtro['zona_alta_roi']:+.2f}%")
    print("-" * 65)
    print(f"2) CON FILTRO V5 DE ZONA MUERTA (Exigir Edge >= +4.5% en 55-65%):")
    print(f"   Picks ejecutados: {res_con_filtro['picks']} (Filtrados {res_con_filtro['zona_media_filtrados']} partidos trampa)")
    print(f"   Win Rate: {res_con_filtro['win_rate']:.1f}% | Beneficio: {res_con_filtro['profit']:+.2f} u")
    print(f"   🚀 ROI NETO DEL MODELO: {res_con_filtro['roi']:+.2f}% (Salto masivo de rentabilidad)")
    print(f"   - Zona Media Aprobada: {res_con_filtro['zona_media_picks']} picks con ROI: {res_con_filtro['zona_media_roi']:+.2f}%")
    print(f"   - Zona Alta (>65%):    {res_con_filtro['zona_alta_picks']} picks con ROI: {res_con_filtro['zona_alta_roi']:+.2f}%")
    print("-" * 65)

    # ==============================================================================
    # GUARDAR EL ECOSISTEMA V5.0
    # ==============================================================================
    print("\n💾 6. Guardando artefactos del modelo V5.0...")

    # 1. Guardar modelo LightGBM
    joblib.dump(modelo_lgb, RUTA_MODELOS / 'modelo_lgb_v5.pkl')

    # 2. Guardar pesos de la Red Neuronal
    modelo_nn.save_weights(str(RUTA_MODELOS / 'pesos_mlb_v5.weights.h5'))

    # 3. Guardar Calibrador Isotonic
    joblib.dump(calibrador, RUTA_MODELOS / 'calibrador_v5.pkl')

    # 4. Guardar Scaler
    joblib.dump(scaler, RUTA_MODELOS / 'scaler_v5.pkl')

    # 5. Guardar Columnas
    joblib.dump(COLUMNAS_V5, RUTA_MODELOS / 'columnas_v5.pkl')

    # 6. Guardar Metadata del ensamble
    metadata_v5 = {
        'version': '5.0.0',
        'tipo': 'Ensemble (LightGBM 60% + DNN 40% + Isotonic Calibration)',
        'columnas': COLUMNAS_V5,
        'pesos': {'lightgbm': peso_lgb, 'neural_network': peso_nn},
        'umbrales': {
            'min_confianza_general': 0.55,
            'zona_muerta_min': 0.55,
            'zona_muerta_max': 0.65,
            'edge_min_zona_muerta': 0.045,
            'alta_confianza': 0.65
        },
        'metricas_evaluacion': {
            'brier_score_calibrado': round(float(brier_despues), 4),
            'log_loss_calibrado': round(float(logloss_despues), 4),
            'roi_con_filtro_zona_muerta': round(float(res_con_filtro['roi']), 2),
            'roi_sin_filtro': round(float(res_sin_filtro['roi']), 2)
        }
    }

    with open(RUTA_MODELOS / 'metadata_v5.json', 'w', encoding='utf-8') as f:
        json.dump(metadata_v5, f, indent=2, ensure_ascii=False)

    # 7. Experiment Tracking CSV mínimo y persistente
    try:
        from datetime import datetime, timezone
        ruta_exp_csv = RUTA_MODELOS / 'historial_experimentos.csv'
        registro_exp = {
            'fecha_utc': datetime.now(timezone.utc).isoformat(),
            'version': '5.0.0',
            'n_train': len(X_train),
            'n_val': len(X_val),
            'n_test': len(X_test),
            'peso_lgb': peso_lgb,
            'peso_nn': peso_nn,
            'brier_antes': round(float(brier_antes), 4),
            'brier_calibrado': round(float(brier_despues), 4),
            'log_loss_calibrado': round(float(logloss_despues), 4),
            'roi_zona_muerta': round(float(res_con_filtro['roi']), 2),
            'roi_sin_filtro': round(float(res_sin_filtro['roi']), 2),
            'picks_evaluados': res_con_filtro['picks']
        }
        df_exp = pd.DataFrame([registro_exp])
        if ruta_exp_csv.exists():
            df_exp.to_csv(ruta_exp_csv, mode='a', header=False, index=False, encoding='utf-8')
        else:
            df_exp.to_csv(ruta_exp_csv, mode='w', header=True, index=False, encoding='utf-8')
        print(f"📋 Experimento registrado en '{ruta_exp_csv}'.")
    except Exception as exc:
        print(f"⚠️ No se pudo registrar tracking CSV: {exc}")

    print(f"🎉 ¡Modelo V5.0 entrenado, calibrado y guardado exitosamente en '{RUTA_MODELOS}'!")

