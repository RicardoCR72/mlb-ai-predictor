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



## Integración de apuestas realizadas y correcciones

- Bankroll usa `bankroll_apuestas` y `bankroll_config` en el mismo MySQL del panel. Las tablas se crean de forma aditiva al abrir la página o ejecutar `python scripts/actualizar_bankroll.py`. El usuario de MySQL necesita permiso `CREATE TABLE` para la primera ejecución.
- Registra manualmente una apuesta o selecciona una predicción de MLB (moneyline/totales), NFL (totales/props) o Liga MX. Confirma el monto y la cuota decimal realmente tomada. Las predicciones por sí solas no cuentan como apuestas ni modifican tu saldo.
- Cada apuesta conserva su cuota, línea, confianza y referencia del partido. Las liquidaciones usan la selección original aunque el modelo se actualice. Puedes cambiar el estado de una apuesta en «Registrar / Gestionar»; un resultado manual cerrado no se sobrescribe automáticamente.
- El saldo es capital inicial más beneficio liquidado; el disponible descuenta montos pendientes. El ROI se calcula sobre montos liquidados (ganadas, perdidas y push); pendientes y anuladas quedan fuera.
- El CSV anterior contenía ejemplos y ya no se usa como banca real. Si tienes apuestas reales guardadas allí, conserva una copia y regístralas en el portafolio MySQL. No se importan ejemplos ni se descartan apuestas existentes en MySQL.
- Los workflows MLB y NFL liquidan las apuestas registradas después de actualizar resultados. También se liquidan al abrir Bankroll. Juegos MLB que requieren revisión de reglas y props sin estadísticas oficiales permanecen pendientes para revisión manual.
- NFL usa DraftKings exclusivamente para captura y selección de props. El workflow manual consulta cuotas únicamente con `actualizar_odds=true`, una vez, con reserva de 120 créditos.
- Liga MX comparte variables e inferencia entre pantalla y CLI; su historial no usa resultados futuros. El workflow intenta recuperar 2025–26 desde fuentes gratuitas, conserva resultados ante respuestas parciales y refresca eventos no finalizados. Si la temporada sigue incompleta, muestra el motivo del bloqueo sin generar recomendaciones ni consumir cuotas. No se reentrena el modelo congelado.
- Las pruebas de integración corren en pull requests y cambios en `main`, sin credenciales ni solicitudes a APIs deportivas.

### Estado, auditoría y evaluación (octubre 2026)

- **Estado y Modelos** muestra fechas de datos/cuotas, ejecuciones de GitHub Actions y el último éxito disponible. Consulta GitHub con caché de cinco minutos y no consume créditos de TheOddsAPI. Si una tabla o API no está disponible, lo indica sin ocultar las otras integraciones.
- Se recuperaron **306 resultados de fase regular 2025–26** de ESPN: 153 Apertura, 153 Clausura, 18 equipos y 17 rivales por equipo y torneo. Cada resultado conserva su identificador de evento. Se excluyen play-in, liguilla, partidos sin marcador válido y resultados pendientes. `cobertura_2025_26.json` contiene la auditoría y `confirmacion_2025_26.json` la evaluación adicional, sin reentrenar ni cambiar el modelo.
- El proveedor no inventa números de jornada a partir de fechas cercanas. La cobertura actual se valida con un escaneo desde el inicio del torneo, sin días fallidos ni eventos pendientes vencidos, y una huella de los resultados. El gate solo acepta esa evidencia si coincide con los datos y está vigente; conserva el bloqueo si falta. La actualización ESPN corre diariamente a las 06:00 CDMX.
- Bankroll prepara tablas **aditivas** de recibos, auditoría y migraciones. Las apuestas previas se conservan y se indexan una vez; no se inventa una bitácora retrospectiva. El registro y el cambio de estado se guardan en la misma transacción que su auditoría. El cambio de estado exige motivo, conserva monto/cuota/confianza y usa bloqueo de fila para no sobrescribir una liquidación concurrente.
- El control de duplicados compara fecha, selección, casa, monto, cuota e identidad del mercado. Un ticket distinto permite dos apuestas reales idénticas. Un reenvío con el mismo recibo no modifica la apuesta. **Exportar banca completa** descarga apuestas, auditoría, recibos y capital inicial en ZIP.
- El panel separa registros con hora y zona verificables anteriores al inicio de los históricos sin esa evidencia. NFL actualmente almacena fecha de partido sin hora; se muestra como no verificable. Las métricas de apuestas dependen de los registros del usuario y no representan todas las predicciones del modelo. MLB V2 tiene además métricas de sus snapshots previos: ROI **teórico** de 1u, separado del ROI de dinero realmente apostado. La calibración MLB usa líneas de media carrera; los push no se convierten en derrotas.
- Prueba MySQL real del CI: base efímera `bankroll_ci` en MySQL 8; verifica reconexión, persistencia, idempotencia, duplicados, correcciones, rollback, exportación y saldo. **Validar conexión MySQL de producción** usa los secretos existentes en main y solo realiza consultas de lectura. No imprime credenciales ni registra apuestas ficticias en Aiven. Las tablas se crean al abrir Bankroll o ejecutar `scripts/actualizar_bankroll.py`; se requieren permisos CREATE/SELECT/INSERT/UPDATE.

Pruebas adicionales: `python -m unittest tests.test_integracion_deportes tests.test_observabilidad -v`. La prueba `tests.test_bankroll_mysql` solo se activa con `BANKROLL_MYSQL_TEST=1` y exige `DB_NAME=bankroll_ci`; no debe apuntarse a producción.
