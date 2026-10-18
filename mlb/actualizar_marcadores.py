import os
import sys
import pandas as pd
import requests
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_MX
from core.db import get_db_connection
from core.alerts import enviar_telegram


def hoy_mx():
    return datetime.now(ZONA_MX).date()


def notificar_telegram(mensaje):
    if os.environ.get("TELEGRAM_REPORTE_UNIFICADO") == "1":
        return
    enviar_telegram(mensaje)

print("⚾ Iniciando actualización de marcadores de la MLB...")

# 1. CONEXIÓN A TU BD
conexion = get_db_connection()
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

# Compartir el evaluador de la app: exige un final oficial con ambos marcadores
# y no aplica un marcador a dos partidos de una doble cartelera.
from core.actualizacion_manual import refresh_mlb_games
mensaje_exito = refresh_mlb_games(conexion)
print(mensaje_exito)
notificar_telegram(mensaje_exito)

print("🧠 Iniciando actualización de la memoria de la IA...")

archivo_csv = RAIZ / "data" / "mlb" / "mlb_dataset_ia.csv"

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
                # Un aplazado también puede tener abstractGameState=Final: exigir marcador.
                if juego.get('status', {}).get('abstractGameState') == 'Final':
                    local = juego['teams']['home']['team']['name']
                    visita = juego['teams']['away']['team']['name']
                    score_l = juego['teams']['home'].get('score')
                    score_v = juego['teams']['away'].get('score')
                    if score_l is None or score_v is None:
                        continue

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
