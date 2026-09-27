-- Toda llamada al modelo queda registrada aquí: qué se pidió, qué contestó, cuántos tokens y
-- cuánto costó en dólares y en euros (CLAUDE.md, innegociable 7). Sin fila aquí no hay llamada.
CREATE TABLE IF NOT EXISTS llm_llamadas (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nodo                TEXT NOT NULL,          -- qué parte del grafo la pidió
    modelo              TEXT NOT NULL,
    esfuerzo            TEXT,                   -- low · medium · high · xhigh · max
    prompt_version      TEXT,
    prompt_sha256       CHAR(64),
    request_id          TEXT,                   -- el de Anthropic, para reclamar si algo falla
    tokens_entrada      INTEGER NOT NULL DEFAULT 0,
    tokens_salida       INTEGER NOT NULL DEFAULT 0,
    tokens_cache_escritura INTEGER NOT NULL DEFAULT 0,
    tokens_cache_lectura   INTEGER NOT NULL DEFAULT 0,
    batch               BOOLEAN NOT NULL DEFAULT false,
    coste_usd           NUMERIC(12, 6) NOT NULL,
    coste_eur           NUMERIC(12, 6) NOT NULL,
    tipo_cambio         NUMERIC(10, 6) NOT NULL,
    tipo_cambio_origen  TEXT NOT NULL,          -- de dónde salió el cambio, con su fecha
    latencia_ms         INTEGER,
    stop_reason         TEXT,
    respuesta           JSONB,                  -- íntegra, para poder rehacer la evaluación sin volver a pagar
    llamada_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id              UUID REFERENCES ejecuciones(run_id),
    licitacion          BIGINT REFERENCES licitaciones(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_dia ON llm_llamadas (llamada_en DESC);
CREATE INDEX IF NOT EXISTS idx_llm_nodo ON llm_llamadas (nodo, modelo);

-- El cambio dólar-euro del día, con el fichero original del que salió.
CREATE TABLE IF NOT EXISTS tipos_cambio (
    fecha           DATE PRIMARY KEY,
    usd_eur         NUMERIC(10, 6) NOT NULL,
    origen          TEXT NOT NULL,
    raw_fichero     CHAR(64) REFERENCES raw_ficheros(sha256)
);
