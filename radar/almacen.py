"""Capa raw: lo descargado se guarda tal cual, identificado por su sha256.

Un fichero descargado dos veces ocupa un solo sitio. El manifiesto (CSV) permite volver a
descargarlo todo y detectar si la fuente ha cambiado (docs/DATOS.md §1 y §8).
"""

from __future__ import annotations

import csv
import hashlib
from datetime import UTC, datetime
from pathlib import Path

RAIZ_DATOS = Path("data")
RAW = RAIZ_DATOS / "raw"
MANIFIESTOS = RAIZ_DATOS / "manifiestos"

# La Plataforma sirve pliegos en PDF, comprimidos y firmados: el nombre del fichero tiene que
# decir lo que hay dentro, no lo que se esperaba (de los 118 de la Fase 1, 3 eran zip).
FIRMAS = ((b"%PDF", ".pdf"), (b"PK\x03\x04", ".zip"), (b"<?xml", ".xml"))


def extension(tipo: str, contenido: bytes) -> str:
    if tipo == "feed":
        return ".atom"
    for firma, sufijo in FIRMAS:
        if contenido.startswith(firma):
            return sufijo
    return ".bin"


def _ruta(tipo: str, huella: str, sufijo: str) -> Path:
    return RAW / tipo / huella[:2] / f"{huella}{sufijo}"


def guardar(contenido: bytes, tipo: str, url: str, manifiesto: str) -> dict:
    """Guarda el contenido y anota una línea en el manifiesto. Devuelve la ficha del fichero."""
    huella = hashlib.sha256(contenido).hexdigest()
    destino = _ruta(tipo, huella, extension(tipo, contenido))
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.exists():
        destino.write_bytes(contenido)

    ficha = {
        "sha256": huella,
        "tipo": tipo,
        "url": url,
        "bytes": len(contenido),
        "ruta": str(destino.as_posix()),
        "descargado_en": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if _indice(manifiesto).get(url.strip()) != ficha["ruta"]:
        anotar(ficha, manifiesto)
    return ficha


_INDICES: dict[str, dict[str, str]] = {}


def _indice(manifiesto: str) -> dict[str, str]:
    """URL -> ruta local, leyendo el manifiesto una sola vez por ejecución."""
    if manifiesto not in _INDICES:
        indice: dict[str, str] = {}
        fichero = MANIFIESTOS / f"{manifiesto}.csv"
        if fichero.exists():
            with fichero.open(encoding="utf-8", newline="") as f:
                for fila in csv.DictReader(f):
                    indice[fila["url"]] = fila["ruta"]
        _INDICES[manifiesto] = indice
    return _INDICES[manifiesto]


def buscar_por_url(url: str, *manifiestos: str) -> bytes | None:
    """Devuelve el contenido ya descargado en una ejecución anterior, si sigue en disco.

    Se pueden consultar varios manifiestos: lo que bajó la Fase 1 sirve para la ingesta.
    """
    for manifiesto in manifiestos:
        ruta = _indice(manifiesto).get(url.strip())
        if ruta and Path(ruta).exists():
            return Path(ruta).read_bytes()
    return None


def anotar(ficha: dict, manifiesto: str) -> None:
    MANIFIESTOS.mkdir(parents=True, exist_ok=True)
    fichero = MANIFIESTOS / f"{manifiesto}.csv"
    nuevo = not fichero.exists()
    with fichero.open("a", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(ficha.keys()))
        if nuevo:
            escritor.writeheader()
        escritor.writerow(ficha)
    if "url" in ficha and "ruta" in ficha:
        _indice(manifiesto)[ficha["url"]] = ficha["ruta"]
