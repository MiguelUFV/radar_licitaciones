"""El formulario de alta: lo que una empresa rellena para que el radar la conozca.

Se sirve en `GET /alta` y se guarda con `POST /alta`. Escucha solo en el ordenador, como todo
lo demás del radar (`docs/SPEC.md` §9): esto no es todavía una página para que la rellene un
cliente desde su oficina, es la herramienta con la que se le da de alta.

**Por qué el formulario está escrito así.** La Fase 5 midió que el techo del radar es lo poco
que sabe de la empresa, y que los contratos que se le escapan son los productos que el perfil no
menciona. Un cuadro de texto libre no arregla eso, porque nadie escribe de sí mismo lo que no
cree importante. Por eso cada pregunta va suelta, con un ejemplo real al lado, y las tres que
más cambian el resultado —las marcas, lo que hace de paso y lo que no hace— llevan escrito por
qué se preguntan.
"""

from __future__ import annotations

import html

from radar.clientes import CAMPOS

ESTILO = """
:root {
  --papel: #fcfbf8; --tinta: #1c1e22; --apunte: #5a6270; --regla: #d5d0c4;
  --sello: #1f3a6e; --oxido: #8c2f1f; --medida: 34rem;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-tema="claro"]) {
    --papel: #16181c; --tinta: #e8e6e0; --apunte: #9aa1ad;
    --regla: #33373f; --sello: #8fb0e8; --oxido: #e0937f;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--papel); color: var(--tinta);
  font-family: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  font-size: 16px; line-height: 1.55;
}
main { max-width: 44rem; margin: 0 auto; padding: 3.5rem 16px 6rem; }
h1 {
  font-family: "Source Serif 4", Georgia, serif; font-weight: 400;
  font-size: clamp(1.6rem, 1.2rem + 1.8vw, 2.25rem); line-height: 1.2;
  margin: 0 0 .75rem; letter-spacing: -.01em;
}
.entrada { color: var(--apunte); max-width: var(--medida); margin: 0 0 3rem; }
.campo { padding: 1.75rem 0; border-top: 1px solid var(--regla); }
label { display: block; font-weight: 600; margin-bottom: .25rem; }
.ayuda { color: var(--apunte); font-size: .9375rem; margin: 0 0 .75rem; max-width: var(--medida); }
input, textarea {
  width: 100%; max-width: var(--medida); background: transparent; color: var(--tinta);
  border: 1px solid var(--regla); border-radius: 2px; padding: .625rem .75rem;
  font: inherit; font-size: 1rem;
}
textarea { min-height: 5.5rem; resize: vertical; line-height: 1.5; }
input:focus, textarea:focus {
  outline: 2px solid var(--sello); outline-offset: 1px; border-color: transparent;
}
.ejemplo {
  font-family: "Source Serif 4", Georgia, serif; color: var(--apunte);
  font-size: .9375rem; margin: .5rem 0 0; max-width: var(--medida);
}
.error { color: var(--oxido); font-size: .9375rem; margin: .5rem 0 0; }
.error-campo { border-color: var(--oxido); }
.obligatorio { color: var(--apunte); font-weight: 400; }
button {
  margin-top: 2.5rem; background: var(--tinta); color: var(--papel); border: 0;
  border-radius: 2px; padding: .75rem 1.5rem; font: inherit; font-weight: 600; cursor: pointer;
}
button:focus-visible { outline: 2px solid var(--sello); outline-offset: 3px; }
.aviso { border-left: 2px solid var(--sello); padding: .25rem 0 .25rem 1.25rem; margin: 0 0 2.5rem;
         max-width: var(--medida); }
.hecho { border-top: 1px solid var(--regla); padding-top: 2rem; }
pre { background: rgba(127,127,127,.08); padding: 1rem; border-radius: 2px; overflow-x: auto;
      font-size: .875rem; line-height: 1.5; white-space: pre-wrap; max-width: var(--medida); }
a { color: var(--sello); }
"""

TIPOGRAFIAS = (
    "https://fonts.googleapis.com/css2"
    "?family=IBM+Plex+Sans:wght@400;600"
    "&family=Source+Serif+4:opsz,wght@8..60,400"
    "&display=swap"
)


def envoltorio(titulo: str, cuerpo: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{TIPOGRAFIAS}" rel="stylesheet">
<style>{ESTILO}</style>
<main>{cuerpo}</main>
</html>
"""


def campo_html(campo, valor: str, error: str | None) -> str:
    clase = "error-campo" if error else ""
    etiqueta = html.escape(campo.etiqueta)
    if not campo.obligatorio:
        etiqueta += ' <span class="obligatorio">(opcional)</span>'
    control = (
        f'<textarea id="{campo.nombre}" name="{campo.nombre}" class="{clase}" '
        f'rows="4">{html.escape(valor)}</textarea>'
        if campo.largo
        else f'<input id="{campo.nombre}" name="{campo.nombre}" class="{clase}" value="{html.escape(valor)}">'
    )
    ejemplo = f'<p class="ejemplo">Por ejemplo: {html.escape(campo.ejemplo)}</p>' if campo.ejemplo else ""
    aviso = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return f"""
  <div class="campo">
    <label for="{campo.nombre}">{etiqueta}</label>
    <p class="ayuda">{html.escape(campo.ayuda)}</p>
    {control}{aviso}{ejemplo}
  </div>"""


def formulario(valores: dict | None = None, errores: dict | None = None) -> str:
    valores, errores = valores or {}, errores or {}
    campos = "".join(
        campo_html(c, str(valores.get(c.nombre, "") or ""), errores.get(c.nombre)) for c in CAMPOS
    )
    resumen = (
        f'<p class="error">Hay {len(errores)} campo(s) por corregir, marcados más abajo.</p>'
        if errores
        else ""
    )
    return envoltorio(
        "Dar de alta una empresa en el radar",
        f"""
  <h1>Qué tiene que saber el radar de su empresa</h1>
  <p class="entrada">Con esto el radar mira cada día las licitaciones que se publican y le avisa
     de las que encajan, con la frase del pliego y la página que lo dice.</p>
  <div class="aviso">
    <p>Lo que más cambia el resultado no es lo que su empresa destaca en su web, sino
       <strong>las marcas que distribuye</strong> y <strong>lo que hace de paso</strong>. Está
       medido: de veinte contratos que el radar dejó escapar en la prueba, diecinueve eran
       productos que el perfil de la empresa no nombraba.</p>
  </div>
  {resumen}
  <form method="post" action="/alta">{campos}
    <button type="submit">Dar de alta</button>
  </form>""",
    )


def guardado(resultado: dict) -> str:
    que = "dada de alta" if resultado["nuevo"] else "actualizada"
    return envoltorio(
        f"{resultado['alias']}, {que}",
        f"""
  <h1>{html.escape(resultado["alias"])}, {que}</h1>
  <p class="entrada">A partir de mañana entra en el aviso diario. Esto es exactamente lo que el
     radar va a leer de su empresa cada vez que mire una licitación:</p>
  <div class="hecho">
    <pre>{html.escape(resultado["texto"])}</pre>
    <p class="ayuda">Si falta algo, vuelva al <a href="/alta">formulario</a> y guárdelo otra vez
       con el mismo nombre: se actualiza, no se duplica.</p>
  </div>""",
    )
