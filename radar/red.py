"""Descargas HTTP.

Tres decisiones que vienen de haberlo roto antes (docs/DECISIONES.md D12 y D31):
- Los certificados se verifican siempre, con el almacén de certifi. Nunca `verify=False`.
- Las URL salen de un XML y llegan con `&amp;`. Sin deshacer esa codificación, el servidor
  de documentos responde 500.
- Solo se descarga de los dominios de la Plataforma, y con un tope de tamaño. Las URL de los
  documentos vienen del feed, y en el feed publica cualquier organismo: sin esa lista, un
  anuncio manipulado podría hacer que el radar pidiera direcciones de la red interna.
"""

from __future__ import annotations

import html
import ssl
import time
from urllib.parse import urljoin, urlsplit

import certifi
import httpx

from radar.errores import CertificadoNoVerificable, FuenteNoResponde, SinConexion

ESPERA_ENTRE_INTENTOS = (2, 5, 10)
DOMINIOS = ("contrataciondelestado.es", "contrataciondelsectorpublico.gob.es")
# Los zip mensuales del histórico pesan unos 200 MB; un pliego, unos pocos.
MAXIMO = 400 * 1024 * 1024
MAXIMO_DOCUMENTO = 60 * 1024 * 1024
SALTOS = 5
REDIRECCIONES = (301, 302, 303, 307, 308)
CABECERAS = {
    # Sin tildes: httpx exige cabeceras ASCII (ver tests/test_red.py).
    "User-Agent": "radar-licitaciones/0.1 (proyecto academico; contacto en el repositorio)",
    "Accept": "*/*",
    "Accept-Language": "es-ES,es;q=0.9",
}


def normalizar_url(url: str) -> str:
    """Deshace las entidades XML de una URL sacada del feed."""
    return html.unescape(url.strip())


def contexto_tls() -> ssl.SSLContext:
    """Los certificados se verifican con el almacén de certifi, siempre (D12).

    Se construye el contexto a mano porque pasar la ruta del almacén a httpx está
    obsoleto y dejará de funcionar; y esto no es un detalle cosmético: es la comprobación
    de que hablamos con quien creemos.
    """
    return ssl.create_default_context(cafile=certifi.where())


def crear_cliente(timeout: float = 90.0) -> httpx.Client:
    return httpx.Client(
        verify=contexto_tls(),
        timeout=timeout,
        # Los saltos se siguen a mano para comprobar el dominio en cada uno: una redirección
        # a 127.0.0.1 no se puede pedir "y luego mirar".
        follow_redirects=False,
        headers=CABECERAS,
    )


def dominio_permitido(url: str) -> bool:
    partes = urlsplit(url)
    if partes.scheme not in {"http", "https"}:
        return False
    host = (partes.hostname or "").lower()
    return any(host == dominio or host.endswith(f".{dominio}") for dominio in DOMINIOS)


class _Reintentar(Exception):
    """Fallo del servidor (5xx o 429): merece la pena volver a intentarlo."""


def _pedir(cliente, url: str, maximo: int) -> bytes:
    for _ in range(SALTOS + 1):
        with cliente.stream("GET", url) as respuesta:
            if respuesta.status_code in REDIRECCIONES:
                destino = urljoin(url, respuesta.headers.get("location", ""))
                if not dominio_permitido(destino):
                    raise FuenteNoResponde(
                        "La Plataforma de Contratación ha redirigido la descarga fuera de sus "
                        "propios servidores. No se sigue.",
                        detalle=f"{url} -> {destino}",
                    )
                url = destino
                continue
            if 400 <= respuesta.status_code < 500 and respuesta.status_code != 429:
                raise FuenteNoResponde(
                    f"La Plataforma de Contratación rechazó la petición (código {respuesta.status_code}).",
                    detalle=url,
                )
            if respuesta.status_code >= 400:
                raise _Reintentar(str(respuesta.status_code))

            trozos, total = [], 0
            for trozo in respuesta.iter_bytes(chunk_size=1 << 20):
                total += len(trozo)
                if total > maximo:
                    raise FuenteNoResponde(
                        f"El fichero es demasiado grande ({total / 1_048_576:.0f} MB o más). No se descarga.",
                        detalle=url,
                    )
                trozos.append(trozo)
            return b"".join(trozos)
    raise FuenteNoResponde("La Plataforma de Contratación encadena demasiadas redirecciones.", detalle=url)


def descargar(url: str, cliente: httpx.Client, intentos: int = 3, maximo: int = MAXIMO) -> bytes:
    """Descarga una URL de la Plataforma y traduce cualquier fallo a un mensaje legible."""
    url = normalizar_url(url)
    if not dominio_permitido(url):
        raise FuenteNoResponde(
            "Esa dirección no es de la Plataforma de Contratación, así que no se descarga.",
            detalle=url,
        )
    ultimo: Exception | None = None

    for intento in range(intentos):
        try:
            return _pedir(cliente, url, maximo)
        except _Reintentar as e:
            ultimo = e
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
