-- Qué cuentan de verdad las columnas de `historico_meses`.
--
-- No cambian los datos: cambia lo que dicen que son. `licitaciones` y `adjudicaciones` no son
-- el total de ese mes, son **lo que insertó la última pasada**, y una carga que se corta y se
-- retoma deja ahí solo el resto. El 29-09-2026 la fila de 2025-04 decía «55.492 entradas, 998
-- licitaciones» y pareció un agujero en mitad del periodo del estudio; el mes tenía sus 54.569
-- licitaciones enteras y lo que pasó es que se cargó en dos veces.
--
-- Un contador que se lee como un total y no lo es acaba costando un susto o, peor, una
-- conclusión equivocada. Aquí queda dicho en la propia base.

COMMENT ON COLUMN historico_meses.entradas IS
    'Entradas leídas del zip en la última pasada, no el total del mes.';
COMMENT ON COLUMN historico_meses.licitaciones IS
    'Licitaciones insertadas por la última pasada, no el total del mes: una carga retomada '
    'solo cuenta lo que le faltaba. Para el total, contar sobre licitaciones.entry_updated.';
COMMENT ON COLUMN historico_meses.adjudicaciones IS
    'Adjudicaciones insertadas por la última pasada, no el total del mes.';
