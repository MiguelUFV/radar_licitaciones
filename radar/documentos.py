"""Análisis de un pliego en PDF: cuánto hay que leer y dónde están los requisitos.

No usa modelo de lenguaje: aquí solo se cuenta y se localiza. Lo que decide el coste del
proyecto es cuántas páginas hay que mirar, no cuántas tiene el documento.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader

from radar.errores import DocumentoIlegible

REQUISITOS = {
    "volumen_negocios": r"volumen anual de negocios|cifra (?:anual )?de negocios",
    "trabajos_similares": r"anual acumulado|principales servicios|trabajos realizados de igual",
    "certificaciones": r"ISO\s?\d{4,5}|Esquema Nacional de Seguridad|EMAS|PCI[- ]?DSS",
    "clasificacion": r"clasificaci[oó]n empresarial|grupo\s+[A-Z]\s*,?\s*subgrupo",
    "habilitacion": r"habilitaci[oó]n empresarial|habilitaci[oó]n profesional",
    "adscripcion": r"adscribir a la ejecuci[oó]n|adscripci[oó]n de medios",
}
SECCION_SOLVENCIA = re.compile(
    r"solvencia econ[oó]mica|capacidad y solvencia|volumen anual de negocios", re.I
)
CIFRA = re.compile(r"\d[\d.\s]{2,}(?:,\d+)?\s*(?:€|euros)", re.I)
REMITE = re.compile(r"anexo\s+[IVX0-9]|anuncio de licitaci[oó]n|cuadro (?:de caracter|resumen)", re.I)
CASILLAS = re.compile(r"[☐☑☒█]")  # ☐ ☑ ☒


MINIMO_TEXTO = 50  # menos de esto en una página es una página sin capa de texto útil


def paginas_de(datos: bytes) -> list[tuple[int, str]]:
    """El texto de cada página, numeradas desde 1 como las ve una persona.

    La numeración importa: la cita que extrae el modelo se verifica contra el texto de **esa**
    página, y si aquí se empezara a contar en 0 la evidencia apuntaría a la página de al lado.
    """
    if not datos:
        raise DocumentoIlegible("El pliego está vacío.")
    if datos[:4] != b"%PDF":
        raise DocumentoIlegible("El fichero descargado no es un PDF.", detalle=repr(datos[:40]))
    try:
        lector = PdfReader(io.BytesIO(datos))
        paginas = [(n + 1, p.extract_text() or "") for n, p in enumerate(lector.pages)]
    except Exception as e:  # pypdf lanza muchas cosas distintas ante un fichero dañado
        raise DocumentoIlegible("El pliego no se ha podido leer (fichero dañado).", detalle=str(e)) from e
    if not paginas:
        raise DocumentoIlegible("El pliego no tiene páginas.")
    return paginas


def analizar(datos: bytes) -> dict:
    """Devuelve las medidas de un pliego. Lanza DocumentoIlegible si no es un PDF que se pueda abrir."""
    paginas = paginas_de(datos)

    con_texto = [n for n, t in paginas if len(t.strip()) > MINIMO_TEXTO]
    texto_completo = "\n".join(t for _, t in paginas)

    paginas_requisitos: dict[str, int] = {}
    for nombre, patron in REQUISITOS.items():
        for n, t in paginas:
            if re.search(patron, t, re.I):
                paginas_requisitos[nombre] = n
                break

    pagina_solvencia = next((n for n, t in paginas if SECCION_SOLVENCIA.search(t)), None)
    contexto = ""
    if pagina_solvencia:
        indices = range(pagina_solvencia - 1, min(pagina_solvencia + 2, len(paginas)))
        contexto = "\n".join(paginas[i][1] for i in indices)

    return {
        "paginas": len(paginas),
        "paginas_con_texto": len(con_texto),
        "escaneado": len(con_texto) < max(1, len(paginas) // 2),
        "caracteres": len(texto_completo),
        "pagina_solvencia": pagina_solvencia,
        "paginas_requisitos": paginas_requisitos,
        "requisitos_encontrados": sorted(paginas_requisitos),
        "cifra_junto_a_solvencia": bool(CIFRA.search(contexto)),
        "remite_a_anexo_o_anuncio": bool(REMITE.search(contexto)),
        "casillas_visibles": len(CASILLAS.findall(texto_completo)),
        "es_formulario": len(CASILLAS.findall(texto_completo)) > 10,
        "paginas_a_leer": len({p for p in paginas_requisitos.values()}) or (1 if pagina_solvencia else 0),
    }
