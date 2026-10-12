# Comparación temporal de yardas de recepción

## Decisión

Mantener el predictor actual. La alternativa de recepciones × yardas por recepción no confirma una mejora suficiente. Conservar como candidato experimental el ajuste de confianza con temperatura 1.25; no está conectado a la generación de picks ni modifica sus probabilidades en producción.

Se ejecutó el experimento con los datos del commit `e8e0392db28569c85d81e0192f1c7970ec815e40`. Los hashes de entradas, la configuración y la decisión están en `reports/nfl_yardas_validacion/decision.json`. El script no consulta APIs ni bases de datos y no escribe modelos.

## Proyecciones

La referencia utiliza las predicciones fuera de muestra que generaron los modelos entrenados en 2012–2023, no los archivos joblib de producción reentrenados después. La metadata existente identifica la variante control, sin variables explícitas de lesiones, tanto en recepciones como en yardas. Por ello, el efecto directo de redistribución por lesiones no queda demostrado en el predictor actual; los escenarios de lesión pueden coincidir cuando el modelo no utiliza esas variables.

La alternativa multiplica las recepciones predichas por un ratio de yardas por recepción. El ratio combina la media de posición calculada exclusivamente con 2012–2023 y el ratio rolling-5 del jugador. Se prueban cinco mezclas y un límite opcional: cuando la suma de recepciones predichas de los jugadores disponibles en la muestra supera el promedio previo de recepciones del equipo, se reduce proporcionalmente. Es un límite de coherencia, no una nueva predicción de volumen total del equipo.

Los parámetros se eligen únicamente por MAE de 2024 en jugadores con al menos tres targets previos promedio y sin estado out/doubtful, siguiendo la elegibilidad de producción. Ganó 25% del ratio reciente y 75% de la referencia por posición, con límite de equipo. 2025 y 2026 no seleccionan parámetros.

| Temporada | Jugadores-partido elegibles | MAE actual | MAE alternativa |
| --- | ---: | ---: | ---: |
| 2024, selección | 2,388 | 23.3865 | 23.1043 |
| 2025, confirmación | 2,280 | 23.2058 | 23.1238 |
| 2026, evaluación posterior | 265 | 24.0240 | 24.0841 |

En 2025 la diferencia alternativa − actual es −0.0821 yardas, con intervalo de remuestreo por partido del 95% de −0.3310 a +0.1550. Incluye cero: no confirma una ventaja. El RMSE tampoco mejora en 2025 ni 2026. Se incluyen también las métricas de toda la muestra en `point_metrics.csv`, para evitar confundirla con el subconjunto elegible.

## Probabilidades

Se reproduce la probabilidad empírica de residuales de 2024 por posición, con referencia global cuando hay menos de 100 casos. Para elegir el ajuste se divide 2024 por fecha: la primera parte ajusta y la segunda, desde el 10 de noviembre, selecciona. Se comparan el cálculo actual, temperaturas 1.25/1.5/2 y Platt. Luego se ajusta el candidato elegido con 2024 completo y se comprueba en 2025 y 2026.

La temperatura 1.25 suaviza los log-odds: una probabilidad de 80% queda aproximadamente en 75.2%. El ajuste es simétrico para OVER y UNDER. No cambia el punto proyectado.

| Temporada | Brier actual | Brier candidato | Logloss actual | Logloss candidato |
| --- | ---: | ---: | ---: | ---: |
| 2025 | 0.153257 | 0.151476 | 0.474913 | 0.464881 |
| 2026 | 0.157352 | 0.155898 | 0.496064 | 0.482737 |

Menor es mejor. La diferencia de logloss 2025 es −0.01003, con intervalo por partido del 95% de −0.01332 a −0.00693.

Estas métricas utilizan una cuadrícula fija de **líneas sintéticas**, de 10.5 a 100.5 yardas: no son momios ni líneas históricas de DraftKings. Cada jugador se evalúa en las mismas siete líneas y las dependencias se agrupan por partido. Es una comprobación de probabilidades, no una demostración de ROI. `historical_market_roi` queda explícitamente sin dato.

## Contraste con los 78 picks exportados

El candidato elegido sin utilizar 2026 se aplica después a las probabilidades guardadas del CSV del usuario. El Brier conjunto pasa de 0.26254 a 0.25292. Empeora en la semana 3 y mejora en las semanas 4 y 5; no corrige por sí solo la caída.

Una reproducción retrospectiva de los mismos picks, conservando lado, cuota y proyección y aplicando los criterios actuales de confianza y EV, elimina un ganador en la semana 3 y un perdedor en la 5. El resultado conjunto cambia apenas de +7.242 a +7.349 u, con 76 en vez de 78 picks. Los registros originales no están verificados, por lo que esta reproducción está etiquetada como **no verificada** y no se usa para elegir parámetros ni autorizar el cambio en producción.

## Límites y siguiente comprobación

- La muestra fuera de muestra de 2026 termina el 21 de septiembre. No contiene la semana 5; el CSV de 78 picks es una fuente posterior distinta y no reemplaza aquella muestra.
- El proceso anterior de elección control/lesiones consultó también 2025. La referencia heredada no permite llamar a toda la comparación una prueba completamente ciega; los parámetros nuevos sí se seleccionaron sin 2025/2026.
- Faltan líneas y cuotas históricas verificadas de 2024–2025 para comparar cantidad de picks y ROI real.
- Antes de activar la temperatura candidata, comprobarla con nuevas publicaciones conservadas, sus líneas y cuotas, sin modificar el criterio basándose en la semana 5. El experimento no despliega automáticamente ningún candidato.

## Reproducción

Desde la raíz del repositorio:

```bash
python nfl/validar_yardas_recepcion.py --source-ref e8e0392db28569c85d81e0192f1c7970ec815e40
```

Opcionalmente agregar `--audit-file auditoria_yardas_recepcion.csv` para el contraste posterior de picks guardados. Los argumentos `--dataset`, `--predictions` y `--output` permiten trabajar sobre una copia de las entradas congeladas. Los resultados registran los hashes de las entradas efectivamente utilizadas.
