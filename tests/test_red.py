"""Comprobaciones de la capa de red.

El test de las cabeceras nace de un fallo real del 25-09-2026: la cabecera User-Agent llevaba
una tilde y httpx solo admite ASCII, así que la Fase 1 moría antes de descargar nada.
"""

import types

import certifi
import pytest

from radar import red
from radar.errores import FuenteNoResponde, SinConexion


def test_las_cabeceras_son_ascii():
    for nombre, valor in red.CABECERAS.items():
        valor.encode("ascii")  # falla si alguien vuelve a meter una tilde
        assert nombre.isascii()


def test_el_cliente_se_crea_y_verifica_certificados():
    with red.crear_cliente() as cliente:
        assert cliente.headers["user-agent"].isascii()
    assert certifi.where().endswith("cacert.pem")


def test_las_urls_del_feed_se_desescapan():
    sucia = "https://ejemplo.es/doc?cifrado=ABC%3D%3D&amp;DocumentIdParam=XYZ"
    assert red.normalizar_url(sucia) == "https://ejemplo.es/doc?cifrado=ABC%3D%3D&DocumentIdParam=XYZ"


def test_sin_red_da_un_mensaje_en_castellano(monkeypatch):
    import httpx

    class ClienteRoto:
        def stream(self, metodo, url):
            raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    with pytest.raises(SinConexion) as fallo:
        red.descargar("https://contrataciondelsectorpublico.gob.es/x", ClienteRoto(), intentos=1)
    assert "conexión a internet" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_un_404_no_se_reintenta_y_se_explica():

    class RespuestaCuatroCientosCuatro:
        status_code = 404
        headers: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class ClienteQueDa404:
        llamadas = 0

        def stream(self, metodo, url):
            ClienteQueDa404.llamadas += 1
            return RespuestaCuatroCientosCuatro()

    with pytest.raises(FuenteNoResponde):
        red.descargar("https://contrataciondelsectorpublico.gob.es/x", ClienteQueDa404(), intentos=3)
    assert ClienteQueDa404.llamadas == 1


# --- De donde se permite descargar -----------------------------------------------------


def test_solo_se_descarga_de_los_dominios_de_la_plataforma():
    # Las URL de los documentos vienen del feed, y cualquiera puede publicar un anuncio. Sin
    # esta lista, un anuncio manipulado haria que el radar pidiera direcciones de la red
    # interna del ordenador que lo ejecuta.
    assert red.dominio_permitido("https://contrataciondelestado.es/FileSystem/servlet/x")
    assert red.dominio_permitido("http://contrataciondelsectorpublico.gob.es/sindicacion/x.zip")
    assert red.dominio_permitido("https://www.contrataciondelestado.es/algo")

    assert not red.dominio_permitido("http://127.0.0.1:8000/ingesta")
    assert not red.dominio_permitido("http://localhost:5679/api/v1/workflows")
    assert not red.dominio_permitido("http://192.168.1.1/")
    assert not red.dominio_permitido("http://169.254.169.254/latest/meta-data/")
    assert not red.dominio_permitido("https://contrataciondelestado.es.malo.com/x")
    assert not red.dominio_permitido("file:///C:/Users/migue/.env")


def test_una_url_de_fuera_no_se_pide_siquiera():
    def no_deberia_pedirse(*args, **kwargs):
        raise AssertionError("se ha pedido una URL que no es de la Plataforma")

    cliente = types.SimpleNamespace(get=no_deberia_pedirse, request=no_deberia_pedirse)
    with pytest.raises(FuenteNoResponde) as fallo:
        red.descargar("http://127.0.0.1:8000/ingesta", cliente)
    assert "no es de la Plataforma" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_un_documento_gigante_se_corta():
    # Un fichero enorme llenaria la memoria del proceso antes de poder mirar que es.
    trozos = [b"x" * 1024] * 100

    class RespuestaFalsa:
        status_code = 200
        url = "https://contrataciondelestado.es/doc.pdf"
        headers: dict = {}

        def iter_bytes(self, chunk_size=None):
            yield from trozos

        def raise_for_status(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    cliente = types.SimpleNamespace(stream=lambda *a, **kw: RespuestaFalsa())
    with pytest.raises(FuenteNoResponde) as fallo:
        red.descargar("https://contrataciondelestado.es/doc.pdf", cliente, maximo=10 * 1024)
    assert "demasiado grande" in str(fallo.value)


def test_el_contexto_tls_verifica_de_verdad():
    import ssl

    contexto = red.contexto_tls()
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    assert contexto.check_hostname is True
