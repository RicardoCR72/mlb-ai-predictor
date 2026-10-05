# 🏆 Oráculo Sports AI

Sistema cuantitativo y predictivo multideporte para análisis de valor, proyección de resultados, seguimiento de cuotas y auditoría de rendimiento en **MLB**, **NFL** y **Fútbol (Liga MX)**.

---

## 📁 Estructura del Proyecto

El proyecto está organizado siguiendo principios de arquitectura modular por dominio deportivo:

```text
deporte_definitivo/
│
├── .github/workflows/          # Automatizaciones CI/CD (GitHub Actions)
│   ├── bot_diario.yml          # Pipeline diario MLB, NFL y Telegram
│   ├── bot_flash.yml           # Actualización rápida de pitchers y lesiones
│   ├── bot_nfl_props.yml       # Captura de líneas y props NFL
│   ├── consultar_creditos.yml  # Consulta de saldos y marcadores
│   ├── nfl_predicciones.yml    # Proyección semanal de totales NFL
│   └── nfl_props.yml           # Modelo de jugadores / props NFL
│
├── .streamlit/                 # Configuración y secretos de la interfaz web
│
├── dashboard.py                # Entrada principal de la aplicación Web (Streamlit Hub)
│
├── core/                       # Núcleo de servicios compartidos
│   ├── __init__.py
│   ├── db.py                   # Conexión unificada MySQL/Aiven con soporte SSL
│   ├── constants.py            # Equipos, husos horarios y códigos estandarizados
│   ├── cache.py                # Caché local con TTL para The Odds API
│   └── alerts.py               # Envío de alertas y señales a Telegram
│
├── pages/                      # Vistas multipágina de la aplicación
│   ├── 0_💼_Bankroll.py        # Portafolio, Criterio de Kelly y auditoría de apuestas
│   ├── 1_⚾_MLB.py             # Centro de operaciones y predicciones MLB
│   ├── 2_🏈_NFL.py             # Centro de operaciones y props NFL
│   └── 3_⚽_Liga_MX.py         # Centro de análisis y modelos Liga MX
│
├── mlb/                        # Módulo principal de MLB (Moneyline, abridores, escáneres)
│   ├── __init__.py
│   ├── scraper.py              # Captura de cuotas Moneyline y Totales (DraftKings)
│   ├── actualizar_marcadores.py# Actualización de scores y memoria histórica
│   ├── escaner_pitchers.py     # Análisis de abridores (ERA global y últimas 3 salidas)
│   ├── escaner_lesiones.py     # Monitor médico de jugadores lesionados
│   ├── escaner_equipos.py      # Splits zurdos/derechos y fatiga de bullpen
│   ├── analista.py             # Detección de edges y mejores cuotas
│   ├── calcular_variables.py   # Ingeniería de características (rachas y descanso)
│   ├── preparar_datos.py       # Preparación y preprocesamiento del dataset histórico
│   ├── entrenar_v4.py          # Entrenamiento de red neuronal profunda V4
│   ├── oraculo.py              # Motor de inferencia y prueba de predicción
│   └── limpiar_y_recalcular_dataset.py # Limpieza y depuración del dataset
│
├── mlb_totales/                # Paquete especializado en Totales y Pitcheo MLB (V2)
│   ├── automatizar.py          # CLI de orquestación de tareas de totales
│   ├── core.py                 # Lógica de cálculo y modelos matemáticos
│   ├── ui_totales_mlb.py       # Componentes visuales de Totales MLB
│   ├── mercado.py              # Conexión con cuotas de mercado
│   └── ...
│
├── nfl/                        # Módulo especializado en NFL (Totales y Props)
│   ├── ui_totales.py           # Dashboard de Totales NFL
│   ├── ui_props.py             # Dashboard de Props de jugadores NFL
│   ├── actualizar_lineas_props.py # Extracción de líneas de jugadores
│   ├── predecir_semana_actual.py  # Predicción de partidos
│   ├── predecir_props_semana_actual.py # Predicción de props de jugadores
│   ├── evaluar_resultados.py   # Auditoría de resultados
│   └── ...
│
├── futbol_liga_mx/             # Módulo especializado en Fútbol (Liga MX)
│   ├── continuidad.py          # Evaluación de modelos y continuidad de temporada
│   ├── proveedor_api.py        # Conector con API-Football
│   └── modelo.py               # Lógica de estimación
│
├── data/                       # Almacenamiento centralizado de datos
│   ├── mlb/                    # Datasets históricos y procesados de MLB
│   │   ├── mlb_dataset_ia.csv
│   │   ├── mlb_dataset_ia_limpio.csv
│   │   ├── mlb_historial_22_26.csv
│   │   └── mlb_historico.csv
│   └── nfl/                    # Datos crudos, procesados, caché y predicciones NFL
│
├── modelos_mlb/                # Pesos y transformadores serializados de MLB
│   ├── pesos_mlb_v4.weights.h5 # Pesos de la red neuronal V4
│   ├── scaler_v4.pkl           # Escalador de variables continuas
│   └── columnas_v4.pkl         # Vector de características
│
├── modelos_nfl/                # Modelos calibrados y serializados de NFL
│
├── scripts/                    # Scripts de utilidad, reportes y respaldos
│   ├── reporte_deportes.py     # Envío de reporte consolidado a Telegram
│   └── respaldo_nube.py        # Volcado de BD y copia a la nube
│
├── requirements/               # Requerimientos segmentados por entorno
│   ├── requirements_futbol.txt
│   ├── requirements_mlb_actions.txt
│   ├── requirements_mlb_totales.txt
│   ├── requirements_mlb_v2_actions.txt
│   └── requirements_nfl_actions.txt
│
└── requirements.txt            # Dependencias principales del entorno raíz
```

---

## 🚀 Puesta en Marcha

### 1. Entorno Virtual e Instalación
```bash
python -m venv venv
# En Windows:
.\venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Ejecutar la Aplicación Web (Streamlit)
```bash
streamlit run dashboard.py
```
El panel estará disponible en `http://localhost:8501`, permitiendo navegar fluidamente entre el Hub Central, el módulo de **MLB** y el módulo de **NFL**.

### 3. Tareas CLI Principales

#### MLB
- **Capturar cuotas del día:** `python mlb/scraper.py`
- **Actualizar marcadores:** `python mlb/actualizar_marcadores.py`
- **Escanear abridores:** `python mlb/escaner_pitchers.py`
- **Escanear lesiones:** `python mlb/escaner_lesiones.py`
- **Reentrenar modelo V4:** `python mlb/entrenar_v4.py`

#### MLB Totales V2
- **Orquestación completa:** `python -m mlb_totales.automatizar --help`

#### NFL
- **Predecir semana actual:** `python nfl/predecir_semana_actual.py`
- **Actualizar props:** `python nfl/actualizar_lineas_props.py`

#### Notificaciones
- **Reporte diario en Telegram:** `python scripts/reporte_deportes.py`
