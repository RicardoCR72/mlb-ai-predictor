# Liga MX: comprobar fuente alternativa gratuita

Tu plan de API-Football solo devuelve temporadas 2022–2024. Esta prueba
consulta dos intervalos de resultados y calendario en ESPN para comprobar
si podemos obtener 2025–26 y Apertura 2026 sin pagar otra API.

El acceso JSON de ESPN es público pero no tiene contrato formal de
estabilidad. Por eso el script **solo imprime un resumen**: no actualiza
`partidos.csv`, no crea predicciones y no consulta The Odds API.

> **Nota sobre el entorno virtual (`.venv_futbol`)**:
> `.venv_futbol` fue un entorno temporal aislado creado exclusivamente para probar scripts de raspado manual con ESPN (`probar_fuente_espn.py`). 
> **Para el sistema en producción**, todo el código de fútbol (`futbol/`) utiliza el entorno virtual principal unificado del proyecto con las dependencias listadas en `requirements.txt`. No es necesario activar `.venv_futbol` para la ejecución del dashboard ni los modelos.

Extrae el ZIP en `D:\Rich\Escritorio\deporte_definitivo` y ejecuta:

```powershell
python -m futbol_liga_mx.probar_fuente_espn
```

Comparte la salida completa. El resumen muestra cuántos eventos aparecieron,
sus estados, los equipos y los campos disponibles para distinguir jornada
regular de liguilla. No contiene claves ni contraseñas.
