# Uso diario y contexto de los pronósticos

El inicio muestra primero la agenda, cuenta los partidos pendientes de hoy y reúne
consultas parciales y resultados por actualizar en «Necesita atención». Los accesos a
cada deporte se mantienen. El contador Moneyline usa el umbral inicial de 50%.

Las tarjetas destacan selección, línea, cuota y probabilidad original. Proyección,
lesiones, contexto y captura de cuota quedan dentro de «Ver detalles». Los resultados
históricos mantienen sus unidades y resultado visibles. No reaparece el registro de apuestas.

Las solicitudes manuales de resultados y predicciones NFL muestran estado y hora CDMX
junto al botón. El resultado se conserva al cambiar filtros o volver a dibujar la página
durante esa sesión. No representa una consulta global de GitHub Actions. Si la pantalla
se recarga durante una solicitud sin resultado terminal, pasa a «Estado por confirmar»;
no se da por finalizada ni se afirma indefinidamente que sigue ejecutándose. En NFL se
mantienen el presupuesto, el alcance diario y la advertencia de consumo por pulsación.

El contexto de confianza consulta registros guardados, con caché de cinco minutos y sin
APIs de cuotas. Solo incluye publicaciones previas al inicio verificadas, de igual deporte,
mercado y versión, en el rango de diez puntos de la probabilidad del pick. Excluye su propio
evento y fechas iguales o posteriores al día del pronóstico. Las alertas originales no aptas
se excluyen. Se muestran acierto descriptivo y tamaño de muestra con al menos 100 picks y
30 partidos; por debajo se indica «Muestra insuficiente». Este mínimo es una regla operativa,
no una certificación estadística. Para Totales MLB, la comparación es condicional a no push
y se rotula como tal; la probabilidad publicada en la tarjeta permanece igual. Sin versión,
reloj verificable o conexión no se inventa evidencia ni se bloquea la tarjeta.

«Comparar periodos» en Rendimiento usa ventanas consecutivas de 7, 14 o 28 días, sin
solapamiento. Mantiene los filtros no temporales y usa sus propias fechas. El día final
predeterminado es ayer en CDMX. Se separan versiones y procedencias. El cambio de ROI
se expresa en puntos porcentuales; no se sustituye un periodo sin datos por ROI cero.

Los filtros compartidos agrupan periodo y confianza en una fila en escritorio y se apilan
en móvil. «Volver arriba» usa un ancla nativa, disponible solo en pantallas pequeñas,
sin JavaScript ni recarga; conserva los filtros y la paginación de la sesión.
