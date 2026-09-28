-- Que una empresa dada de alta por el formulario pueda de verdad entrar en el radar.
--
-- `triajes.alias`, `lecturas.alias` y `fichas.alias` apuntaban con una clave foránea a
-- `perfiles`, que es la tabla **del estudio**: siete empresas elegidas por sorteo, congeladas
-- antes de medir. Un cliente nunca está ahí y no puede estarlo (D38), así que la base rechazaba
-- su primera fila: «Key (alias)=(Empresa del Norte) is not present in table "perfiles"». El
-- formulario le prometía que entraba en el aviso diario y era mentira.
--
-- No se puede poner una clave foránea a la unión de dos tablas, así que la comprobación pasa a
-- un disparador. Sigue estando **en la base** y no solo en el código, por lo mismo que la de
-- datos personales (007): el día que alguien inserte por otro camino, la base lo para.

ALTER TABLE triajes  DROP CONSTRAINT IF EXISTS triajes_alias_fkey;
ALTER TABLE lecturas DROP CONSTRAINT IF EXISTS lecturas_alias_fkey;
ALTER TABLE fichas   DROP CONSTRAINT IF EXISTS fichas_alias_fkey;

-- Un alias tiene que ser de alguien: de un cliente o de una empresa del estudio. Si no,
-- estaríamos guardando decisiones que no le llegarán nunca a nadie.
CREATE OR REPLACE FUNCTION alias_de_alguien() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM perfiles WHERE alias = NEW.alias)
       AND NOT EXISTS (SELECT 1 FROM clientes WHERE alias = NEW.alias) THEN
        RAISE EXCEPTION
            'El alias «%» no es de ninguna empresa: ni de un cliente ni del estudio.', NEW.alias;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER triajes_alias_de_alguien
    BEFORE INSERT OR UPDATE OF alias ON triajes
    FOR EACH ROW EXECUTE FUNCTION alias_de_alguien();

CREATE OR REPLACE TRIGGER lecturas_alias_de_alguien
    BEFORE INSERT OR UPDATE OF alias ON lecturas
    FOR EACH ROW EXECUTE FUNCTION alias_de_alguien();

CREATE OR REPLACE TRIGGER fichas_alias_de_alguien
    BEFORE INSERT OR UPDATE OF alias ON fichas
    FOR EACH ROW EXECUTE FUNCTION alias_de_alguien();

-- Y el alias no puede repetirse entre las dos tablas. Si un cliente se llamara «Empresa A»,
-- leería en su correo las decisiones que el estudio tomó para otra empresa, y las mediciones
-- publicadas se mezclarían con el trabajo diario de un cliente. Cada tabla tiene su UNIQUE;
-- lo que falta es que no se pisen entre ellas.
CREATE OR REPLACE FUNCTION alias_sin_repetir() RETURNS trigger AS $$
DECLARE
    otra TEXT := CASE TG_TABLE_NAME WHEN 'clientes' THEN 'perfiles' ELSE 'clientes' END;
    hay BOOLEAN;
BEGIN
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE alias = $1)', otra)
        INTO hay USING NEW.alias;
    IF hay THEN
        RAISE EXCEPTION 'Ya hay una empresa con el nombre «%» en la tabla %.', NEW.alias, otra;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER clientes_alias_sin_repetir
    BEFORE INSERT OR UPDATE OF alias ON clientes
    FOR EACH ROW EXECUTE FUNCTION alias_sin_repetir();

CREATE OR REPLACE TRIGGER perfiles_alias_sin_repetir
    BEFORE INSERT OR UPDATE OF alias ON perfiles
    FOR EACH ROW EXECUTE FUNCTION alias_sin_repetir();
