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

EXTENSIONES = {"feed": ".atom", "pliego": ".pdf", "otro": ".bin"}


def _ruta(tipo: str, huella: str) -> Path:
    return RAW / tipo / huella[:2] / f"{huella}{EXTENSIONES.get(tipo, '.bin')}"


def guardar(contenido: bytes, tipo: str, url: str, manifiesto: str) -> dict:
    """Guarda el contenido y anota una línea en el manifiesto. Devuelve la ficha del fichero."""
    huella = hashlib.sha256(contenido).hexdigest()
    destino = _ruta(tipo, huella)
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
    anotar(ficha, manifiesto)
    return ficha


def anotar(ficha: dict, manifiesto: str) -> None:
    MANIFIESTOS.mkdir(parents=True, exist_ok=True)
    fichero = MANIFIESTOS / f"{manifiesto}.csv"
    nuevo = not fichero.exists()
    with fichero.open("a", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(ficha.keys()))
        if nuevo:
            escritor.writeheader()
        escritor.writerow(ficha)
