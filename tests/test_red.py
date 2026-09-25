"""Comprobaciones de la capa de red.

El test de las cabeceras nace de un fallo real del 25-09-2026: la cabecera User-Agent llevaba
una tilde y httpx solo admite ASCII, así que la Fase 1 moría antes de descargar nada.
"""

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
        def get(self, url):
            raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    with pytest.raises(SinConexion) as fallo:
        red.descargar("https://contrataciondelsectorpublico.gob.es/x", ClienteRoto(), intentos=1)
    assert "conexión a internet" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_un_404_no_se_reintenta_y_se_explica():
    import httpx

    class ClienteQueDa404:
        llamadas = 0

        def get(self, url):
            ClienteQueDa404.llamadas += 1
            peticion = httpx.Request("GET", url)
            respuesta = httpx.Response(404, request=peticion)
            raise httpx.HTTPStatusError("404", request=peticion, response=respuesta)

    with pytest.raises(FuenteNoResponde):
        red.descargar("https://contrataciondelsectorpublico.gob.es/x", ClienteQueDa404(), intentos=3)
    assert ClienteQueDa404.llamadas == 1
