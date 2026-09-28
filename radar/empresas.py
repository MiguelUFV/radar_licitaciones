"""De quién es este alias: de un cliente o de una empresa del estudio.

El radar trabaja hoy para dos clases de empresa, y el resto del código no tiene por qué saber
cuál es cuál:

- **clientes** — se dan de alta solas por el formulario, editan su ficha cuando quieren y pagan
  un tope al día (`radar/clientes.py`);
- **perfiles** — las siete del estudio, elegidas por sorteo y congeladas antes de medir. No son
  clientes de nadie: existen para que las cifras publicadas se puedan repetir (D38).

Las dos dan lo mismo a los nodos del grafo: un texto que lee el modelo y una cifra de negocio
con la que comparar. Este módulo es el único sitio donde se decide de dónde sale.

**El candado es el mismo para las dos.** Si el texto guardado no coincide con su huella, algo lo
ha cambiado por detrás y no se tría: en el estudio porque obligaría a volver a medir, y en un
cliente porque una decisión tiene que poder explicarse con el texto exacto que la produjo.
"""

from __future__ import annotations

import hashlib

from radar.errores import ErrorRadar, PerfilCambiado
from radar.fechas import el_dia

DEL_ESTUDIO = """
SELECT alias, texto, texto_sha256, cifra_negocio, cifra_fuente
FROM perfiles WHERE alias = %s
"""

DE_UN_CLIENTE = """
SELECT alias, texto, texto_sha256, cifra_negocio, cifra_fuente, correo, tope_diario_eur, activo
FROM clientes WHERE alias = %s
"""


def la_de(conexion, alias: str, con_candado: bool = True) -> dict:
    """La empresa que hay detrás de un alias, venga de donde venga.

    El estudio se mira primero: sus aliases están publicados en los informes y no pueden quedar
    tapados por un cliente que se ponga el mismo nombre (la base tampoco lo permite, 012).

    `con_candado=False` para lo que solo consulta. Escribir el correo de la mañana no decide
    nada —las decisiones ya están tomadas y guardadas en `fichas`—, así que un perfil sin
    congelar no puede ser motivo para dejar a un cliente sin su aviso.
    """
    with conexion.cursor() as cur:
        cur.execute(DEL_ESTUDIO, (alias,))
        fila = cur.fetchone()
        if fila:
            empresa = {
                "alias": fila[0],
                "origen": "estudio",
                "texto": fila[1] or "",
                "huella": fila[2],
                "cifra_negocio": fila[3],
                "cifra_fuente": fila[4],
                "correo": None,
                "tope_diario_eur": None,
                "activo": True,
            }
        else:
            cur.execute(DE_UN_CLIENTE, (alias,))
            fila = cur.fetchone()
            if not fila:
                raise ErrorRadar(f"No hay ninguna empresa con el nombre «{alias}».")
            empresa = {
                "alias": fila[0],
                "origen": "cliente",
                "texto": fila[1] or "",
                "huella": fila[2],
                "cifra_negocio": fila[3],
                "cifra_fuente": fila[4],
                "correo": fila[5],
                "tope_diario_eur": float(fila[6]),
                "activo": fila[7],
            }
    if con_candado:
        comprobar(empresa)
    return empresa


def comprobar(empresa: dict) -> None:
    """El candado: el texto tiene que ser el que se guardó."""
    alias, texto, huella = empresa["alias"], empresa["texto"], empresa["huella"]
    if not texto or not huella:
        if empresa["origen"] == "cliente":
            raise ErrorRadar(
                f"La ficha de {alias} está vacía. Hay que volver a rellenar el formulario de alta."
            )
        raise ErrorRadar(
            f"El perfil de {alias} no está congelado todavía. Antes de triar nada: "
            "uv run python -m radar.perfiles --congelar"
        )
    if hashlib.sha256(texto.encode("utf-8")).hexdigest() == huella:
        return
    if empresa["origen"] == "estudio":
        # Aquí la huella no es una comprobación de integridad cualquiera: es la prueba de que
        # lo publicado se midió con este texto. Cambiarlo obliga a volver a medir.
        raise PerfilCambiado(
            f"El perfil de {alias} no coincide con la huella con la que se congeló. Eso obliga a "
            "volver a medir todo lo que se haya medido con él: no se tría hasta aclararlo."
        )
    raise PerfilCambiado(
        f"La ficha de {alias} no coincide con la huella con la que se guardó. Algo la ha cambiado "
        "por detrás: no se tría hasta aclararlo. Se arregla volviendo a guardar el formulario."
    )


def activas(conexion) -> list[dict]:
    """Los clientes que hoy esperan un correo. El estudio no está aquí: no es cliente de nadie.

    **Sin candado a propósito.** Hacer la lista es hacer la lista; el texto se comprueba cuando
    se va a usar, ya dentro de la mañana de cada empresa. Comprobándolo aquí, una sola ficha
    tocada dejaba a todos los clientes sin trabajo.
    """
    with conexion.cursor() as cur:
        cur.execute("SELECT alias FROM clientes WHERE activo ORDER BY alias")
        aliases = [fila[0] for fila in cur.fetchall()]
    return [la_de(conexion, alias, con_candado=False) for alias in aliases]


# Lo que ha costado un día **a una empresa**. Una llamada de triaje lleva veinte licitaciones
# dentro, así que se cuentan identificadores distintos y no filas: contar filas fue el fallo
# del 27-09-2026, que multiplicaba por veinte el coste de cada triaje.
GASTO = f"""
WITH mias AS (
    SELECT DISTINCT t.llm_llamada AS id
    FROM triajes t
    WHERE t.alias = %s AND {el_dia("t.triada_en")} = %s AND t.llm_llamada IS NOT NULL
    UNION
    SELECT DISTINCT r.llm_llamada
    FROM requisitos r JOIN lecturas l ON l.id = r.lectura
    WHERE l.alias = %s AND {el_dia("l.leida_en")} = %s AND r.llm_llamada IS NOT NULL
)
SELECT count(*), coalesce(sum(c.coste_eur), 0)
FROM llm_llamadas c JOIN mias ON mias.id = c.id
"""


def gastado_hoy(conexion, alias: str, dia) -> tuple[int, float]:
    """Cuántas llamadas y cuántos euros lleva esta empresa ese día."""
    with conexion.cursor() as cur:
        cur.execute(GASTO, (alias, dia, alias, dia))
        llamadas, gasto = cur.fetchone()
    return llamadas, float(gasto)
