-- Capas de datos del radar (docs/DATOS.md §3 y §4).
-- L0 raw: lo descargado, inmutable. L1 staging: cada entrada del feed con su XML.
-- L2 núcleo: licitaciones, lotes, documentos y adjudicaciones.
-- L3 análisis: ejecuciones (las tablas del agente llegan en la Fase 4).

CREATE TABLE IF NOT EXISTS ejecuciones (
    run_id          UUID PRIMARY KEY,
    tipo            TEXT NOT NULL CHECK (tipo IN ('diaria', 'historica', 'evaluacion', 'manual')),
    n8n_execution_id TEXT,
    git_commit      TEXT,
    inicio          TIMESTAMPTZ NOT NULL DEFAULT now(),
    fin             TIMESTAMPTZ,
    estado          TEXT NOT NULL DEFAULT 'en_curso' CHECK (estado IN ('en_curso', 'ok', 'error')),
    mensaje         TEXT
);

-- L0 ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_ficheros (
    sha256          CHAR(64) PRIMARY KEY,
    tipo            TEXT NOT NULL CHECK (tipo IN ('feed', 'pliego', 'anexo', 'tipo_cambio')),
    url             TEXT NOT NULL,
    ruta            TEXT NOT NULL,
    bytes           BIGINT NOT NULL,
    descargado_en   TIMESTAMPTZ NOT NULL,
    ejecucion_id    UUID REFERENCES ejecuciones(run_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_url ON raw_ficheros (url);

-- L1 ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stg_entradas (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_fichero     CHAR(64) NOT NULL REFERENCES raw_ficheros(sha256),
    posicion        INTEGER NOT NULL,
    entry_id        TEXT NOT NULL,
    entry_updated   TIMESTAMPTZ,
    xml             TEXT NOT NULL,
    estado_parseo   TEXT NOT NULL DEFAULT 'ok' CHECK (estado_parseo IN ('ok', 'cuarentena')),
    error           TEXT,
    UNIQUE (raw_fichero, posicion)
);
CREATE INDEX IF NOT EXISTS idx_stg_entry ON stg_entradas (entry_id, entry_updated);

-- L2 ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS licitaciones (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id        TEXT NOT NULL,
    entry_updated   TIMESTAMPTZ NOT NULL,
    stg_entrada     BIGINT NOT NULL REFERENCES stg_entradas(id),
    expediente      TEXT,
    organo          TEXT,
    objeto          TEXT,
    estado          TEXT,
    tipo_contrato   TEXT,
    cpv             TEXT[] NOT NULL DEFAULT '{}',
    importe_sin_iva NUMERIC(14, 2),
    valor_estimado  NUMERIC(14, 2),
    plazo_presentacion DATE,
    solvencia_feed  TEXT,
    ficha_url       TEXT,
    -- Idempotencia: una licitación aparece una vez por cada cambio de estado.
    UNIQUE (entry_id, entry_updated)
);
CREATE INDEX IF NOT EXISTS idx_lic_estado ON licitaciones (estado);
CREATE INDEX IF NOT EXISTS idx_lic_cpv ON licitaciones USING GIN (cpv);
CREATE INDEX IF NOT EXISTS idx_lic_plazo ON licitaciones (plazo_presentacion);

CREATE TABLE IF NOT EXISTS lotes (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    licitacion      BIGINT NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    numero          INTEGER,
    objeto          TEXT,
    importe         NUMERIC(14, 2),
    cpv             TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS documentos (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    licitacion      BIGINT NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('PCAP', 'PPT', 'anexo')),
    url             TEXT NOT NULL,
    raw_fichero     CHAR(64) REFERENCES raw_ficheros(sha256),
    estado_descarga TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_descarga IN ('pendiente', 'descargado', 'ilegible', 'error')),
    paginas         INTEGER,
    con_capa_texto  BOOLEAN,
    motivo_error    TEXT,
    UNIQUE (licitacion, tipo, url)
);

CREATE TABLE IF NOT EXISTS adjudicaciones (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    licitacion      BIGINT NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    adjudicatario   TEXT,
    nombre          TEXT,
    es_pyme         BOOLEAN,
    importe         NUMERIC(14, 2)
);
CREATE INDEX IF NOT EXISTS idx_adj_nif ON adjudicaciones (adjudicatario);

-- Vista de trabajo: la última versión de cada expediente.
CREATE OR REPLACE VIEW v_licitaciones_vigentes AS
SELECT DISTINCT ON (entry_id) *
FROM licitaciones
ORDER BY entry_id, entry_updated DESC;

-- Cursor de la ingesta: por dónde iba la última vez.
CREATE TABLE IF NOT EXISTS cursor_feed (
    fuente          TEXT PRIMARY KEY,
    ultima_entrada  TEXT,
    ultima_fecha    TIMESTAMPTZ,
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);
