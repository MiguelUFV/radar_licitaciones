"""El trabajo de cada día, cliente a cliente.

DATOS DE EJEMPLO — no usar en producción. El escenario se monta aquí y no sale a ningún sitio.

Lo que se comprueba, en orden de importancia:

1. **Que una empresa dada de alta por el formulario pueda de verdad entrar en el radar.** El
   formulario le promete que «a partir de mañana entra en el aviso diario», y hasta el
   28-09-2026 eso era mentira: `triajes.alias`, `lecturas.alias` y `fichas.alias` eran claves
   foráneas a `perfiles`, la tabla del estudio, así que la base rechazaba la primera fila.
2. **Que a cada cliente le llegue lo suyo y solo lo suyo.** El correo contaba el gasto del día
   entero, de todos los clientes: uno veía en su pie lo que habían gastado los demás.
3. **Que nadie gaste más de su tope.** El tope diario lo pone el cliente en el formulario y es
   lo único que impide que un día con muchas licitaciones se coma el presupuesto.
"""

import hashlib
from datetime import date

import pytest

from radar import clientes, correo, prompts, triaje
from radar.errores import ErrorRadar

CLIENTE = {
    "nombre": "Soluciones del Norte, S.L.",
    "alias": "Empresa del Norte",
    "correo": "contratacion@ejemplo.es",
    "que_hace": "Desarrollamos software de control horario para ayuntamientos y empresas.",
    "productos": "Autodesk, PRESTO",
    "servicios": "Formación, suministro de terminales",
    "no_hace": "Obra civil",
    "certificaciones": "ISO 9001",
    "ambito": "Asturias",
    "cifra_negocio": "850000",
    "tope_diario_eur": "0.50",
}

PERFIL_ESTUDIO = "## Qué hace\nMantenimiento de equipos informáticos.\n"


def licitacion(conexion, numero: int, objeto: str = "Suministro de licencias de software") -> int:
    """Una licitación vigente, con su rastro hasta la capa raw."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('f', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
            " ON CONFLICT DO NOTHING"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('f', 64), %s, %s, '2026-09-28T10:00:00+02:00') RETURNING id",
            (numero, f"e{numero}"),
        )
        stg = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, expediente, objeto,"
            " organo, importe_sin_iva, plazo_presentacion)"
            " VALUES (%s, '2026-09-28T10:00:00+02:00', %s, %s, %s, 'Ayuntamiento de ejemplo',"
            " 40000, '2026-12-01') RETURNING id",
            (f"e{numero}", stg, f"2026/{numero}", objeto),
        )
        return cur.fetchone()[0]


def empresa_del_estudio(conexion, alias: str = "Empresa A") -> None:
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256, texto, texto_sha256, congelado_en)"
            " VALUES (%s, 'B00000001', 'desarrollo', 2, 2, '1', repeat('c', 64), %s, %s, now())"
            " ON CONFLICT (alias) DO NOTHING",
            (alias, PERFIL_ESTUDIO, hashlib.sha256(PERFIL_ESTUDIO.encode()).hexdigest()),
        )
    conexion.commit()


def ficha_de_prueba(identificador: int | None = None) -> dict:
    return {"modelo": "claude-haiku-4-5", "esfuerzo": None, "id": identificador}


def triar_a_mano(conexion, alias: str, licitaciones: list[int], decision: str = "si") -> None:
    """Apunta un triaje ya hecho, sin llamar al modelo ni pagar nada."""
    lote = [{"id": i} for i in licitaciones]
    respuesta = triaje.Respuesta(decisiones={str(n): (decision, "encaja") for n in range(1, len(lote) + 1)})
    triaje.guardar(conexion, alias, lote, respuesta, ficha_de_prueba(), prompts.cargar("triaje_v1"), 20)


# --- 1. Que un cliente pueda entrar en el radar ---------------------------------------


def test_una_empresa_dada_de_alta_puede_quedar_triada(bd):
    """El fallo de verdad: el alias tenía que estar en `perfiles`, y un cliente nunca lo está."""
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        una = licitacion(conexion, 1)
        triar_a_mano(conexion, "Empresa del Norte", [una])
        with conexion.cursor() as cur:
            cur.execute("SELECT decision FROM triajes WHERE alias = 'Empresa del Norte'")
            assert cur.fetchone()[0] == "si"


def test_un_alias_que_no_es_de_nadie_se_rechaza(bd):
    """Sin la clave foránea hace falta otra cosa: un triaje de un alias fantasma no se avisa."""
    import psycopg

    with bd() as conexion:
        una = licitacion(conexion, 1)
        with pytest.raises(psycopg.errors.RaiseException):
            triar_a_mano(conexion, "Empresa que no existe", [una])


def test_un_cliente_no_puede_llamarse_como_una_empresa_del_estudio(bd):
    """Si coincidieran, el cliente leería las decisiones del estudio y al revés."""
    with bd() as conexion:
        empresa_del_estudio(conexion, "Empresa A")
    with pytest.raises(ErrorRadar) as e:
        clientes.dar_de_alta({**CLIENTE, "alias": "Empresa A"})
    assert "Empresa A" in str(e.value)


# --- 2. Que a cada uno le llegue lo suyo ----------------------------------------------


def test_el_correo_de_un_cliente_va_a_su_direccion(bd):
    clientes.dar_de_alta(CLIENTE)
    escrito = correo.del_correo("Empresa del Norte", date.today())
    assert escrito["destinatario"] == "contratacion@ejemplo.es"
    assert escrito["para"] == "Empresa del Norte"


def test_el_gasto_del_correo_es_solo_el_de_esa_empresa(bd):
    """El pie decía «el día ha costado X» con el gasto de todos los clientes juntos."""
    clientes.dar_de_alta(CLIENTE)
    clientes.dar_de_alta({**CLIENTE, "alias": "Otra Empresa", "correo": "otra@ejemplo.es"})
    with bd() as conexion:
        una, otra = licitacion(conexion, 1), licitacion(conexion, 2)
        with conexion.cursor() as cur:
            for cuanto in (0.01, 0.40):
                cur.execute(
                    "INSERT INTO llm_llamadas (nodo, modelo, coste_usd, coste_eur, tipo_cambio,"
                    " tipo_cambio_origen) VALUES ('triaje', 'claude-haiku-4-5', %s, %s, 1,"
                    " 'prueba') RETURNING id",
                    (cuanto, cuanto),
                )
                cur.fetchone()
        conexion.commit()
        triar_a_mano(conexion, "Empresa del Norte", [una])
        triar_a_mano(conexion, "Otra Empresa", [otra])
        with conexion.cursor() as cur:
            cur.execute(
                "UPDATE triajes SET llm_llamada = (SELECT min(id) FROM llm_llamadas)"
                " WHERE alias = 'Empresa del Norte'"
            )
            cur.execute(
                "UPDATE triajes SET llm_llamada = (SELECT max(id) FROM llm_llamadas)"
                " WHERE alias = 'Otra Empresa'"
            )
            conexion.commit()
    escrito = correo.del_correo("Empresa del Norte", date.today())
    assert "0,01" in escrito["texto"]
    assert "0,41" not in escrito["texto"]
    assert "0,40" not in escrito["texto"]
