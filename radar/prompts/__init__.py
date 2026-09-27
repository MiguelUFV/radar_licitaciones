"""Los prompts del radar, uno por fichero y con la versión en el nombre.

Cambiar un prompt es **crear un fichero nuevo** (`triaje_v2.md`), nunca editar el anterior: una
cifra medida con `triaje_v1` tiene que poder recalcularse con el texto exacto que se usó. Por eso
cada llamada al modelo guarda la versión y el sha256 de lo que se envió (`llm_llamadas`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from radar.errores import ErrorRadar

CARPETA = Path(__file__).parent
NOMBRE = re.compile(r"^([a-z_]+)_(v\d+)\.md$")


@dataclass(frozen=True)
class Prompt:
    nombre: str
    version: str
    texto: str
    sha256: str


def cargar(nombre: str) -> Prompt:
    """Lee `triaje_v1` → radar/prompts/triaje_v1.md, con su huella."""
    m = NOMBRE.match(f"{nombre}.md")
    if not m:
        raise ErrorRadar(
            f"El prompt «{nombre}» no lleva versión en el nombre. Tienen que llamarse así: "
            "triaje_v1, extraccion_v2…",
        )
    fichero = CARPETA / f"{nombre}.md"
    if not fichero.exists():
        raise ErrorRadar(f"No existe el prompt {fichero.as_posix()}.")
    texto = fichero.read_text(encoding="utf-8")
    return Prompt(
        nombre=m.group(1),
        version=m.group(2),
        texto=texto,
        sha256=hashlib.sha256(texto.encode("utf-8")).hexdigest(),
    )


def todos() -> list[str]:
    return sorted(f.name for f in CARPETA.glob("*.md"))
