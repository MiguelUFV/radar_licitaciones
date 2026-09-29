"""Arreglo de los textos que se guardaron con los codigos del XML sin traducir."""

from radar import reparar


def test_traduce_los_codigos_del_xml_de_lo_ya_guardado(bd):
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('7', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('7', 64), 0, 'e1', '2025-03-01T10:00:00+01:00') RETURNING id"
        )
        stg = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, objeto, organo)"
            " VALUES ('e1', '2025-03-01T10:00:00+01:00', %s, %s, %s) RETURNING id",
            (stg, "Sistema &quot;Ebiblio&quot; de KOENIG &amp; BAUER &#40;lote 2&#41;", "Ayuntamiento"),
        )
        cur.execute(
            "INSERT INTO lotes (licitacion, numero, objeto) VALUES (%s, 1, %s)",
            (cur.fetchone()[0], "Mantenimiento &amp; soporte"),
        )
        conexion.commit()

    resumen = reparar.limpiar_textos()
    assert resumen["licitaciones"] == 1
    assert resumen["lotes"] == 1

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT objeto, organo FROM licitaciones")
        objeto, organo = cur.fetchone()
        cur.execute("SELECT objeto FROM lotes")
        lote = cur.fetchone()[0]
    assert objeto == 'Sistema "Ebiblio" de KOENIG & BAUER (lote 2)'
    assert organo == "Ayuntamiento"  # lo que ya estaba bien no se toca
    assert lote == "Mantenimiento & soporte"


def test_volver_a_pasarlo_no_cambia_nada(bd):
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('8', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('8', 64), 0, 'e1', '2025-03-01T10:00:00+01:00') RETURNING id"
        )
        stg = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, objeto)"
            " VALUES ('e1', '2025-03-01T10:00:00+01:00', %s, 'Suministro &amp; montaje')",
            (stg,),
        )
        conexion.commit()

    reparar.limpiar_textos()
    assert reparar.limpiar_textos()["licitaciones"] == 0


def test_una_ejecucion_cortada_se_cierra_diciendo_que_se_corto(bd):
    # El diagnóstico avisa de las ejecuciones que se quedaron a medias y no había forma de
    # cerrarlas: pedía arreglar algo a mano sin decir cómo. Ahora se cierran como lo que son,
    # un error, sin tocar las que siguen vivas de verdad.
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO ejecuciones (run_id, tipo, inicio) VALUES"
            " (gen_random_uuid(), 'evaluacion', now() - interval '6 hours'),"
            " (gen_random_uuid(), 'diaria', now() - interval '5 minutes')"
        )
        conexion.commit()

    assert reparar.cerrar_cortadas(horas=2) == 1

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT tipo, estado, mensaje FROM ejecuciones ORDER BY inicio")
        cortada, viva = cur.fetchall()
    assert cortada[1] == "error" and "cortó" in cortada[2]
    assert viva[1] == "en_curso", "una que acaba de empezar no se toca"
    assert reparar.cerrar_cortadas(horas=2) == 0


def test_se_pueden_cerrar_las_recien_paradas(bd):
    # Al parar una carga a proposito, sus ejecuciones quedan abiertas y no llevan dos horas.
    # Con --horas 0 se cierran las de ahora mismo, que es lo que hace falta en ese momento.
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO ejecuciones (run_id, tipo, inicio) VALUES"
            " (gen_random_uuid(), 'historica', now() - interval '2 minutes')"
        )
        conexion.commit()
    assert reparar.cerrar_cortadas(horas=2) == 0, "una de hace dos minutos no es una colgada"
    # Con decimales, que es lo que manda el CLI: `make_interval(hours => ...)` solo acepta
    # enteros y el comando reventaba con un error de tipos de PostgreSQL.
    assert reparar.cerrar_cortadas(horas=0.5) == 0
    assert reparar.cerrar_cortadas(horas=0.0) == 1
