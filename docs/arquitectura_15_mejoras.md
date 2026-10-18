# Correcciones de arquitectura

| # | Problema | Implementación |
|---|---|---|
| 1 | Entorno virtual versionado | Se retiran del índice 7,041 archivos; se conserva .gitignore y requirements. No se borra el entorno local. |
| 2 | Módulos con demasiadas responsabilidades | Se extraen persistencia de totales y props, cálculo de totales, calendario, adaptador HTTP y especificación de variables. |
| 3 | core sin límites | Dominio, infraestructura y aplicación separados; fachadas mantienen compatibilidad. |
| 4 | Reglas temporales diferentes | Servicio de elegibilidad usa inicio UTC y resultado; excluye juegos iniciados y horarios desconocidos. |
| 5 | Cuotas viejas | La inferencia y candidatos props exigen captura verificable de las últimas 2 horas. |
| 6 | Deduplicación bloqueaba renovación | Capturas exitosas vencen a las 2 horas; cobros inciertos siguen bloqueados durante el día. |
| 7 | Lecturas históricas completas | SQL NFL filtra temporada; publicaciones asociadas se consultan por IDs del lote. Rendimiento mantiene su lector histórico. |
| 8 | Configuración MySQL duplicada | Scripts y web usan el mismo resolver, incluyendo aliases y certificados. |
| 9 | Esquema disperso | Registro central de esquemas activos, migraciones versionadas con checksum y candado, actualización aditiva del payload. |
| 10 | Contratos implícitos | Prediction validado al publicar totales y require_columns en fronteras; validación explícita de probabilidades props. |
| 11 | Escala por heurística | Escala declarada por fuente: totales 100, props 1; valores inválidos quedan sin probabilidad. |
| 12 | Worker en Streamlit | Cola con payload durable; procesos independientes y opción de servicio externo, candados y límite global MySQL de 3 workers. |
| 13 | Varios planificadores NFL | Un workflow automático; entradas anteriores quedan manuales. |
| 14 | Acoplamiento a funciones retiradas | Cuotas, consultas y lectura de calendario extraídas de Bankroll y Combinadas. |
| 15 | Vistas por runpy | Inicio, NFL y Rendimiento utilizan funciones render explícitas. |

## Operación y límites

No se ejecutan migraciones contra producción durante el desarrollo. El despliegue
puede aplicar `python -m scripts.migrate`; los puntos de escritura verifican sus
esquemas al usarlos. No hay eliminación de tablas ni reconstrucción de históricos.
Los modelos y fórmulas se conservan. El recorte de temporada aplica a las vistas
operativas; no elimina datos de la base.

Un worker independiente del proceso web evita interrumpir tareas por reruns o
reinicios del intérprete Streamlit. Para sobrevivir reemplazos del contenedor,
se debe desplegar el worker como servicio externo supervisado. Las tareas ya
ejecutándose no se reintentan automáticamente: se conserva la protección de
créditos frente a interrupciones o cobros desconocidos.
