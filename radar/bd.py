"""Conexión a PostgreSQL y aplicación de migraciones.

Las migraciones son ficheros .sql numerados en sql/migraciones/. Se aplican en orden y
se anotan en la tabla migraciones, así que ejecutarlas dos veces no rompe nada.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from radar.errores import FaltaConfiguracion

MIGRACIONES = Path("sql/migraciones")


def cadena_conexion() -> str:
    load_dotenv()
    contrasena = os.getenv("POSTGRES_PASSWORD")
    if not contrasena:
        raise FaltaConfiguracion(
            "Falta POSTGRES_PASSWORD en el fichero .env, necesaria para la base de datos."
        )
    usuario = os.getenv("POSTGRES_USER", "radar")
    base = os.getenv("POSTGRES_DB", "radar")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    puerto = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql://{usuario}:{contrasena}@{host}:{puerto}/{base}"


@contextmanager
def conectar():
    try:
        with psycopg.connect(cadena_conexion(), autocommit=False) as conexion:
            yield conexion
    except psycopg.OperationalError as e:
        raise FaltaConfiguracion(
            "La base de datos no está disponible. Arráncala con: docker compose up -d",
            detalle=str(e),
        ) from e


def aplicar_migraciones() -> list[str]:
    """Aplica las migraciones pendientes y devuelve los nombres de las aplicadas."""
    aplicadas = []
    with conectar() as conexion:
        with conexion.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS migraciones ("
                " nombre TEXT PRIMARY KEY,"
                " aplicada_en TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            cur.execute("SELECT nombre FROM migraciones")
            ya = {fila[0] for fila in cur.fetchall()}

            for fichero in sorted(MIGRACIONES.glob("*.sql")):
                if fichero.name in ya:
                    continue
                cur.execute(fichero.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO migraciones (nombre) VALUES (%s)", (fichero.name,))
                aplicadas.append(fichero.name)
        conexion.commit()
    return aplicadas


if __name__ == "__main__":
    nuevas = aplicar_migraciones()
    print("Migraciones aplicadas:", ", ".join(nuevas) if nuevas else "ninguna (ya estaba al día)")
