# Diagnóstico por mercado

En Calibración, “Diagnóstico por mercado y versión” resume los resultados
decididos por deporte, mercado, versión y procedencia, sin mezclar fuentes.
Incluye picks, partidos distintos, confianza media, acierto observado,
diferencia, intervalo por partido, Brier y log-loss. La diferencia se calcula
como acierto menos confianza; una diferencia negativa es descriptiva, no una
prueba de que el modelo empeoró o una autorización para ajustar porcentajes.

Los umbrales de 100 picks y 30 partidos solo describen amplitud de muestra.
Los intervalos remuestrean juegos completos para considerar props relacionados.
La preparación completa IDs ausentes por fila cuando se combinan fuentes y
no añade dos veces el prefijo del deporte al preparar un marco ya preparado.

El workflow `diagnostico_confianza.yml` ejecuta el mismo diagnóstico por lectura
y guarda un JSON descargable en el artefacto `diagnostico-confianza`. Las fuentes
que no se pudieron leer aparecen explícitamente. No consulta cuotas ni envía
mensajes ni cambia probabilidades, predicciones o modelos en producción.

La prueba temporal conserva el método existente: datos originales verificables
y elegibles, cortes cronológicos completos 60/20/20, mínimos por bloque y
selección sin observar la prueba final. Si no puede ejecutarse, explica el
motivo. Incluso un resultado favorable permanece experimental; no se aplica
automáticamente ni demuestra rentabilidad futura. Liga MX reconstruida y
registros antiguos sin hora comprobable solo sirven para descripción.
