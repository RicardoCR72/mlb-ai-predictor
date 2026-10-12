# Auditoría de yardas de recepción

En NFL → Props de jugadores → Rendimiento, abrir **Auditoría de yardas de recepción**. El panel respeta los filtros actuales; para comparar semanas, seleccionar todo el historial y el mercado de yardas de recepción. Muestra semana y lado, confianza, contexto de lesiones, unidades y muestra del ROI. El CSV conserva el detalle de cada selección y la procedencia de la proyección.

Un error positivo significa que se proyectó más de lo observado. La descomposición utiliza:

- Volumen: (recepciones proyectadas − recepciones reales) × yardas proyectadas por recepción.
- Eficiencia: recepciones reales × (yardas proyectadas por recepción − yardas reales por recepción).

Ambos componentes suman el error de yardas. Solo se calculan cuando hay recepciones proyectadas y reales mayores que cero. No se imputan ceros a datos faltantes. Los resultados describen asociaciones; los picks del mismo jugador o partido no son independientes.

## Disponibilidad de compañeros

Para yardas de recepción se ejecuta el modelo congelado en dos escenarios: todos los compañeros WR/TE/RB/FB con estado questionable o doubtful juegan, o todos quedan fuera. Se ajustan únicamente las variables de lesiones de compañeros y su conteo, excluyendo al propio jugador, otros equipos y otras semanas. Las bajas confirmadas conservan su peso. Los escenarios son límites de sensibilidad, no probabilidades de participación ni una simulación exacta de targets redistribuidos.

Si una selección publicada cambia de lado o deja de cumplir los criterios existentes en algún escenario, pasa a **Revisar lesión**. La nota muestra los compañeros, ambas proyecciones y sus estados. No se modifica la proyección base, la calibración ni los criterios de otros mercados. Si el modelo congelado no usa variables de lesiones, los escenarios pueden coincidir; no se inventa un ajuste externo.

## Conservación de publicaciones

Las nuevas selecciones publicadas de yardas con una línea y hora de inicio verificadas se registran antes del kickoff en `nfl_publicaciones_props`. La clave incluye partido, jugador, mercado, modelo y línea. La primera publicación de esa clave se conserva aunque se recalculen las proyecciones; otra línea crea otro registro. Se incluyen la proyección de recepciones del mismo cálculo, la cuota, la confianza y los escenarios.

La auditoría usa ese registro solo cuando coincide con la línea y el modelo del pick actual. Su resultado de simulación de 1 u se calcula con la selección, línea y momio conservados. No modifica el bankroll ni los resultados originales. Los registros anteriores se etiquetan **versión original no verificada**: no se reconstruyen capturas históricas ni se afirma que equivalgan a lo publicado en su momento. La tabla se crea en la primera publicación elegible; el lector permite que todavía no exista, pero no oculta otros errores de base de datos.

## Antes de recalibrar

Comparar varias semanas, overs/unders y grupos de lesión con su número de muestras. Comprobar también error medio y absoluto, no solo victorias. Si se propone un ajuste, seleccionarlo en un período anterior y evaluar en semanas posteriores que no se usaron para elegirlo. Este cambio no reentrena ni optimiza umbrales con la semana 5.
