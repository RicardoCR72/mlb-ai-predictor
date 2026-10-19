# Oráculo Sports AI

Panel Streamlit para consultar publicaciones MLB, NFL y Liga MX, resultados,
rendimiento simulado y calibración. Los registros originales y los históricos
sin hora verificable se distinguen explícitamente.

## Ejecutar

Python 3.12:

```bash
python -m venv venv
pip install -r requirements.txt
streamlit run dashboard.py
```

## Acceso y configuración

MySQL utiliza `core/db.py`: Secrets de Streamlit, sección `mysql` o variables
`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`/`DB_PASS`, `DB_NAME`. Los certificados
Aiven existentes siguen admitidos. No deben incluirse credenciales en Git.

Los botones de actualización están disponibles sin inicio de sesión administrativo.
Las acciones se solicitan explícitamente desde cada sección; abrir una página no
inicia generación de predicciones ni capturas de cuotas.

## Navegación

- Inicio: agenda y disponibilidad de datos guardados.
- MLB: picks publicados, totales y rendimiento por mercado.
- NFL: totales, props, lesiones y rendimiento.
- Liga MX: próximos partidos, resultados y cobertura histórica.
- Rendimiento: comparación y análisis avanzado.
- Calibración: confianza frente a acierto, muestra y evaluación temporal.

Bankroll, Comparador independiente y Combinadas no forman parte de la navegación.
Los registros y utilidades históricas de esas funciones se conservan; actualizar
resultados deportivos no liquida Bankroll como efecto secundario.

## Arquitectura

- `pages/`: composición y navegación.
- `core/confianza_datos.py`: lectura común de publicaciones/resultados.
- `core/comparador.py`: normalización y registros legacy identificados.
- `core/ui_historial_publicado.py`: filtros, métricas y tarjetas de rendimiento.
- `mlb/moneyline_service.py`: generación Moneyline fuera de la interfaz.
- `nfl/repositorio.py`: consultas y normalización SQL NFL.
- `futbol_liga_mx/repositorio.py`: CSV con invalidación por versión del archivo.
- `core/trabajos.py`: ejecuciones manuales persistidas y exclusión MySQL.
- `assets/ui.css` y `.streamlit/config.toml`: tema y componentes comunes.

Consultar MLB no ejecuta TensorFlow ni guarda nuevas predicciones. **Generar
predicciones MLB con cuotas guardadas** ejecuta Moneyline y Totales sin pedir
cuotas nuevas. Requiere modelos, históricos y líneas válidas ya disponibles.
El workflow `mlb_publicaciones.yml` hace lo mismo después del proceso diario
MLB exitoso de `main`; también puede ejecutarse manualmente. No usa The Odds API.
Los pesos y calibradores permanecen congelados. La huella Moneyline incorpora
el código del servicio, por lo que la extracción del servicio puede producir
una nueva versión técnica aun cuando sus pesos y fórmulas no cambien.

## Publicaciones y resultados

Rendimiento y Calibración comparten originales cuando existen. Los registros
legacy se mantienen con hora no verificable; no se reconstruyen picks al abrir
el historial. Cada juego/modelo conserva su primera publicación. Totales MLB
usa su probabilidad original en rendimiento y probabilidad condicionada a no
push para el diagnóstico binario; ambos cálculos se identifican.

Las nuevas publicaciones de Totales NFL guardan selección, línea, confianza,
cuota del predictor, inicio UTC y reloj de publicación MySQL. Se rechazan
publicaciones posteriores al inicio y los reintentos no sobrescriben originales.
No se certifican retrospectivamente registros viejos. La cuota NFL Totales es
la del predictor/nflverse, no una nueva captura de DraftKings por The Odds API.

El día operativo es CDMX; instantes conocidos se almacenan/interpretan en UTC.
Las zonas históricas de captura de cuotas conservan su interpretación original,
en particular `MLB_ODDS_CAPTURE_TIMEZONE=America/Mazatlan`.

## Actualizaciones manuales

`oracle_trabajos` es una tabla aditiva creada al solicitar la primera ejecución
manual. Requiere CREATE/SELECT/INSERT/UPDATE. Conserva identificador, servicio,
estados, pasos y respuesta; no almacena contraseñas ni claves de API.

Una clave única evita dos solicitudes activas del mismo servicio. La solicitud y
su payload se guardan en MySQL. Cada tarea se ejecuta en un proceso separado de
Streamlit; el navegador y sus reruns no son propietarios del trabajo. Candados
MySQL por servicio y tres permisos de capacidad global coordinan los procesos.

Por defecto se lanza un proceso independiente por solicitud. Para un servidor
supervisado, configurar `ORACLE_WORKER_MODE=external` en la web y ejecutar
`python -m core.application.job_worker` como servicio separado. `--once` procesa
un lote; `--job ID` procesa una solicitud. No se reejecutan trabajos que ya
pasaron a `ejecutando`: una captura interrumpida requiere revisar el consumo.
Un reinicio del contenedor puede terminar procesos locales; para continuidad
ante reemplazos del host se necesita desplegar el worker externo. La cola
permanece en MySQL. No se almacenan credenciales en el payload ni en Git.

Migraciones aditivas: `python -m scripts.migrate`. Los esquemas operativos NFL y
de trabajos tienen registro de versiones, checksum y candado MySQL. Las
instalaciones anteriores incorporan la columna payload sin borrar sus tareas.
No se modifican pesos ni versiones de los modelos al aplicar migraciones.

La captura pagada NFL mantiene el alcance del día CDMX, DraftKings, reserva y
candado de crédito existente. El botón selecciona por defecto solo juegos que inician en las próximas dos horas,
con reloj CDMX; sin juegos próximos no carga otras tandas. La casilla «Todos los
partidos de hoy» permite ampliar explícitamente el alcance. La lista previa
muestra horarios y presupuesto. Totales y props respetan la misma ventana.
La ejecución vuelve a validar las horas antes de pedir cuotas. Los procesos
automáticos también usan dos horas, incluyendo una captura dominical intermedia.
Web y workflows omiten capturas exitosas de las últimas dos horas por partido.
Las capturas anteriores pueden renovarse. Una solicitud con cobro incierto se
bloquea durante el día y necesita revisión; nunca se reintenta automáticamente.
La inferencia y los candidatos activos rechazan cuotas con más de dos horas,
con fecha futura o sin hora verificable.
Los picks ya guardados continúan visibles; el alcance controla qué se actualiza.
Totales usa la línea de nflverse, no cuotas nuevas de The Odds API.

## Pruebas y entornos

El CI ejecuta unittest/AppTest, MySQL desechable y navegador a varios tamaños.
Los fixtures de navegación no solicitan APIs deportivas ni usan datos privados.
`tests/test_arquitectura.py` verifica servicios permitidos, acciones explícitas, vistas reales,
fuente original compartida, estado persistente y corte CDMX.

MySQL de pruebas exige `BANKROLL_MYSQL_TEST=1` y `DB_NAME=bankroll_ci`; nunca debe
apuntar a producción. No se insertan apuestas ficticias en Aiven.

Streamlit está fijado a la versión comprobada 1.66.0. Las dependencias MLB V2
usan sklearn 1.8.0; el entorno web/NFL usa 1.9.1 según sus artefactos existentes.
Son entornos separados: no se cambia la versión de un modelo serializado sin
verificar compatibilidad. El entorno virtual local no se versiona.

## Capas y contratos

- `core/domain/`: contratos, probabilidades en 0–1, cuotas y vigencia; sin UI ni SQL.
- `core/infrastructure/`: conexión MySQL, consultas y migraciones.
- `core/application/`: solicitudes, ejecución y orquestación NFL.
- `nfl/services/`: elegibilidad, calendario y cálculo del modelo.
- `nfl/persistence/`: calendario local y escrituras de totales/props.
- `nfl/providers/`: adaptadores HTTP.
- `pages/` y módulos `ui_`: presentación mediante funciones `render()`.

`core.db`, `core.trabajos` y `core.nfl_creditos` son fachadas de compatibilidad:
conservan importaciones existentes sin duplicar implementaciones. Las tarjetas
usan primitivas de cuotas independientes de Bankroll. Los repositorios NFL leen
una temporada (seleccionable) y limitan publicaciones a los juegos consultados;
los históricos completos de Rendimiento conservan su lector separado.

La base histórica conserva el formato original: totales NFL en porcentaje,
props NFL en fracción. Los adaptadores declaran la escala explícitamente, sin
inferirla por la mediana. Un contrato validado impide publicar totales fuera de
0–1, con cuota inválida o después del inicio. Horarios desconocidos no se
presentan como oportunidades prepartido verificadas.

`bot_nfl_props.yml` es el único propietario de la programación NFL y liquida
resultados de totales y props. Los workflows anteriores quedan disponibles solo
manualmente; no son otros planificadores automáticos. La web mantiene sus
acciones explícitas. El entorno virtual MLB se reconstruye con sus requirements
y ya no forma parte del seguimiento de Git.

Ver [detalle de los 15 cambios](docs/arquitectura_15_mejoras.md).

## Devoluciones por cancelación o ausencia

Los partidos MLB confirmados como cancelados sin marcador se registran como
PUSH/devolución al actualizar resultados. Se verifica la identidad del partido;
una doble cartelera ambigua no se liquida por aproximación. Un aplazado sin marcador
con reprogramación oficial para otro día devuelve el pick de la fecha original.
Un suspendido, un retraso del mismo día o un partido ausente del feed sigue pendiente.

Los props NFL de un partido finalizado se devuelven cuando falta la estadística
del jugador y existe evidencia explícita de ausencia: cero snaps, reporte Out
o estado inactivo del roster semanal del mismo jugador/equipo/semana. Una
participación positiva contradice una designación inactiva anterior. Cero yardas
en una estadística oficial de un jugador que participó se evalúa normalmente.
Si no hay evidencia suficiente o la fuente todavía no publica los datos, sigue
pendiente. No se inventan estadísticas ni se consulta The Odds API para liquidar.

`oracle_devoluciones` conserva motivo, fuente y evidencia de forma idempotente.
El historial aplica la devolución sin alterar la publicación original: muestra
PUSH, 0 unidades y el motivo; no cuenta como ganada ni perdida. El resumen deja
de listar esas selecciones como pendientes. Las devoluciones de un jugador no
se aplican a compañeros ni al total del partido. Las apuestas reales de cada
casa deben seguir sus propias liquidaciones; esto es el registro del modelo.

En Rendimiento, cada pick pendiente de MLB/NFL permite **Registrar devolución**.
El usuario selecciona el motivo y confirma **Guardar como push**. Se conserva
la confirmación manual en la auditoría; no se presenta como evidencia oficial,
no se inventan yardas ni marcadores y se invalida la caché tras guardarla.
