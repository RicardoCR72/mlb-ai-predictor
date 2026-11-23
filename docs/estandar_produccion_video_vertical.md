# Estándar de Producción de Video Vertical (TikTok / Shorts / Reels)
**OVERDOG AI · Quantitative Sports Media**

Este documento establece las especificaciones técnicas obligatorias y el estándar de calidad para la generación automatizada o semi-automatizada de videos verticales (9:16, 1080x1920) de la plataforma.

---

## 1. Estructura Temporal y Retención

### Formato Ultra-Retención Individual (Duración Total: 15 – 18 segundos)
Optimizado para maximizar el hook en los primeros 3 segundos, disparar la tasa de finalización (>90%) y generar comentarios:

| Fase | Ventana | Regla Estricta | Elemento Visual |
|---|---|---|---|
| **1. Gancho Táctico** | **0.0s – 3.0s** (~8 a 11 palabras) | Oración directa sobre matchup o desajuste de línea. Prohibido leer la racha histórica que ya está en pantalla. | **Tarjeta Estado 1 (Teaser):** Encabezado oficial + Nombre gigante + Badge neón `ANOMALÍA DETECTADA` (Línea oculta en suspenso). |
| **2. Revelación y Modelo** | **3.0s – 12.0s** (~18 a 22 palabras) | Se pronuncia explícitamente el pick (Over/Under + línea) respaldado por la ventaja del modelo. | **Tarjeta Estado 2 (Revelación):** Transición dinámica en `t_revelacion` mostrando el pick completo, línea, proyección y racha histórica. |
| **3. Cierre en Seco** | **12.0s – 16.0s** (~8 a 12 palabras) | Pregunta corta directa para debate en comentarios. Cero despedidas ("no olvides seguirme" está prohibido). | Tarjeta completa visible hasta el corte exacto en `dur_audio + 0.25s`. |

---

## 2. Ingeniería de Audio y Procesamiento TTS
- **Voz Oficial**: Álvaro (`es-ES-AlvaroNeural`) a velocidad base `rate="+8%"`.
- **Recorte de Silencio Extremo**:
  - `silenceremove` en ambos extremos (`silenceremove=start_periods=1:start_duration=0.01:start_threshold=-50dB,areverse,silenceremove=...,areverse`) para que la primera sílaba de la voz arranque exactamente en `t = 0.0s`.
- **Dinamismo Temporal (`atempo`)**:
  - Aceleración a `1.08x` manteniendo el pitch natural sin distorsión.
- **Normalización de Sonoridad**:
  - **`-14.0 LUFS`** integrados (`loudnorm=I=-14:LRA=7:tp=-1.5`).
- **Corte de Video**:
  - El render final corta exactamente `0.25s` después de que termina el audio para eliminar tiempos muertos al cierre.
- **Música de Fondo Dinámica**:
  - Pista instrumental con ritmo/beat deportivo a **`-22 LUFS`** (aproximadamente -18 a -20 dB por debajo de la voz).
  - Evita la frialdad de la locución sintética aislada y enriquece el rango dinámico.

---

## 3. Coherencia Visual de Fondos (Cero Inconsistencias)
- **Prohibición de Transmisiones con Marcador Erróneo**:
  - No usar recortes ampliados de transmisiones de TV 16:9 donde aparezcan marcadores cortados o rivales que no correspondan al pick del día (ej. mostrar marcador `PHI vs CLE` cuando el pick es `Knicks @ Cavaliers`, o rival de uniforme azul cuando el juego es vs Spurs).
  - Destruye la autoridad y credibilidad del modelo si se anuncia como análisis de "hoy".
- **Alternativas Visuales Profesionales**:
  1. **Composición Cinemática Vertical**: Jugador en acción / cutout recortado sobre fondo de duela/estadio con desenfoque de movimiento vertical (evita chyrons y marcadores de TV cortados).
  2. **Highlight centrado sin scorebug**: Tomas cerradas de tiro, clavada o festejo donde no haya cintillos inferiores de estadísticas ajenas (evitar superposiciones con nombres como Kris Murray o marcadores de TV).

---

## 4. Legibilidad Tipográfica Móvil (Viewport 1080x1920)
En una pantalla de teléfono de 6 pulgadas, cualquier texto por debajo de 30pt es ilegible:
- **Títulos y Picks**: `Impact` o `Segoe UI Black` a **54 – 60 pt**.
- **Momio y Valor Esperado**: `Segoe UI Bold` a **34 – 38 pt** en color de contraste (Dorado `#ffd700` o Neón `#00ffa3`).
- **Notas y Datos de Proyección**: Tamaño mínimo **30 – 34 pt**. Prohibido texto descriptivo pequeño a 20-22 pt.
- **Zona Segura (Safe Zone)**:
  - Margen superior: 200 px libres (para no chocar con la interfaz de TikTok/Shorts).
  - Margen inferior: 350 px libres (reservado para título, descripción, audio y botones de me gusta/compartir de la app).
  - Márgenes laterales: 60 px mínimos.

---

## 5. Cierre y Call to Action (CTA)
- No colocar falsos botones interactivos en video (los usuarios no pueden tocar una imagen).
- Indicar verbal y visualmente con flecha sutil o animación: *"Picks completos en el link del perfil / comentarios fijados"*.

