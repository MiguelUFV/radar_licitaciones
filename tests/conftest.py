"""Piezas comunes de los tests.

DATOS DE EJEMPLO — no usar en producción. Las páginas del feed que se arman aquí parten de
una entrada real grabada (`tests/fixtures/entrada_real.xml`) y solo se les cambia el
identificador y la fecha, que es lo que hace falta para provocar situaciones concretas del
cursor. Nada de esto sale del directorio `tests/`.

Los tests que tocan PostgreSQL trabajan sobre una base aparte (`radar_test`): la base de
trabajo nunca recibe filas de prueba (CLAUDE.md, innegociable 2).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
BASE_PRUEBAS = "radar_test"

TABLAS = [
    "adjudicaciones",
    "documentos",
    "lotes",
    "bajas",
    "licitaciones",
    "stg_entradas",
    "raw_ficheros",
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
