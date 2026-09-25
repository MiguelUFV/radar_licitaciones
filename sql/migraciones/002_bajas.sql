-- Bajas del feed y control de la descarga de documentos (Fase 2).

-- La Plataforma retira licitaciones con <at:deleted-entry ref=... when=...><at:comment
-- type="ANULADA"/>. La baja puede llegar antes de que hayamos ingerido el expediente, así
-- que se guarda por su entry_id, exista o no la fila en licitaciones.
CREATE TABLE IF NOT EXISTS bajas (
    entry_id        TEXT PRIMARY KEY,
    cuando          TIMESTAMPTZ,
    motivo          TEXT,
    raw_fichero     CHAR(64) REFERENCES raw_ficheros(sha256),
    registrada_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- La vista de trabajo pasa a decir si el expediente está anulado, para no proponer nunca
-- una licitación que ya no existe.
DROP VIEW IF EXISTS v_licitaciones_vigentes;
CREATE VIEW v_licitaciones_vigentes AS
SELECT DISTINCT ON (l.entry_id) l.*, (b.entry_id IS NOT NULL) AS anulada
FROM licitaciones l
LEFT JOIN bajas b ON b.entry_id = l.entry_id
ORDER BY l.entry_id, l.entry_updated DESC;

-- Descarga de pliegos: cuántas veces se ha intentado y cuándo fue la última.
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS intentos INTEGER NOT NULL DEFAULT 0;
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS ultimo_intento TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_doc_pendientes ON documentos (estado_descarga, tipo);
