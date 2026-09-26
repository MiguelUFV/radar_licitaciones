"""Adjudicatarios que son personas físicas: nunca se guardan en claro.

Un autónomo gana contratos con su DNI o su NIE, que son datos personales. La regla del
proyecto (docs/DATOS.md §7) dice que se guardan como hash con sal y que su nombre no aparece
en ninguna salida. Esto es lo que lo hace cumplir.

El seudónimo es estable: la misma persona da siempre el mismo, así que se puede contar
cuántos contratos ganó sin saber quién es.

    uv run python -m radar.personas --anonimizar
"""

from __future__ import annotations

import argparse
import hashlib
import os

from dotenv import load_dotenv

from radar.bd import conectar
from radar.errores import FaltaConfiguracion

# Letras con las que empieza el NIF de una persona jurídica (CIF). Las que faltan no son
# casualidad: un DNI empieza por número y un NIE por X, Y o Z, y los dos son de una persona.
LETRAS_EMPRESA = "ABCDEFGHJNPQRSUVW"
PREFIJO = "pf_"

# La condición que distingue "esto es un dato personal en claro" del resto, escrita una sola
# vez: la usan la restricción de la base, el diagnóstico y el informe de estado. Cuando estaba
# repetida se desincronizó, y el diagnóstico daba 1.849 falsas alarmas por NIF de empresa
# escritos en minúscula en el feed.
SQL_EN_CLARO = (
    "adjudicatario IS NOT NULL"
    f" AND upper(left(adjudicatario, 1)) !~ '^[{LETRAS_EMPRESA}]$'"
    f" AND adjudicatario NOT LIKE '{PREFIJO[:2]}|{PREFIJO[2:]}%' ESCAPE '|'"
)


def es_persona_fisica(nif: str | None) -> bool:
    if not nif:
        return False
    if nif.startswith(PREFIJO):
        return True
    return nif.strip().upper()[0] not in LETRAS_EMPRESA


def sal() -> str:
    load_dotenv()
    valor = os.getenv("SAL_PERSONAS")
    if not valor:
        raise FaltaConfiguracion(
            "Falta SAL_PERSONAS en el fichero .env. Sin ella no se pueden guardar las "
            "adjudicaciones de autónomos sin exponer su DNI."
        )
    return valor


def seudonimo(nif: str, con_sal: str | None = None) -> str:
    """Mismo DNI, mismo seudónimo; y del seudónimo no se puede volver al DNI."""
    if nif.startswith(PREFIJO):
        return nif
    huella = hashlib.sha256(f"{con_sal or sal()}{nif.strip().upper()}".encode()).hexdigest()
    return f"{PREFIJO}{huella[:24]}"


def como_se_guarda(nif: str | None, nombre: str | None) -> tuple[str | None, str | None]:
    """Lo que se escribe en la base: de una persona física, ni el DNI ni el nombre."""
    if not nif:
        return nif, nombre
    if es_persona_fisica(nif):
        return seudonimo(nif), None
    return nif, nombre


def anonimizar_lo_ya_guardado() -> dict:
    """Arregla las filas que se guardaron antes de que esto existiera."""
    con_sal = sal()
    cambiadas = 0
    with conectar() as conexion:
        with conexion.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT adjudicatario FROM adjudicaciones"
                " WHERE adjudicatario IS NOT NULL AND adjudicatario NOT LIKE %s",
                (f"{PREFIJO}%",),
            )
            personales = [n for (n,) in cur.fetchall() if es_persona_fisica(n)]
            for nif in personales:
                cur.execute(
                    "UPDATE adjudicaciones SET adjudicatario = %s, nombre = NULL WHERE adjudicatario = %s",
                    (seudonimo(nif, con_sal), nif),
                )
                cambiadas += cur.rowcount
        conexion.commit()
    return {"personas": len(personales), "adjudicaciones": cambiadas}


def main() -> int:
    parser = argparse.ArgumentParser(description="Adjudicatarios que son personas físicas")
    parser.add_argument("--anonimizar", action="store_true", help="arregla lo ya guardado")
    args = parser.parse_args()
    if not args.anonimizar:
        parser.print_help()
        return 0
    try:
        resumen = anonimizar_lo_ya_guardado()
    except FaltaConfiguracion as e:
        print(f"\n{e}")
        return 1
    print(f"\nPersonas físicas seudonimizadas: {resumen['personas']}")
    print(f"Filas de adjudicaciones corregidas: {resumen['adjudicaciones']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
