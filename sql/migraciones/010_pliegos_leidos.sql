-- Lo que el radar lee de un pliego y lo que decide con ello.
--
-- Tres tablas y un motivo para cada una:
--  · lecturas   — una pasada del grafo sobre un pliego para una empresa. Es la unidad que hace
--                 el proceso idempotente: repetirla no vuelve a pagar.
--  · requisitos — cada exigencia extraída, con su cita y su página. Se guardan también las que
--                 **no** se pudieron verificar, con el motivo: de ahí sale M5, y una tabla que
--                 solo guardara los aciertos no permitiría medir nada.
--  · fichas     — la decisión (apta / no apta / revisar) con la versión de las reglas que la
--                 tomó y el motivo de cada requisito. Es lo que verá la empresa.
CREATE TABLE IF NOT EXISTS lecturas (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    documento       BIGINT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    licitacion      BIGINT NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    alias           TEXT NOT NULL REFERENCES perfiles(alias),
    -- solvencia · anexos · no_localizada: por qué camino del grafo se fue
    via             TEXT NOT NULL,
    paginas         INTEGER[] NOT NULL DEFAULT '{}',   -- las que se mandaron al modelo
    paginas_totales INTEGER,
    modelo          TEXT,
    prompt_version  TEXT NOT NULL,
    estado          TEXT NOT NULL CHECK (estado IN ('leido', 'sin_localizar', 'ilegible', 'ilegible_respuesta')),
    motivo          TEXT,                              -- en castellano, para la persona
    intentos        INTEGER NOT NULL DEFAULT 1,        -- 2 si hubo que repetir por una cita mala
    run_id          UUID REFERENCES ejecuciones(run_id),
    leida_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (documento, alias, prompt_version)
);
CREATE INDEX IF NOT EXISTS idx_lecturas_empresa ON lecturas (alias, estado);

CREATE TABLE IF NOT EXISTS requisitos (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lectura         BIGINT NOT NULL REFERENCES lecturas(id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL,
    exigencia       TEXT,
    importe_eur     NUMERIC(14, 2),
    anios           INTEGER,
    cita            TEXT NOT NULL,
    pagina          INTEGER,
    -- La cita aparece literal en el texto de esa página. Si es false, el requisito no se usa
    -- para decidir nada y `motivo_rechazo` dice por qué.
    verificada      BOOLEAN NOT NULL,
    motivo_rechazo  TEXT,
    llm_llamada     BIGINT REFERENCES llm_llamadas(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_requisitos_lectura ON requisitos (lectura, verificada);

CREATE TABLE IF NOT EXISTS fichas (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    licitacion      BIGINT NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    alias           TEXT NOT NULL REFERENCES perfiles(alias),
    lectura         BIGINT REFERENCES lecturas(id) ON DELETE SET NULL,
    veredicto       TEXT NOT NULL CHECK (veredicto IN ('apta', 'no_apta', 'revisar')),
    reglas_version  TEXT NOT NULL,
    -- Un motivo por requisito: tipo, resultado, explicación, cita y página.
    motivos         JSONB NOT NULL DEFAULT '[]',
    run_id          UUID REFERENCES ejecuciones(run_id),
    creada_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (licitacion, alias, reglas_version, lectura)
);
CREATE INDEX IF NOT EXISTS idx_fichas_empresa ON fichas (alias, veredicto);
