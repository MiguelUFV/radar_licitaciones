"""El informe de estado, que es lo que se mira para saber como va todo.

Se lee en una consola de Windows, que no sabe escribir cualquier caracter: si el informe
lleva uno raro, revienta con una traza delante del usuario, que es justo lo que el proyecto
no permite (CLAUDE.md, innegociable 3).
"""

from radar import estado


def test_el_informe_se_puede_imprimir_en_una_consola_de_windows(bd):
    texto = estado.informe()
    texto.encode("cp1252")  # si lleva un caracter que la consola no sabe, esto falla


def test_el_informe_dice_lo_que_hay_aunque_no_haya_nada(bd):
    texto = estado.informe()
    assert "DESCARGA DEL HISTORICO" in texto.replace("Ó", "O")
    assert "Ninguno." in texto  # sin datos no hay avisos
    assert "todavía no se ha lanzado ninguna" in texto


def test_avisa_de_los_datos_personales_en_claro(bd):
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('f', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('f', 64), 0, 'e1', '2025-03-01T10:00:00+01:00') RETURNING id"
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

    texto = estado.informe()
    assert "datos personales guardados en claro" in texto
    texto.encode("cp1252")


def test_los_meses_se_cuentan_bien():
    assert estado.meses_totales("2025-01", "2025-06") == 6
    assert estado.meses_totales("2025-07", "2026-08") == 14
    assert estado.meses_totales("2025-01", "2025-01") == 1
