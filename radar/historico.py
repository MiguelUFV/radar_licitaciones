"""Carga histórica: los meses anteriores, desde los zip mensuales de la Plataforma.

La Plataforma publica un zip por mes con las mismas entradas que el feed diario
(comprobado el 25-09-2026: `..._202501.zip`, 139,6 MB, application/zip). Eso evita paginar
miles de veces hacia atrás.

Un mes son unos 137 MB y tarda unos 4 minutos: la carga va mes a mes y se puede retomar
donde se quedó. Lo ya descargado no se vuelve a pedir.

De las entradas históricas no se guarda el XML en la base: son cientos de miles y el zip es
inmutable, así que se guarda el puntero (zip + fichero .atom + posición) y el original se
recupera cuando haga falta con `entrada_original()`.

    uv run python -m radar.historico --desde 2025-01 --hasta 2026-08
"""

from __future__ import annotations

import argparse
import io
import zipfile
from datetime import date

from radar import almacen, feed
from radar.bd import conectar
from radar.errores import ErrorRadar, FuenteNoResponde
from radar.ingesta import (
    abrir_ejecucion,
    cerrar_ejecucion,
    guardar_baja,
    guardar_fichero_raw,
    guardar_licitacion,
)
from radar.red import crear_cliente, descargar

MANIFIESTO = "historico"
BASE = (
    "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
    "licitacionesPerfilesContratanteCompleto3_{mes}.zip"
)
# El servidor va a unos 0,6 MB/s y un mes pesa 137 MB, así que la descarga entera son unos
# 4 minutos. Esto no es el total: es lo que se tolera sin recibir un solo byte. Con 15 minutos
# una conexión muerta (el portátil se durmió) tardaba una eternidad en darse por vencida.
ESPERA = 120.0
# Una página del feed ocupa unos 17 MB descomprimida. Este tope es el que separa "el fichero
# de este mes es grande" de "esto no es lo que dice ser".
MAXIMO_POR_FICHERO = 200 * 1024 * 1024


def meses(desde: str, hasta: str) -> list[str]:
    """['2025-01', '2025-02', ...]. Los meses se escriben AAAA-MM."""
    inicio, fin = date.fromisoformat(f"{desde}-01"), date.fromisoformat(f"{hasta}-01")
    if inicio > fin:
        raise ErrorRadar(f"El mes inicial ({desde}) es posterior al final ({hasta}).")
    listado, actual = [], inicio
    while actual <= fin:
        listado.append(actual.strftime("%Y-%m"))
        siguiente = actual.month + 1
        actual = date(actual.year + siguiente // 13, siguiente % 12 or 12, 1)
    return listado


def url_del_mes(mes: str) -> str:
    return BASE.format(mes=mes.replace("-", ""))


def meses_cargados(conexion) -> set[str]:
    with conexion.cursor() as cur:
        cur.execute("SELECT mes FROM historico_meses")
        return {fila[0] for fila in cur.fetchall()}


def guardar_entrada_historica(conexion, sha256: str, miembro: str, posicion: int, lic) -> int | None:
    """Anota de dónde sale la entrada, sin copiar su XML."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, miembro, posicion, entry_id, entry_updated)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (raw_fichero, coalesce(miembro, ''), posicion) DO NOTHING RETURNING id",
            (sha256, miembro, posicion, lic.entry_id or "(sin id)", lic.actualizada),
        )
        fila = cur.fetchone()
        return fila[0] if fila else None


def entrada_original(sha256: str, miembro: str, posicion: int) -> str:
    """Devuelve el XML exacto de una entrada histórica, sacándolo otra vez del zip.

    Es lo que hace verificable no haber copiado el XML a la base: el original sigue estando.
    """
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT ruta FROM raw_ficheros WHERE sha256 = %s", (sha256,))
        fila = cur.fetchone()
    if not fila:
        raise ErrorRadar("Ese fichero no está en la capa raw.", detalle=sha256)
    with zipfile.ZipFile(fila[0]) as zip_mes:
        bloques = feed.entradas(zip_mes.read(miembro).decode("utf-8", "ignore"))
    if posicion >= len(bloques):
        raise ErrorRadar("Esa entrada no está en el fichero indicado.", detalle=f"{miembro}#{posicion}")
    return bloques[posicion]


def expedientes_conocidos(conexion) -> set[str]:
    with conexion.cursor() as cur:
        cur.execute("SELECT DISTINCT entry_id FROM licitaciones")
        return {fila[0] for fila in cur.fetchall()}


def interesa(lic, dentro_de_la_ventana: bool, conocidos: set[str]) -> bool:
    """Qué se guarda de cada entrada.

    De los meses del periodo de estudio se guarda todo. De los meses posteriores solo
    interesa quién ganó los expedientes de ese periodo: el resto del movimiento del feed
    (miles de anuncios de otros meses) no se usa para nada y multiplicaría la carga.
    """
    if dentro_de_la_ventana:
        return True
    return bool(lic.adjudicatario_nif) and lic.entry_id in conocidos


def comprobar_tamanos(zip_mes: zipfile.ZipFile, nombres: list[str], mes: str) -> None:
    """Un .atom del feed pesa unos 17 MB descomprimido.

    Si uno declara cientos de megas, o el fichero está mal o alguien lo ha manipulado para
    que llene la memoria al abrirlo. Se para antes de leerlo, no después.
    """
    for nombre in nombres:
        tamano = zip_mes.getinfo(nombre).file_size
        if tamano > MAXIMO_POR_FICHERO:
            raise ErrorRadar(
                f"Una de las páginas del mes {mes} ocupa {tamano / 1_048_576:.0f} MB al "
                "descomprimirse, mucho más de lo normal. No se abre.",
                detalle=f"{nombre}: {tamano} bytes",
            )


def totales_del_mes(conexion, sha256: str) -> dict:
    """Lo que hay en la base para ese zip, venga de la pasada que venga."""
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT count(*) FILTER (WHERE l.id IS NOT NULL),"
            " count(*) FILTER (WHERE a.id IS NOT NULL)"
            " FROM stg_entradas s"
            " LEFT JOIN licitaciones l ON l.stg_entrada = s.id"
            " LEFT JOIN adjudicaciones a ON a.licitacion = l.id"
            " WHERE s.raw_fichero = %s",
            (sha256,),
        )
        licitaciones, adjudicaciones = cur.fetchone()
    return {"licitaciones": licitaciones, "adjudicaciones": adjudicaciones}


def cargar_mes(conexion, mes: str, run_id, cliente, ventana: tuple[str, str] | None = None) -> dict:
    url = url_del_mes(mes)
    contenido = almacen.buscar_por_url(url, MANIFIESTO)
    if contenido is None:
        contenido = descargar(url, cliente)
    ficha = almacen.guardar(contenido, "historico", url, MANIFIESTO)
    guardar_fichero_raw(conexion, ficha, run_id)
    conexion.commit()

    dentro = ventana is None or ventana[0] <= mes <= ventana[1]
    conocidos = set() if dentro else expedientes_conocidos(conexion)
    cuenta = {
        "ficheros_atom": 0,
        "entradas": 0,
        "licitaciones": 0,
        "adjudicaciones": 0,
        "bajas": 0,
        "descartadas": 0,
    }
    with zipfile.ZipFile(io.BytesIO(contenido)) as zip_mes:
        nombres = sorted(n for n in zip_mes.namelist() if n.lower().endswith(".atom"))
        if not nombres:
            raise ErrorRadar(
                f"El fichero del mes {mes} no trae ninguna página del feed dentro.",
                detalle=str(zip_mes.namelist()[:5]),
            )
        comprobar_tamanos(zip_mes, nombres, mes)
        for nombre in nombres:
            xml = zip_mes.read(nombre).decode("utf-8", "ignore")
            cuenta["ficheros_atom"] += 1
            for baja in feed.bajas(xml):
                guardar_baja(conexion, baja, ficha["sha256"])
                cuenta["bajas"] += 1
            for posicion, bloque in enumerate(feed.entradas(xml)):
                cuenta["entradas"] += 1
                lic = feed.parsear_entrada(bloque)
                if not interesa(lic, dentro, conocidos):
                    cuenta["descartadas"] += 1
                    continue
                stg_id = guardar_entrada_historica(conexion, ficha["sha256"], nombre, posicion, lic)
                if stg_id is None:
                    continue
                if guardar_licitacion(conexion, stg_id, lic):
                    cuenta["licitaciones"] += 1
                    cuenta["adjudicaciones"] += 1 if lic.adjudicatario_nif else 0
            conexion.commit()

    # Lo que se anota es lo que hay en la base para ese mes, no lo que ha insertado esta
    # pasada: si una carga se corta a la mitad y se relanza, la segunda solo añade lo que
    # faltaba, y decir "998 licitaciones" de un mes que tiene 55.380 sería engañoso.
    cuenta.update(totales_del_mes(conexion, ficha["sha256"]))

    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO historico_meses (mes, raw_fichero, ficheros_atom, entradas, licitaciones,"
            " adjudicaciones, ejecucion_id) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (mes) DO UPDATE SET raw_fichero = EXCLUDED.raw_fichero,"
            " ficheros_atom = EXCLUDED.ficheros_atom, entradas = EXCLUDED.entradas,"
            " licitaciones = EXCLUDED.licitaciones, adjudicaciones = EXCLUDED.adjudicaciones,"
            " cargado_en = now(), ejecucion_id = EXCLUDED.ejecucion_id",
            (
                mes,
                ficha["sha256"],
                cuenta["ficheros_atom"],
                cuenta["entradas"],
                cuenta["licitaciones"],
                cuenta["adjudicaciones"],
                run_id,
            ),
        )
    conexion.commit()
    cuenta["megabytes"] = round(ficha["bytes"] / 1_048_576, 1)
    return cuenta


def cargar(desde: str, hasta: str, rehacer: bool = False, ventana: tuple[str, str] | None = None) -> dict:
    pedidos = meses(desde, hasta)
    resumen = {"meses": [], "entradas": 0, "licitaciones": 0, "adjudicaciones": 0, "saltados": 0}
    with conectar() as conexion:
        run_id = abrir_ejecucion(conexion, "historica", None)
        ya = set() if rehacer else meses_cargados(conexion)
        try:
            with crear_cliente(timeout=ESPERA) as cliente:
                for mes in pedidos:
                    if mes in ya:
                        resumen["saltados"] += 1
                        print(f"  {mes}: ya estaba cargado", flush=True)
                        continue
                    cuenta = cargar_mes(conexion, mes, run_id, cliente, ventana)
                    resumen["meses"].append(mes)
                    for clave in ("entradas", "licitaciones", "adjudicaciones"):
                        resumen[clave] += cuenta[clave]
                    print(
                        f"  {mes}: {cuenta['megabytes']} MB, {cuenta['ficheros_atom']} ficheros, "
                        f"{cuenta['entradas']} entradas ({cuenta['descartadas']} fuera de estudio), "
                        f"{cuenta['licitaciones']} licitaciones y {cuenta['adjudicaciones']} "
                        "adjudicaciones en la base",
                        flush=True,
                    )
            cerrar_ejecucion(conexion, run_id, "ok")
        except Exception as e:
            legible = e.mensaje if isinstance(e, ErrorRadar) else "Fallo no previsto en la carga histórica."
            cerrar_ejecucion(conexion, run_id, "error", legible)
            if isinstance(e, ErrorRadar):
                raise
            raise ErrorRadar(legible, detalle=repr(e)) from e
    resumen["run_id"] = str(run_id)
    return resumen


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga histórica desde los zip mensuales")
    parser.add_argument("--desde", required=True, help="mes inicial, AAAA-MM")
    parser.add_argument("--hasta", required=True, help="mes final, AAAA-MM")
    parser.add_argument("--rehacer", action="store_true", help="vuelve a cargar meses ya cargados")
    parser.add_argument(
        "--ventana",
        nargs=2,
        metavar=("AAAA-MM", "AAAA-MM"),
        help="meses del periodo de estudio; de los demás solo se guarda quién ganó esos expedientes",
    )
    args = parser.parse_args()
    try:
        resumen = cargar(args.desde, args.hasta, args.rehacer, tuple(args.ventana) if args.ventana else None)
    except FuenteNoResponde as e:
        print(f"\n{e}\nLo cargado hasta ahora se conserva: vuelve a lanzarlo y sigue donde estaba.")
        return 1
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print("\nResumen:", resumen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
