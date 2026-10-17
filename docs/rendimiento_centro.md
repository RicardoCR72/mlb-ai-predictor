# Organización de rendimiento

Las páginas MLB, NFL y Liga MX mantienen los pronósticos y su historial filtrado.
Todos los historiales usan `performance_filters`: periodo, fechas, confianza mediante
slider 0–100%, resultado y, cuando la fuente lo permite, temporada, semana, mercado
y procedencia. Restablecer filtros vuelve a sus valores iniciales. En Totales MLB se
conserva el filtro opcional de candidatos originales con EV positivo, activado por defecto.
La confianza predeterminada en los pronósticos actuales de MLB sigue en 50%.

La nueva página **Rendimiento** sustituye al acceso independiente del Comparador:

- **Panorama:** filtros de deporte y modelo, cuatro indicadores, curva en unidades,
  ROI por mercado, balance, equivalencia ilustrativa en pesos, análisis semanal,
  sensibilidad a umbrales y descarga de la muestra filtrada.
- **Comparación:** conserva la comparación por deporte, mercado, modelo y procedencia,
  con tamaños de muestra, curvas y exportación.
- **Auditoría NFL:** conserva la auditoría de recepción, lesiones, errores de volumen
  y eficiencia y CSV, con filtros propios de versión y muestra.
- **Validación Liga MX:** métricas de confirmación, baseline, cobertura y diagnóstico
  de confianza. Sin cuotas históricas no se inventan unidades ni ROI.

Los análisis financieros centrales reutilizan los registros guardados del comparador;
no reconstruyen picks antiguos ni incorporan los históricos reconstruidos de la vista
Moneyline deportiva. Las curvas usan únicamente resultados liquidados con beneficio
conocido. La auditoría de recepción usa publicaciones conservadas donde están disponibles
y distingue el histórico sin versión original verificada. Cada versión y procedencia se
mantiene separada en las comparaciones. Los umbrales son descriptivos, sin seleccionar
ni promocionar automáticamente modelos.

Las semanas NFL usan el calendario oficial guardado. Las demás fechas se agrupan por
semana ISO, rotulada como tal. El valor ilustrativo de 1 unidad se introduce únicamente
en la sesión; no configura una banca ni guarda apuestas.

Bankroll ya no aparece en la navegación, el dashboard ni las tarjetas. Se retiran sus
formularios de registro y selectores asociados. No se borran tablas ni datos existentes.
Los módulos de persistencia siguen disponibles para los procesos existentes. La página
principal omite las consultas financieras al preparar su resumen.

No cambian modelos, probabilidades, workflows, capturas de cuotas ni créditos de APIs.
La actualización de Rendimiento solo relee registros guardados.

## Presentación visual

Combinadas se retira de la navegación. El panorama y la comparación muestran primero
un pastel de resultados, barras de ROI por grupo y una curva del beneficio acumulado.
El panorama añade barras de retorno semanal ponderadas por la cantidad de picks con
beneficio conocido. Las tablas quedan en detalles desplegables.

El pastel cuenta todas las ganadas, perdidas y push liquidados; el acierto excluye push.
ROI y unidades excluyen beneficios desconocidos. Pendientes, anulados y otros estados
no se convierten en pérdidas ni ganancias. Cada gráfica aclara su denominador. Los
picks sin fecha válida participan en el ROI, pero no en la curva. ROI negativo se
representa por debajo de cero, nunca como proporción de un pastel. Los filtros, las
cuotas originales y la separación de versiones/procedencias se mantienen.
