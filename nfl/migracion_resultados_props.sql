-- Ejecutar una sola vez en DBeaver sobre defaultdb.
-- Permite conservar el resultado real de cada proyección de props.

ALTER TABLE nfl_proyecciones_props
    ADD COLUMN valor_real DECIMAL(8,2) NULL AFTER contexto_lesiones,
    ADD COLUMN resultado_pick VARCHAR(12) NOT NULL DEFAULT 'PENDIENTE'
        AFTER valor_real,
    ADD COLUMN beneficio_unidades DECIMAL(8,4) NULL AFTER resultado_pick,
    ADD COLUMN evaluado_en DATETIME NULL AFTER beneficio_unidades;

CREATE INDEX idx_nfl_props_pendientes
    ON nfl_proyecciones_props (resultado_pick, id_juego);

-- Comprobación esperada: las cuatro columnas nuevas deben aparecer.
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'nfl_proyecciones_props'
  AND COLUMN_NAME IN (
      'valor_real',
      'resultado_pick',
      'beneficio_unidades',
      'evaluado_en'
  )
ORDER BY ORDINAL_POSITION;
