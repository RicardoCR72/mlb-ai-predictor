"""Migraciones aditivas y versionadas; repetirlas conserva datos existentes."""
import hashlib

SCHEMAS = {
    'jobs': """CREATE TABLE IF NOT EXISTS oracle_trabajos (
 id CHAR(36) PRIMARY KEY,servicio VARCHAR(40) NOT NULL,
 activo VARCHAR(40) NULL UNIQUE,estado VARCHAR(24) NOT NULL,
 creado_utc DATETIME(6) NOT NULL,iniciado_utc DATETIME(6) NULL,
 terminado_utc DATETIME(6) NULL,paso VARCHAR(180) NULL,resultado JSON NULL,payload JSON NULL,
 KEY ix_oracle_jobs_service(servicio,creado_utc)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    'captures': """CREATE TABLE IF NOT EXISTS nfl_capturas_odds (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_juego VARCHAR(64) NOT NULL, evento_id VARCHAR(64) NOT NULL,
            fecha_mexico DATE NOT NULL, solicitada_en DATETIME NOT NULL,
            estado VARCHAR(20) NOT NULL, creditos INT NULL,
            INDEX jornada (id_juego,fecha_mexico)
        )""",
    'total_publications': """CREATE TABLE IF NOT EXISTS nfl_publicaciones_totales (
 id_juego VARCHAR(128) NOT NULL, modelo VARCHAR(128) NOT NULL,
 seleccion VARCHAR(5) NOT NULL,linea DOUBLE NOT NULL,probabilidad DOUBLE NOT NULL,
 cuota DOUBLE NOT NULL,start_utc DATETIME(6) NOT NULL,publicada_utc DATETIME(6) NOT NULL,
 PRIMARY KEY(id_juego,modelo)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    'prop_publications': """CREATE TABLE IF NOT EXISTS nfl_publicaciones_props (
            id_juego VARCHAR(64) NOT NULL, id_jugador VARCHAR(64) NOT NULL,
            tipo_prop VARCHAR(40) NOT NULL, modelo_version VARCHAR(100) NOT NULL,
            id_linea BIGINT NOT NULL, publicada_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            payload JSON NOT NULL,
            PRIMARY KEY(id_juego,id_jugador,tipo_prop,modelo_version,id_linea)
        )""",
}


def ensure_schema(conn, name):
    if name not in SCHEMAS:
        raise ValueError('Esquema desconocido.')
    cursor = conn.cursor()
    locked = False
    try:
        cursor.execute("SELECT GET_LOCK('oracle-schema-migrations',30)")
        row = cursor.fetchone()
        if not row or row[0] != 1:
            raise RuntimeError('No se pudo adquirir el candado de migraciones.')
        locked = True
        cursor.execute("""CREATE TABLE IF NOT EXISTS oracle_schema_migrations (
            version VARCHAR(100) PRIMARY KEY,checksum CHAR(64) NOT NULL,
            applied_utc DATETIME(6) NOT NULL)""")
        version = '001_' + name
        checksum = hashlib.sha256(SCHEMAS[name].encode()).hexdigest()
        cursor.execute('SELECT checksum FROM oracle_schema_migrations WHERE version=%s',(version,))
        previous = cursor.fetchone()
        if previous:
            if previous[0] != checksum:
                raise RuntimeError('Una migración aplicada fue modificada: ' + version)
        else:
            cursor.execute(SCHEMAS[name])
            cursor.execute('INSERT INTO oracle_schema_migrations VALUES (%s,%s,UTC_TIMESTAMP(6))',(version,checksum))
            conn.commit()
        if name == 'jobs':
            # Existing installations predate the payload column. MySQL DDL commits implicitly;
            # inspect before ALTER so an interrupted upgrade is safe to repeat.
            cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='oracle_trabajos' AND column_name='payload'")
            if cursor.fetchone()[0] == 0:
                cursor.execute('ALTER TABLE oracle_trabajos ADD COLUMN payload JSON NULL')
            cursor.execute("INSERT IGNORE INTO oracle_schema_migrations VALUES ('002_job_payload',%s,UTC_TIMESTAMP(6))",(hashlib.sha256(b'job_payload_v1').hexdigest(),))
            conn.commit()
    finally:
        if locked:
            cursor.execute("SELECT RELEASE_LOCK('oracle-schema-migrations')")
            cursor.fetchone()
        cursor.close()
