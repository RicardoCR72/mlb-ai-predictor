import os
import shutil
from datetime import datetime

# 1. Configuración de Rutas
# Ruta donde XAMPP guarda la herramienta de respaldos
ruta_xampp_mysql = r"C:\xampp\mysql\bin\mysqldump.exe"
nombre_bd = "tu_base_de_datos"  # Cambia esto por el nombre real de tu BD en XAMPP
usuario_bd = "root"
password_bd = ""  # En XAMPP suele estar vacío por defecto

ruta_proyecto = r"D:\Rich\Escritorio\deporte_definitivo"

# Ruta de tu carpeta local que se sincroniza automáticamente con la nube
ruta_nube = r"C:\Users\TuUsuario\Google Drive\Respaldos_MLB" 

# 2. Generar el nombre del respaldo con la fecha de hoy
fecha_hoy = datetime.now().strftime("%Y-%m-%d")
archivo_sql = os.path.join(ruta_proyecto, f"backup_mlb_{fecha_hoy}.sql")

print(f"⏳ Generando volcado de la base de datos: {nombre_bd}...")

# 3. Ejecutar el volcado de MySQL a un archivo .sql
comando_dump = f'"{ruta_xampp_mysql}" -u {usuario_bd} {nombre_bd} > "{archivo_sql}"'
os.system(comando_dump)

# 4. Copiar los archivos críticos a la nube
print("☁️ Subiendo archivos críticos a Google Drive/OneDrive...")
if not os.path.exists(ruta_nube):
    os.makedirs(ruta_nube)

# Subimos el historial de la base de datos
shutil.copy(archivo_sql, ruta_nube)

# Subimos también tu valioso CSV histórico y el archivo del modelo
shutil.copy(os.path.join(ruta_proyecto, "mlb_dataset_ia.csv"), ruta_nube)
shutil.copy(os.path.join(ruta_proyecto, "cerebro_mlb_v2.keras"), ruta_nube)

# 5. Limpieza local (Opcional: borra el .sql de tu escritorio para no llenar espacio)
os.remove(archivo_sql)

print("✅ ¡Respaldo en la nube completado con éxito!")