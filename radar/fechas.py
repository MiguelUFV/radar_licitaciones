"""Qué día es para el radar.

La base guarda las horas en UTC y el radar trabaja en España. Entre medianoche y las dos de la
mañana esos dos relojes no están en el mismo día: a las 00:30 en Madrid, en la base son las
22:30 del día anterior.

Eso no es una pega de presentación. El tope diario de cada cliente se calcula sumando lo que ha
gastado «hoy»; si el día de Python y el día de la base no son el mismo, **el radar ve cero euros
gastados con el tope recién agotado y el cliente se lo puede gastar dos veces**. Se descubrió el
29-09-2026, cuando la fecha cambió a mitad de sesión y cuatro pruebas se pusieron en rojo solas
sin que nadie hubiera tocado nada.

Así que el día del radar es **el día en España**, en los dos sitios: `hoy()` para Python y
`el_dia("columna")` para las consultas. La misma zona que ya usa el reloj de n8n.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

ZONA = "Europe/Madrid"
MADRID = ZoneInfo(ZONA)


def hoy() -> date:
    """El día de hoy en España, venga de donde venga el reloj de la máquina."""
    return datetime.now(MADRID).date()


def el_dia(columna: str) -> str:
    """El trozo de SQL que saca de una marca de tiempo el día que fue en España.

    Se usa dentro de las consultas del proyecto, siempre con un nombre de columna escrito en el
    código, nunca con algo que venga de fuera.
    """
    return f"(({columna}) AT TIME ZONE '{ZONA}')::date"
