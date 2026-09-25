-- Carga histórica: los meses anteriores vienen en un zip por mes, no paginando el feed.

-- El zip es un fichero de la capa raw como cualquier otro.
ALTER TABLE raw_ficheros DROP CONSTRAINT IF EXISTS raw_ficheros_tipo_check;
ALTER TABLE raw_ficheros ADD CONSTRAINT raw_ficheros_tipo_check
    CHECK (tipo IN ('feed', 'historico', 'pliego', 'anexo', 'tipo_cambio'));

-- Una entrada histórica se identifica por el zip, el fichero .atom de dentro y su posición.
-- No se copia su XML a la base: son cientos de miles de entradas y el original es inmutable,
-- así que se puede volver a sacar cuando haga falta (radar.historico.entrada_original).
ALTER TABLE stg_entradas ADD COLUMN IF NOT EXISTS miembro TEXT;
ALTER TABLE stg_entradas ALTER COLUMN xml DROP NOT NULL;
ALTER TABLE stg_entradas DROP CONSTRAINT IF EXISTS stg_entradas_raw_fichero_posicion_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_origen
    ON stg_entradas (raw_fichero, coalesce(miembro, ''), posicion);

-- Qué meses están cargados, para poder retomar la descarga donde se quedó.
CREATE TABLE IF NOT EXISTS historico_meses (
    mes             CHAR(7) PRIMARY KEY,
    raw_fichero     CHAR(64) REFERENCES raw_ficheros(sha256),
    ficheros_atom   INTEGER,
    entradas        INTEGER,
    licitaciones    INTEGER,
    adjudicaciones  INTEGER,
    cargado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ejecucion_id    UUID REFERENCES ejecuciones(run_id)
);
