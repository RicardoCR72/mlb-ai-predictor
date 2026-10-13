# Combinadas por confianza

La página **Combinadas** reúne moneyline y totales MLB, totales y seis mercados de
props NFL, y totales Over/Under 2.5 Liga MX. Ordena por la probabilidad individual
del modelo. Los modelos de distintos deportes y mercados pueden tener distinta
calibración: este orden no demuestra rentabilidad ni garantiza aciertos.

Permite filtrar por deporte, confianza mínima y fecha (hoy en CDMX o próximos
siete días), elegir entre dos y cinco selecciones, editar y descargar la propuesta.
La propuesta toma los picks elegibles de mayor confianza de partidos distintos.
Si hay menos partidos disponibles, no rellena la propuesta con picks inferiores
al mínimo elegido. La fecha y el inicio se vuelven a comprobar en cada ejecución.

## Datos y elegibilidad

Todas las consultas SQL son SELECT. NFL usa el calendario parquet guardado y su
hora Eastern convertida a UTC; no interpreta una fecha sin hora como medianoche.
MLB totales usa `start_utc` del registro. Moneyline solo hereda esa hora cuando
existe un único encuentro de esos equipos y fecha; los registros ambiguos de
doble cartelera se excluyen. Liga MX usa el modelo congelado y archivos existentes
con el mismo adaptador que su pestaña.

Se excluyen partidos iniciados, probabilidades no válidas y datos fuera del
intervalo. Los picks con hora sin verificar, estado `REVISAR LESION` o captura de
cuota conocida de más de 24 horas (o futura por más de cinco minutos) aparecen
en el ranking, pero no entran en la propuesta automática ni en el editor.
La ausencia de una alerta no certifica la salud del jugador.

Solo se permite una selección por encuentro, incluso entre mercados o modelos.
Los partidos se identifican conservadoramente por deporte, fecha CDMX y equipos;
dos juegos de una doble cartelera no se combinan. El editor también valida esto.

Las fuentes normalizan explícitamente las probabilidades: NFL totales y MLB
moneyline dividen los porcentajes entre 100; NFL props, MLB totales y Liga MX ya
son fracciones. No se adivina la escala por el tamaño de cada número.

## Estimaciones y cuotas

La estimación conjunta es el producto de probabilidades **bajo independencia**,
no una probabilidad conjunta calibrada. Una selección por partido reduce la
dependencia directa, pero no establece independencia estadística.

La cuota decimal orientativa solo se calcula cuando todas las selecciones tienen
cuota válida y pertenecen a la misma casa verificada. NFL props y MLB totales
verifican DraftKings en sus registros. Las fuentes actuales de NFL totales y MLB
moneyline no prueban la casa ni la fecha de captura; se conservan sus cuotas
individuales sin atribuirlas a una casa. Liga MX no guarda cuotas: su selección
puede formar parte de la propuesta, pero deja el precio combinado pendiente.
No se inventan cuotas, beneficios ni pagos. El precio final debe confirmarse en
la casa; no se soportan combinadas del mismo partido ni su fórmula especial.

**Recargar picks guardados** invalida únicamente la caché de lectura (60 segundos).
No consulta APIs, consume créditos, genera nuevas predicciones, realiza apuestas
ni registra movimientos en Bankroll. La sección tampoco modifica los modelos.

## Validación

`tests.test_combinadas` cubre ranking, independencia de mercados al identificar
partidos, cuotas y casas, lesiones, horas ausentes, fechas CDMX, partidos iniciados,
cuotas antiguas, probabilidades inválidas, fallos parciales y edición en Streamlit.
La prueba de navegador comprueba la propuesta y sus tarjetas a 390 y 1280 px.
