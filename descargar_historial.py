import requests
import pandas as pd

print("⚾ Iniciando la extracción masiva de la MLB (2022 - 2026)...")

# Definimos el rango de años que te faltan, hasta el día de ayer
temporadas = [
    ("2022-01-01", "2022-12-31"),
    ("2023-01-01", "2023-12-31"),
    ("2024-01-01", "2024-12-31"),
    ("2025-01-01", "2025-12-31"),
    ("2026-01-01", "2026-07-28") # Hasta ayer
]

todos_los_juegos = []

for inicio, fin in temporadas:
    print(f"⏳ Descargando datos desde {inicio} hasta {fin}...")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={inicio}&endDate={fin}"
    
    try:
        respuesta = requests.get(url).json()
        
        if 'dates' in respuesta:
            for dia in respuesta['dates']:
                fecha = dia['date']
                for juego in dia['games']:
                    # 'F' significa Finalizado. No queremos juegos cancelados o pospuestos.
                    if juego['status']['statusCode'] == 'F':
                        local = juego['teams']['home']['team']['name']
                        visita = juego['teams']['away']['team']['name']
                        score_local = juego['teams']['home'].get('score', 0)
                        score_visita = juego['teams']['away'].get('score', 0)
                        
                        # Normalizar Athletics
                        if local == "Oakland Athletics": local = "Athletics"
                        if visita == "Oakland Athletics": visita = "Athletics"

                        todos_los_juegos.append({
                            "fecha": fecha,
                            "equipo_local": local,
                            "equipo_visitante": visita,
                            "marcador_local": score_local,
                            "marcador_visitante": score_visita
                        })
    except Exception as e:
        print(f"Error descargando el periodo {inicio}: {e}")

# Convertir la lista a un DataFrame de Pandas
df_nuevo = pd.DataFrame(todos_los_juegos)

# Guardar el resultado
nombre_archivo = "mlb_historial_22_26.csv"
df_nuevo.to_csv(nombre_archivo, index=False)

print(f"✅ ¡Listo, Rich! Se guardaron {len(df_nuevo)} partidos oficiales en '{nombre_archivo}'.")