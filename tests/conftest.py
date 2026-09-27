"""Piezas comunes de los tests.

DATOS DE EJEMPLO — no usar en producción. Las páginas del feed que se arman aquí parten de
una entrada real grabada (`tests/fixtures/entrada_real.xml`) y solo se les cambia el
identificador y la fecha, que es lo que hace falta para provocar situaciones concretas del
cursor. Nada de esto sale del directorio `tests/`.

Los tests que tocan PostgreSQL trabajan sobre una base aparte (`radar_test`): la base de
trabajo nunca recibe filas de prueba (CLAUDE.md, innegociable 2).
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
BASE_PRUEBAS = "radar_test"

# Todas las tablas de la aplicación. Si se añade una migración con una tabla nueva, va aquí:
# la que falte deja filas de un test metiéndose en el siguiente. Pasó el 27-09-2026 con
# `tipos_cambio`, y el test que comprobaba que sin tipo de cambio no se llama al modelo empezó
# a pasar por el motivo equivocado.
TABLAS = [
    "triajes",
    "llm_llamadas",
    "eval_resultados",
    "adjudicaciones",
    "documentos",
    "lotes",
    "bajas",
    "licitaciones",
    "stg_entradas",
    "historico_meses",
    "raw_ficheros",
    "perfiles",
    "incidencias",
    "tipos_cambio",
    "ejecuciones",
    "cursor_feed",
]


def entrada_real() -> str:
    return (FIXTURES / "entrada_real.xml").read_text(encoding="utf-8")


def entrada(identificador: str, actualizada: str) -> str:
    """La entrada real con otro id y otra fecha, para simular varias páginas del feed."""
    bloque = entrada_real()
    bloque = re.sub(r"<id>[^<]+</id>", f"<id>{identificador}</id>", bloque, count=1)
    return re.sub(r"<updated>[^<]+</updated>", f"<updated>{actualizada}</updated>", bloque, count=1)


BAJA_REAL = (
    '<at:deleted-entry ref="https://contrataciondelestado.es/sindicacion/'
    'licitacionesPerfilContratante/20499474" when="2026-09-04T11:54:25.818+02:00">\n'
    '        <at:comment type="ANULADA"/>\n'
    "    </at:deleted-entry>"
)


def pagina(bloques: list[str], siguiente: str | None = None, bajas: str = "") -> bytes:
    """Arma una página del feed con la misma estructura que la real."""
    enlace = f'<link href="{siguiente}" rel="next"/>' if siguiente else ""
    cuerpo = "\n".join(bloques)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:at="http://purl.org/atompub/tombstones/1.0">\n'
        "<id>https://contrataciondelestado.es/sindicacion/sindicacion_643/pagina.atom</id>\n"
        f"{enlace}\n{cuerpo}\n{bajas}\n</feed>\n"
    ).encode()


def _hay_postgres() -> bool:
    try:
        from radar.bd import conectar

        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture
def bd(monkeypatch):
    """Base de datos de pruebas, vacía, con las migraciones aplicadas."""
    if not _hay_postgres():
        pytest.skip("PostgreSQL no está levantado")

    import psycopg

    from radar.bd import aplicar_migraciones, cadena_conexion, conectar

    admin = cadena_conexion().rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin, autocommit=True) as conexion, conexion.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (BASE_PRUEBAS,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{BASE_PRUEBAS}"')

    monkeypatch.setenv("POSTGRES_DB", BASE_PRUEBAS)
    aplicar_migraciones()
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(TABLAS)} RESTART IDENTITY CASCADE")
        conexion.commit()
    yield conectar


@pytest.fixture
def almacen_temporal(monkeypatch, tmp_path):
    """Manda la capa raw a un directorio temporal: los tests no escriben en data/."""
    from radar import almacen

    monkeypatch.setattr(almacen, "RAW", tmp_path / "raw")
    monkeypatch.setattr(almacen, "MANIFIESTOS", tmp_path / "manifiestos")
    monkeypatch.setattr(almacen, "_INDICES", {})
    return tmp_path


class ClienteFalso:
    """Sustituye a crear_cliente() en los tests: no abre ninguna conexion de red."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


RESTRICCIONES = Path("sql/migraciones/007_sin_datos_personales.sql")


@contextlib.contextmanager
def como_antes_de_la_restriccion(bd):
    """Deja meter una fila con el DNI en claro, como las que habia antes de prohibirlo.

    Hace falta para probar que la limpieza y los avisos funcionan: hoy la base ya no acepta
    esas filas. Al salir borra lo que haya quedado mal y vuelve a poner la restriccion.
    """
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("ALTER TABLE adjudicaciones DROP CONSTRAINT adjudicaciones_sin_datos_personales")
        cur.execute("ALTER TABLE adjudicaciones DROP CONSTRAINT adjudicaciones_persona_sin_nombre")
        conexion.commit()
    try:
        yield
    finally:
        from radar.personas import SQL_EN_CLARO

        with bd() as conexion, conexion.cursor() as cur:
            cur.execute(f"DELETE FROM adjudicaciones WHERE {SQL_EN_CLARO}")
            cur.execute(RESTRICCIONES.read_text(encoding="utf-8"))
            conexion.commit()


def pdf_con_paginas(textos: list[str]) -> bytes:
    """Un PDF de verdad con texto, escrito a mano.

    DATOS DE EJEMPLO — no usar en producción. `pypdf` sabe leer texto pero no escribirlo, y los
    tests de localización y de extracción necesitan páginas con palabras dentro: sin esto se
    probaría con páginas en blanco, que es como no probar nada.
    """
    objetos: dict[int, bytes] = {}
    ids = [3 + 2 * i for i in range(len(textos))]
    objetos[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = b" ".join(b"%d 0 R" % i for i in ids)
    objetos[2] = b"<< /Type /Pages /Count %d /Kids [%s] >>" % (len(textos), kids)
    for texto, pid in zip(textos, ids, strict=True):
        objetos[pid] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents %d 0 R /Resources "
            b"<< /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>" % (pid + 1)
        )
        lineas = [
            b"("
            + linea.replace("\\", "").replace("(", "").replace(")", "").encode("latin-1", "replace")
            + b") Tj T*"
            for linea in texto.split("\n")
        ]
        ops = b"BT /F1 11 Tf 14 TL 40 800 Td\n" + b"\n".join(lineas) + b"\nET"
        objetos[pid + 1] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(ops), ops)

    salida, posiciones = bytearray(b"%PDF-1.4\n"), {}
    for numero in sorted(objetos):
        posiciones[numero] = len(salida)
        salida += b"%d 0 obj\n" % numero + objetos[numero] + b"\nendobj\n"
    inicio = len(salida)
    ultimo = max(objetos)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (ultimo + 1)
    for numero in range(1, ultimo + 1):
        salida += b"%010d 00000 n \n" % posiciones.get(numero, 0)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (ultimo + 1, inicio)
    return bytes(salida)
