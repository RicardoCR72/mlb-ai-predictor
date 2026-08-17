import pandas as pd
import requests
import mysql.connector
import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# 🔧 CORRECCIÓN: la línea original era "from turtle import st", que importaba
# la función showturtle() del módulo de gráficos turtle en vez de Streamlit.
# Eso hacía que st.secrets fallara. Ya corregido arriba con "import streamlit as st".

# 🔧 CORRECCIÓN: mismo ajuste de zona horaria que en el dashboard, para que
# las fechas siempre se calculen con la hora de México y no con la del servidor (UTC).
ZONA_MX = ZoneInfo("America/Mazatlan")

def hoy_mx():
    return datetime.now(ZONA_MX).date()


def notificar_telegram(mensaje):
    # Pega aquí los datos que obtuviste en los pasos 1 y 2
    token = "8530510635:AAF1IH7GKYBUVgVnp3-p6UyEuxYOA1E6axE"
    chat_id = "5339277237"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    datos = {'chat_id': chat_id, 'text': mensaje}
    
    try:
        requests.post(url, data=datos)
    except Exception as e:
        print("No se pudo enviar el mensaje a Telegram:", e)

print("⚾ Iniciando actualización de marcadores de la MLB...")

# 1. CONEXIÓN A TU BD
conexion = mysql.connector.connect(
        host=st.secrets["host"],
        port=st.secrets["port"],
        user=st.secrets["user"],
        password=st.secrets["password"],
        database=st.secrets["database"]
    )
cursor = conexion.cursor()

# 2. FECHAS A REVISAR: HOY y AYER
# 🔧 CORRECCIÓN: antes el script solo revisaba "ayer", pensado para correr una
# sola vez al día bien temprano. Si lo corres a media tarde/noche, los partidos
# de HOY que ya terminaron se quedaban sin actualizar hasta el día siguiente.
# Ahora revisamos ambas fechas en cada corrida, así puedes ejecutarlo cuantas
# veces quieras durante el día sin perder resultados.
fecha_hoy_dt = hoy_mx()
fecha_ayer_dt = fecha_hoy_dt - timedelta(days=1)
fechas_a_revisar = [fecha_hoy_dt.strftime('%Y-%m-%d'), fecha_ayer_dt.strftime('%Y-%m-%d')]

partidos_actualizados_total = 0

for fecha_str in fechas_a_revisar:
    print(f"📅 Buscando resultados oficiales del: {fecha_str}")

    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={fecha_str}"
    respuesta = requests.get(url).json()

    if 'dates' in respuesta and len(respuesta['dates']) > 0:
        juegos = respuesta['dates'][0]['games']

        for juego in juegos:
            # 'F' significa que el partido ya es Final / Terminó
            if juego['status']['statusCode'] == 'F':
                # Extraer nombres de la API
                equipo_local_api = juego['teams']['home']['team']['name']
                equipo_visita_api = juego['teams']['away']['team']['name']

                # Normalizar el caso de los Athletics (a veces la API manda Oakland Athletics)
                if equipo_local_api == "Oakland Athletics": equipo_local_api = "Athletics"
                if equipo_visita_api == "Oakland Athletics": equipo_visita_api = "Athletics"

                # Extraer marcadores
                carreras_local = juego['teams']['home']['score']
                carreras_visita = juego['teams']['away']['score']

                # 3. ACTUALIZAR TU TABLA EN XAMPP
                # Buscamos por equipo, estado programado Y LA FECHA EXACTA para evitar errores de series
                query = """
                UPDATE juegos
                SET marcador_local = %s, marcador_visitante = %s, estado = 'finalizado'
                WHERE equipo_local = %s 
                  AND equipo_visitante = %s 
                  AND estado = 'programado'
                  AND DATE(fecha) = %s
                """

                cursor.execute(query, (carreras_local, carreras_visita, equipo_local_api, equipo_visita_api, fecha_str))

                # Solo contamos si realmente modificó una fila (si la encontró)
                if cursor.rowcount > 0:
                    print(f"✅ Actualizado: {equipo_local_api} {carreras_local} - {carreras_visita} {equipo_visita_api}")
                    partidos_actualizados_total += 1
    else:
        print(f"😴 No se encontraron juegos de MLB para {fecha_str}.")

# Guardar los cambios
conexion.commit()
mensaje_exito = f"✅ MLB Base de datos actualizada: {partidos_actualizados_total} partidos guardados en XAMPP."
print(mensaje_exito)
notificar_telegram(mensaje_exito)

# ... (Tu código actual que actualiza XAMPP se queda igual arriba de esto) ...

print("🧠 Iniciando actualización de la memoria de la IA...")

archivo_csv = 'mlb_dataset_ia.csv'

try:
    # 1. Cargar el historial actual
    df_memoria = pd.read_csv(archivo_csv)

    # Función matemática interna para calcular cómo llegaban al partido en cuestión
    def calcular_estado_previo(equipo, df_hist, fecha_del_juego):
        df_equipo = df_hist[(df_hist['equipo_local'] == equipo) | (df_hist['equipo_visitante'] == equipo)]
        if df_equipo.empty: return 0, 3

        ultimo = df_equipo.iloc[-1]
        fecha_ultimo = pd.to_datetime(ultimo['fecha']).date()
        fecha_juego = pd.to_datetime(fecha_del_juego).date()
        descanso = (fecha_juego - fecha_ultimo).days

        if ultimo['equipo_local'] == equipo:
            racha = ultimo['racha_local']
            gano = ultimo['marcador_local'] > ultimo['marcador_visitante']
        else:
            racha = ultimo['racha_visitante']
            gano = ultimo['marcador_visitante'] > ultimo['marcador_local']

        racha_nueva = racha + 1 if gano and racha > 0 else (1 if gano else (racha - 1 if racha < 0 else -1))
        return racha_nueva, descanso

    nuevos_registros_total = []

    # 🔧 CORRECCIÓN: igual que arriba, revisamos HOY y AYER, en orden cronológico
    # (ayer primero) para que las rachas se calculen correctamente en orden.
    for fecha_str in sorted(fechas_a_revisar):
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={fecha_str}"
        respuesta = requests.get(url).json()

        if 'dates' in respuesta and len(respuesta['dates']) > 0:
            for juego in respuesta['dates'][0]['games']:
                # Solo procesar juegos que sí finalizaron ('F')
                if juego['status']['statusCode'] == 'F':
                    local = juego['teams']['home']['team']['name']
                    visita = juego['teams']['away']['team']['name']
                    score_l = juego['teams']['home'].get('score', 0)
                    score_v = juego['teams']['away'].get('score', 0)

                    # Homologar el nombre de los Athletics
                    if local == "Oakland Athletics": local = "Athletics"
                    if visita == "Oakland Athletics": visita = "Athletics"

                    # Candado de seguridad: Evitar duplicados si el script corre dos veces
                    # ⚠️ NOTA: este candado solo compara fecha + equipo_local. Si algún día
                    # hay doble cartelera (dos juegos el mismo día entre los mismos equipos),
                    # el segundo juego se saltaría por error. Si te llega a pasar, hay que
                    # comparar también equipo_visitante para diferenciarlos.
                    ya_existe = df_memoria[(df_memoria['fecha'] == fecha_str) & (df_memoria['equipo_local'] == local)].shape[0] > 0

                    if not ya_existe:
                        # Calcular estado previo al partido
                        racha_l, descanso_l = calcular_estado_previo(local, df_memoria, fecha_str)
                        racha_v, descanso_v = calcular_estado_previo(visita, df_memoria, fecha_str)
                        res_final = 1 if score_l > score_v else 0

                        nuevo_registro = {
                            "fecha": fecha_str, "equipo_local": local, "equipo_visitante": visita,
                            "marcador_local": score_l, "marcador_visitante": score_v,
                            "racha_local": racha_l, "racha_visitante": racha_v,
                            "descanso_local": descanso_l, "descanso_visitante": descanso_v,
                            "resultado_final": res_final
                        }
                        nuevos_registros_total.append(nuevo_registro)

                        # Lo agregamos también a df_memoria en memoria (no solo a la lista),
                        # para que el siguiente partido del mismo día calcule su racha
                        # tomando en cuenta este que acabamos de procesar.
                        df_memoria = pd.concat([df_memoria, pd.DataFrame([nuevo_registro])], ignore_index=True)

    # 2. Guardar todos los juegos nuevos encontrados
    if nuevos_registros_total:
        df_memoria.to_csv(archivo_csv, index=False)
        print(f"✅ Se agregaron {len(nuevos_registros_total)} partidos nuevos a la memoria de la IA.")
    else:
        print("ℹ️ No hubo partidos nuevos para agregar (o ya estaban guardados).")

except Exception as e:
    print(f"🚨 Error actualizando la memoria de la IA: {e}")

# 🔧 CORRECCIÓN: cerramos la conexión a la BD al terminar el script.
cursor.close()
conexion.close()