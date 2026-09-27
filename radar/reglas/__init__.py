"""Las reglas que deciden, con versión en el nombre del fichero.

El modelo extrae; **Python decide** (`docs/DECISIONES.md` D09). Aquí vive esa decisión, y vive
separada del modelo a propósito: una regla se lee, se discute y se prueba con casos, y un
prompt no.

Cambiar una regla es crear `v2.py`, no editar `v1.py`: una decisión guardada tiene que poder
explicarse con el texto exacto de la regla que se le aplicó, y por eso cada ficha guarda la
versión con la que se decidió.
"""

from __future__ import annotations

import importlib
import re

from radar.errores import ErrorRadar

VERSION_ACTUAL = "v1"
_NOMBRE = re.compile(r"^v\d+$")


def cargar(version: str = VERSION_ACTUAL):
    if not _NOMBRE.match(version):
        raise ErrorRadar(f"La versión de reglas «{version}» no tiene la forma v1, v2…")
    try:
        return importlib.import_module(f"radar.reglas.{version}")
    except ModuleNotFoundError as e:
        raise ErrorRadar(f"No existen las reglas {version} (radar/reglas/{version}.py).") from e
