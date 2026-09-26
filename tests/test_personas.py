"""Adjudicatarios que son personas físicas.

Los identificadores de aquí son inventados con el formato real (letra de CIF, DNI de ocho
cifras, NIE con X/Y/Z), no corresponden a nadie.
"""

import pytest
from conftest import como_antes_de_la_restriccion

from radar import personas
from radar.errores import FaltaConfiguracion

SAL = "sal-de-prueba"


def test_distingue_empresa_de_persona():
    assert personas.es_persona_fisica("B12345678") is False  # sociedad limitada
    assert personas.es_persona_fisica("A12345678") is False  # sociedad anonima
    assert personas.es_persona_fisica("U12345678") is False  # UTE, que es de empresas
    assert personas.es_persona_fisica("12345678Z") is True  # DNI


def test_un_nie_es_una_persona_aunque_empiece_por_letra():
    # X, Y y Z son NIE: empiezan por letra y colarian como empresa si solo se mirara eso.
    for nie in ("X1234567L", "Y1234567X", "Z1234567R"):
        assert personas.es_persona_fisica(nie) is True


def test_el_seudonimo_es_estable_y_no_deja_ver_el_dni():
    uno = personas.seudonimo("12345678Z", SAL)
    assert uno == personas.seudonimo("12345678z", SAL)  # da igual como venga escrito
    assert uno.startswith("pf_")
    assert "12345678" not in uno
    assert uno != personas.seudonimo("12345678Z", "otra-sal")


def test_seudonimizar_dos_veces_no_cambia_nada():
    uno = personas.seudonimo("12345678Z", SAL)
    assert personas.seudonimo(uno, SAL) == uno


def test_de_una_persona_no_se_guarda_ni_el_dni_ni_el_nombre(monkeypatch):
    monkeypatch.setenv("SAL_PERSONAS", SAL)
    monkeypatch.setattr(personas, "load_dotenv", lambda *a, **kw: None)

    nif, nombre = personas.como_se_guarda("12345678Z", "NOMBRE APELLIDO APELLIDO")
    assert nif.startswith("pf_")
    assert nombre is None


def test_de_una_empresa_se_guarda_todo_tal_cual(monkeypatch):
    monkeypatch.setenv("SAL_PERSONAS", SAL)
    monkeypatch.setattr(personas, "load_dotenv", lambda *a, **kw: None)

    assert personas.como_se_guarda("B12345678", "EJEMPLO SL") == ("B12345678", "EJEMPLO SL")


def test_sin_sal_no_se_guarda_nada_y_el_aviso_se_entiende(monkeypatch):
    monkeypatch.delenv("SAL_PERSONAS", raising=False)
    monkeypatch.setattr(personas, "load_dotenv", lambda *a, **kw: None)

    with pytest.raises(FaltaConfiguracion) as fallo:
        personas.como_se_guarda("12345678Z", "NOMBRE APELLIDO")
    assert "SAL_PERSONAS" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_la_ingesta_no_escribe_el_dni_de_un_autonomo(bd, almacen_temporal, monkeypatch):
    from conftest import ClienteFalso, entrada, pagina

    from radar import ingesta

    monkeypatch.setenv("SAL_PERSONAS", SAL)
    monkeypatch.setattr(personas, "load_dotenv", lambda *a, **kw: None)

    bloque = entrada("https://ejemplo.es/1", "2026-09-05T10:00:00.000+02:00")
    bloque = bloque.replace("A08169294", "12345678Z")
    paginas = {ingesta.feed.FEED_PERFILES: pagina([bloque])}
    monkeypatch.setattr(ingesta, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: paginas[url])
    monkeypatch.setattr(ingesta.almacen, "buscar_por_url", lambda *a, **kw: None)

    ingesta.ingerir(1, "manual")

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT adjudicatario, nombre FROM adjudicaciones")
        adjudicatario, nombre = cur.fetchone()
    assert adjudicatario.startswith("pf_")
    assert "12345678" not in adjudicatario
    assert nombre is None


def test_anonimiza_lo_que_ya_estaba_guardado(bd, monkeypatch):
    monkeypatch.setenv("SAL_PERSONAS", SAL)
    monkeypatch.setattr(personas, "load_dotenv", lambda *a, **kw: None)

    # La limpieza tiene que correr con la puerta abierta: es lo que arregla las filas de
    # antes de que existiera la restricción.
    with como_antes_de_la_restriccion(bd):
        with bd() as conexion, conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
                " VALUES (repeat('d', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
            )
            cur.execute(
                "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
                " VALUES (repeat('d', 64), 0, 'e1', '2025-03-01T10:00:00+01:00') RETURNING id"
            )
            stg = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada)"
                " VALUES ('e1', '2025-03-01T10:00:00+01:00', %s) RETURNING id",
                (stg,),
            )
            licitacion = cur.fetchone()[0]
            for nif, nombre in [("12345678Z", "NOMBRE APELLIDO"), ("B12345678", "EJEMPLO SL")]:
                cur.execute(
                    "INSERT INTO adjudicaciones (licitacion, adjudicatario, nombre) VALUES (%s, %s, %s)",
                    (licitacion, nif, nombre),
                )
            conexion.commit()

        resumen = personas.anonimizar_lo_ya_guardado()

    assert resumen["personas"] == 1
    assert resumen["adjudicaciones"] == 1

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT adjudicatario, nombre FROM adjudicaciones ORDER BY adjudicatario")
        filas = cur.fetchall()
    assert filas[0] == ("B12345678", "EJEMPLO SL")  # la empresa no se toca
    assert filas[1][0].startswith("pf_")
    assert filas[1][1] is None


def test_el_diagnostico_avisa_si_queda_un_dni_en_claro(bd):
    from radar import diagnostico

    correcto, mensaje = diagnostico.comprobar_datos_personales()
    assert correcto is True

    with como_antes_de_la_restriccion(bd), bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('e', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('e', 64), 0, 'e1', '2025-03-01T10:00:00+01:00') RETURNING id"
        )
        stg = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada)"
            " VALUES ('e1', '2025-03-01T10:00:00+01:00', %s) RETURNING id",
            (stg,),
        )
        cur.execute(
            "INSERT INTO adjudicaciones (licitacion, adjudicatario) VALUES (%s, '12345678Z')",
            (cur.fetchone()[0],),
        )
        conexion.commit()

        correcto, mensaje = diagnostico.comprobar_datos_personales()

    assert correcto is False
    assert "en claro" in mensaje
    assert "radar.personas --anonimizar" in mensaje


def test_la_base_rechaza_un_dni_aunque_el_codigo_falle(bd):
    # Defensa en profundidad: si manana alguien inserta por otro camino y se olvida de
    # seudonimizar, la base lo rechaza igual.
    import psycopg

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('9', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('9', 64), 0, 'e1', '2025-03-01T10:00:00+01:00') RETURNING id"
        )
        stg = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada)"
            " VALUES ('e1', '2025-03-01T10:00:00+01:00', %s) RETURNING id",
            (stg,),
        )
        licitacion = cur.fetchone()[0]
        conexion.commit()

    for identificador in ("12345678Z", "X1234567L"):
        with bd() as conexion, conexion.cursor() as cur:
            with pytest.raises(psycopg.errors.CheckViolation):
                cur.execute(
                    "INSERT INTO adjudicaciones (licitacion, adjudicatario) VALUES (%s, %s)",
                    (licitacion, identificador),
                )

    # Y de una persona seudonimizada tampoco se puede guardar el nombre.
    with bd() as conexion, conexion.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO adjudicaciones (licitacion, adjudicatario, nombre)"
                " VALUES (%s, 'pf_abc123', 'NOMBRE APELLIDO')",
                (licitacion,),
            )

    # Una empresa entra sin problema.
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO adjudicaciones (licitacion, adjudicatario, nombre)"
            " VALUES (%s, 'B12345678', 'EJEMPLO SL')",
            (licitacion,),
        )
        conexion.commit()
