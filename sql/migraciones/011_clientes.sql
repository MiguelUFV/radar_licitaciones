-- Las empresas que usan el radar. **No es la tabla `perfiles`, y no puede serlo.**
--
-- `perfiles` es la tabla del estudio: cada fila lleva la semilla del sorteo y el sha256 de la
-- regla con la que se eligió esa empresa, y su perfil está bajo candado para que nadie pueda
-- cambiarlo después de publicar una medición. Un cliente es lo contrario: entra cuando quiere,
-- se describe como quiere y edita su ficha cuando quiere. Si compartieran tabla, una fila de
-- cliente parecería un sujeto del estudio y el estudio dejaría de demostrar nada.
--
-- Los campos salen de lo que midió la Fase 5: de los 20 contratos que el radar dejó escapar,
-- 19 eran productos que el perfil de la empresa no mencionaba. Por eso hay un campo solo para
-- las marcas que distribuye y otro para lo que hace aunque no sea su bandera.
CREATE TABLE IF NOT EXISTS clientes (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alias           TEXT NOT NULL UNIQUE,      -- lo único que aparece en cualquier salida pública
    nombre          TEXT NOT NULL,
    correo          TEXT NOT NULL,
    -- Lo que la empresa cuenta de sí misma. De aquí sale el texto que lee el modelo.
    que_hace        TEXT NOT NULL,
    productos       TEXT,                      -- marcas y productos que distribuye o mantiene
    servicios       TEXT,                      -- lo que hace aunque no sea su bandera
    no_hace         TEXT,                      -- para poder descartar con criterio, no por silencio
    certificaciones TEXT,
    ambito          TEXT,                      -- dónde trabaja
    cifra_negocio   NUMERIC(14, 2),
    cifra_fuente    TEXT,
    -- Lo que el cliente está dispuesto a gastar al día en leer pliegos. Sin esto, el radar no
    -- sabe cuántos puede abrir y tendría que decidirlo alguien por él.
    tope_diario_eur NUMERIC(6, 2) NOT NULL DEFAULT 1.00 CHECK (tope_diario_eur >= 0),
    activo          BOOLEAN NOT NULL DEFAULT true,
    -- El texto tal y como lo lee el modelo, generado de los campos de arriba, con su huella.
    -- Se guarda en lugar de generarse al vuelo porque una decisión tiene que poder explicarse
    -- con el texto exacto que la produjo, y este texto cambia cada vez que el cliente lo edita.
    texto           TEXT NOT NULL,
    texto_sha256    CHAR(64) NOT NULL,
    alta_en         TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_clientes_activos ON clientes (activo, alias);

-- Con qué versión del perfil se decidió cada triaje. Un cliente edita su ficha cuando quiere,
-- así que sin esto no se podría explicar por qué el radar descartó algo hace tres semanas.
ALTER TABLE triajes ADD COLUMN IF NOT EXISTS perfil_sha256 CHAR(64);
