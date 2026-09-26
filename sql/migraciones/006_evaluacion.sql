-- Resultados de medición. Toda cifra que se publique sale de aquí, con el commit de git con
-- el que se calculó (CLAUDE.md, innegociable 1).
CREATE TABLE IF NOT EXISTS eval_resultados (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metrica         TEXT NOT NULL,               -- M1, M2…
    variante        TEXT NOT NULL,               -- baseline_a, baseline_b, agente
    alias           TEXT REFERENCES perfiles(alias),  -- NULL si la métrica no es por empresa
    periodo_desde   DATE NOT NULL,
    periodo_hasta   DATE NOT NULL,
    valor           NUMERIC(12, 4) NOT NULL,
    ic_inferior     NUMERIC(12, 4),
    ic_superior     NUMERIC(12, 4),
    n               INTEGER,                     -- tamaño de la muestra sobre la que se calcula
    detalle         JSONB,
    git_commit      TEXT,
    comando         TEXT NOT NULL,
    calculada_en    TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id          UUID REFERENCES ejecuciones(run_id)
);
CREATE INDEX IF NOT EXISTS idx_eval_metrica ON eval_resultados (metrica, variante, alias);
