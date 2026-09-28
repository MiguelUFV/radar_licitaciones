"""Congela los perfiles de las empresas del estudio.

El perfil es todo lo que el radar va a saber de una empresa. Una vez congelado no se toca: si
cambia, hay que volver a medir todo lo que dependa de él (docs/REGLA_SELECCION.md §6).

Los perfiles viven en `data/privado/perfiles/`, fuera de git, porque identifican a la empresa.
Lo que sí se versiona es `docs/perfiles_congelados.md`: alias, huella y fecha, sin nombres ni
direcciones. Eso basta para demostrar que el perfil no se ha cambiado después de medir.

    uv run python -m radar.perfiles --congelar
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from radar import fechas
from radar.bd import conectar
from radar.errores import ErrorRadar

CARPETA = Path("data/privado/perfiles")
PUBLICO = Path("docs/perfiles_congelados.md")
_NOMBRE = re.compile(r"^perfil_empresa_([a-z])\.md$")


def alias_del_fichero(fichero: Path) -> str:
    m = _NOMBRE.match(fichero.name)
    if not m:
        raise ErrorRadar(
            f"El perfil {fichero.name} no se llama como debe: perfil_empresa_a.md, _b.md…",
        )
    return f"Empresa {m.group(1).upper()}"


def fuentes_de(texto: str) -> str:
    """Las líneas de la lista del apartado Fuentes, para poder auditar de dónde salió."""
    trozo = texto.split("## Fuentes", 1)
    if len(trozo) == 1:
        raise ErrorRadar("El perfil no tiene apartado 'Fuentes'. Sin fuentes no se puede auditar.")
    lineas = []
    for linea in trozo[1].splitlines():
        if linea.startswith("## "):
            break
        if linea.strip().startswith("- "):
            lineas.append(linea.strip()[2:])
    if not lineas:
        raise ErrorRadar("El apartado 'Fuentes' está vacío. Sin fuentes no se puede auditar.")
    return "\n".join(lineas)


# La línea del perfil que trae la cifra de negocio, y los importes que haya en ella.
CIFRA = re.compile(r"^\|\s*Cifra anual de negocio\s*\|(.+?)\|(.*?)\|\s*$", re.M | re.I)
IMPORTE = re.compile(r"([\d][\d.\s]*)\s*€")
SIN_CIFRA = re.compile(r"no\s+(publicada|localizada|consta|disponible)", re.I)


def cifra_de(texto: str) -> tuple[float | None, str | None]:
    """La cifra de negocio de un perfil y de dónde sale.

    Los directorios publican intervalos, no cifras exactas. Se usa **el extremo inferior**
    (`docs/SPEC.md` §9): es el que menos solvencia atribuye a la empresa, así que si con él el
    radar dice que cumple, cumple de verdad.

    Si el perfil dice que no hay cifra pública, devuelve None y esa empresa queda fuera de M3.
    """
    fila = CIFRA.search(texto or "")
    if not fila:
        return None, None
    valor, fuente = fila.group(1).strip(), fila.group(2).strip()
    if SIN_CIFRA.search(valor):
        return None, f"sin cifra pública ({fuente})" if fuente else "sin cifra pública"
    importes = [float(i.replace(".", "").replace(" ", "")) for i in IMPORTE.findall(valor)]
    if not importes:
        return None, f"sin cifra pública ({fuente})" if fuente else "sin cifra pública"
    return min(importes), f"{valor} — {fuente}" if fuente else valor


def cargar_cifras() -> list[tuple[str, float | None, str | None]]:
    """Rellena `cifra_negocio` leyendo el perfil **ya congelado** de la base.

    Se lee de la base, no del fichero, y se comprueba la huella antes: así la cifra sale del
    mismo texto que se congeló. No se toca ningún perfil, solo se extrae un dato que estaba
    escrito en él y que la tabla tenía vacío. Sin esta columna, la regla del volumen de
    negocios no puede dispararse nunca y M3 no se puede medir.
    """
    resultados = []
    with conectar() as conexion:
        with conexion.cursor() as cur:
            cur.execute(
                "SELECT alias, texto, texto_sha256 FROM perfiles WHERE texto IS NOT NULL ORDER BY alias"
            )
            filas = cur.fetchall()
        for alias, texto, huella in filas:
            if hashlib.sha256(texto.encode("utf-8")).hexdigest() != huella:
                raise ErrorRadar(
                    f"El perfil de {alias} no coincide con su huella: no se carga nada hasta aclararlo."
                )
            importe, fuente = cifra_de(texto)
            with conexion.cursor() as cur:
                cur.execute(
                    "UPDATE perfiles SET cifra_negocio = %s, cifra_fuente = %s WHERE alias = %s",
                    (importe, fuente, alias),
                )
            resultados.append((alias, importe, fuente))
        conexion.commit()
    return resultados


def congelar(carpeta: Path = CARPETA, rehacer: bool = False) -> dict:
    ficheros = sorted(carpeta.glob("perfil_empresa_*.md")) if carpeta.exists() else []
    if not ficheros:
        raise ErrorRadar(f"No hay ningún perfil en {carpeta.as_posix()}.")

    resumen = {"congelados": 0, "ya_estaban": 0}
    with conectar() as conexion:
        for fichero in ficheros:
            alias = alias_del_fichero(fichero)
            texto = fichero.read_text(encoding="utf-8")
            huella = hashlib.sha256(texto.encode("utf-8")).hexdigest()
            with conexion.cursor() as cur:
                cur.execute("SELECT texto_sha256 FROM perfiles WHERE alias = %s", (alias,))
                fila = cur.fetchone()
                if not fila:
                    raise ErrorRadar(
                        f"{alias} no está en la tabla perfiles. Primero hay que aplicar la regla: "
                        "uv run python -m radar.seleccion"
                    )
                if fila[0] and not rehacer:
                    if fila[0] != huella:
                        raise ErrorRadar(
                            f"El perfil de {alias} ha cambiado después de congelarse. Eso obliga a "
                            "volver a medir: si es a propósito, usa --rehacer y anótalo en el informe."
                        )
                    resumen["ya_estaban"] += 1
                    continue
                cur.execute(
                    "UPDATE perfiles SET texto = %s, texto_sha256 = %s, fuentes = %s,"
                    " congelado_en = now() WHERE alias = %s",
                    (texto, huella, fuentes_de(texto), alias),
                )
                resumen["congelados"] += 1
        conexion.commit()
        resumen["registro"] = escribir_registro(conexion)
    return resumen


def escribir_registro(conexion, destino: Path = PUBLICO) -> str:
    """El registro que sí se versiona: huellas y fechas, sin nombres ni direcciones."""
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT alias, rol, texto_sha256, congelado_en::date,"
            " coalesce(array_length(string_to_array(fuentes, chr(10)), 1), 0)"
            " FROM perfiles ORDER BY alias"
        )
        filas = cur.fetchall()
    lineas = [
        "# Perfiles congelados",
        "",
        "Un perfil es todo lo que el radar sabe de una empresa. Se escribe **antes** de medir y a",
        "partir de fuentes públicas, sin mirar los contratos que esa empresa ganó",
        "(`docs/REGLA_SELECCION.md` §6).",
        "",
        "Aquí solo va la huella. El texto y las direcciones de las fuentes se quedan en",
        "`data/privado/perfiles/`, fuera de git, porque identifican a la empresa (`docs/DATOS.md` §7).",
        "Con la huella basta para lo que importa: comprobar que el perfil **no se ha cambiado**",
        "después de publicar una medición.",
        "",
        "| Empresa | Papel | Fuentes | Congelado | sha256 del perfil |",
        "|---|---|---|---|---|",
    ]
    for alias, rol, huella, cuando, fuentes in filas:
        lineas.append(f"| {alias} | {rol} | {fuentes} | {cuando or '(sin congelar)'} | `{huella or '—'}` |")
    lineas += [
        "",
        f"Generado por `radar/perfiles.py` el {fechas.hoy().isoformat()}.",
        "",
        "Para comprobar uno:",
        "",
        "```bash",
        "sha256sum data/privado/perfiles/perfil_empresa_a.md",
        "```",
        "",
    ]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return destino.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Congela los perfiles de las empresas")
    parser.add_argument("--congelar", action="store_true")
    parser.add_argument("--rehacer", action="store_true", help="vuelve a congelar uno ya congelado")
    parser.add_argument(
        "--cifras", action="store_true", help="rellena la cifra de negocio desde el perfil congelado"
    )
    args = parser.parse_args()
    if args.cifras:
        try:
            cargadas = cargar_cifras()
        except ErrorRadar as e:
            print(f"\n{e}")
            return 1
        print()
        for alias, importe, fuente in cargadas:
            cuanto = f"{importe:,.0f} €".replace(",", ".") if importe else "sin cifra pública"
            print(f"  {alias:12} {cuanto:22} {(fuente or '')[:60]}")
        return 0
    if not args.congelar:
        parser.print_help()
        return 0
    try:
        resumen = congelar(rehacer=args.rehacer)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print(f"\nPerfiles congelados ahora: {resumen['congelados']}")
    print(f"Ya estaban congelados y no han cambiado: {resumen['ya_estaban']}")
    print(f"Registro versionado: {resumen['registro']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
