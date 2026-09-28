"""La ficha de una licitación: lo que el radar ha leído del pliego, para poder comprobarlo.

    uv run python -m radar.ficha --licitacion 65034 --empresa "Empresa A"

**Qué tiene que conseguir esta página.** Que alguien con veinte minutos decida si se presenta, y
que pueda desconfiar del radar: al lado de cada requisito está la frase literal del pliego y el
número de página donde está, para abrir el PDF y verlo. Si la ficha no se puede comprobar, no
sirve de nada.

De ahí sale el diseño, que no es decoración:

- **Dos voces, dos tipografías.** La cita del pliego va en serif y lo que dice el radar en sans.
  Sin leer nada se distingue lo que pone el documento oficial de lo que ha concluido una máquina.
- **La página, a la izquierda de una regla vertical.** Todo lo que hay a la derecha de la regla
  sale de esa página. Es la coordenada para ir al PDF.
- **El color marca la comprobación, no la decisión.** El número de página va en azul de sello
  cuando la cita se ha verificado letra a letra, y en óxido cuando no. La decisión (apta, no
  apta, revisar) es una frase, no un semáforo: «revisar» es el caso más común y un ámbar
  convertiría lo normal en una alarma.
"""

from __future__ import annotations

import argparse
import html
from datetime import date
from pathlib import Path

from radar.bd import conectar
from radar.errores import ErrorRadar

SALIDA = Path("data/privado/fichas")

# Dos familias y sus papeles: la serif es la voz del pliego, la sans la del radar.
TIPOGRAFIAS = (
    "https://fonts.googleapis.com/css2"
    "?family=IBM+Plex+Sans:wght@400;600"
    "&family=Source+Serif+4:opsz,wght@8..60,400"
    "&display=swap"
)

CONSULTA = """
SELECT f.veredicto, f.motivos, f.reglas_version, f.creada_en::date,
       l.expediente, l.objeto, l.organo, l.importe_sin_iva, l.plazo_presentacion, l.ficha_url,
       le.paginas, le.paginas_totales, le.via,
       (SELECT d.url FROM documentos d
        JOIN licitaciones s ON s.id = d.licitacion
        WHERE s.entry_id = l.entry_id AND d.tipo = 'PCAP' AND d.estado_descarga = 'descargado'
        ORDER BY d.id LIMIT 1) AS pliego_url
FROM fichas f
JOIN licitaciones l ON l.id = f.licitacion
LEFT JOIN lecturas le ON le.id = f.lectura
WHERE f.licitacion = %s AND f.alias = %s
ORDER BY f.creada_en DESC
LIMIT 1
"""

# Lo que se le dice a la empresa, no el nombre interno del estado.
VEREDICTOS = {
    "apta": "Puede presentarse",
    "no_apta": "No puede presentarse",
    "revisar": "Hay que revisarlo a mano",
}
RESULTADOS = {
    "cumple": "Cumple",
    "no_cumple": "No cumple",
    "no_se_puede_saber": "Por comprobar",
}


def datos(conexion, licitacion: int, alias: str) -> dict:
    with conexion.cursor() as cur:
        cur.execute(CONSULTA, (licitacion, alias))
        fila = cur.fetchone()
    if not fila:
        raise ErrorRadar(
            f"No hay ninguna ficha de esa licitación para {alias}. Se genera leyendo su pliego: "
            "uv run python -m radar.evaluacion.pliegos --gastar"
        )
    campos = (
        "veredicto",
        "motivos",
        "reglas",
        "fecha",
        "expediente",
        "objeto",
        "organo",
        "importe",
        "plazo",
        "ficha_url",
        "paginas",
        "paginas_totales",
        "via",
        "pliego_url",
    )
    return dict(zip(campos, fila, strict=True))


def euros(cantidad) -> str:
    return f"{float(cantidad):,.2f} €".replace(",", "@").replace(".", ",").replace("@", ".")


def en_una_linea(texto: str) -> str:
    """La cita, tal cual está en el pliego pero sin los saltos de línea del PDF.

    El texto extraído de un PDF parte las frases donde acaba el renglón. Se juntan los espacios
    para poder leerla; las palabras no se tocan, que es lo que se ha verificado.
    """
    return " ".join((texto or "").split())


def cuantos(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno}" if n == 1 else f"{n} {varios}"


def resumen_de(motivos: list[dict]) -> str:
    """Una frase que explique el veredicto contando lo que hay, sin adjetivos."""
    cuenta: dict[str, int] = {}
    for m in motivos:
        cuenta[m.get("resultado")] = cuenta.get(m.get("resultado"), 0) + 1
    total = sum(cuenta.values())
    if not total:
        return "No se ha podido leer ningún requisito del pliego."
    partes = []
    if cuenta.get("cumple"):
        partes.append(cuantos(cuenta["cumple"], "cumple", "cumplen"))
    if cuenta.get("no_cumple"):
        partes.append(cuantos(cuenta["no_cumple"], "no cumple", "no cumplen"))
    if cuenta.get("no_se_puede_saber"):
        partes.append(
            cuantos(
                cuenta["no_se_puede_saber"],
                "queda por comprobar a mano",
                "quedan por comprobar a mano",
            )
        )
    cabeza = cuantos(total, "requisito leído del pliego", "requisitos leídos del pliego")
    return f"De {cabeza}: {'; '.join(partes)}."


ESTILO = """
:root {
  --papel: #fcfbf8;
  --tinta: #1c1e22;
  --apunte: #5a6270;
  --regla: #d5d0c4;
  --sello: #1f3a6e;
  --oxido: #8c2f1f;
  --medida: 34rem;
}
:root:not([data-tema="claro"]) { color-scheme: light dark; }
@media (prefers-color-scheme: dark) {
  :root:not([data-tema="claro"]) {
    --papel: #16181c; --tinta: #e8e6e0; --apunte: #9aa1ad;
    --regla: #33373f; --sello: #8fb0e8; --oxido: #e0937f;
  }
}
:root[data-tema="oscuro"] {
  --papel: #16181c; --tinta: #e8e6e0; --apunte: #9aa1ad;
  --regla: #33373f; --sello: #8fb0e8; --oxido: #e0937f;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--papel); color: var(--tinta);
  font-family: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  font-size: 16px; line-height: 1.55;
  -webkit-text-size-adjust: 100%;
}
main { max-width: 46rem; margin: 0 auto; padding: 3.5rem 16px 5rem; }
.cabecera { display: flex; flex-wrap: wrap; gap: .5rem 1.5rem; color: var(--apunte); font-size: .8125rem; }
.cabecera b { font-weight: 600; color: var(--tinta); }
h1 {
  font-family: "Source Serif 4", Georgia, "Times New Roman", serif;
  font-weight: 400; font-size: clamp(1.5rem, 1.15rem + 1.6vw, 2.125rem);
  line-height: 1.22; letter-spacing: -.01em;
  margin: 1.25rem 0 .5rem; max-width: var(--medida);
}
.organo { color: var(--apunte); margin: 0 0 2.5rem; max-width: var(--medida); }
.decision { border-top: 1px solid var(--regla); border-bottom: 1px solid var(--regla); padding: 1.5rem 0; }
.decision p { margin: 0; }
.decision .que { font-size: 1.25rem; font-weight: 600; }
.decision .porque { color: var(--apunte); margin-top: .375rem; }
.requisitos { margin: 2.5rem 0 0; padding: 0; list-style: none; }
.requisito { display: grid; grid-template-columns: 5.5rem 1fr; gap: 0 1.5rem; padding: 1.75rem 0; }
.requisito + .requisito { border-top: 1px solid var(--regla); }
.pagina {
  font-variant-numeric: tabular-nums; font-size: .8125rem; color: var(--sello);
  padding-top: .45rem; white-space: nowrap;
}
.pagina.sin-verificar { color: var(--oxido); }
.cuerpo { border-left: 1px solid var(--regla); padding-left: 1.5rem; min-width: 0; }
blockquote {
  margin: 0; font-family: "Source Serif 4", Georgia, serif; font-size: 1.125rem;
  line-height: 1.5; max-width: var(--medida); hyphens: auto;
}
.conclusion { margin: .875rem 0 0; color: var(--apunte); font-size: .9375rem; max-width: var(--medida); }
.conclusion b { color: var(--tinta); font-weight: 600; }
.sin-cita { font-style: italic; color: var(--apunte); }
.pie { margin-top: 3rem; border-top: 1px solid var(--regla); padding-top: 1.5rem;
       color: var(--apunte); font-size: .8125rem; }
.pie p { margin: .375rem 0; max-width: var(--medida); }
.pie a { color: var(--sello); }
a:focus-visible, .pie a:focus-visible { outline: 2px solid var(--sello); outline-offset: 3px; }
@media (max-width: 34rem) {
  main { padding-top: 2rem; }
  .requisito { grid-template-columns: 1fr; gap: .5rem; }
  .cuerpo { border-left: 0; padding-left: 0; }
  .pagina { padding-top: 0; }
}
"""


def requisito_html(motivo: dict) -> str:
    cita = en_una_linea(motivo.get("cita") or "")
    pagina = motivo.get("pagina")
    verificada = bool(cita and pagina)
    etiqueta = f"pág. {pagina}" if verificada else "sin cita"
    clase = "pagina" if verificada else "pagina sin-verificar"
    cuerpo = (
        f"<blockquote>«{html.escape(cita)}»</blockquote>"
        if verificada
        else '<p class="sin-cita">El radar no ha podido citar esto del pliego.</p>'
    )
    return (
        '<li class="requisito">'
        f'<div class="{clase}">{etiqueta}</div>'
        f'<div class="cuerpo">{cuerpo}'
        f'<p class="conclusion"><b>{RESULTADOS.get(motivo.get("resultado"), "")}.</b> '
        f"{html.escape(motivo.get('texto') or '')}</p></div></li>"
    )


def titulo_corto(objeto: str | None, tope: int = 70) -> str:
    """El objeto para la pestaña del navegador, cortado por una palabra entera."""
    texto = en_una_linea(objeto or "Licitación")
    if len(texto) <= tope:
        return texto
    return texto[:tope].rsplit(" ", 1)[0] + "…"


def como_html(d: dict, alias: str) -> str:
    motivos = d["motivos"] or []
    paginas = d.get("paginas") or []
    leido = (
        f"Se han leído las páginas {', '.join(str(p) for p in paginas)} de "
        f"{d['paginas_totales']} que tiene el pliego."
        if paginas and d.get("paginas_totales")
        else "No se ha llegado a leer el pliego."
    )
    enlaces = []
    if d.get("pliego_url"):
        enlaces.append(f'<a href="{html.escape(d["pliego_url"])}">Abrir el pliego en PDF</a>')
    if d.get("ficha_url"):
        enlaces.append(f'<a href="{html.escape(d["ficha_url"])}">Ver el expediente en la Plataforma</a>')

    meta = [f"<span>Expediente <b>{html.escape(d['expediente'] or 'sin número')}</b></span>"]
    meta.append(f"<span>{html.escape(alias)}</span>")
    if d.get("importe"):
        meta.append(f"<span>{euros(d['importe'])}</span>")
    if d.get("plazo"):
        meta.append(f"<span>Plazo hasta {d['plazo']}</span>")

    return f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo_corto(d["objeto"]))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{TIPOGRAFIAS}" rel="stylesheet">
<style>{ESTILO}</style>
<main>
  <div class="cabecera">{"".join(meta)}</div>
  <h1>{html.escape(en_una_linea(d["objeto"] or "Sin objeto"))}</h1>
  <p class="organo">{html.escape(d["organo"] or "")}</p>

  <section class="decision">
    <p class="que">{VEREDICTOS.get(d["veredicto"], d["veredicto"])}</p>
    <p class="porque">{html.escape(resumen_de(motivos))}</p>
  </section>

  <ol class="requisitos">
    {"".join(requisito_html(m) for m in motivos)}
  </ol>

  <footer class="pie">
    <p>{leido}</p>
    <p>{" · ".join(enlaces) if enlaces else "No hay enlace al pliego original."}</p>
    <p>Decidido con las reglas {html.escape(d["reglas"])} el {d["fecha"]}. El radar lee el pliego y
       cita lo que dice; la decisión de presentarse es tuya.</p>
  </footer>
</main>
</html>
"""


def generar(licitacion: int, alias: str, destino: Path | None = None) -> Path:
    with conectar() as conexion:
        d = datos(conexion, licitacion, alias)
    carpeta = destino or SALIDA
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{date.today().isoformat()}_{licitacion}_{alias.replace(' ', '_').lower()}.html"
    fichero = carpeta / nombre
    fichero.write_text(como_html(d, alias), encoding="utf-8")
    return fichero


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera la ficha HTML de una licitación")
    parser.add_argument("--licitacion", type=int, required=True)
    parser.add_argument("--empresa", required=True, help='alias, por ejemplo "Empresa A"')
    parser.add_argument("--salida", type=Path, default=None)
    args = parser.parse_args()
    try:
        fichero = generar(args.licitacion, args.empresa, args.salida)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print(f"\nFicha: {fichero.as_posix()}")
    # La carpeta del proyecto tiene espacios y el navegador parte la ruta por el primero: se
    # queda intentando resolver «code» como si fuera una web (DNS_PROBE_FINISHED_NXDOMAIN).
    # Con la ruta escapada se abre bien, y ya la damos escapada.
    print(f"Para verla:  {fichero.resolve().as_uri()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
