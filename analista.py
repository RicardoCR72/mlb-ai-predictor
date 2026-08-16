from turtle import st

import mysql.connector

def conectar_bd():
    try:
        return mysql.connector.connect(
        host=st.secrets["host"],
        port=st.secrets["port"],
        user=st.secrets["user"],
        password=st.secrets["password"],
        database=st.secrets["database"]
    )
    except mysql.connector.Error as err:
        print(f"❌ Error DB: {err}")
        return None

def buscar_oportunidades():
    conexion = conectar_bd()
    if not conexion:
        return

    cursor = conexion.cursor(dictionary=True)
    
    consulta = """
        SELECT 
            j.id_juego, j.equipo_local, j.equipo_visitante,
            c.casa_apuestas, c.cuota_local, c.cuota_visitante
        FROM juegos j
        JOIN cuotas_moneyline c ON j.id_juego = c.id_juego
    """
    cursor.execute(consulta)
    datos = cursor.fetchall()
    
    partidos = {}
    
    # Agrupamos para encontrar la mejor cuota de cada equipo en cada partido
    for fila in datos:
        id_j = fila['id_juego']
        
        if id_j not in partidos:
            partidos[id_j] = {
                'local': fila['equipo_local'],
                'visitante': fila['equipo_visitante'],
                'max_cuota_local': {'cuota': 0, 'casa': ''},
                'max_cuota_visitante': {'cuota': 0, 'casa': ''}
            }
            
        if fila['cuota_local'] > partidos[id_j]['max_cuota_local']['cuota']:
            partidos[id_j]['max_cuota_local'] = {'cuota': float(fila['cuota_local']), 'casa': fila['casa_apuestas']}
            
        if fila['cuota_visitante'] > partidos[id_j]['max_cuota_visitante']['cuota']:
            partidos[id_j]['max_cuota_visitante'] = {'cuota': float(fila['cuota_visitante']), 'casa': fila['casa_apuestas']}

    print("🔍 Analizando el mercado...\n")
    encontro_arbitraje = False
    
    # NUEVO: Lista maestra para guardar a todos los equipos y sus mejores cuotas
    lista_todos_los_equipos = []

    for id_j, p in partidos.items():
        cuota_L = p['max_cuota_local']['cuota']
        cuota_V = p['max_cuota_visitante']['cuota']
        
        # Guardamos al Local en la lista maestra
        if cuota_L > 0:
            lista_todos_los_equipos.append({
                'equipo': p['local'], 
                'rival': p['visitante'],
                'cuota': cuota_L, 
                'casa': p['max_cuota_local']['casa']
            })
            
        # Guardamos al Visitante en la lista maestra
        if cuota_V > 0:
            lista_todos_los_equipos.append({
                'equipo': p['visitante'], 
                'rival': p['local'],
                'cuota': cuota_V, 
                'casa': p['max_cuota_visitante']['casa']
            })
        
        # --- LÓGICA DE ARBITRAJE ---
        if cuota_L > 0 and cuota_V > 0:
            margen = (1 / cuota_L) + (1 / cuota_V)
            
            if margen < 1.0:
                encontro_arbitraje = True
                ganancia_porcentaje = (1.0 - margen) * 100
                print(f"🚨 ¡OPORTUNIDAD DE ARBITRAJE ENCONTRADA! 🚨")
                print(f"⚾ {p['local']} vs {p['visitante']}")
                print(f"   💸 Ganas asegurado un: {ganancia_porcentaje:.2f}%")
                print(f"   🏠 {p['local']} en: {p['max_cuota_local']['casa']} (Cuota: {cuota_L})")
                print(f"   ✈️ {p['visitante']} en: {p['max_cuota_visitante']['casa']} (Cuota: {cuota_V})")
                print("-" * 50)
                
    if not encontro_arbitraje:
        print("📉 No se encontraron Surebets en este momento.\n")

    # --- NUEVA LÓGICA: TOP 3 UNDERDOGS ---
    print("🏆 TOP 3 UNDERDOGS (LOS EQUIPOS QUE MÁS PAGAN HOY):")
    print("-" * 50)
    
    # Magia de Python: Ordenamos la lista de mayor a menor basándonos en la llave 'cuota'
    equipos_ordenados = sorted(lista_todos_los_equipos, key=lambda x: x['cuota'], reverse=True)
    
    # Recorremos solo los primeros 3 elementos de la lista ya ordenada
    for i, underdog in enumerate(equipos_ordenados[:3]):
        print(f"{i+1}. {underdog['equipo']} (Jugando contra {underdog['rival']})")
        print(f"   💰 Paga una cuota de {underdog['cuota']} en {underdog['casa']}")
        print("")
        
    print("-" * 50)

    cursor.close()
    conexion.close()

if __name__ == "__main__":
    buscar_oportunidades()