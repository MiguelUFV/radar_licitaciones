-- Ningún DNI ni NIE de adjudicatario puede quedar guardado en claro (docs/DATOS.md §7).
--
-- Esto ya lo hace radar/personas.py antes de escribir, pero la comprobación vive también en
-- la base a propósito: si mañana alguien inserta por otro camino y se olvida, la base lo
-- rechaza. Se descubrió por las malas (26-09-2026: 6.270 DNI y 129 NIE guardados en claro).
--
-- Letras de persona jurídica: A-H, J, N, P-S, U, V, W. Las que faltan no es casualidad: un
-- DNI empieza por número y un NIE por X, Y o Z, y los dos son de una persona.

ALTER TABLE adjudicaciones DROP CONSTRAINT IF EXISTS adjudicaciones_sin_datos_personales;
ALTER TABLE adjudicaciones ADD CONSTRAINT adjudicaciones_sin_datos_personales CHECK (
    adjudicatario IS NULL
    OR upper(left(adjudicatario, 1)) ~ '^[ABCDEFGHJNPQRSUVW]$'
    OR adjudicatario LIKE 'pf|_%' ESCAPE '|'
);

-- De una persona seudonimizada tampoco se guarda el nombre.
ALTER TABLE adjudicaciones DROP CONSTRAINT IF EXISTS adjudicaciones_persona_sin_nombre;
ALTER TABLE adjudicaciones ADD CONSTRAINT adjudicaciones_persona_sin_nombre CHECK (
    adjudicatario IS NULL
    OR adjudicatario NOT LIKE 'pf|_%' ESCAPE '|'
    OR nombre IS NULL
);
