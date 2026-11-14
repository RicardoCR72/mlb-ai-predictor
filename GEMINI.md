# Reglas y Estándares del Proyecto: Deporte Definitivo

## 🛡️ Política de Contenido para Redes Sociales (TikTok, Reels, Shorts) - TOLERANCIA CERO A BANEOS

Para evitar suspensiones, bloqueos o shadowbans en TikTok, Instagram y YouTube, el agente debe cumplir rigurosamente estas normas al redactar guiones, generar tarjetas visuales, crear copys o renderizar videos:

### 1. Vocabulario Estrictamente Prohibido
Queda **completamente prohibido** el uso de términos asociados al juego o apuestas en guiones de voz, subtítulos, tarjetas en pantalla, títulos, descripciones y hashtags:
* ❌ **PROHIBIDO:** `apuesta`, `apuestas`, `apostar`, `parlay`, `momio`, `cuotas`, `cuota`, `dinero`, `dólares`, `ganar dinero`, `lock`, `fija`, `bomba de cuota`, `bank`, `stake`, `casino`, `bookie`.
* ❌ **PROHIBIDO:** Mostrar cuotas americanas o decimales (`+150`, `-110`, `1.90`) o logos de casas de apuestas (Caliente, Bet365, Bovada, DraftKings, etc.).
* ❌ **PROHIBIDO:** Mostrar boletos o capturas de pantallas de apuestas.

### 2. Vocabulario Oficial Permitido (Enfoque Periodístico y Big Data)
Toda comunicación debe enmarcarse como **análisis deportivo cuantitativo, ciencia de datos e Inteligencia Artificial** (modelo `@elmagodelospicks`):
* ✅ **PERMITIDO:** `proyección`, `pronóstico`, `tendencia`, `Inteligencia Artificial (IA)`, `modelo matemático`, `análisis estadístico`, `probabilidad`, `margen de valor`, `Más de (Over)`, `Menos de (Under)`, `producción reciente`, `línea del mercado`.

### 3. Estándares de Producción Audiovisual (Formato Vertical 9:16)
* **Resolución y Calidad:** 1080x1920 Full HD, 30.00 FPS continuos sin caídas de cuadros, codificación con `libx264 -crf 18`.
* **Metraje de Fondo:** Clips de jugadores en Full HD 1080p nativo con duración mínima de 16-17 segundos para evitar bucles forzados (`stream_loop`). Verificar siempre que el jugador en pantalla coincida con el analizado.
* **Gancho Inmediato (Segundo 0.0s):** El video arranca sin intro genérica ni saludos; entra de golpe en el segundo 0.0s con la tarjeta de impacto visual (métrica extrema o racha) para retener el scroll.
* **Transición Dinámica:** Segundo 0.0 a 4.5s tarjeta de choque -> Segundo 4.5s en adelante tarjeta limpia de proyección.
* **Cierre / Outro Contundente:** Duración máxima de 3.2 a 3.4 segundos. Fondo desenfocado con tarjeta resumen y llamado a la acción rápido: *"¡Guarda el video y síguenos para más datos de la IA!"*.
* **Voz y Audio:** Voz en español Álvaro (`es-ES-AlvaroNeural`) a velocidad `rate="+7%"` (cierre a `+14%`). Normalización obligatoria a **-14.0 LUFS**.
* **Diseño de Tarjetas (PIL):** Todo texto debe medir sus píxeles con `draw_text_fitted` para garantizar que nunca desborde los contenedores visuales, manteniendo al menos 35-50 px de margen interno.

---

## 🏀 Modelos Matemáticos y Motores de Predicción

### NBA Props Engine:
* **Shrinkage Bayesiano:** Ponderación calibrada 60% línea de mercado / 40% proyección del modelo para eliminar sobreajustes y líneas infladas.
* **Ponderación Temporal:** 35% rendimiento últimos 5 juegos (L5) / 65% temporada completa.
* **Filtros de Calidad:** Mínimo 18 minutos proyectados y al menos 5 partidos jugados.
* **Tope Diario Oficial:** Máximo 20 mejores selecciones diarias (`Top 20 Oficiales`) para mantener calidad y control de ROI.

### NFL Engine:
* **Candados Defensivos:** Validación obligatoria de los 9 filtros defensivos (EPA/Play permitido, tasa de presiones, targets en zona roja, ritmo de posesión y script de partido).
