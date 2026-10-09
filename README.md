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

- El estado de los datos se consulta en el inicio y dentro de cada deporte. La página independiente **Estado y Modelos** se retiró de la navegación.
- Se recuperaron **306 resultados de fase regular 2025–26** de ESPN: 153 Apertura, 153 Clausura, 18 equipos y 17 rivales por equipo y torneo. Cada resultado conserva su identificador de evento. Se excluyen play-in, liguilla, partidos sin marcador válido y resultados pendientes. `cobertura_2025_26.json` contiene la auditoría y `confirmacion_2025_26.json` la evaluación adicional, sin reentrenar ni cambiar el modelo.
- El proveedor no inventa números de jornada a partir de fechas cercanas. La cobertura actual se valida con un escaneo desde el inicio del torneo, sin días fallidos ni eventos pendientes vencidos, y una huella de los resultados. El gate solo acepta esa evidencia si coincide con los datos y está vigente; conserva el bloqueo si falta. La actualización ESPN corre diariamente a las 06:00 CDMX.
- Bankroll prepara tablas **aditivas** de recibos, auditoría y migraciones. Las apuestas previas se conservan y se indexan una vez; no se inventa una bitácora retrospectiva. El registro y el cambio de estado se guardan en la misma transacción que su auditoría. El cambio de estado exige motivo, conserva monto/cuota/confianza y usa bloqueo de fila para no sobrescribir una liquidación concurrente.
- El control de duplicados compara fecha, selección, casa, monto, cuota e identidad del mercado. Un ticket distinto permite dos apuestas reales idénticas. Un reenvío con el mismo recibo no modifica la apuesta. **Exportar banca completa** descarga apuestas, auditoría, recibos y capital inicial en ZIP.
- Las evaluaciones conservan la distinción entre registros con hora y zona verificables anteriores al inicio e históricos sin esa evidencia. NFL actualmente almacena fecha de partido sin hora; se muestra como no verificable. Las métricas de apuestas dependen de los registros del usuario y no representan todas las predicciones del modelo. MLB V2 tiene además métricas de sus snapshots previos: ROI **teórico** de 1u, separado del ROI de dinero realmente apostado. La calibración MLB usa líneas de media carrera; los push no se convierten en derrotas.
- Prueba MySQL real del CI: base efímera `bankroll_ci` en MySQL 8; verifica reconexión, persistencia, idempotencia, duplicados, correcciones, rollback, exportación y saldo. **Validar conexión MySQL de producción** usa los secretos existentes en main y solo realiza consultas de lectura. No imprime credenciales ni registra apuestas ficticias en Aiven. Las tablas se crean al abrir Bankroll o ejecutar `scripts/actualizar_bankroll.py`; se requieren permisos CREATE/SELECT/INSERT/UPDATE.

Pruebas adicionales: `python -m unittest tests.test_integracion_deportes tests.test_observabilidad -v`. La prueba `tests.test_bankroll_mysql` solo se activa con `BANKROLL_MYSQL_TEST=1` y exige `DB_NAME=bankroll_ci`; no debe apuntarse a producción.

Aiven se comprobó desde Actions: conexión real MySQL 8.4.8 y TLS activo. El workflow **Preparar tablas aditivas de Bankroll** aplica la preparación e indexación de recibos, verifica que apuestas y capital previos se conserven y ejecuta el diagnóstico de lectura. Se dispara al publicar su archivo en main o manualmente; no inserta apuestas de prueba. La suite valida además que los entornos de job no usen contextos que GitHub todavía no ha inicializado (por ejemplo `runner`); la ruta del certificado NFL se exporta desde el paso de preparación mediante `GITHUB_ENV`.

### Actualizar resultados desde cada pestaña

Cada módulo tiene un botón de actualización manual: MLB (moneyline y Totales V2), NFL totales, NFL props, Liga MX y Bankroll. El botón consulta resultados oficiales, guarda los cambios, liquida las apuestas relacionadas y borra la caché de lectura antes de volver a mostrar las tablas. No captura nuevas cuotas, no consume créditos de TheOddsAPI, no reentrena modelos y no envía Telegram. NFL ejecuta únicamente sus evaluadores mediante procesos separados; reciben la configuración MySQL de la app sin modificar las variables globales del servidor ni mostrar credenciales.

El botón de Bankroll primero actualiza las fuentes de sus apuestas de modelo pendientes y después las liquida; las apuestas manuales conservan su gestión manual. Una actualización fallida aparece como parcial, con el paso afectado; los pasos ya guardados no se presentan como perdidos. Un candado por servicio evita ejecuciones simultáneas entre sesiones del mismo proceso Streamlit. El botón puede tardar mientras la fuente oficial publica y entrega resultados; los juegos en curso y jugadores sin estadística oficial siguen pendientes.

Liga MX consulta ESPN con hasta cuatro peticiones simultáneas, reutiliza el caché de finales y revisa hasta los próximos 14 días. Permite traer también partidos de hoy que ya finalizaron. La cobertura identifica el día en curso como parcial y esa evidencia caduca al cambiar de día: nunca se declara completo un día con partidos pendientes. Los CSV se actualizan en el servidor de la app; los workflows siguen manteniendo su copia en GitHub. MLB moneyline conserva sin liquidar las coincidencias ambiguas de doble cartelera; Totales V2 usa sus identificadores oficiales.


### Tarjetas, registro desde picks y filtros de rendimiento

Las tarjetas de MLB (moneyline y Totales V2), NFL (totales y props) y Liga MX comparten el orden partido/fecha, selección, probabilidad y cuota decimal. Cuando no hay hora verificada se indica explícitamente; las horas conocidas se muestran en CDMX.

El botón **Registrar en bankroll** abre un formulario, conserva la línea, selección y probabilidad de la tarjeta y requiere cuota tomada, monto y confirmación de la apuesta realizada. La casa se puede corregir y el ticket distingue dos apuestas reales iguales. Cancelar no guarda; un reintento conserva el recibo y la base impide duplicados. Liga MX requiere introducir la cuota. Los resultados históricos no ofrecen registro desde su tarjeta. Este flujo no solicita cuotas ni consume créditos.

Rendimiento admite todo el historial, hoy, últimos siete días (hoy y seis días anteriores), mes, temporada y rango inclusivo personalizado. Confianza, mercado y resultado se ofrecen donde la fuente contiene esos campos. En MLB y Bankroll la temporada se agrupa por año del partido; NFL y Liga MX usan su temporada propia. Los filtros se aplican antes de calcular métricas y exportar el historial; los límites de tarjetas solo afectan la presentación. En Bankroll el saldo y disponible globales se mantienen separados del beneficio y ROI de la muestra filtrada. La evaluación histórica de Liga MX sigue separada de las apuestas realizadas.


### Inicio y estado de datos en cada pestaña

El inicio muestra partidos registrados para hoy, picks guardados disponibles hoy, registros de deportes pendientes de revisión y banca disponible, además del calendario de siete días incluido hoy. NFL no tiene hora verificada y sus partidos se filtran por fecha/estado; MLB V2 y Liga MX usan sus horas UTC conocidas para excluir partidos iniciados. Moneyline MLB cuenta picks con confianza mínima de 74% y omite parejas ambiguas; NFL usa PICK/CANDIDATO; MLB V2 usa candidatos guardados; Liga MX cuenta sus dos selecciones O/U habilitadas, con cuotas por confirmar.

El panel junto a cada botón de actualizar muestra la fecha del último dato, la cantidad pendiente y hasta diez registros que requieren revisar resultados/calendario. Los pendientes de deportes corresponden a fechas anteriores o partidos marcados finalizados sin evaluación; Bankroll incluye todas las apuestas pendientes. No se suman esos registros como partidos únicos. Una fuente sin conexión aparece no disponible o parcial, y las demás permanecen visibles. La última modificación SQL sin zona verificada se identifica como tal; las horas UTC conocidas se convierten a CDMX. Antigüedad no equivale a fallo: puede haber días sin partidos.

El resumen se almacena en caché hasta 60 segundos y se vuelve a leer tras una actualización manual. «Volver a consultar el resumen» limpia únicamente esa caché. Abrir el inicio/estado solo consulta MySQL y archivos locales: no genera predicciones, no actualiza resultados, no liquida apuestas, no modifica capital y no consume créditos ni solicita cuotas. Los botones manuales de cada servicio conservan su función anterior.


### Evolución, exposición y presentación móvil

En Bankroll → Portafolio, las vistas «Evolución del saldo» y «Exposición pendiente» usan toda la banca. La curva suma beneficios de ganadas/perdidas/push por fecha del partido sobre el capital inicial actual, con pico y caída máxima absoluta/porcentual entre cierres diarios. No reconstruye movimientos intradía, depósitos, retiros ni fechas reales de liquidación; corregir estados o capital recalcula la curva. Pendientes y anuladas no suman beneficio. Si no hay liquidadas no se inventa una curva; porcentajes con saldo/pico no positivo se marcan no calculables.

La exposición muestra monto pendiente por deporte y encuentro, concentración sobre todo el dinero comprometido y porcentaje del saldo. Totales y props NFL se agrupan por game_id común. MLB moneyline y V2 conservan sus identificadores de origen y las dobles carteleras se distinguen; apuestas sin id se agrupan aproximadamente por fecha y nombre exacto, con etiqueta visible. No se interpreta esa concentración como probabilidad conjunta o correlación. Las descargas incluyen toda la exposición aunque la lista visible esté limitada.

El historial de Bankroll abre en tarjetas, con límite de presentación y opción de tabla/columnas visibles; la descarga mantiene la muestra filtrada completa. Los filtros de rendimiento están en un panel plegable y conservan sus valores. A 760 px o menos, columnas de tarjetas/métricas se apilan, los botones tienen área táctil y las pestañas permiten desplazamiento. Inicio presenta disponibilidad y calendario en tarjetas, dejando las tablas completas como opción. No cambia modelos, cuotas, registros ni la forma de liquidar.

CI comprueba cálculos y controles con unittest/AppTest y ejecuta una prueba de navegador Chrome a 390 y 1280 px con datos sintéticos, sin credenciales ni acceso a APIs: tarjetas en una/dos columnas y vista de tabla sin desbordar la página.


### NFL: predicciones del día y créditos

El botón «Actualizar predicciones NFL de hoy» consulta primero el calendario de eventos (0 créditos), muestra los partidos sin iniciar y el consumo máximo, y actualiza totales y props del día de Ciudad de México. DraftKings es la única casa; los seis mercados de props cuestan hasta 6 créditos por evento (domingo: hasta 6 × partidos dominicales aún sin iniciar). Totales sigue usando las líneas del calendario NFL/nflverse, sin una consulta adicional de cuotas de The Odds API. Cada pulsación puede pagar otra captura; el botón de resultados conserva su operación gratuita. La clave se configura como `ODDS_API_KEY` u `odds_api_key` en los secretos de la página, además de los secretos de Actions.

Los workflows de cuotas deciden si capturar mediante `github.event.schedule`, no mediante el día UTC del runner. TNF/MNF se intentan a las 14:00 y 16:00 CDMX; domingo a las 06:00, 10:00 y 16:00, incluyendo partidos internacionales tempranos. Los retrasos de GitHub Actions pueden hacer que un intento llegue después del kickoff: esos partidos se omiten para no registrar cuotas en vivo como prepartido. Viernes y martes liquidan sin pedir cuotas.

Toda consulta pagada filtra por fecha México e inicio verificado antes de pagar; también verifica que el evento y el juego NFL coincidan en equipos y fecha. La captura automática es una por partido **en ese día**, no una por toda su historia. Una línea de un jueves anterior no bloquea la captura del domingo. `nfl_capturas_odds` conserva consultas solicitadas/recibidas y créditos reportados, incluso si la línea no cambia; un candado MySQL evita capturas simultáneas entre Actions y la web. Si una petición falla y no puede confirmarse el cobro, no se informa falsamente un consumo de cero ni se reintenta automáticamente. Se respeta la reserva de 120 créditos. Los presupuestos mostrados son máximos; el consumo real usa `x-requests-last` y el saldo usa `x-requests-remaining`.

Incidente TNF del 8 de octubre de 2026: el cron de las 22:00 UTC arrancó a las 01:50 UTC del 9 de octubre (19:50 CDMX del jueves). La decisión anterior por `date -u` seleccionó viernes y `HORAS=0`, por lo que omitió la captura aunque regeneró 725 proyecciones. Totales sí se ejecutó antes, a las 13:07 CDMX, pero regeneró los 15 partidos pendientes de la semana. La selección diaria nueva corrige ambas rutas. Las predicciones nuevas del día no sobrescriben el CSV semanal previo.


### Rendimiento de totales NFL

Los filtros de rendimiento se muestran abiertos y permiten combinar periodo, temporada, confianza, semana, mercado (OVER/UNDER), resultado (GANADA/PERDIDA/PUSH) y partido. Todos se aplican antes de balance, acierto, beneficio, ROI, comparación por mercado, resumen semanal, tarjetas y descarga del rendimiento. La comparación por mercado ordena OVER y UNDER por ROI de la muestra filtrada y usa una unidad por pick; no representa apuestas reales. Si se filtra solo Ganada o Perdida, las métricas describen solo ese subconjunto. La página Estado y Modelos y sus enlaces se retiraron; los indicadores de datos permanecen en el inicio y en cada deporte.


### Rendimiento en unidades y banca real

MLB Moneyline, MLB Totales V2 y NFL Totales/Props simulan **1 unidad por pick**. Moneyline ya no pondera el monto según la confianza: ganada aporta cuota decimal menos 1, perdida −1 u. Tarjetas, métricas, curva y CSV de Moneyline usan esa misma simulación; la curva muestra beneficio acumulado, no saldo de dinero real. Los filtros de confianza se conservan.

En **Bankroll → Portafolio → Valor de 1 unidad (MXN)** se guarda una denominación común (valor inicial 100 MXN) en la tabla aditiva `bankroll_unidad`, con auditoría transaccional. No cambia capital, montos, cuotas ni beneficios de apuestas anteriores. Las equivalencias de toda la banca se calculan con el valor actual: monto/unidad y beneficio/unidad. Historial y CSV muestran pesos y unidades; la exportación completa conserva los pesos originales y el valor de la unidad en `config.json`.

Las equivalencias monetarias de las simulaciones MLB/NFL usan ese mismo valor mediante una consulta de lectura. Si no está disponible, se mantienen las unidades y no se inventa una conversión en pesos. Cambiar la unidad no cambia el ROI. Liga MX mantiene su evaluación estadística sin fabricar rentabilidad donde faltan cuotas históricas; sus apuestas realizadas sí aparecen en pesos y unidades en Bankroll.
