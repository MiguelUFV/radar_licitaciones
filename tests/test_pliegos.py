"""Descarga de pliegos: qué se guarda, qué se marca y qué pasa cuando algo falla.

Ningún test sale a la red. El PDF de prueba lo construye pypdf, así que es un PDF de
verdad, y el zip es la cabecera real de un fichero comprimido (3 de los 118 pliegos que
bajó la Fase 1 venían así).
"""

import io

import pytest
from conftest import ClienteFalso, entrada, pagina
from pypdf import PdfWriter

from radar import ingesta, pliegos
from radar.errores import ErrorRadar, FuenteNoResponde, SinConexion

ZIP = b"PK\x03\x04\x14\x00\x00\x00lo que sea"


def pdf_de(paginas: int = 3) -> bytes:
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=595, height=842)
    memoria = io.BytesIO()
    escritor.write(memoria)
    return memoria.getvalue()


def una_licitacion_con_pliego(monkeypatch, cpv_informatica: bool = True) -> None:
    """Ingiere una licitación real; si hace falta, con el CPV cambiado a informática."""
    bloque = entrada("https://ejemplo.es/licitacion/1", "2026-09-05T10:00:00.000+02:00")
    if cpv_informatica:
        bloque = bloque.replace("66512200", "72253200")
    paginas = {ingesta.feed.FEED_PERFILES: pagina([bloque])}
    monkeypatch.setattr(ingesta, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: paginas[url])
    monkeypatch.setattr(ingesta.almacen, "buscar_por_url", lambda *a, **kw: None)
    ingesta.ingerir(1, "manual")



def preparar_descarga(monkeypatch, respuesta) -> None:
    monkeypatch.setattr(pliegos, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(pliegos.almacen, "buscar_por_url", lambda *a, **kw: None)
    monkeypatch.setattr(pliegos, "descargar", respuesta)


def test_el_pliego_descargado_queda_ligado_a_su_huella(bd, almacen_temporal, monkeypatch):
    una_licitacion_con_pliego(monkeypatch)
    preparar_descarga(monkeypatch, lambda url, cliente, **kw: pdf_de(3))

    resumen = pliegos.descargar_pendientes(limite=5)
    assert resumen["descargados"] == 1

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "SELECT d.estado_descarga, d.paginas, d.con_capa_texto, r.bytes, r.ruta"
            " FROM documentos d JOIN raw_ficheros r ON r.sha256 = d.raw_fichero"
            " WHERE d.tipo = 'PCAP'"
        )
        estado, paginas_pdf, con_texto, bytes_, ruta = cur.fetchone()
    assert estado == "descargado"
    assert paginas_pdf == 3
    assert con_texto is False  # páginas en blanco: no hay capa de texto
    assert bytes_ > 0
    assert ruta.endswith(".pdf")


def test_un_pliego_comprimido_se_marca_ilegible_con_un_motivo_legible(bd, almacen_temporal, monkeypatch):
    una_licitacion_con_pliego(monkeypatch)
    preparar_descarga(monkeypatch, lambda url, cliente, **kw: ZIP)

    resumen = pliegos.descargar_pendientes(limite=5)
    assert resumen["ilegibles"] == 1

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT estado_descarga, motivo_error, raw_fichero FROM documentos WHERE tipo = 'PCAP'")
        estado, motivo, raw = cur.fetchone()
    assert estado == "ilegible"
    assert "no es un PDF" in motivo
    assert "Traceback" not in motivo
    assert raw is not None  # el fichero se guarda igual: saber que no se puede leer es un dato


def test_un_pliego_ilegible_no_se_reintenta(bd, almacen_temporal, monkeypatch):
    una_licitacion_con_pliego(monkeypatch)
    preparar_descarga(monkeypatch, lambda url, cliente, **kw: ZIP)
    pliegos.descargar_pendientes(limite=5)

    segunda = pliegos.descargar_pendientes(limite=5)
    assert segunda["pedidos"] == 0


def test_si_se_cae_la_red_lo_ya_descargado_no_se_pierde(bd, almacen_temporal, monkeypatch):
    una_licitacion_con_pliego(monkeypatch)

    def sin_red(url, cliente, **kw):
        raise SinConexion("No hay conexión a internet. No se ha descargado nada.")

    preparar_descarga(monkeypatch, sin_red)

    with pytest.raises(ErrorRadar) as fallo:
        pliegos.descargar_pendientes(limite=5)
    assert "conexión" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT estado, mensaje FROM ejecuciones WHERE tipo = 'manual' ORDER BY inicio DESC")
        estado, mensaje = cur.fetchone()
        assert estado == "error"
        assert "Traceback" not in mensaje
        cur.execute("SELECT estado_descarga FROM documentos WHERE tipo = 'PCAP'")
        assert cur.fetchone()[0] == "pendiente"  # sigue en la cola para la próxima


def test_un_pliego_que_da_error_vuelve_a_la_cola(bd, almacen_temporal, monkeypatch):
    una_licitacion_con_pliego(monkeypatch)

    def rechazado(url, cliente, **kw):
        raise FuenteNoResponde("La Plataforma de Contratación rechazó la petición (código 404).")

    preparar_descarga(monkeypatch, rechazado)
    primera = pliegos.descargar_pendientes(limite=5)
    assert primera["errores"] == 1

    # Un 404 puede ser pasajero: se reintenta, pero no para siempre.
    preparar_descarga(monkeypatch, lambda url, cliente, **kw: pdf_de(1))
    segunda = pliegos.descargar_pendientes(limite=5)
    assert segunda["descargados"] == 1


def test_no_se_baja_el_pliego_de_una_licitacion_anulada(bd, almacen_temporal, monkeypatch):
    anulada = "https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/20499474"
    bloque = entrada(anulada, "2026-09-05T10:00:00.000+02:00").replace("66512200", "72253200")
    from conftest import BAJA_REAL

    paginas = {ingesta.feed.FEED_PERFILES: pagina([bloque], bajas=BAJA_REAL)}
    monkeypatch.setattr(ingesta, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: paginas[url])
    monkeypatch.setattr(ingesta.almacen, "buscar_por_url", lambda *a, **kw: None)
    ingesta.ingerir(1, "manual")

    preparar_descarga(monkeypatch, lambda url, cliente, **kw: pdf_de(1))
    assert pliegos.descargar_pendientes(limite=5)["pedidos"] == 0


def test_el_pliego_ya_bajado_no_se_vuelve_a_pedir(bd, almacen_temporal, monkeypatch):
    una_licitacion_con_pliego(monkeypatch)

    def no_deberia_pedirse(url, cliente, **kw):
        raise AssertionError("se ha pedido a la red un pliego que ya estaba en disco")

    monkeypatch.setattr(pliegos, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(pliegos, "descargar", no_deberia_pedirse)
    monkeypatch.setattr(pliegos.almacen, "buscar_por_url", lambda *a, **kw: pdf_de(2))

    resumen = pliegos.descargar_pendientes(limite=5)
    assert resumen["desde_disco"] == 1
    assert resumen["descargados"] == 1
