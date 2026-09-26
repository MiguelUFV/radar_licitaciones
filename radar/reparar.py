"""Arreglos puntuales de datos ya guardados.

Cuando se corrige un fallo del parser, lo nuevo sale bien pero lo que ya estaba en la base
sigue mal. Aquí viven esos arreglos, cada uno con la fecha y el motivo, para no tener que
volver a procesar cientos de miles de entradas.

    uv run python -m radar.reparar --textos
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Arreglos de datos ya guardados")
    parser.add_argument("--textos", action="store_true", help="traduce los códigos del XML (&quot; y demás)")
    args = parser.parse_args()
    if not args.textos:
        parser.print_help()
        return 0
    try:
        resumen = limpiar_textos()
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    for tabla, cuantos in resumen.items():
        print(f"{tabla}: {cuantos} textos arreglados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
