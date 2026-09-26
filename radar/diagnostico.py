"""Comprobación del entorno. Cada fallo se explica en castellano, sin trazas.

uv run python -m radar.diagnostico
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from radar.errores import ErrorRadar
from radar.feed import FEED_PERFILES
from radar.red import crear_cliente

OK, FALLO, AVISO = "  [ok]   ", "  [FALLO]", "  [aviso]"


def comprobar_python() -> tuple[bool, str]:
    v = sys.version_info
    if (v.major, v.minor) != (3, 12):
        return False, f"Se esperaba Python 3.12 y hay {v.major}.{v.minor}. Ejecuta: uv python pin 3.12"
    return True, f"Python {v.major}.{v.minor}.{v.micro}"


def comprobar_env() -> list[tuple[bool, str, bool]]:
    """Devuelve (correcto, mensaje, es_crítico) por cada variable."""
    if not Path(".env").exists():
        return [(False, "No existe el fichero .env. Copia .env.example y rellénalo.", True)]
    load_dotenv()
    resultados = []
    for variable, critica, para_que in [
        ("POSTGRES_PASSWORD", True, "la base de datos"),
        ("N8N_ENCRYPTION_KEY", True, "n8n"),
        ("SAL_PERSONAS", True, "no guardar en claro el DNI de los adjudicatarios autónomos"),
        ("ANTHROPIC_API_KEY", False, "el modelo (hace falta a partir de la Fase 4)"),
    ]:
        valor = os.getenv(variable)
        if valor:
            resultados.append((True, f"{variable} definida", critica))
        else:
            resultados.append((False, f"Falta {variable} en .env, necesaria para {para_que}.", critica))
    return resultados


def comprobar_plataforma() -> tuple[bool, str]:
    """Descarga solo el principio del feed: comprueba red, DNS y certificado sin bajar 8 MB."""
    try:
        with crear_cliente(timeout=30) as cliente, cliente.stream("GET", FEED_PERFILES) as respuesta:
            respuesta.raise_for_status()
            for trozo in respuesta.iter_bytes():
                if b"<feed" in trozo or b"<?xml" in trozo:
                    return True, "La Plataforma de Contratación responde y su certificado es válido"
                break
        return False, "La Plataforma respondió algo que no parece el feed."
    except ErrorRadar as e:
        return False, str(e)
    except httpx.HTTPError as e:
        return False, f"No se ha podido leer el feed de la Plataforma. Detalle técnico: {type(e).__name__}"


def comprobar_puerto(host: str, puerto: int, nombre: str, pista: str) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, puerto), timeout=3):
            return True, f"{nombre} responde en {host}:{puerto}"
    except OSError:
        return False, f"{nombre} no responde en {host}:{puerto}. {pista}"


def comprobar_n8n() -> tuple[bool, str]:
    """El n8n del proyecto vive en el 5679; el 5678 se deja libre para la instalación propia."""
    try:
        r = httpx.get("http://127.0.0.1:5679/healthz", timeout=5)
        if r.status_code == 200:
            return True, "n8n del proyecto responde en http://localhost:5679"
        return False, f"n8n contesta con el código {r.status_code}."
    except httpx.HTTPError:
        return False, "n8n del proyecto no responde. Arráncalo con: docker compose up -d"


def comprobar_datos_personales() -> tuple[bool, str]:
    """Ningún DNI ni NIE de adjudicatario puede estar guardado en claro (docs/DATOS.md §7)."""
    try:
        from radar.bd import conectar

        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM adjudicaciones"
                " WHERE adjudicatario IS NOT NULL AND left(adjudicatario, 1) !~ '[ABCDEFGHJNPQRSUVW]'"
                " AND adjudicatario NOT LIKE 'pf%'"
            )
            en_claro = cur.fetchone()[0]
    except ErrorRadar as e:
        return False, e.mensaje
    if en_claro:
        return False, (
            f"Hay {en_claro} adjudicaciones con el DNI de una persona guardado en claro. "
            "Arréglalo con: uv run python -m radar.personas --anonimizar"
        )
    return True, "Ningún dato personal guardado en claro"


def comprobar_ejecuciones_abiertas() -> tuple[bool, str]:
    """Una ejecución que lleva horas 'en_curso' es una que se murió sin cerrarse."""
    try:
        from radar.bd import conectar

        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM ejecuciones"
                " WHERE estado = 'en_curso' AND inicio < now() - interval '2 hours'"
            )
            colgadas = cur.fetchone()[0]
    except ErrorRadar as e:
        return False, e.mensaje
    if colgadas:
        return False, (
            f"Hay {colgadas} ejecución(es) empezadas hace más de dos horas y sin terminar. "
            "Seguramente se cortaron: revisa la tabla ejecuciones."
        )
    return True, "Ninguna ejecución colgada"


def main() -> int:
    print("Diagnóstico del entorno\n")
    problemas = 0

    correcto, mensaje = comprobar_python()
    print(f"{OK if correcto else FALLO} {mensaje}")
    problemas += not correcto

    for correcto, mensaje, critica in comprobar_env():
        marca = OK if correcto else (FALLO if critica else AVISO)
        print(f"{marca} {mensaje}")
        problemas += (not correcto) and critica

    for comprobacion in (
        comprobar_plataforma,
        lambda: comprobar_puerto("127.0.0.1", 5432, "PostgreSQL", "Arráncalo con: docker compose up -d"),
        comprobar_n8n,
        comprobar_datos_personales,
        comprobar_ejecuciones_abiertas,
    ):
        correcto, mensaje = comprobacion()
        print(f"{OK if correcto else FALLO} {mensaje}")
        problemas += not correcto

    print()
    if problemas:
        print(f"Hay {problemas} cosa(s) que arreglar antes de seguir.")
        return 1
    print("Todo en orden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
