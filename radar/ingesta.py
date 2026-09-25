"""Ingesta diaria: del feed a las tablas del núcleo, con trazabilidad.

Cada fila guarda de dónde sale: la licitación apunta a su entrada del feed, y esa entrada
al fichero descargado y su sha256 (docs/DATOS.md §6).

Es idempotente: una licitación se identifica por (entry_id, entry_updated), así que
ejecutarla dos veces el mismo día no duplica nada.

    uv run python -m radar.ingesta --paginas 5
"""

from __future__ import annotations

import argparse
import subprocess
import uuid
from datetime import UTC, datetime

from radar import almacen, feed
from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.red import crear_cliente, descargar

MANIFIESTO = "ingesta_feed"


def commit_actual() -> str | None:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            or None
        )
    except Exception:
        return None


def abrir_ejecucion(conexion, tipo: str, n8n_execution_id: str | None) -> uuid.UUID:
    run_id = uuid.uuid4()
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO ejecuciones (run_id, tipo, n8n_execution_id, git_commit) VALUES (%s, %s, %s, %s)",
            (run_id, tipo, n8n_execution_id, commit_actual()),
        )
    conexion.commit()
    return run_id


def cerrar_ejecucion(conexion, run_id, estado: str, mensaje: str | None = None) -> None:
    with conexion.cursor() as cur:
        cur.execute(
            "UPDATE ejecuciones SET fin = now(), estado = %s, mensaje = %s WHERE run_id = %s",
            (estado, mensaje, run_id),
        )
    conexion.commit()


def guardar_fichero_raw(conexion, ficha: dict, run_id) -> None:
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en, ejecucion_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (sha256) DO NOTHING",
            (
                ficha["sha256"],
                ficha["tipo"],
                ficha["url"],
                ficha["ruta"],
                ficha["bytes"],
                ficha["descargado_en"],
                run_id,
            ),
        )


def guardar_entrada(conexion, sha256: str, posicion: int, lic: feed.Licitacion, xml: str) -> int | None:
    """Guarda la entrada en staging y devuelve su id, o None si ya estaba."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated, xml)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (raw_fichero, posicion) DO NOTHING RETURNING id",
            (sha256, posicion, lic.entry_id or "(sin id)", lic.actualizada, xml),
        )
        fila = cur.fetchone()
        return fila[0] if fila else None


def guardar_licitacion(conexion, stg_id: int, lic: feed.Licitacion) -> int | None:
    """Inserta la licitación si esa versión no estaba. Devuelve su id, o None si ya existía."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, expediente, organo,"
            " objeto, estado, tipo_contrato, cpv, importe_sin_iva, valor_estimado,"
            " plazo_presentacion, solvencia_feed, ficha_url)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (entry_id, entry_updated) DO NOTHING RETURNING id",
            (
                lic.entry_id,
                lic.actualizada,
                stg_id,
                lic.expediente,
                lic.organo,
                lic.objeto,
                lic.estado,
                lic.tipo_contrato,
                lic.cpv,
                lic.importe_sin_iva,
                lic.valor_estimado,
                lic.plazo_presentacion,
                lic.solvencia_feed,
                lic.ficha,
            ),
        )
        fila = cur.fetchone()
        if not fila:
            return None
        licitacion_id = fila[0]

        for tipo, url in [("PCAP", lic.pcap), ("PPT", lic.ppt), *[("anexo", a) for a in lic.anexos]]:
            if url:
                cur.execute(
                    "INSERT INTO documentos (licitacion, tipo, url) VALUES (%s, %s, %s)"
                    " ON CONFLICT (licitacion, tipo, url) DO NOTHING",
                    (licitacion_id, tipo, url),
                )

        if lic.adjudicatario_nif:
            cur.execute(
                "INSERT INTO adjudicaciones (licitacion, adjudicatario, es_pyme) VALUES (%s, %s, %s)",
                (licitacion_id, lic.adjudicatario_nif, _bandera(lic.adjudicatario_pyme)),
            )
        return licitacion_id


def _bandera(valor: str | None) -> bool | None:
    if valor is None:
        return None
    return valor.strip().lower() in {"true", "1", "si", "sí"}


def leer_cursor(conexion) -> str | None:
    with conexion.cursor() as cur:
        cur.execute("SELECT ultima_fecha FROM cursor_feed WHERE fuente = 'placsp_643'")
        fila = cur.fetchone()
        return fila[0].isoformat() if fila and fila[0] else None


def escribir_cursor(conexion, ultima_fecha: str | None, ultima_entrada: str | None) -> None:
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO cursor_feed (fuente, ultima_entrada, ultima_fecha, actualizado_en)"
            " VALUES ('placsp_643', %s, %s, now())"
            " ON CONFLICT (fuente) DO UPDATE SET ultima_entrada = EXCLUDED.ultima_entrada,"
            " ultima_fecha = EXCLUDED.ultima_fecha, actualizado_en = now()",
            (ultima_entrada, ultima_fecha),
        )
    conexion.commit()


def ingerir(paginas_max: int, tipo: str = "manual", n8n_execution_id: str | None = None) -> dict:
    """Descarga y carga el feed hasta alcanzar el punto de la ejecución anterior."""
    resumen = {
        "paginas": 0,
        "entradas_leidas": 0,
        "licitaciones_nuevas": 0,
        "ya_conocidas": 0,
        "documentos": 0,
        "desde_disco": 0,
    }
    with conectar() as conexion:
        run_id = abrir_ejecucion(conexion, tipo, n8n_execution_id)
        cursor_anterior = leer_cursor(conexion)
        mas_reciente = None
        url = feed.FEED_PERFILES

        try:
            with crear_cliente() as cliente:
                while url and resumen["paginas"] < paginas_max:
                    # Lo que ya bajó la Fase 1 se reutiliza: la ingesta no vuelve a pedirlo.
                    guardado = almacen.buscar_por_url(url, MANIFIESTO, "fase1_feed")
                    if guardado is not None:
                        contenido = guardado
                        resumen["desde_disco"] += 1
                    else:
                        contenido = descargar(url, cliente)
                    ficha = almacen.guardar(contenido, "feed", url, MANIFIESTO)
                    guardar_fichero_raw(conexion, ficha, run_id)

                    xml = contenido.decode("utf-8", "ignore")
                    licitaciones, url = feed.parsear_pagina(xml)
                    bloques = xml.split("<entry>")[1:]
                    alcanzado = False

                    for posicion, (lic, bloque) in enumerate(zip(licitaciones, bloques, strict=False)):
                        resumen["entradas_leidas"] += 1
                        if mas_reciente is None or (lic.actualizada or "") > mas_reciente:
                            mas_reciente = lic.actualizada
                        if cursor_anterior and lic.actualizada and lic.actualizada <= cursor_anterior:
                            alcanzado = True
                            continue
                        stg_id = guardar_entrada(conexion, ficha["sha256"], posicion, lic, bloque)
                        if stg_id is None:
                            resumen["ya_conocidas"] += 1
                            continue
                        licitacion_id = guardar_licitacion(conexion, stg_id, lic)
                        if licitacion_id:
                            resumen["licitaciones_nuevas"] += 1
                            resumen["documentos"] += sum(1 for u in [lic.pcap, lic.ppt, *lic.anexos] if u)
                        else:
                            resumen["ya_conocidas"] += 1

                    conexion.commit()
                    resumen["paginas"] += 1
                    print(
                        f"  página {resumen['paginas']}: {len(licitaciones)} entradas, "
                        f"{resumen['licitaciones_nuevas']} nuevas acumuladas",
                        flush=True,
                    )
                    if alcanzado:
                        break

            escribir_cursor(conexion, mas_reciente, None)
            cerrar_ejecucion(conexion, run_id, "ok")
        except ErrorRadar as e:
            conexion.rollback()
            cerrar_ejecucion(conexion, run_id, "error", str(e))
            raise

    resumen["run_id"] = str(run_id)
    resumen["terminada"] = datetime.now(UTC).isoformat(timespec="seconds")
    return resumen


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingesta del feed a la base de datos")
    parser.add_argument("--paginas", type=int, default=5)
    parser.add_argument("--tipo", default="manual", choices=["manual", "diaria", "historica"])
    parser.add_argument("--n8n", default=None, help="identificador de la ejecución de n8n")
    args = parser.parse_args()
    try:
        resumen = ingerir(args.paginas, args.tipo, args.n8n)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print("\nResumen:", resumen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
