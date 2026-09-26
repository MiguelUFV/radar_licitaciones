"""El "antes": el filtro por códigos CPV con el que se compara el radar.

El procedimiento está escrito y congelado en docs/BASELINE.md; aquí solo se aplica. La idea
es imitar lo que hace hoy una persona: elegir unas cuantas divisiones y grupos del
vocabulario CPV que encajen con lo que hace su empresa, y mirar lo que sale.

No lee ningún pliego. Esa es exactamente la diferencia que el proyecto quiere medir.

    uv run python -m radar.baseline --perfil perfiles/perfil_empresa_a.md
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import unicodedata
from pathlib import Path

from radar import almacen
from radar.errores import ErrorRadar
from radar.red import crear_cliente, descargar

VOCABULARIO_URL = "http://contrataciondelestado.es/codice/cl/2.04/CPV2008-2.04.gc"
# Baseline A: lo que tiene configurado cualquier empresa de informatica en su alerta.
PREFIJOS_OBVIOS = ("72", "48")
MANIFIESTO = "vocabulario"
LONGITUD_MINIMA = 5

# Palabras que aparecen en el vocabulario CPV en cualquier sector y no dicen nada del negocio.
# Corta a propósito y congelada con el procedimiento (docs/BASELINE.md §3.6): sin ella, un
# término como "servicios" casaría con media Plataforma.
GENERICAS = {
    "afines",
    "apoyo",
    "asistencia",
    "clientes",
    "diversos",
    "empresa",
    "empresas",
    "especializados",
    "generales",
    "gestion",
    "integral",
    "integrales",
    "nuestra",
    "nuestros",
    "ofrecemos",
    "personalizado",
    "producto",
    "productos",
    "profesional",
    "profesionales",
    "proyecto",
    "proyectos",
    "realizacion",
    "relacionados",
    "sector",
    "servicio",
    "servicios",
    "solucion",
    "soluciones",
    "suministro",
    "suministros",
    "trabajo",
    "trabajos",
    "varios",
}

_APARTADO = re.compile(r"^##\s*(\d+)\.", re.M)
_FILA = re.compile(r"<Row>(.*?)</Row>", re.S)
_CODIGO = re.compile(r'ColumnRef="code">\s*<SimpleValue>([^<]+)')
_NOMBRE = re.compile(r'ColumnRef="nombre">\s*<SimpleValue>([^<]*)')


def sin_acentos(texto: str) -> str:
    plano = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def vocabulario(descargar_si_falta: bool = True) -> dict[str, str]:
    """El vocabulario oficial CPV 2008: código -> descripción en español."""
    datos = almacen.buscar_por_url(VOCABULARIO_URL, MANIFIESTO)
    if datos is None:
        if not descargar_si_falta:
            raise ErrorRadar("El vocabulario CPV no está descargado y no se ha permitido bajarlo.")
        with crear_cliente(timeout=120) as cliente:
            datos = descargar(VOCABULARIO_URL, cliente)
        almacen.guardar(datos, MANIFIESTO, VOCABULARIO_URL, MANIFIESTO)

    texto = datos.decode("utf-8", "ignore")
    codigos = {}
    for fila in _FILA.findall(texto):
        codigo, nombre = _CODIGO.search(fila), _NOMBRE.search(fila)
        if codigo and nombre:
            codigos[codigo.group(1)] = html.unescape(nombre.group(1))
    if not codigos:
        raise ErrorRadar("El vocabulario CPV descargado no tiene el formato esperado.")
    return codigos


def huella_del_vocabulario() -> str:
    datos = almacen.buscar_por_url(VOCABULARIO_URL, MANIFIESTO)
    if datos is None:
        raise ErrorRadar("El vocabulario CPV no está descargado.")
    return hashlib.sha256(datos).hexdigest()


def es_division_o_grupo(codigo: str) -> bool:
    """Los niveles que elige una persona en la Plataforma: 72 (división) o 7225 (grupo)."""
    return codigo.endswith("0000")


def parte_util(perfil: str) -> str:
    """Los apartados 1 (qué hace) y 2 (servicios) del perfil, y nada más.

    Lo dice el procedimiento, y no es un capricho: el apartado de certificaciones o el de lo
    que la empresa dejó de hacer meterían en el filtro sectores enteros que no son suyos.
    """
    marcas = list(_APARTADO.finditer(perfil))
    trozos = []
    for n, marca in enumerate(marcas):
        if marca.group(1) not in {"1", "2"}:
            continue
        inicio = perfil.find("\n", marca.end())
        fin = marcas[n + 1].start() if n + 1 < len(marcas) else len(perfil)
        trozos.append(perfil[inicio:fin])
    if not trozos:
        raise ErrorRadar(
            "El perfil no tiene los apartados 1 y 2. Escríbelo con la plantilla de "
            "ejemplos/perfil_plantilla.md."
        )
    return "\n".join(trozos)


def terminos(texto: str) -> set[str]:
    """Palabras del perfil con las que se busca en el vocabulario (docs/BASELINE.md §3)."""
    palabras = re.findall(r"[a-zñ]+", sin_acentos(texto))
    return {p for p in palabras if len(p) >= LONGITUD_MINIMA and p not in GENERICAS}


def codigos_semilla(texto_perfil: str, cpv: dict[str, str]) -> dict[str, str]:
    """Códigos de división o grupo cuya descripción usa alguna palabra del perfil."""
    buscados = terminos(texto_perfil)
    if not buscados:
        raise ErrorRadar(
            "El perfil no tiene ninguna palabra con la que buscar. Repásalo: tiene que decir a qué "
            "se dedica la empresa."
        )
    patron = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, buscados))) + r")\b")
    return {c: n for c, n in cpv.items() if es_division_o_grupo(c) and patron.search(sin_acentos(n))}


def prefijos(codigos) -> list[str]:
    """72250000 -> 7225. Es como busca la Plataforma: por el principio del código.

    Nunca menos de dos dígitos: 30000000 sin ceros finales se quedaría en "3", y "3" casa
    con 03xxxxxx, que es agricultura.
    """
    recortados = set()
    for codigo in codigos:
        corto = codigo.rstrip("0")
        recortados.add(corto if len(corto) >= 2 else codigo[:2])
    return sorted(recortados)


def pasa_el_filtro(cpv_licitacion: list[str], prefijos_baseline: list[str]) -> bool:
    return any(c.startswith(p) for c in cpv_licitacion for p in prefijos_baseline)


def congelar(perfil: Path, destino: Path, empresa: str | None = None) -> dict:
    """Escribe el Baseline B de una empresa, con la huella del perfil y la del vocabulario."""
    if not perfil.exists():
        raise ErrorRadar(f"No se encuentra el perfil {perfil}.")
    texto = perfil.read_text(encoding="utf-8")
    cpv = vocabulario()
    semilla = codigos_semilla(parte_util(texto), cpv)

    lineas = [
        f"# Baseline B (filtro amplio) — {perfil.stem}",
        "",
        "Generado por `radar/baseline.py` con el procedimiento de `docs/BASELINE.md`.",
        "Una vez congelado no se toca: si cambia, hay que volver a medir.",
        "",
        f"- Empresa: {empresa or perfil.stem}",
        f"- Perfil del que sale: `{perfil.as_posix()}`",
        f"- Huella del perfil: sha256 `{hashlib.sha256(texto.encode()).hexdigest()[:16]}`",
        f"- Vocabulario CPV: sha256 `{huella_del_vocabulario()[:16]}`",
        f"- Códigos: {len(semilla)}, todos calculados; aquí no se añade ni se quita nada a mano",
        "",
        "| Código | Descripción oficial |",
        "|---|---|",
    ]
    for codigo in sorted(semilla):
        lineas.append(f"| {codigo} | {semilla[codigo]} |")
    lineas += ["", "## Prefijos con los que se filtra", "", "`" + "`, `".join(prefijos(semilla)) + "`", ""]

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return {"codigos": len(semilla), "prefijos": len(prefijos(semilla)), "fichero": destino.as_posix()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Filtro CPV de referencia a partir de un perfil")
    parser.add_argument("--perfil", required=True, type=Path)
    parser.add_argument("--destino", type=Path, default=None)
    parser.add_argument("--empresa", default=None, help="alias de la empresa (Empresa A…)")
    args = parser.parse_args()
    destino = args.destino or Path("docs/baselines") / f"{args.perfil.stem}.md"
    try:
        resumen = congelar(args.perfil, destino, args.empresa)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print("\nResumen:", resumen)
    print("El Baseline A no necesita fichero: son las divisiones 72 y 48 (docs/BASELINE.md §2).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
