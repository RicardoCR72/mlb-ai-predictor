import sys
from datetime import datetime
from pathlib import Path
import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.constants import ZONA_MX
from core.db import get_db_connection

print("[MLB V5] Iniciando Escáner de Pitchers Abridores Sabermétricos (FIP + xFIP + K-BB% + WHIP 3)...")

try:
    conexion = get_db_connection()
    cursor = conexion.cursor()
    
    # Asegurar que la tabla abridores cuenta con las columnas sabermétricas V5
    columnas_nuevas = [
        ("whip_ultimas_3", "DOUBLE DEFAULT 1.30"),
        ("fip", "DOUBLE DEFAULT 4.20"),
        ("xfip", "DOUBLE DEFAULT 4.20"),
        ("k_bb_pct", "DOUBLE DEFAULT 0.14"),
        ("mano", "VARCHAR(5) DEFAULT 'R'")
    ]
    cursor.execute("SHOW COLUMNS FROM abridores")
    cols_existentes = {col[0].lower() for col in cursor.fetchall()}
    for col_nom, col_def in columnas_nuevas:
        if col_nom not in cols_existentes:
            try:
                cursor.execute(f"ALTER TABLE abridores ADD COLUMN {col_nom} {col_def}")
                conexion.commit()
            except Exception:
                pass
except Exception as e:
    print(f"❌ Error conectando a BD: {e}")
    exit(1)

hoy = datetime.now(ZONA_MX).strftime('%Y-%m-%d')
url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={hoy}&hydrate=probablePitcher(stats)"

try:
    respuesta = requests.get(url).json()
    if 'dates' in respuesta and len(respuesta['dates']) > 0:
        juegos = respuesta['dates'][0]['games']
        for juego in juegos:
            for tipo in ['home', 'away']:
                equipo_nombre = juego['teams'][tipo]['team']['name']
                if "Oakland" in equipo_nombre or "Athletics" in equipo_nombre:
                    equipo_nombre = "Athletics"
                    
                if 'probablePitcher' in juego['teams'][tipo]:
                    pitcher = juego['teams'][tipo]['probablePitcher']
                    nombre_pitcher = pitcher['fullName']
                    pitcher_id = pitcher.get('id')
                    
                    era_global = 4.20
                    era_3_juegos = 4.20
                    whip_3_juegos = 1.30
                    fip = 4.20
                    xfip = 4.20
                    k_bb_pct = 0.14
                    mano = 'R'
                    
                    if pitcher_id:
                        # 1. Extraer stats de temporada y mano
                        url_stats = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}?hydrate=stats(group=[pitching],type=[season])"
                        try:
                            res_stats = requests.get(url_stats).json()
                            if 'people' in res_stats and len(res_stats['people']) > 0:
                                person = res_stats['people'][0]
                                mano = person.get('pitchHand', {}).get('code', 'R')
                                stats_blocks = person.get('stats', [])
                                if stats_blocks and stats_blocks[0].get('splits'):
                                    s = stats_blocks[0]['splits'][0]['stat']
                                    era_str = s.get('era', '4.20')
                                    if era_str != '-.--':
                                        era_global = float(era_str)
                                    
                                    ip = float(s.get('inningsPitched', 1.0))
                                    k = int(s.get('strikeOuts', 0))
                                    bb = int(s.get('baseOnBalls', 0))
                                    hr = int(s.get('homeRuns', 0))
                                    bf = int(s.get('battersFaced', 1))
                                    hbp = int(s.get('hitByPitch', 0))
                                    
                                    if ip > 0:
                                        fip = ((13 * hr + 3 * (bb + hbp) - 2 * k) / ip) + 3.15
                                        xfip = ((13 * (ip * 1.15 / 9.0) + 3 * (bb + hbp) - 2 * k) / ip) + 3.15
                                    if bf > 0:
                                        k_pct = k / bf
                                        bb_pct = bb / bf
                                        k_bb_pct = k_pct - bb_pct
                        except Exception:
                            pass
                        
                        # 2. Extraer ERA y WHIP de las Últimas 3 Aperturas
                        url_log = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=gameLog&group=pitching&season={hoy[:4]}"
                        try:
                            res_log = requests.get(url_log).json()
                            if 'stats' in res_log and len(res_log['stats']) > 0:
                                ultimos_3 = res_log['stats'][0].get('splits', [])[:3]
                                if ultimos_3:
                                    carreras_limpias = 0
                                    tercios_inning = 0
                                    hits_3 = 0
                                    bb_3 = 0
                                    for j in ultimos_3:
                                        carreras_limpias += int(j['stat'].get('earnedRuns', 0))
                                        hits_3 += int(j['stat'].get('hits', 0))
                                        bb_3 += int(j['stat'].get('baseOnBalls', 0))
                                        ip_str = str(j['stat'].get('inningsPitched', '0.0'))
                                        parts = ip_str.split('.')
                                        enteros = int(parts[0])
                                        decimales = int(parts[1]) if len(parts) > 1 else 0
                                        tercios_inning += (enteros * 3) + decimales
                                    
                                    if tercios_inning > 0:
                                        ip_real = tercios_inning / 3.0
                                        era_3_juegos = (carreras_limpias * 27) / tercios_inning
                                        whip_3_juegos = (hits_3 + bb_3) / ip_real
                        except Exception:
                            pass

                    # Guardar métricas sabermétricas completas V5 en MySQL
                    query = """
                    INSERT INTO abridores (fecha, equipo, nombre_pitcher, era, era_ultimas_3, whip_ultimas_3, fip, xfip, k_bb_pct, mano)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        nombre_pitcher=VALUES(nombre_pitcher),
                        era=VALUES(era),
                        era_ultimas_3=VALUES(era_ultimas_3),
                        whip_ultimas_3=VALUES(whip_ultimas_3),
                        fip=VALUES(fip),
                        xfip=VALUES(xfip),
                        k_bb_pct=VALUES(k_bb_pct),
                        mano=VALUES(mano)
                    """
                    cursor.execute(query, (
                        hoy, equipo_nombre, nombre_pitcher,
                        round(era_global, 2), round(era_3_juegos, 2), round(whip_3_juegos, 2),
                        round(fip, 2), round(xfip, 2), round(k_bb_pct, 3), mano
                    ))
                    print(f"⚾ {equipo_nombre}: {nombre_pitcher} ({mano}HP) | FIP: {fip:.2f} | K-BB%: {k_bb_pct:.1%} | WHIP 3: {whip_3_juegos:.2f}")
        
        conexion.commit()
        print("✅ ¡Pitchers actualizados con métricas sabermétricas V5 completas!")
except Exception as e:
    print(f"🚨 Error: {e}")
finally:
    if 'cursor' in locals(): cursor.close()
    if 'conexion' in locals(): conexion.close()