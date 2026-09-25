"""Capa raw: lo descargado se guarda tal cual y con su formato real."""

from radar import almacen

# Cabeceras reales: de los 118 pliegos que bajó la Fase 1, 115 empiezan por %PDF y 3 por PK.
PDF = b"%PDF-1.4\n1 0 obj\n"
ZIP = b"PK\x03\x04\x14\x00\x00\x00"


def test_un_zip_no_se_guarda_con_extension_de_pdf(almacen_temporal):
    # La Plataforma sirve algunos pliegos comprimidos. Guardarlos como .pdf hace que la
    # capa raw mienta sobre lo que contiene, y quien la revise abra un fichero que no es.
    comprimido = almacen.guardar(ZIP, "pliego", "https://ejemplo.es/pliego.zip", "prueba")
    suelto = almacen.guardar(PDF, "pliego", "https://ejemplo.es/pliego.pdf", "prueba")

    assert comprimido["ruta"].endswith(".zip")
    assert suelto["ruta"].endswith(".pdf")


def test_el_feed_conserva_su_extension(almacen_temporal):
    ficha = almacen.guardar(b"<?xml version='1.0'?><feed/>", "feed", "https://ejemplo.es/f", "prueba")
    assert ficha["ruta"].endswith(".atom")


def test_el_mismo_contenido_ocupa_un_solo_fichero(almacen_temporal):
    primera = almacen.guardar(PDF, "pliego", "https://ejemplo.es/a", "prueba")
    segunda = almacen.guardar(PDF, "pliego", "https://ejemplo.es/b", "prueba")
    assert primera["sha256"] == segunda["sha256"]
    assert primera["ruta"] == segunda["ruta"]
