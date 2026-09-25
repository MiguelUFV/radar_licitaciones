"""Descargas HTTP.

Dos decisiones que vienen de haberlo roto antes (docs/DECISIONES.md D12 y docs/DOMINIO.md §9):
- Los certificados se verifican siempre, con el almacén de certifi. Nunca `verify=False`.
- Las URL salen de un XML y llegan con `&amp;`. Sin deshacer esa codificación, el servidor
  de documentos responde 500.
"""

from __future__ import annotations

import html
import time

import certifi
import httpx

from radar.errores import CertificadoNoVerificable, FuenteNoResponde, SinConexion

ESPERA_ENTRE_INTENTOS = (2, 5, 10)
CABECERAS = {
    # Sin tildes: httpx exige cabeceras ASCII (ver tests/test_red.py).
    "User-Agent": "radar-licitaciones/0.1 (proyecto academico; contacto en el repositorio)",
    "Accept": "*/*",
    "Accept-Language": "es-ES,es;q=0.9",
}


def normalizar_url(url: str) -> str:
    """Deshace las entidades XML de una URL sacada del feed."""
    return html.unescape(url.strip())


def crear_cliente(timeout: float = 90.0) -> httpx.Client:
    return httpx.Client(
        verify=certifi.where(),
        timeout=timeout,
        follow_redirects=True,
        headers=CABECERAS,
    )


def descargar(url: str, cliente: httpx.Client, intentos: int = 3) -> bytes:
    """Descarga una URL y traduce cualquier fallo a un error con mensaje legible."""
    url = normalizar_url(url)
    ultimo: Exception | None = None

    for intento in range(intentos):
        try:
            respuesta = cliente.get(url)
            respuesta.raise_for_status()
            return respuesta.content
        except httpx.HTTPStatusError as e:
            ultimo = e
            if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                raise FuenteNoResponde(
                    f"La Plataforma de Contratación rechazó la petición (código {e.response.status_code}).",
                    detalle=f"{url} -> {e}",
                ) from e
        except httpx.ConnectError as e:
            ultimo = e
            texto = str(e).lower()
            if "certificate" in texto or "ssl" in texto:
                raise CertificadoNoVerificable(
                    "No se ha podido verificar la identidad del servidor de la Plataforma de "
                    "Contratación. Revisa la instalación de certificados (paquete certifi).",
                    detalle=str(e),
                ) from e
            if "getaddrinfo" in texto or "name or service" in texto or "nodename" in texto:
                raise SinConexion(
                    "No hay conexión a internet. No se ha descargado nada; se reintentará en la "
                    "próxima ejecución.",
                    detalle=str(e),
                ) from e
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ReadError) as e:
            ultimo = e

        if intento < intentos - 1:
            time.sleep(ESPERA_ENTRE_INTENTOS[min(intento, len(ESPERA_ENTRE_INTENTOS) - 1)])

    raise FuenteNoResponde(
        "La Plataforma de Contratación no responde. No hay datos nuevos en esta ejecución.",
        detalle=f"{url} -> {ultimo!r}",
    )
