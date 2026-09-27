"""Dónde va la traza técnica cuando al usuario se le da un mensaje en castellano.

La regla del proyecto es «nunca se muestra una traza al usuario; la traza va al log»
(`CLAUDE.md`, innegociable 3). Hasta el 27-09-2026 la segunda mitad de esa frase no existía: un
fallo no previsto se traducía a «Fallo no previsto al leer los pliegos» y el detalle técnico se
perdía, así que no había forma de arreglarlo. Ahora va aquí.

Se usa la tabla `incidencias`, la misma en la que n8n anota los fallos de los workflows (D25),
porque el sitio donde se mira cuando algo va mal debe ser uno, no dos. `radar.estado` ya avisa
de las incidencias de la semana.

Apuntar un fallo no puede provocar otro: si la base no está disponible, esta función no levanta
nada. Un error que no se pudo registrar sigue siendo mejor que un programa que se cae al
intentar registrarlo.
"""

from __future__ import annotations

import traceback

from radar.bd import conectar

TOPE_DETALLE = 8000


def apuntar(nodo: str, mensaje: str, error: BaseException | None = None) -> int | None:
    """Deja el fallo en `incidencias` con su traza. Devuelve el id, o None si no se pudo."""
    detalle = ""
    if error is not None:
        detalle = "\n" + "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
    texto = f"{mensaje}{detalle}"[:TOPE_DETALLE]
    try:
        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO incidencias (workflow, nodo, mensaje) VALUES (%s, %s, %s) RETURNING id",
                ("radar", nodo, texto),
            )
            identificador = cur.fetchone()[0]
            conexion.commit()
        return identificador
    except Exception:  # noqa: BLE001  registrar un fallo no puede provocar otro
        return None


def ultimas(limite: int = 5) -> list[tuple]:
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(
            "SELECT id, ocurrida_en, nodo, mensaje FROM incidencias"
            " ORDER BY ocurrida_en DESC LIMIT %s",
            (limite,),
        )
        return cur.fetchall()
