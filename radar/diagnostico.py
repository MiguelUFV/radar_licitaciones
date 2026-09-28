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


def parece_clave_anthropic(valor: str | None) -> bool:
    """Que la clave tenga forma de clave.

    El 27-09-2026 en ANTHROPIC_API_KEY habia pegada la direccion de un perfil de LinkedIn, y
    el diagnostico la daba por buena porque solo miraba que no estuviera vacia. Una clave mal
    puesta se descubre en la primera llamada al modelo, y esa llamada se paga.
    """
    return bool(valor) and valor.startswith("sk-ant-") and len(valor) > 50


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
        ("TIPO_CAMBIO_USD_EUR", True, "decir en euros lo que cuesta cada ejecución"),
        ("PRESUPUESTO_DIARIO_EUR", True, "no gastar más de la cuenta en el modelo"),
        ("ANTHROPIC_API_KEY", False, "el modelo (hace falta a partir de la Fase 4)"),
    ]:
        valor = os.getenv(variable)
        if valor and variable == "ANTHROPIC_API_KEY" and not parece_clave_anthropic(valor):
            resultados.append(
                (
                    False,
                    f"Lo que hay en {variable} no parece una clave de Anthropic: empiezan por "
                    "sk-ant- y tienen mas de 100 caracteres. Revisa que no hayas pegado otra cosa.",
                    critica,
                )
            )
        elif valor:
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
        from radar import personas
        from radar.bd import conectar

        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM adjudicaciones WHERE {personas.SQL_EN_CLARO}")
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


def comprobar_regla_congelada() -> tuple[bool, str]:
    """El documento con el que se sortearon las empresas, ¿sigue siendo el mismo?

    `perfiles.regla_sha256` guarda la huella que tenía `docs/REGLA_SELECCION.md` el día del
    sorteo. Hasta ahora nadie la volvía a mirar: un candado que no se comprueba no es un
    candado. Cambiar ese documento está permitido —con su entrada en el apartado Cambios y
    volviendo a medir lo que dependa de él—, así que esto avisa, no falla.
    """
    try:
        from radar.bd import conectar
        from radar.seleccion import huella_de_la_regla

        actual = huella_de_la_regla()
        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute("SELECT DISTINCT regla_sha256 FROM perfiles")
            guardadas = {fila[0] for fila in cur.fetchall()}
    except ErrorRadar as e:
        return False, e.mensaje
    if not guardadas:
        return True, "Todavía no se ha sorteado ninguna empresa"
    if actual in guardadas:
        return True, "La regla de selección es la misma con la que se sortearon las empresas"
    return False, (
        "docs/REGLA_SELECCION.md ha cambiado desde que se sortearon las empresas "
        f"({actual[:12]} ahora, {sorted(guardadas)[0][:12]} entonces). Si el cambio está "
        "anotado en su apartado Cambios, es lo esperado; si no está, alguien lo tocó sin "
        "dejarlo escrito y hay que averiguar qué se midió con qué."
    )


def comprobar_universo_del_estudio() -> tuple[bool, str]:
    """El periodo sobre el que se midió, ¿sigue teniendo los mismos expedientes?

    Las cifras publicadas se calcularon sobre 120.656 expedientes del primer semestre de 2025, y
    ese número está guardado en `eval_resultados` como la `n` de M2. Cargar más histórico no
    debería tocarlo —las consultas del estudio filtran por fecha—, pero «no debería» no es una
    comprobación. Si un día cambia, las cifras publicadas dejan de corresponder a los datos que
    hay, y eso tiene que saltar solo.
    """
    try:
        from radar.bd import conectar
        from radar.evaluacion.triaje import DESDE, HASTA, PUBLICADAS

        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM ({PUBLICADAS}) AS s", (DESDE, HASTA))
            ahora = cur.fetchone()[0]
            cur.execute(
                "SELECT DISTINCT ON (variante) n FROM eval_resultados"
                " WHERE metrica = 'M2' AND variante LIKE 'baseline%' AND n > 1000"
                " ORDER BY variante, calculada_en DESC"
            )
            medidos = {fila[0] for fila in cur.fetchall()}
    except ErrorRadar as e:
        return False, e.mensaje
    if not medidos:
        return True, "Todavía no hay ninguna medición publicada sobre el universo del estudio"
    if ahora in medidos:
        return True, f"El universo del estudio sigue siendo el medido ({ahora:,} expedientes)".replace(
            ",", "."
        )
    return False, (
        f"El periodo del estudio tiene ahora {ahora} expedientes y las cifras publicadas se "
        f"midieron sobre {sorted(medidos)[0]}. O se ha cargado algo que cae dentro del periodo, "
        "o se ha borrado algo: hasta aclararlo, lo publicado no corresponde a lo que hay."
    )


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

    # Avisos: cosas que hay que mirar pero que pueden ser correctas.
    for comprobacion in (comprobar_regla_congelada, comprobar_universo_del_estudio):
        correcto, mensaje = comprobacion()
        print(f"{OK if correcto else AVISO} {mensaje}")

    print()
    if problemas:
        print(f"Hay {problemas} cosa(s) que arreglar antes de seguir.")
        return 1
    print("Todo en orden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
