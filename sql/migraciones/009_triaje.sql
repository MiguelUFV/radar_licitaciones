-- Primer nodo del grafo: el triaje. De cada licitación y cada empresa queda qué decidió el
-- modelo, con qué prompt, con qué modelo y en qué llamada, para poder rehacer la medición sin
-- volver a pagar.
--
-- La clave única es lo que hace el triaje idempotente: repetir la pasada no duplica filas ni
-- vuelve a gastar. Incluye `por_llamada` porque triar de una en una o de veinte en veinte son
-- dos condiciones distintas del experimento de D06, y las dos se guardan a la vez.
CREATE TABLE IF NOT EXISTS triajes (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    licitacion      BIGINT NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    alias           TEXT NOT NULL REFERENCES perfiles(alias),
    modelo          TEXT NOT NULL,
    esfuerzo        TEXT,
    por_llamada     INTEGER NOT NULL,       -- cuántas licitaciones iban en la misma llamada
    prompt_version  TEXT NOT NULL,
    -- 'revisar' es lo que pasa cuando el modelo no devuelve una decisión usable para esa
    -- licitación: va a una persona. Nunca se descarta en silencio.
    decision        TEXT NOT NULL CHECK (decision IN ('si', 'no', 'duda', 'revisar')),
    motivo          TEXT,
    llm_llamada     BIGINT REFERENCES llm_llamadas(id) ON DELETE SET NULL,
    run_id          UUID REFERENCES ejecuciones(run_id),
    triada_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (licitacion, alias, modelo, por_llamada, prompt_version)
);
CREATE INDEX IF NOT EXISTS idx_triaje_empresa ON triajes (alias, modelo, por_llamada);
CREATE INDEX IF NOT EXISTS idx_triaje_decision ON triajes (decision);
