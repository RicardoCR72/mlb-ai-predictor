# Estándar de Producción de Video Vertical (TikTok / Shorts / Reels)
**OVERDOG AI · Quantitative Sports Media**

Este documento establece las especificaciones técnicas obligatorias y el estándar de calidad para la generación automatizada o semi-automatizada de videos verticales (9:16, 1080x1920) de la plataforma.

---

## 1. Estructura Temporal y Retención (Duración Total: 35 – 42 segundos)
El algoritmo de Shorts y TikTok premia videos con tasa de finalización >80%. Cada segundo innecesario destruye la retención.

| Segmento | Duración Objetivo | Regla de Oro |
|---|---|---|
| **Intro / Hook** | **1.5 a 2.0 s** | Gancho inmediato o arrancar directamente en el segundo 0 con el Pick #1. Prohibidas intros estáticas largas. |
| **Pick #1 (Top Prop / Pick Principal)** | **8.5 a 10.0 s** | Jugador/partido, línea, selección, momio y edge clave. Sin explicaciones redundantes. |
| **Pick #2 (Totales / Moneyline)** | **8.5 a 10.0 s** | Partido, línea, proyección, colchón numérico y momio. |
| **Pick #3 (Spread / Valor)** | **8.0 a 9.5 s** | Partido, selección, ventaja en puntos y momio. |
| **Outro / Cierre** | **2.5 a 3.5 s** | Llamado al enlace en descripción / comentario fijado. Prohibido simular botones falsos en pantalla. |

---

## 2. Ingeniería de Audio y Masterización de Sonoridad
- **Norma de Sonoridad**: **`-14.0 LUFS`** integrados (estándar nativo de YouTube Shorts, TikTok e Instagram Reels).
- **True Peak**: Máximo **`-1.0 dBFS`**.
- **Filtro de Normalización ffmpeg**:
  ```bash
  -af "loudnorm=I=-14:LRA=7:tp=-1"
  ```
- **Pausas y Silencios**:
  - Eliminar silencios muertos entre oraciones de la locución sintética.
  - Pausa máxima inter-frase: **0.25 a 0.35 s** (nunca pausas de ~1.0 s dentro de un mismo pick).
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
