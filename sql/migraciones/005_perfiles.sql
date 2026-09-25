-- Empresas del estudio. Quién entra lo decide docs/REGLA_SELECCION.md, aplicada por
-- radar/seleccion.py; aquí solo queda el resultado, con la huella de la regla que se aplicó.
CREATE TABLE IF NOT EXISTS perfiles (
    alias           TEXT PRIMARY KEY,              -- Empresa A, Empresa B… (lo único que se publica)
    nif             TEXT NOT NULL UNIQUE,
    nombre          TEXT,
    rol             TEXT NOT NULL CHECK (rol IN ('desarrollo', 'test')),
    adjudicaciones  INTEGER NOT NULL,
    de_informatica  INTEGER NOT NULL,
    -- El perfil lo escribe una persona a partir de la web de la empresa, sin mirar sus
    -- contratos, y se congela con su hash (regla §6). Vacío hasta entonces.
    texto           TEXT,
    texto_sha256    CHAR(64),
    fuentes         TEXT,
    cifra_negocio   NUMERIC(14, 2),
    cifra_fuente    TEXT,
    congelado_en    TIMESTAMPTZ,
    -- Con qué se eligió: semilla del sorteo y hash del fichero de la regla en ese momento.
    seleccionada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    semilla         TEXT NOT NULL,
    regla_sha256    CHAR(64) NOT NULL,
    ejecucion_id    UUID REFERENCES ejecuciones(run_id)
);
