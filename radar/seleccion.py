"""Aplica la regla de selección de empresas (docs/REGLA_SELECCION.md).

La regla se escribió y se commiteó antes de esta ejecución; aquí no se decide nada, solo se
aplica. Cada empresa seleccionada queda con la semilla del sorteo y con el hash del fichero
de la regla que estaba vigente, para que se pueda comprobar que no se cambió después.

    uv run python -m radar.seleccion --desde 2025-01-01 --hasta 2025-07-01 --corte 2026-09-01
"""

from __future__ import annotations

import argparse
import hashlib
import random
import re
from dataclasses import dataclass
from pathlib import Path

from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion

REGLA = Path("docs/REGLA_SELECCION.md")
SEMILLA = 20260925
MINIMO_ADJUDICACIONES = 8
PARTE_INFORMATICA = 0.5
DE_DESARROLLO = 2
DE_TEST = 5
ALIAS = "ABCDEFGHIJ"

# "UTE" tiene que ir suelta: hay empresas que se llaman COMPUTER, y ahí no hay ninguna unión
# temporal de empresas.
UTE = re.compile(r"\bU\.?\s?T\.?\s?E\.?\b", re.I)

CANDIDATAS = """
WITH publicacion AS (
    SELECT entry_id, min(entry_updated) AS publicada
    FROM licitaciones GROUP BY entry_id
),
por_expediente AS (
    SELECT a.adjudicatario AS nif,
           l.entry_id,
           max(a.nombre) AS nombre,
           bool_and(coalesce(a.es_pyme, false)) AS es_pyme,
           bool_or(EXISTS (SELECT 1 FROM unnest(l.cpv) AS c
                           WHERE c LIKE '72%%' OR c LIKE '48%%')) AS es_informatica
    FROM adjudicaciones a
    JOIN licitaciones l ON l.id = a.licitacion
    JOIN publicacion p ON p.entry_id = l.entry_id
    WHERE a.adjudicatario IS NOT NULL
      AND p.publicada >= %s AND p.publicada < %s
      AND l.entry_updated < %s
    GROUP BY a.adjudicatario, l.entry_id
)
SELECT nif,
       max(nombre) AS nombre,
       count(*) AS adjudicaciones,
       count(*) FILTER (WHERE es_informatica) AS de_informatica,
       bool_and(es_pyme) AS siempre_pyme
FROM por_expediente
GROUP BY nif
"""


@dataclass
class Candidata:
    nif: str
    nombre: str | None
    adjudicaciones: int
    de_informatica: int
    siempre_pyme: bool


def motivo_de_descarte(c: Candidata) -> str | None:
    """Devuelve el criterio que no cumple, o None si entra en el sorteo (regla §3)."""
    if not c.nif or not c.nif[0].isalpha():
        return "no es persona juridica"
    if c.nif[0].upper() == "U" or (c.nombre and UTE.search(c.nombre)):
        return "es UTE"
    if not c.siempre_pyme:
        return "no consta como pyme"
    if c.adjudicaciones < MINIMO_ADJUDICACIONES:
        return "menos de 8 adjudicaciones"
    if c.de_informatica <= c.adjudicaciones * PARTE_INFORMATICA:
        return "no es mayoritariamente de informatica"
    return None


def sortear(nifs: list[str], semilla: int = SEMILLA) -> tuple[list[str], list[str]]:
    """Orden reproducible (por NIF) y barajado con semilla fija (regla §4)."""
    orden = sorted(nifs)
    random.Random(semilla).shuffle(orden)
    return orden[:DE_DESARROLLO], orden[DE_DESARROLLO : DE_DESARROLLO + DE_TEST]


def huella_de_la_regla() -> str:
    if not REGLA.exists():
        raise ErrorRadar(
            "No se encuentra docs/REGLA_SELECCION.md. La selección no se ejecuta sin la regla escrita."
        )
    return hashlib.sha256(REGLA.read_bytes()).hexdigest()


def candidatas(conexion, desde: str, hasta: str, corte: str) -> list[Candidata]:
    with conexion.cursor() as cur:
        cur.execute(CANDIDATAS, (desde, hasta, corte))
        return [Candidata(*fila) for fila in cur.fetchall()]


def aplicar(desde: str, hasta: str, corte: str, semilla: int = SEMILLA, rehacer: bool = False) -> dict:
    regla = huella_de_la_regla()
    with conectar() as conexion:
        with conexion.cursor() as cur:
            cur.execute("SELECT count(*) FROM perfiles")
            if cur.fetchone()[0] and not rehacer:
                raise ErrorRadar(
                    "Ya hay empresas seleccionadas. Volver a sortear después de haber visto los "
                    "datos invalidaría el estudio: si de verdad hace falta, anota el motivo en "
                    "docs/REGLA_SELECCION.md y usa --rehacer."
                )

        run_id = abrir_ejecucion(conexion, "evaluacion", None)
        try:
            todas = candidatas(conexion, desde, hasta, corte)
            descartes: dict[str, int] = {}
            aptas: dict[str, Candidata] = {}
            for c in todas:
                motivo = motivo_de_descarte(c)
                if motivo:
                    descartes[motivo] = descartes.get(motivo, 0) + 1
                else:
                    aptas[c.nif] = c

            desarrollo, test = sortear(list(aptas), semilla)
            if len(test) < 3:
                raise ErrorRadar(
                    f"Solo hay {len(aptas)} empresas que cumplan la regla, y hacen falta al menos 5 "
                    "(2 de desarrollo y 3 de test). Amplía el periodo y anótalo en la regla."
                )

            with conexion.cursor() as cur:
                if rehacer:
                    cur.execute("DELETE FROM perfiles")
                for posicion, (nif, rol) in enumerate(
                    [(n, "desarrollo") for n in desarrollo] + [(n, "test") for n in test]
                ):
                    c = aptas[nif]
                    cur.execute(
                        "INSERT INTO perfiles (alias, nif, nombre, rol, adjudicaciones,"
                        " de_informatica, semilla, regla_sha256, ejecucion_id)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            f"Empresa {ALIAS[posicion]}",
                            nif,
                            c.nombre,
                            rol,
                            c.adjudicaciones,
                            c.de_informatica,
                            str(semilla),
                            regla,
                            run_id,
                        ),
                    )
            conexion.commit()
            cerrar_ejecucion(conexion, run_id, "ok")
        except Exception as e:
            legible = e.mensaje if isinstance(e, ErrorRadar) else "Fallo no previsto en la selección."
            conexion.rollback()
            cerrar_ejecucion(conexion, run_id, "error", legible)
            if isinstance(e, ErrorRadar):
                raise
            raise ErrorRadar(legible, detalle=repr(e)) from e

    return {
        "adjudicatarios_en_el_periodo": len(todas),
        "cumplen_la_regla": len(aptas),
        "descartes": descartes,
        "desarrollo": len(desarrollo),
        "test": len(test),
        "semilla": semilla,
        "regla_sha256": regla[:12],
        "run_id": str(run_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Selección de las empresas del estudio")
    parser.add_argument("--desde", default="2025-01-01", help="primera fecha de publicación")
    parser.add_argument("--hasta", default="2025-07-01", help="primera fecha excluida")
    parser.add_argument("--corte", default="2026-09-01", help="hasta cuándo cuentan las adjudicaciones")
    parser.add_argument("--rehacer", action="store_true")
    args = parser.parse_args()
    try:
        resumen = aplicar(args.desde, args.hasta, args.corte, rehacer=args.rehacer)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print("\nResumen:", resumen)
    print("Los NIF y los nombres se quedan en la base de datos; fuera se usan los alias.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
