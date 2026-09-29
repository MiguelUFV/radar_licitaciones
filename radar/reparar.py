"""Arreglos puntuales de datos ya guardados.

Cuando se corrige un fallo del parser, lo nuevo sale bien pero lo que ya estaba en la base
sigue mal. Aquí viven esos arreglos, cada uno con la fecha y el motivo, para no tener que
volver a procesar cientos de miles de entradas.

    uv run python -m radar.reparar --textos
    uv run python -m radar.reparar --ejecuciones
"""

from __future__ import annotations

import argparse
import html

from radar.bd import conectar
from radar.errores import ErrorRadar

# 26-09-2026: el parser guardaba los textos con los códigos del XML sin traducir
# (&quot;Ebiblio&quot;, KOENIG &amp; BAUER). Arreglado en radar/feed.py; esto limpia lo que
# ya estaba guardado.
CAMPOS = {"licitaciones": ("objeto", "organo", "expediente", "solvencia_feed"), "lotes": ("objeto",)}


def limpiar_textos(por_lotes: int = 5000) -> dict:
    cambiados = {}
    with conectar() as conexion:
        for tabla, columnas in CAMPOS.items():
            total = 0
            for columna in columnas:
                while True:
                    with conexion.cursor() as cur:
                        cur.execute(
                            f"SELECT id, {columna} FROM {tabla}"  # noqa: S608  nombres de esta constante
                            # %% porque la consulta lleva parámetros: psycopg lo deja en un %.
                            f" WHERE {columna} LIKE '%%&%%;%%' LIMIT %s",
                            (por_lotes,),
                        )
                        filas = cur.fetchall()
                        if not filas:
                            break
                        arreglados = [
                            (html.unescape(texto), id_)
                            for id_, texto in filas
                            if texto != html.unescape(texto)
                        ]
                        if not arreglados:
                            break
                        cur.executemany(
                            f"UPDATE {tabla} SET {columna} = %s WHERE id = %s",  # noqa: S608
                            arreglados,
                        )
                        total += len(arreglados)
                    conexion.commit()
            cambiados[tabla] = total
    return cambiados


# Una ejecución que se corta —se cae el proceso, se cierra el portátil— se queda «en_curso»
# para siempre. `radar.diagnostico` avisaba de ellas y no había forma de cerrarlas: pedía
# arreglar algo a mano sin decir cómo. Se cierran como lo que son, un error, y no se borran:
# el rastro de que aquella pasada existió y no terminó es justamente lo que interesa.
CORTADAS = """
UPDATE ejecuciones
SET fin = now(), estado = 'error',
    mensaje = coalesce(mensaje || ' ', '') ||
              'La pasada se cortó y nadie la cerró; la cerró radar.reparar.'
WHERE fin IS NULL AND inicio < now() - make_interval(secs => %s)
"""


def cerrar_cortadas(horas: float = 2) -> int:
    """Cierra las ejecuciones que llevan más de `horas` sin terminar. Devuelve cuántas.

    En segundos por dentro: `make_interval(hours => ...)` solo acepta enteros, y al poder pedir
    media hora desde la línea de comandos el comando reventaba con un error de tipos.
    """
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(CORTADAS, (float(horas) * 3600,))
        cuantas = cur.rowcount
        conexion.commit()
    return cuantas


def main() -> int:
    parser = argparse.ArgumentParser(description="Arreglos de datos ya guardados")
    parser.add_argument("--textos", action="store_true", help="traduce los códigos del XML")
    parser.add_argument(
        "--ejecuciones", action="store_true", help="cierra las pasadas que se quedaron a medias"
    )
    # Dos horas es el tope normal, el mismo que usa el diagnóstico para avisar. Se puede bajar
    # cuando se acaba de parar una carga a propósito y se sabe que esas pasadas ya no siguen.
    parser.add_argument("--horas", type=float, default=2.0, help="antigüedad mínima para cerrarlas")
    args = parser.parse_args()
    if not (args.textos or args.ejecuciones):
        parser.print_help()
        return 0
    try:
        if args.ejecuciones:
            print(f"ejecuciones cortadas que se han cerrado: {cerrar_cortadas(args.horas)}")
        if args.textos:
            for tabla, cuantos in limpiar_textos().items():
                print(f"{tabla}: {cuantos} textos arreglados")
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
