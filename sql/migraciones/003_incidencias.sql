-- Incidencias que n8n registra cuando un workflow falla.
-- Se escriben desde n8n directamente contra Postgres, no a través del agente: si el fallo es
-- que el agente no responde, el aviso tiene que quedar igualmente.
CREATE TABLE IF NOT EXISTS incidencias (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ocurrida_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
    workflow        TEXT,
    n8n_execution_id TEXT,
    nodo            TEXT,
    mensaje         TEXT
);
CREATE INDEX IF NOT EXISTS idx_incidencias_fecha ON incidencias (ocurrida_en DESC);
