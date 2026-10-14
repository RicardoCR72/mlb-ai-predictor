# Calibración de confianza

La página **Calibración** evalúa probabilidades originales por deporte, mercado,
versión y procedencia. No tiene un filtro Ganada/Perdida: seleccionar solamente
ganadas produciría un acierto engañoso del 100%. Los rangos son de diez puntos,
incluyen probabilidades 0 y 1 y muestran picks, partidos, probabilidad media,
acierto observado, diferencia, Brier, log-loss y un intervalo descriptivo del
acierto obtenido por remuestreo de partidos (400 repeticiones, semilla fija).
No son observaciones independientes cuando hay varios props del mismo juego.

Menos de 100 picks o 30 partidos en un rango se etiqueta como muestra limitada.
Superar esos umbrales indica únicamente una muestra descriptiva más amplia;
no certifica una calibración correcta. Los intervalos no contemplan todos los
cambios entre temporadas, errores de datos ni selección de candidatos.

## Fuentes y resultados

Las consultas son SELECT y no consumen créditos. Se conservan las versiones
originales. Moneyline MLB divide sus porcentajes entre 100; NFL Totales también
divide entre 100, corregido igualmente en el Comparador. NFL props y MLB Totales
ya guardan fracciones. No se infiere la escala por el tamaño del número.

MLB Totales usa snapshots previos al inicio y la cuota capturada antes del juego.
Como puede haber push, la probabilidad binaria se evalúa **condicionada a no push**:
`p_decidido = confianza / (1 - p_push)`. Pushes, pendientes y revisiones no se
convierten en pérdidas. Para precios, `EV = (1-p_push)*(p_decidido*cuota-1)`;
la cuota implícita es `1/cuota`, sin corregir el margen de la casa. NFL Totales
con línea entera se excluye porque no conserva una masa push explícita.

Los seis mercados NFL guardan ahora publicaciones inmutables; las capturas anteriores siguen disponibles cuando existen. Se
comprueba `publicada_en < inicio` contra el calendario guardado; las horas SQL de
publicación se interpretan UTC. Las nuevas capturas usan UTC_TIMESTAMP() y una marca explícita publicacion_utc en el payload; las anteriores sin esa marca no se certifican para ajustar el calibrador. Resultado, lado y probabilidad proceden del
payload original y valor oficial del jugador. Se conserva la primera captura
por jugador, partido y versión, y se sustituye el registro mutable correspondiente.
Si falta calendario o publicación, el registro permanece como no verificable.
La falta de la tabla se informa y no se certifica el historial anterior.

Liga MX usa el CSV de confirmación 2024–25 del modelo congelado, sin reentrenarlo.
Es confirmación histórica reconstruida, evaluando Over 2.5, y no publicación real
previa al partido. No guarda cuota: no se inventan EV, pagos ni ROI.

## Ensayo temporal de reajuste

Solo participan publicaciones verificadas; en NFL se exige estado original CANDIDATO, excluyendo alertas de lesión o estado desconocido del ajuste. El diagnóstico puede incluir esas alertas. Se separan fechas completas: primeras
60% para ajuste, siguientes 20% para selección y últimas 20% para prueba. Ningún
partido puede tener fechas distintas que lo ubiquen en varios bloques. Cada
deporte, mercado y versión se mantiene independiente.

Los mínimos son 200/100/100 picks y 30/20/20 partidos, con al menos 20 ganadas y
20 perdidas por bloque. Son condiciones operativas conservadoras, no un cálculo
formal de potencia estadística. Se compara identidad, temperatura (1.1, 1.25,
1.5, 2) y Platt regularizado ajustado exclusivamente en el primer bloque; se
descarta una pendiente negativa. La selección minimiza log-loss en el segundo
bloque. El último bloque no participa en el ajuste ni en la selección.

El informe declara una validación favorable experimental únicamente si el método
no es identidad, mejora log-loss posterior y el intervalo por partidos de la
diferencia Brier es completamente negativo. Se guardan transformación, cortes,
muestras, resultados y hash de los datos. **No se promueve a producción**: todavía
requiere seguimiento prospectivo de un calibrador congelado. La evaluación es
sobre candidatos publicados; no representa todas las líneas ofrecidas por la casa.

La prueba evita mezclar resultados futuros al seleccionar. No puede probar que
un modelo original nunca consultó datos posteriores durante su desarrollo; por
eso los registros no verificables no ajustan el calibrador. Repetir el ensayo al
añadir datos cambia sus cortes; no debe confundirse con una confirmación ciega
de un artefacto previamente congelado.

## Exportación y reproducibilidad

La página permite descargar rangos, datos canónicos para Orange y el informe
temporal. El script no accede a SQL, APIs ni modelos productivos:

```bash
python scripts/evaluar_confianza.py confianza_datos.csv --output reports/confianza
```

El CSV debe tener `fecha,deporte,mercado,modelo,procedencia,identidad,probabilidad,
cuota,resultado`; opcionalmente `evento` y `p_push`. Fecha sin zona mantiene su día
oficial; fecha con zona se convierte al día CDMX. Probabilidades fuera de [0,1],
identificadores ausentes, fechas inválidas y duplicados se excluyen y contabilizan.

No altera picks pasados, predicciones, Combinadas ni movimientos de Bankroll.
Calibrar puede mejorar la interpretación de las probabilidades sin aumentar el
acierto; tampoco prueba rentabilidad. Referencia metodológica:
[scikit-learn](https://scikit-learn.org/stable/modules/calibration.html).

Para Orange, usa `y` (ganada=1, perdida=0) como objetivo y conserva identidad,
fecha y procedencia como metadatos. No uses resultado o y como variables de entrada.
Una partición aleatoria no sustituye la comprobación temporal del script.
Los contadores de exclusión pueden solaparse cuando una fila tiene varios problemas.

Primera comprobación real: `reports/confianza_liga_mx` contiene 306 juegos de
confirmación histórica. 40–50%: 62 casos, confianza media 48.87%, acierto 48.39%;
50–60%: 237, confianza 52.97%, acierto 56.12%; 60–70%: 7, confianza 61.71%,
acierto 57.14%. No se reajusta ese modelo a partir de siete casos ni se considera
esta reconstrucción una publicación verificada.
