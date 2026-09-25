"""Descarga de los pliegos de las licitaciones candidatas.

El feed solo trae el enlace. Aquí se baja el documento, se guarda en la capa raw por su
sha256 y se anota en `documentos` qué se descargó, cuántas páginas tiene y si trae capa de
texto. A partir de ahí, el expediente y su pliego están unidos por la huella del fichero
(docs/DATOS.md §6).

No se bajan los 5.438 documentos del feed: solo el PCAP de lo que puede interesar. La regla
de selección de verdad llega en la Fase 3; aquí el filtro es grueso (CPV de informática) y
está para acotar el gasto de disco y de red.

    uv run python -m radar.pliegos --limite 20
"""

from __future__ import annotations

import argparse

from radar import almacen, documentos
from radar.bd import conectar
from radar.errores import DocumentoIlegible, ErrorRadar, FuenteNoResponde
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion, guardar_fichero_raw
from radar.red import crear_cliente, descargar

MANIFIESTO = "pliegos"
INTENTOS_MAXIMOS = 3
# Si fallan tres seguidos, el problema no es de un documento suelto: se para y se avisa.
FALLOS_SEGUIDOS = 3
FUENTE_CAIDA = (
    "Varios pliegos seguidos han fallado. Se para la descarga para no insistir sobre un "
    "servidor que no responde; los que ya se bajaron quedan guardados."
)

CANDIDATOS = """
SELECT d.id, d.url
FROM documentos d
JOIN v_licitaciones_vigentes l ON l.id = d.licitacion
WHERE d.tipo = %s
  -- 'error' vuelve a la cola (puede ser un corte pasajero); 'ilegible' no: un zip no va a
  -- convertirse en PDF por insistir.
  AND d.estado_descarga IN ('pendiente', 'error')
  AND d.intentos < %s
  AND NOT l.anulada
  AND (NOT %s OR EXISTS (
        SELECT 1 FROM unnest(l.cpv) AS c WHERE c LIKE '72%%' OR c LIKE '48%%'))
ORDER BY l.plazo_presentacion NULLS LAST, d.id
LIMIT %s
"""


def pendientes(conexion, limite: int, tipo: str, solo_informatica: bool) -> list[tuple[int, str]]:
    with conexion.cursor() as cur:
        cur.execute(CANDIDATOS, (tipo, INTENTOS_MAXIMOS, solo_informatica, limite))
        return cur.fetchall()


def anotar_intento(conexion, documento_id: int, **campos) -> None:
    asignaciones = ", ".join(f"{nombre} = %s" for nombre in campos)
    with conexion.cursor() as cur:
        cur.execute(
            f"UPDATE documentos SET {asignaciones}, intentos = intentos + 1,"
            " ultimo_intento = now() WHERE id = %s",
            (*campos.values(), documento_id),
        )
    conexion.commit()


def descargar_pendientes(
    limite: int = 20,
    tipo: str = "PCAP",
    solo_informatica: bool = True,
    tipo_ejecucion: str = "manual",
    n8n_execution_id: str | None = None,
) -> dict:
    resumen = {
        "pedidos": 0,
        "descargados": 0,
        "ilegibles": 0,
        "errores": 0,
        "desde_disco": 0,
        "megabytes": 0.0,
    }
    with conectar() as conexion:
        run_id = abrir_ejecucion(conexion, tipo_ejecucion, n8n_execution_id)
        cola = pendientes(conexion, limite, tipo, solo_informatica)
        resumen["pedidos"] = len(cola)
        seguidos = 0

        try:
            with crear_cliente() as cliente:
                for documento_id, url in cola:
                    # Lo que ya bajó la Fase 1 no se vuelve a pedir.
                    contenido = almacen.buscar_por_url(url, MANIFIESTO, "fase1_pliegos")
                    if contenido is not None:
                        resumen["desde_disco"] += 1
                    else:
                        try:
                            contenido = descargar(url, cliente)
                        except FuenteNoResponde as e:
                            seguidos += 1
                            resumen["errores"] += 1
                            anotar_intento(
                                conexion, documento_id, estado_descarga="error", motivo_error=e.mensaje
                            )
                            if seguidos >= FALLOS_SEGUIDOS:
                                raise FuenteNoResponde(FUENTE_CAIDA, detalle=url) from e
                            continue

                    seguidos = 0
                    ficha = almacen.guardar(contenido, "pliego", url, MANIFIESTO)
                    guardar_fichero_raw(conexion, ficha, run_id)
                    resumen["megabytes"] += ficha["bytes"] / 1_048_576

                    try:
                        medidas = documentos.analizar(contenido)
                    except DocumentoIlegible as e:
                        resumen["ilegibles"] += 1
                        # El fichero se queda guardado: saber que no se puede leer es un dato.
                        anotar_intento(
                            conexion,
                            documento_id,
                            estado_descarga="ilegible",
                            raw_fichero=ficha["sha256"],
                            motivo_error=e.mensaje,
                        )
                        continue

                    resumen["descargados"] += 1
                    anotar_intento(
                        conexion,
                        documento_id,
                        estado_descarga="descargado",
                        raw_fichero=ficha["sha256"],
                        paginas=medidas["paginas"],
                        con_capa_texto=not medidas["escaneado"],
                        motivo_error=None,
                    )

            cerrar_ejecucion(conexion, run_id, "ok")
        except Exception as e:
            legible = e.mensaje if isinstance(e, ErrorRadar) else "Fallo no previsto al bajar los pliegos."
            cerrar_ejecucion(conexion, run_id, "error", legible)
            if isinstance(e, ErrorRadar):
                raise
            raise ErrorRadar(legible, detalle=repr(e)) from e

    resumen["megabytes"] = round(resumen["megabytes"], 1)
    resumen["run_id"] = str(run_id)
    return resumen


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga de pliegos pendientes")
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument("--tipo", default="PCAP", choices=["PCAP", "PPT", "anexo"])
    parser.add_argument("--todos", action="store_true", help="sin filtrar por CPV de informática")
    args = parser.parse_args()
    try:
        resumen = descargar_pendientes(args.limite, args.tipo, not args.todos)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print("\nResumen:", resumen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
