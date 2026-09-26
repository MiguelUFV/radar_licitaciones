"""Mirar las licitaciones que hay guardadas, sin saber SQL.

Todo lo que sale de aquí está en la base tal como lo publicó la Plataforma. No hay nada
calculado ni inventado: es el dato en crudo, para poder verlo con los ojos.

    uv run python -m radar.ver --buscar sanidad
    uv run python -m radar.ver --expediente "2025/1234"
    uv run python -m radar.ver --informatica --ganadas
"""

from __future__ import annotations

import argparse
import textwrap

from radar.bd import conectar
from radar.errores import ErrorRadar

ANCHO = 84

BUSQUEDA = """
SELECT DISTINCT ON (l.entry_id)
       l.id, l.expediente, l.organo, l.objeto, l.estado, l.cpv,
       l.importe_sin_iva, l.valor_estimado, l.plazo_presentacion,
       l.entry_updated::date, l.ficha_url, l.solvencia_feed
FROM licitaciones l
WHERE (%(texto)s::text IS NULL OR l.objeto ILIKE %(patron)s::text)
  AND (%(expediente)s::text IS NULL OR l.expediente ILIKE %(expediente_patron)s::text)
  AND (NOT %(informatica)s::boolean OR EXISTS (
        SELECT 1 FROM unnest(l.cpv) AS c WHERE c LIKE '72%%' OR c LIKE '48%%'))
  AND (NOT %(ganadas)s::boolean OR EXISTS (
        SELECT 1 FROM adjudicaciones a WHERE a.licitacion = l.id AND a.adjudicatario IS NOT NULL))
ORDER BY l.entry_id, l.entry_updated DESC
LIMIT %(limite)s::integer
"""

ESTADOS = {
    "PRE": "anuncio previo",
    "PUB": "publicada, se puede presentar",
    "EV": "en evaluación",
    "ADJ": "adjudicada",
    "RES": "resuelta",
    "ANUL": "anulada",
}


def euros(cantidad) -> str:
    if cantidad is None:
        return "no publicado"
    return f"{float(cantidad):,.0f} €".replace(",", ".")


def detalles(cur, licitacion_id: int) -> dict:
    cur.execute(
        "SELECT tipo, url, estado_descarga, paginas FROM documentos WHERE licitacion = %s ORDER BY tipo",
        (licitacion_id,),
    )
    documentos = cur.fetchall()
    cur.execute(
        "SELECT adjudicatario, nombre, es_pyme FROM adjudicaciones WHERE licitacion = %s",
        (licitacion_id,),
    )
    ganadores = cur.fetchall()
    cur.execute(
        "SELECT numero, objeto, importe FROM lotes WHERE licitacion = %s ORDER BY numero", (licitacion_id,)
    )
    return {"documentos": documentos, "ganadores": ganadores, "lotes": cur.fetchall()}


def pintar(fila, extra: dict) -> str:
    (id_, expediente, organo, objeto, estado, cpv, importe, valor, plazo, fecha, ficha, solvencia) = fila
    lineas = ["=" * ANCHO]
    lineas += textwrap.wrap(objeto or "(sin objeto)", ANCHO)
    lineas.append("-" * ANCHO)
    lineas.append(f"Expediente   {expediente or '(sin número)'}")
    lineas.append(f"Órgano       {(organo or '')[: ANCHO - 13]}")
    lineas.append(f"Estado       {ESTADOS.get(estado, estado or '?')}   (última noticia: {fecha})")
    lineas.append(f"Importe      {euros(importe)}   ·   valor estimado {euros(valor)}")
    lineas.append(f"Plazo        {plazo or 'no publicado'}")
    lineas.append(f"CPV          {', '.join(cpv or []) or 'ninguno'}")

    if extra["lotes"]:
        lineas.append(f"Lotes        {len(extra['lotes'])}")
        for numero, objeto_lote, importe_lote in extra["lotes"][:4]:
            lineas.append(f"             {numero}. {(objeto_lote or '')[:50]}  {euros(importe_lote)}")

    for adjudicatario, nombre, pyme in extra["ganadores"]:
        quien = nombre or (
            "un autónomo (identificador seudonimizado)" if adjudicatario.startswith("pf_") else ""
        )
        etiqueta = " (pyme)" if pyme else ""
        lineas.append(f"Lo ganó      {adjudicatario}  {quien[:44]}{etiqueta}")

    if solvencia:
        lineas.append("Solvencia    " + textwrap.shorten(solvencia, 66, placeholder="…"))
        lineas.append("             ^ esto es lo que trae el feed. Casi nunca trae la cifra.")

    for tipo, url, estado_descarga, paginas in extra["documentos"]:
        if tipo in {"PCAP", "PPT"}:
            detalle = f"{paginas} páginas" if paginas else estado_descarga
            lineas.append(f"{tipo:12} {detalle}")
            lineas.append(f"             {url[: ANCHO - 13]}")
    if ficha:
        lineas.append(f"Ficha web    {ficha[: ANCHO - 13]}")
    return "\n".join(lineas)


def buscar(texto=None, expediente=None, informatica=False, ganadas=False, limite=5) -> str:
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(
            BUSQUEDA,
            {
                "texto": texto,
                "patron": f"%{texto}%" if texto else None,
                "expediente": expediente,
                "expediente_patron": f"%{expediente}%" if expediente else None,
                "informatica": informatica,
                "ganadas": ganadas,
                "limite": limite,
            },
        )
        filas = cur.fetchall()
        if not filas:
            return "No hay ninguna licitación que encaje con eso."
        return "\n\n".join(pintar(fila, detalles(cur, fila[0])) for fila in filas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ver las licitaciones guardadas")
    parser.add_argument("--buscar", help="palabra en el objeto del contrato")
    parser.add_argument("--expediente", help="número de expediente")
    parser.add_argument("--informatica", action="store_true", help="solo CPV 72 o 48")
    parser.add_argument("--ganadas", action="store_true", help="solo las que ya tienen ganador")
    parser.add_argument("--limite", type=int, default=5)
    args = parser.parse_args()
    try:
        print(buscar(args.buscar, args.expediente, args.informatica, args.ganadas, args.limite))
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
