# Actualización de resultados MLB

`mlb_resultados.yml` consulta los marcadores oficiales cada hora (minuto 25;
GitHub puede retrasar las ejecuciones programadas). También se ejecuta al
instalar o cambiar ese workflow o su script, para recuperar pendientes.

El proceso actualiza `juegos` para moneyline y `mlb_totales_resultados` para
totales, reutilizando los evaluadores del botón de la app. No consulta cuotas,
no genera predicciones, no modifica los picks publicados y no envía mensajes.
Revisa hasta 15 fechas pendientes y conserva la protección de doble cartelera.
Si falla un historial, intenta el otro y marca la ejecución como fallida.

El estado abstracto `Final` no basta para liquidar un partido: un aplazado por
lluvia (`DR`) también puede traerlo. Se necesitan ambos marcadores oficiales.
Un juego en curso o aplazado sin marcador permanece pendiente. Los totales de
juegos con reglas especiales conservan la revisión existente.

El historial de moneyline admite juegos de hoy con ambos marcadores. Antes
solo consultaba fechas anteriores a hoy. La caché de esa vista dura cinco
minutos; el botón de actualizar resultados la limpia inmediatamente.

## Auditoría de publicaciones

Cada ejecución captura por lectura los registros de `mlb_publicaciones_moneyline`
y `mlb_totales_predicciones` antes y después de actualizar marcadores. Compara
todos los campos originales, incluidas línea, cuota, selección, confianza,
versión y relojes; admite nuevas publicaciones concurrentes. Informa cambios,
eliminaciones, duplicados y valores o tiempos inconsistentes. Una fuente que no
puede consultarse se informa como `NO_VERIFICABLE`, nunca como correcta.
Los logs contienen solo contadores, no los registros ni las credenciales.

Esta comparación comprueba estabilidad durante esa ejecución, no demuestra que
el historial nunca haya cambiado en el pasado. Las pruebas con MySQL desechable
verifican por separado que reintentar una publicación no cambia su original y
que dos liquidaciones del mismo juego producen un solo resultado y beneficio.
Cada versión del modelo mantiene su propio registro: no son duplicados.

Las ambigüedades solo cuentan registros pendientes de nuestra base, una vez por
fecha y pareja. El log detalla la fecha, equipos e IDs de una ambigüedad real;
sin una correspondencia verificable no se aplica ningún marcador.
