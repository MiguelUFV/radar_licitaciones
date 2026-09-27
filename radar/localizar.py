"""Qué páginas del pliego hay que leer. Sin modelo: esto es búsqueda de texto.

Es el nodo que decide el coste. Un PCAP tiene entre 13 y 112 páginas (medido en la Fase 1) y
los requisitos de solvencia viven en dos o tres. Mandar el pliego entero al modelo costaría
diez veces más y además lo despistaría.

**Cómo se eligen las páginas: se busca el ancla y se lee hacia delante.** Se puntúa cada
página, se toma la de más puntos y se leen esa y las siguientes hasta `TOPE_PAGINAS`. Es lo
que hace una persona: encuentra «Solvencia económica y financiera» y sigue leyendo. Y es
contiguo a propósito, porque la tabla de requisitos se parte entre dos páginas.

Dos versiones anteriores estaban mal, y las dos se vieron con pliegos de verdad:

1. «Las seis primeras páginas que coincidan»: en un pliego de 112 páginas el patrón de
   certificaciones (ISO) aparece en el índice y en 20 páginas del apartado técnico, así que se
   llevaba las páginas 1 a 7 y **la solvencia estaba en la 54**.
2. «El tramo de seis con más puntos en total»: seis páginas mediocres seguidas suman más que
   la sección de solvencia de dos páginas.

Medido sobre los 36 pliegos descargados, las dos reglas y esta aciertan lo mismo (14 de los 15
pliegos donde se puede comprobar), pero el ancla manda **141 páginas en lugar de 182**. Leer
solo 4 hacia delante acertaba también lo mismo y bajaba a 103; no se hace porque el criterio
solo se puede comprobar en 15 de los 36 pliegos y no se recorta contexto para ahorrar sobre una
medición que no cubre el caso. Queda anotado como palanca de coste para la Fase 5.

Tres caminos, los tres del grafo de `docs/SPEC.md` §4:

- **solvencia**: hay una sección de solvencia reconocible. Se lee su ventana.
- **anexos**: no hay sección de solvencia, pero sí un cuadro resumen o un anexo donde suele
  estar. Se lee esa ventana.
- **no_localizada**: ninguna de las dos, o el pliego es un escaneado sin texto. No se llama al
  modelo y el expediente va a una persona con el motivo escrito. Nunca se supone que no hay
  requisitos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from radar import documentos

# Tope de páginas que se mandan al modelo. La Fase 1 midió que los requisitos caben en 3
# (mediana) y 6 (p90); con más, el coste por pliego se dispara sin encontrar nada nuevo.
TOPE_PAGINAS = 6

# Lo que de verdad es solvencia: si esto aparece, la página vale mucho.
NUCLEO = ("volumen_negocios", "trabajos_similares", "clasificacion")
PUNTOS = {"seccion": 3, "nucleo": 2, "otro": 1, "cifra": 1, "indice": -3}
# Un índice se reconoce por las líneas de puntos que llevan al número de página.
INDICE = re.compile(r"\.{5,}")
MINIMO_INDICE = 3
# Dónde se esconde la solvencia cuando el pliego no la trae en su sitio.
ANEXOS = re.compile(
    r"cuadro (?:de caracter[ií]sticas|resumen)|anexo\s+[IVX0-9]+|"
    r"requisitos de (?:capacidad|participaci[oó]n|solvencia)",
    re.I,
)


@dataclass
class Localizacion:
    via: str  # solvencia · anexos · no_localizada
    paginas: list[tuple[int, str]] = field(default_factory=list)
    motivo: str = ""
    # Qué tipo de requisito se ha visto y en qué página, para explicar la decisión sin abrir
    # el PDF y para saber después si la ventana elegida contenía lo que importaba.
    pistas: dict[str, int] = field(default_factory=dict)

    @property
    def hay_que_leer(self) -> bool:
        return bool(self.paginas)

    def numeros(self) -> list[int]:
        return [n for n, _ in self.paginas]


def con_texto(paginas: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [(n, t) for n, t in paginas if len(t.strip()) > documentos.MINIMO_TEXTO]


def pistas_de(paginas: list[tuple[int, str]]) -> dict[str, int]:
    """Primera página donde aparece cada tipo de requisito."""
    encontradas = {}
    for nombre, patron in documentos.REQUISITOS.items():
        for n, texto in paginas:
            if re.search(patron, texto, re.I):
                encontradas[nombre] = n
                break
    return encontradas


def puntuar(texto: str) -> int:
    """Cuánto promete una página. Nunca baja de 0: un índice no resta al tramo entero."""
    puntos = 0
    if documentos.SECCION_SOLVENCIA.search(texto):
        puntos += PUNTOS["seccion"]
    for nombre, patron in documentos.REQUISITOS.items():
        if re.search(patron, texto, re.I):
            puntos += PUNTOS["nucleo"] if nombre in NUCLEO else PUNTOS["otro"]
    if documentos.CIFRA.search(texto):
        puntos += PUNTOS["cifra"]
    if len(INDICE.findall(texto)) >= MINIMO_INDICE:
        puntos += PUNTOS["indice"]
    return max(puntos, 0)


def ventana(puntuaciones: list[tuple[int, int]], tope: int = TOPE_PAGINAS) -> list[int]:
    """La página con más puntos y las siguientes, hasta `tope`. Sin ceros al final.

    `puntuaciones` son pares (página, puntos) en orden. Si dos páginas empatan gana la primera,
    así el resultado no depende del orden en que se recorra. Si ninguna puntúa, no hay ventana.
    """
    if not puntuaciones:
        return []
    ancla = max(puntuaciones, key=lambda par: (par[1], -par[0]))
    if ancla[1] == 0:
        return []
    desde = [n for n, _ in puntuaciones].index(ancla[0])
    tramo = puntuaciones[desde : desde + tope]
    # Las páginas del final que no aportan nada se tiran: ahorran tokens y no aportan contexto.
    while tramo and tramo[-1][1] == 0:
        tramo = tramo[:-1]
    return [n for n, _ in tramo]


def localizar(datos: bytes) -> Localizacion:
    paginas = documentos.paginas_de(datos)
    legibles = con_texto(paginas)
    if not legibles:
        # Rama OCR del grafo: el pliego es una imagen. Se decidió mandar esas páginas como
        # imagen (D21), y todavía no está hecho. Aquí se dice; no se adivina.
        return Localizacion(
            via="no_localizada",
            motivo=(
                "El pliego no tiene texto: es un documento escaneado. Hay que leerlo a mano o "
                "mandar sus páginas como imagen, que todavía no está hecho."
            ),
        )

    pistas = pistas_de(legibles)
    elegidas = ventana([(n, puntuar(t)) for n, t in legibles])
    if elegidas:
        return Localizacion(
            via="solvencia",
            paginas=[(n, t) for n, t in legibles if n in set(elegidas)],
            pistas=pistas,
        )

    anexos = ventana([(n, int(bool(ANEXOS.search(t)))) for n, t in legibles])
    if anexos:
        return Localizacion(
            via="anexos",
            paginas=[(n, t) for n, t in legibles if n in set(anexos)],
            motivo="No hay una sección de solvencia como tal; se leen el cuadro resumen y los anexos.",
            pistas=pistas,
        )

    return Localizacion(
        via="no_localizada",
        motivo=(
            "En este pliego no se encuentra la sección de solvencia ni un cuadro resumen donde "
            "suela estar. Hay que mirarlo a mano: puede que los requisitos estén en otro "
            "documento del expediente."
        ),
        pistas=pistas,
    )


# A qué anexo remite un pliego cuando no dice los requisitos en su sitio: "Anexo Nº 1",
# "ANEXO I", "anexo nº. 1". El número o el romano es lo que hay que buscar después.
REFERENCIA = re.compile(r"anexo\s*n?[ºo°.]{0,3}\s*([IVXLC]+|\d{1,2})\b", re.I)


def anexo_citado(textos: list[str]) -> str | None:
    """El anexo al que remiten las citas, si todas señalan al mismo o hay uno claro."""
    vistos: list[str] = []
    for texto in textos:
        vistos += [m.group(1).upper() for m in REFERENCIA.finditer(texto or "")]
    if not vistos:
        return None
    return max(set(vistos), key=vistos.count)


def localizar_anexo(datos: bytes, anexo: str, ya_leidas: set[int]) -> Localizacion:
    """El anexo al que remite el pliego, buscado como encabezado y no como mención.

    Un pliego nombra «Anexo Nº 1» en la cláusula que remite y otra vez donde empieza el anexo.
    Lo que interesa es lo segundo, y distinguirlos cuesta **dinero**: la primera versión se
    llevaba la otra mención de la misma cláusula, pagaba una segunda llamada al modelo y
    devolvía los mismos requisitos genéricos. Comprobado con un pliego real de 86 páginas:
    0,06 € por nada.

    Por eso una página solo cuenta como anexo si, además de nombrarlo, **trae una cifra en
    euros**. Un anexo de solvencia sin ninguna cifra no es el que se busca; y si no hay ninguna
    página así, el anexo va en otro fichero del expediente, y eso se dice en lugar de gastar.
    """
    paginas = con_texto(documentos.paginas_de(datos))
    patron = re.compile(rf"anexo\s*n?[ºo°.]{{0,3}}\s*{re.escape(anexo)}\b", re.I)
    candidatas = [
        (
            n,
            puntuar(t) + PUNTOS["seccion"]
            if patron.search(t) and documentos.CIFRA.search(t)
            else 0,
        )
        for n, t in paginas
        if n not in ya_leidas
    ]
    elegidas = ventana(candidatas)
    if not elegidas:
        return Localizacion(
            via="no_localizada",
            motivo=(
                f"El pliego remite al anexo {anexo} para decir los requisitos, y ese anexo no "
                "está en este documento: irá en otro fichero del expediente. Hay que abrirlo "
                "a mano."
            ),
        )
    return Localizacion(
        via="anexos",
        paginas=[(n, t) for n, t in paginas if n in set(elegidas)],
        motivo=f"Los requisitos no estaban en la cláusula: el pliego remite al anexo {anexo}.",
        pistas=pistas_de(paginas),
    )


def como_se_manda(localizacion: Localizacion) -> str:
    """El texto que ve el modelo, con la página marcada delante de cada trozo.

    La marca es lo que permite exigirle la página en la respuesta y comprobarla después.
    """
    return "\n\n".join(f"=== Página {n} ===\n{texto.strip()}" for n, texto in localizacion.paginas)
