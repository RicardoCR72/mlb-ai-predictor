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

La consulta está disponible sin acceso de operación. Para habilitar escrituras
y acciones que consumen créditos, configura **ORACLE_ADMIN_PASSWORD** en Secrets
y abre **Acceso administrativo** en la barra lateral. Se admiten como
compatibilidad `NFL_ADMIN_PASSWORD` y `nfl_admin_password` ya configurados.
Sin contraseña administrativa se mantiene el modo consulta; no hay contraseña
predeterminada. La comprobación se repite en el servidor antes de ejecutar.

El acceso administrativo no sustituye autenticación de suscriptores. Antes de
vender acceso se necesita una identidad por usuario y control de suscripción.

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
- `core/permisos.py`: autorización de operación.
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
autorizada. Requiere CREATE/SELECT/INSERT/UPDATE. Conserva identificador, servicio,
estados, pasos y respuesta; no almacena contraseñas ni claves de API.

Una clave única evita dos solicitudes activas del mismo servicio. Cada servicio
obtiene un candado MySQL incluso mientras espera turno; como máximo tres tareas
ejecutan trabajo pesado simultáneamente. El navegador puede recargarse mientras
se ejecuta. El estado se consulta desde MySQL y solo se sondea periódicamente
mientras hay trabajo activo. Al completar, se invalidan las lecturas afectadas.

Los workers viven en el proceso Streamlit: un reinicio puede interrumpirlos.
Si una ejecución queda huérfana, se identifica después de cinco minutos sin
candado. No se reintentan cuotas automáticamente: revisar resultados y consumo
antes de solicitar otra ejecución. Para escalar a varios servidores se puede
reemplazar este ejecutor conservando el contrato persistente.

La captura pagada NFL mantiene el alcance del día CDMX, DraftKings, reserva y
candado de crédito existente. Cada nueva solicitud manual puede consumir
créditos; los workflows conservan su deduplicación diaria por partido.

## Pruebas y entornos

El CI ejecuta unittest/AppTest, MySQL desechable y navegador a varios tamaños.
Los fixtures de navegación no solicitan APIs deportivas ni usan datos privados.
`tests/test_arquitectura.py` verifica permisos antes de conectar, vistas reales,
fuente original compartida, estado persistente y corte CDMX.

MySQL de pruebas exige `BANKROLL_MYSQL_TEST=1` y `DB_NAME=bankroll_ci`; nunca debe
apuntar a producción. No se insertan apuestas ficticias en Aiven.

Streamlit está fijado a la versión comprobada 1.66.0. Las dependencias MLB V2
usan sklearn 1.8.0; el entorno web/NFL usa 1.9.1 según sus artefactos existentes.
Son entornos separados: no se cambia la versión de un modelo serializado sin
verificar compatibilidad. El entorno virtual local no se versiona.
