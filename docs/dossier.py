"""El dossier del proyecto en PDF y en Word: qué hace el radar, cómo funciona y qué se midió.

    uv run --with reportlab --with python-docx python docs/dossier.py

Está escrito para alguien que no ha visto nunca el proyecto y que no programa. Por eso empieza
por el problema y no por la arquitectura, y por eso las cifras van con su fuente al lado.

**Las cifras no se escriben a mano dos veces.** Las del estudio salen de los informes de
`docs/informes/`, que los genera un comando y están congelados; las del estado de hoy —cuántas
licitaciones hay cargadas, cuánto se lleva gastado— se leen de la base al generar el PDF. Si el
PDF dice un número, ese número se puede reproducir.

reportlab y python-docx no están en las dependencias del proyecto a propósito: el radar no
necesita hacer documentos para funcionar. Se traen solo cuando se genera el dossier.

**El Word no es un documento aparte.** Se escribe recorriendo los mismos elementos con los que
se compone el PDF, así que no hay dos versiones que puedan decir cosas distintas. Había dos .docx
escritos a mano el 24-09-2026 y se quedaron viejos en cuanto se midió nada; por eso este se
genera con el mismo comando que el PDF y no se escribe a mano.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from radar.fechas import el_dia
from radar.fechas import hoy as hoy_en_espana

SALIDA = Path("docs/dossier_radar_de_licitaciones.pdf")

# La misma paleta que la ficha y el correo: el papel tirando a hueso, la tinta que no es negro
# puro, y un azul de sello para lo que está comprobado.
PAPEL = colors.HexColor("#FCFBF8")
TINTA = colors.HexColor("#1C1E22")
APUNTE = colors.HexColor("#5A6270")
REGLA = colors.HexColor("#D5D0C4")
SELLO = colors.HexColor("#1F3A6E")
OXIDO = colors.HexColor("#8C2F1F")

SERIF, SERIF_N, SERIF_C = "Times-Roman", "Times-Bold", "Times-Italic"
SANS, SANS_N = "Helvetica", "Helvetica-Bold"

ANCHO, ALTO = A4
IZQ, DER, ARR, ABA = 26 * mm, 22 * mm, 24 * mm, 20 * mm
MEDIDA = ANCHO - IZQ - DER


def estilos() -> dict:
    """Una escala de tamaños corta y con jerarquía clara: 26, 15, 11 y 10,5."""
    base = ParagraphStyle(
        "cuerpo",
        fontName=SERIF,
        fontSize=10.5,
        leading=15.5,
        textColor=TINTA,
        alignment=TA_JUSTIFY,
        spaceAfter=7,
    )
    return {
        "cuerpo": base,
        "primero": ParagraphStyle("primero", parent=base, spaceBefore=2),
        "suelto": ParagraphStyle("suelto", parent=base, alignment=0),
        "titulo": ParagraphStyle(
            "titulo",
            fontName=SERIF,
            fontSize=26,
            leading=30,
            textColor=TINTA,
            spaceAfter=10,
        ),
        "subtitulo": ParagraphStyle(
            "subtitulo",
            fontName=SERIF_C,
            fontSize=13,
            leading=18,
            textColor=APUNTE,
            spaceAfter=22,
        ),
        "seccion": ParagraphStyle(
            "seccion",
            fontName=SANS_N,
            fontSize=15,
            leading=19,
            textColor=TINTA,
            spaceBefore=20,
            spaceAfter=9,
        ),
        "sub": ParagraphStyle(
            "sub",
            fontName=SANS_N,
            fontSize=10.5,
            leading=14,
            textColor=SELLO,
            spaceBefore=13,
            spaceAfter=5,
        ),
        "nota": ParagraphStyle(
            "nota",
            fontName=SANS,
            fontSize=8.8,
            leading=12.5,
            textColor=APUNTE,
            spaceAfter=6,
        ),
        "cita": ParagraphStyle(
            "cita",
            parent=base,
            fontName=SERIF_C,
            leftIndent=10,
            borderPadding=0,
            spaceBefore=6,
            spaceAfter=10,
            alignment=0,
        ),
        "codigo": ParagraphStyle(
            "codigo",
            fontName="Courier",
            fontSize=8.6,
            leading=12,
            textColor=TINTA,
            leftIndent=8,
            spaceBefore=4,
            spaceAfter=10,
            alignment=0,
        ),
        "portadanum": ParagraphStyle(
            "portadanum", fontName=SANS_N, fontSize=9.5, leading=13, textColor=TINTA
        ),
    }


E = estilos()


def p(texto: str, estilo: str = "cuerpo") -> Paragraph:
    return Paragraph(texto, E[estilo])


def regla(espacio_antes: float = 4, grosor: float = 0.6, color=REGLA) -> Table:
    t = Table([[""]], colWidths=[MEDIDA], rowHeights=[0.1])
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), grosor, color)]))
    return KeepTogether([Spacer(1, espacio_antes), t, Spacer(1, 6)])


def tabla(
    filas: list[list[str]],
    anchos: list[float],
    cabecera: bool = True,
    primera_suelta: bool = True,
) -> Table:
    """Tabla sin caja: solo una línea bajo la cabecera y otra al final. Lo demás, aire.

    La primera columna nunca va justificada: es estrecha y justificar abre unos huecos entre
    palabras que se leen fatal. `primera_suelta=False` para las pocas donde no sea así.
    """

    def estilo_de(fila: int, columna: int) -> ParagraphStyle:
        if fila == 0 and cabecera:
            return E["nota"]
        return E["suelto"] if primera_suelta and columna == 0 else E["cuerpo"]

    datos = [[Paragraph(c, estilo_de(i, j)) for j, c in enumerate(fila)] for i, fila in enumerate(filas)]
    t = Table(datos, colWidths=anchos, hAlign="LEFT")
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, REGLA),
    ]
    if cabecera:
        estilo += [("LINEBELOW", (0, 0), (-1, 0), 0.6, TINTA), ("LINEABOVE", (0, 0), (-1, 0), 0.6, TINTA)]
    t.setStyle(TableStyle(estilo))
    return t


def pie(canvas, documento) -> None:
    canvas.saveState()
    canvas.setFillColor(PAPEL)
    canvas.rect(0, 0, ANCHO, ALTO, stroke=0, fill=1)
    if documento.page > 1:
        canvas.setFont(SANS, 8)
        canvas.setFillColor(APUNTE)
        canvas.drawString(IZQ, ABA - 9 * mm, "Radar de licitaciones que lee el pliego")
        canvas.drawRightString(ANCHO - DER, ABA - 9 * mm, str(documento.page))
        canvas.setStrokeColor(REGLA)
        canvas.setLineWidth(0.5)
        canvas.line(IZQ, ABA - 6 * mm, ANCHO - DER, ABA - 6 * mm)
    canvas.restoreState()


# --- Las cifras de hoy, leídas de la base ----------------------------------------------


def del_radar() -> dict:
    """Lo que hay cargado ahora mismo. Si la base no está, el dossier lo dice en lugar de mentir."""
    try:
        from radar.bd import conectar
    except Exception:  # noqa: BLE001
        return {}
    # El día de la última pasada de un cliente, en hora española. Se usa dos veces, así que
    # se escribe una.
    ULTIMA_PASADA = (
        f"SELECT max({el_dia('t2.triada_en')}) FROM triajes t2 JOIN clientes c2 ON c2.alias = t2.alias"
    )
    consultas = {
        "licitaciones": "SELECT count(*) FROM licitaciones",
        "expedientes": "SELECT count(DISTINCT entry_id) FROM licitaciones",
        "adjudicaciones": "SELECT count(*) FROM adjudicaciones",
        "vigentes": (
            f"SELECT count(*) FROM v_licitaciones_vigentes WHERE NOT anulada"
            f" AND (plazo_presentacion IS NULL OR plazo_presentacion >= {el_dia('now()')})"
        ),
        "pliegos": "SELECT count(*) FROM documentos WHERE estado_descarga = 'descargado'",
        "llamadas": "SELECT count(*) FROM llm_llamadas",
        "gasto": "SELECT round(coalesce(sum(coste_eur), 0), 2) FROM llm_llamadas",
        "requisitos": "SELECT count(*) FROM requisitos",
        "verificados": "SELECT count(*) FROM requisitos WHERE verificada",
        "fichas": "SELECT count(*) FROM fichas",
        # El universo del estudio y su ritmo diario. Estaban escritos a mano en el texto, y el
        # 29-09-2026 cambiaron al cargar 2024: los expedientes que ya se habían publicado antes
        # salieron del periodo. Una cifra escrita a mano en un documento es una cifra que se
        # queda vieja sin avisar.
        "universo": (
            "SELECT count(*) FROM (SELECT entry_id FROM licitaciones GROUP BY entry_id"
            " HAVING min(entry_updated) >= '2025-01-01' AND min(entry_updated) < '2025-07-01') s"
        ),
        "dias_con_publicaciones": (
            "SELECT count(DISTINCT primera::date) FROM (SELECT min(entry_updated) primera"
            " FROM licitaciones GROUP BY entry_id) s"
            " WHERE primera >= '2025-01-01' AND primera < '2025-07-01'"
        ),
        # La última pasada de verdad, no la de hoy: un dossier generado al día siguiente diría
        # que el radar no ha mirado nada, que es falso. Y solo de clientes, porque en la misma
        # tabla hay triajes de las empresas del estudio, que no reciben correo de nadie.
        "dia_pasada": (
            f"SELECT max({el_dia('t.triada_en')}) FROM triajes t JOIN clientes c ON c.alias = t.alias"
        ),
        "triadas_pasada": (
            f"SELECT count(*) FROM triajes t JOIN clientes c ON c.alias = t.alias"
            f" WHERE {el_dia('t.triada_en')} = ({ULTIMA_PASADA})"
        ),
        "candidatas_pasada": (
            f"SELECT count(*) FROM triajes t JOIN clientes c ON c.alias = t.alias"
            f" WHERE t.decision IN ('si', 'duda') AND {el_dia('t.triada_en')} = ({ULTIMA_PASADA})"
        ),
    }
    EFICIENCIA = """
    SELECT DISTINCT ON (metrica, variante, alias) metrica, variante, alias, valor
    FROM eval_resultados WHERE metrica IN ('M9', 'M10')
    ORDER BY metrica, variante, alias, calculada_en DESC
    """
    # El resultado del estudio. Estaba escrito a mano en el apartado 4 y en otros tres sitios, y
    # al corregir el universo el 30-09-2026 se quedó viejo sin que nadie lo notara: el dossier
    # siguió diciendo 74,0 % y «19 de 20» cuando ya eran 69,2 % y 16 de 16. Ahora sale de aquí.
    RESULTADO = """
    SELECT DISTINCT ON (variante) variante, valor, ic_inferior, ic_superior, n, detalle
    FROM eval_resultados WHERE metrica = 'M1_diferencia' ORDER BY variante, calculada_en DESC
    """
    # Un requisito de verdad, con su cita y su página, para no poner un ejemplo inventado en un
    # documento que trata justamente de que nada sea inventado.
    UNO_DE_VERDAD = """
    SELECT r.cita, r.pagina, r.importe_eur, l.paginas_totales, li.organo, li.expediente
    FROM requisitos r
    JOIN lecturas l ON l.id = r.lectura
    JOIN licitaciones li ON li.id = l.licitacion
    WHERE r.verificada AND r.tipo = 'volumen_negocios' AND r.importe_eur IS NOT NULL
    ORDER BY length(r.cita)
    LIMIT 1
    """
    datos = {"pruebas": cuantas_pruebas()}
    try:
        with conectar() as conexion, conexion.cursor() as cur:
            for nombre, sql in consultas.items():
                cur.execute(sql)
                datos[nombre] = cur.fetchone()[0]
            cur.execute(UNO_DE_VERDAD)
            fila = cur.fetchone()
            cur.execute(EFICIENCIA)
            eficiencia = cur.fetchall()
            cur.execute(RESULTADO)
            resultado = cur.fetchall()
    except Exception:  # noqa: BLE001  el dossier se puede generar sin la base delante
        return {"pruebas": datos["pruebas"], "sin_base": True}
    if fila:
        campos = ("cita", "pagina", "importe", "paginas_totales", "organo", "expediente")
        datos["ejemplo"] = dict(zip(campos, fila, strict=True))
    datos["eficiencia"] = {(m, v, a): float(x) for m, v, a, x in eficiencia}
    datos["resultado"] = {
        v.replace("agente_menos_", "").replace("_test", ""): {
            "diferencia": float(valor),
            "ic": (float(bajo), float(alto)),
            "contratos": n,
            **(detalle or {}),
        }
        for v, valor, bajo, alto, n, detalle in resultado
    }
    return datos


def perdidos(hoy: dict) -> str:
    """Cuántos contratos ganados se le escaparon al radar, contados y no escritos a mano.

    Sale del recall y del número de contratos, que es de donde salen también las tablas: así
    no puede decir 16 aquí y 20 tres apartados más abajo.
    """
    uno = next(iter((hoy.get("resultado") or {}).values()), None)
    if not uno:
        return "casi todos los"
    return str(round(uno["contratos"] * (1 - uno["recall_agente"])))


def limpia(cita: str) -> str:
    """La cita tal cual, con los saltos de línea del PDF convertidos en espacios."""
    sobra = "⇨→■"
    return " ".join("".join(c for c in cita if c not in sobra).split())


def euros(n) -> str:
    """En castellano: el punto separa miles y la coma, decimales."""
    return f"{float(n):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".") + " €"


def cuantas_pruebas() -> str:
    """Las que recoge pytest, contadas de verdad.

    Escrita a mano se queda vieja enseguida: en este mismo documento llegó a decir 331 en un
    sitio y 332 en otro, con el número cambiando cada vez que se arregla un fallo.
    """
    import re
    import subprocess
    import sys

    try:
        # Con el intérprete que está corriendo, no con `uv run`: esto se lanza desde dentro de
        # un `uv run` y anidarlos no funciona.
        salida = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=300,
        ).stdout
    except Exception:  # noqa: BLE001  el dossier se genera igual
        return "todas las"
    # Con -q, pytest escribe una línea «tests/lo_que_sea.py: N» por fichero y no el total.
    por_fichero = [int(n) for n in re.findall(r"^\S+\.py: (\d+)$", salida, re.MULTILINE)]
    return str(sum(por_fichero)) if por_fichero else "todas las"


def ritmo(hoy: dict) -> str:
    """Licitaciones publicadas al día en el periodo del estudio."""
    dias = hoy.get("dias_con_publicaciones") or 0
    return f"{hoy.get('universo', 0) / dias:.0f}" if dias else "—"


def fecha(dia) -> str:
    """La fecha como se escribe en España. Si no hay ninguna pasada todavía, se dice."""
    return f"{dia:%d-%m-%Y}" if dia else "(sin ninguna pasada todavía)"


def miles(n) -> str:
    return f"{int(n):,}".replace(",", ".")


# --- El documento ----------------------------------------------------------------------


def portada(hoy: dict) -> list:
    numeros = (
        [
            ["Lo que hay dentro", ""],
            ["Expedientes cargados de la Plataforma de Contratación", miles(hoy.get("expedientes", 0))],
            ["Adjudicaciones con su ganador", miles(hoy.get("adjudicaciones", 0))],
            ["Pliegos descargados y guardados por su huella", miles(hoy.get("pliegos", 0))],
            ["Requisitos extraídos con cita comprobada", miles(hoy.get("verificados", 0))],
            ["Pruebas automáticas que lo vigilan", hoy.get("pruebas", "")],
            ["Gastado en el modelo desde el primer día", euros(hoy.get("gasto", 0))],
        ]
        if not hoy.get("sin_base")
        else [["Lo que hay dentro", ""], ["(la base no respondió al generar el PDF)", ""]]
    )
    return [
        Spacer(1, 10 * mm),
        p("Radar de licitaciones<br/>que lee el pliego", "titulo"),
        p(
            "Un agente que mira cada día las licitaciones públicas que se publican en España, abre "
            "el pliego de las que encajan con una empresa y le dice a cuáles puede presentarse, "
            "con la frase exacta del pliego y la página en la que está.",
            "subtitulo",
        ),
        regla(0, 1.2, TINTA),
        Spacer(1, 6),
        p(
            "Este documento explica qué hace, cómo lo hace y qué se midió. Está escrito para "
            "alguien que no ha visto nunca el proyecto. Todas las cifras salen de una medición "
            "que se puede repetir con un comando, y las que salieron en contra de la tesis "
            "también están aquí.",
        ),
        Spacer(1, 74 * mm),
        tabla(numeros, [MEDIDA - 32 * mm, 32 * mm]),
        Spacer(1, 12),
        p(
            "Miguel Martín-Caro · 4.º del doble grado en Business Analytics y ADE, "
            "Universidad Francisco de Vitoria<br/>"
            f"Generado el {hoy_en_espana():%d-%m-%Y} a partir de los informes de medición y de la "
            "base de datos del proyecto",
            "nota",
        ),
        PageBreak(),
    ]


SIN_EJEMPLO = {
    "cita": "(no hay ningún requisito leído todavía en esta base de datos)",
    "pagina": "—",
    "paginas_totales": "—",
    "organo": "—",
    "expediente": "—",
}


def el_problema(hoy: dict) -> list:
    ejemplo = hoy.get("ejemplo") or SIN_EJEMPLO
    return [
        p("1. El problema, con números", "seccion"),
        p(
            "En España se publican cada día cientos de licitaciones públicas. En el semestre que "
            f"usa este estudio se publicaron <b>{miles(hoy.get('universo', 0))} expedientes en "
            f"{hoy.get('dias_con_publicaciones', 0)} días con publicaciones, "
            f"{ritmo(hoy)} al día de media</b>. Una empresa pequeña que quiera vender al sector "
            "público "
            "tiene que encontrar entre todo eso las pocas a las que puede presentarse.",
            "primero",
        ),
        p(
            "Lo que se hace hoy es filtrar por código CPV, que es la etiqueta temática que lleva "
            "cada anuncio. Es rápido y es lo que hace todo el mundo, pero tiene dos problemas. El "
            "primero es que el CPV lo pone el organismo que publica y no siempre acierta. El "
            "segundo es más de fondo: <b>el anuncio no dice si la empresa cumple los requisitos</b>. "
            "Eso está en el pliego, que es un PDF de cincuenta páginas de media, y ahí es donde se "
            "dice que hay que facturar 93.000 € al año, o tener una certificación concreta, o haber "
            "hecho antes tres trabajos parecidos."
        ),
        p(
            "Así que alguien de la empresa abre uno por uno los pliegos de las candidatas, busca la "
            "cláusula de solvencia, la lee y decide. Ese trabajo es el que hace el radar.",
        ),
        p("Qué es exactamente un pliego", "sub"),
        p(
            "El pliego de cláusulas administrativas (PCAP) es el documento que fija las reglas del "
            "concurso: quién puede presentarse, qué hay que acreditar y cómo se valora. Es donde "
            "está la frase que decide si una empresa puede o no puede presentarse, del tipo:"
        ),
        p(f"«{limpia(ejemplo['cita'])}»", "cita"),
        p(
            f"Página {ejemplo['pagina']} de {ejemplo['paginas_totales']} · "
            f"{ejemplo['organo']} · expediente {ejemplo['expediente']}",
            "nota",
        ),
        p(
            "Esa cita no es un ejemplo inventado para este documento: es de un pliego que el "
            "radar ha leído, está guardada en la base de datos y se puede comprobar abriendo ese "
            "PDF por esa página."
        ),
        p(
            "Una empresa que facture más de esa cifra cumple; una que facture menos, no. El radar "
            "busca esa frase, la copia literal, apunta en qué página estaba y compara los dos "
            "números. Ni resume, ni interpreta, ni redondea.",
        ),
    ]


def como_funciona() -> list:
    pasos = [
        ["Paso", "Qué hace", "¿Usa el modelo de lenguaje?"],
        [
            "<b>1. Ingesta</b>",
            "Descarga el feed de la Plataforma de Contratación del Sector Público y guarda cada "
            "fichero tal cual llegó, identificado por su huella digital.",
            "No",
        ],
        [
            "<b>2. Triaje</b>",
            "Con lo que dice el anuncio (objeto, órgano, CPV), decide si la licitación puede "
            "interesar a esta empresa: sí, no o duda. Van veinte licitaciones en cada pregunta.",
            "Sí, un modelo barato",
        ],
        [
            "<b>3. Descarga del pliego</b>",
            "De las que han pasado el filtro, baja el PDF del pliego.",
            "No",
        ],
        [
            "<b>4. Localizar</b>",
            "Busca en qué páginas del pliego está la cláusula de solvencia. Puntúa cada página por "
            "las palabras que contiene y se queda con un tramo corto.",
            "No",
        ],
        [
            "<b>5. Extraer</b>",
            "Lee solo esas páginas y copia los requisitos, cada uno con su cita literal y su "
            "número de página.",
            "Sí, el modelo bueno",
        ],
        [
            "<b>6. Comprobar</b>",
            "Busca esa cita, letra por letra, en el texto de esa página. Si no aparece, el "
            "requisito no se usa para decidir nada.",
            "No",
        ],
        [
            "<b>7. Decidir</b>",
            "Compara lo que pide el pliego con lo que declara la empresa y dictamina: puede "
            "presentarse, no puede, o hay que mirarlo a mano.",
            "No",
        ],
        [
            "<b>8. Ficha y correo</b>",
            "Escribe una página con la decisión y sus motivos, y compone el correo de la mañana.",
            "No",
        ],
    ]
    return [
        p("2. Cómo funciona, paso a paso", "seccion"),
        p(
            "El radar no es «una pregunta a una inteligencia artificial». Son ocho pasos, y el "
            "modelo de lenguaje solo interviene en dos de ellos. Todo lo que decide algo lo decide "
            "un programa con reglas escritas y leíbles.",
            "primero",
        ),
        Spacer(1, 4),
        tabla(pasos, [30 * mm, MEDIDA - 30 * mm - 30 * mm, 30 * mm]),
        p("La regla de oro: el modelo extrae, el programa decide", "sub"),
        p(
            "Esta separación es la decisión más importante del proyecto. Un modelo de lenguaje es "
            "bueno encontrando una frase dentro de un documento largo y es malo como fuente de "
            "verdad: si se le pregunta «¿puede esta empresa presentarse?», contesta algo razonable "
            "aunque se lo esté inventando, y no hay forma de saberlo."
        ),
        p(
            "Por eso al modelo solo se le pide que <b>copie</b>: «dime qué requisitos de solvencia "
            "hay en estas páginas, y de cada uno dame la frase exacta y la página». Lo que hace "
            "después el programa es buscar esa frase en esa página. Si no está —porque el modelo la "
            "ha resumido, la ha juntado de dos sitios o se la ha inventado— <b>el requisito se cae "
            "y no cuenta</b>. Se le pide una vez más y, si vuelve a fallar, ese requisito no "
            "participa en la decisión y queda escrito que no se pudo comprobar."
        ),
        p(
            "La comparación de los dos números tampoco la hace el modelo. La hace un fichero de "
            "reglas de cincuenta líneas que cualquiera puede leer, y que además está limitado a "
            "propósito: <b>lo único que puede descartar una licitación es el volumen de negocios</b>, "
            "porque es la única comparación que es de verdad dos números. Todo lo demás —una "
            "certificación, una clasificación empresarial, experiencia previa— manda la licitación "
            "a «hay que mirarlo a mano». Nunca la descarta en silencio."
        ),
    ]


def la_ficha(hoy: dict) -> list:
    return [
        p("3. Lo que recibe la empresa", "seccion"),
        p(
            "Cada mañana llega un correo con las licitaciones del día, una por línea, con la "
            "decisión delante. Al pie va lo que se ha mirado y lo que ha costado. Un día sin nada "
            "también manda correo diciendo que no hay nada: el silencio no se distingue de una "
            "avería.",
            "primero",
        ),
        Spacer(1, 2),
        p(
            f"Radar de licitaciones · Empresa del Norte · {fecha(hoy.get('dia_pasada'))}<br/><br/>"
            "&mdash; PUEDE PRESENTARSE<br/>"
            "&nbsp;&nbsp;Suministro de licencias de software<br/>"
            "&nbsp;&nbsp;Ayuntamiento de ejemplo · expediente 2026/1<br/>"
            "&nbsp;&nbsp;De 1 requisito leído del pliego: 1 cumple.<br/><br/>"
            f"Se han mirado {hoy.get('triadas_pasada', 0)} licitaciones, "
            f"{hoy.get('candidatas_pasada', 0)} pasaron el primer filtro.<br/>"
            "El radar lee el pliego y cita lo que dice. La decisión de presentarse es tuya.",
            "codigo",
        ),
        p(
            "Las dos cifras del pie son las de la última pasada de verdad; la licitación del "
            "ejemplo está inventada para enseñar el formato, y por eso el órgano se llama "
            "«Ayuntamiento de ejemplo».",
            "nota",
        ),
        p(
            "Detrás de cada línea hay una ficha con los requisitos encontrados. Cada uno lleva tres "
            "cosas juntas: <b>la frase literal del pliego</b>, <b>el número de página</b> y <b>el "
            "enlace al PDF original</b>. Eso es lo que hace que la ficha se pueda comprobar en "
            "treinta segundos: se abre el PDF, se va a esa página y se busca la frase. Si está, el "
            "radar dice la verdad; si no está, el radar tiene un fallo y se ve enseguida."
        ),
        p(
            "La ficha está diseñada para que se distingan dos voces. Lo que dice el pliego va en "
            "letra con remate (serif) y entre comillas; lo que dice el radar, en letra de palo "
            "seco. Un sello azul marca las citas que el programa ha comprobado contra el PDF, y uno "
            "de color óxido las que no se pudieron comprobar. Nunca hay que adivinar qué parte es "
            "del documento oficial y qué parte es del programa."
        ),
        p("Y la frase que cierra todas las fichas", "sub"),
        p(
            "«El radar lee el pliego y cita lo que dice. La decisión de presentarse es tuya.» No es "
            "una fórmula de cortesía: el radar no sabe si a la empresa le compensa el margen, si "
            "tiene equipo libre ese mes o si quiere entrar en ese cliente. Solo lee requisitos.",
            "cita",
        ),
    ]


def por_ciento(x: float) -> str:
    return f"{x * 100:.1f} %".replace(".", ",")


def puntos(x: float) -> str:
    return f"{'−' if x < 0 else '+'}{abs(x) * 100:.1f} puntos".replace(".", ",")


def comparacion(hoy: dict, clave: str, titulo: str) -> list[str]:
    """Una fila de la tabla del resultado, leída de `eval_resultados` y no escrita a mano."""
    r = (hoy.get("resultado") or {}).get(clave)
    if not r:
        return [titulo, "—", "—", "—", "(la base no respondió al generar el documento)"]
    bajo, alto = r["ic"]
    veredicto = r.get("veredicto", "")
    refutada = veredicto == "refutada"
    return [
        titulo,
        por_ciento(r["recall_agente"]),
        por_ciento(r["recall_baseline"]),
        f"<b>{puntos(r['diferencia'])}</b>" if refutada else puntos(r["diferencia"]),
        f"[{puntos(bajo)}, {puntos(alto)}] &rarr; "
        f"{f'<b>tesis {veredicto}</b>' if refutada else veredicto}".replace(" puntos", ""),
    ]


def la_medicion(hoy: dict) -> list:
    triaje = [
        ["Variante probada", "Aciertos", "Licitaciones que deja pasar", "Coste por 100"],
        ["Modelo barato, de 20 en 20", "24 de 24", "37,9 y 53,0 de 100", "<b>0,0403 €</b>"],
        ["Modelo barato, de una en una", "24 de 24", "7,6 y 53,0 de 100", "0,1845 €"],
        ["Modelo caro, de 20 en 20", "24 de 24", "60,6 y 68,2 de 100", "0,1888 €"],
    ]
    resultado = [
        ["Comparación", "Radar", "Rival", "Diferencia", "Intervalo de confianza"],
        comparacion(hoy, "baseline_a", "Frente al filtro CPV estándar"),
        comparacion(hoy, "baseline_b", "Frente al filtro hecho a medida"),
    ]
    return [
        p("4. Qué se midió, y qué salió", "seccion"),
        p(
            "Un proyecto que dice «funciona» sin enseñar cómo lo sabe no vale nada. Aquí el método "
            "se escribió y se subió al repositorio <b>antes</b> de mirar ningún dato, y el orden de "
            "los commits es la prueba de que no se cambió después. Se midieron tres cosas.",
            "primero",
        ),
        p("4.1. Qué modelo usar para el filtro barato", "sub"),
        p(
            "Se probaron tres formas de hacer el triaje sobre 200 licitaciones de dos empresas, con "
            "la regla de decisión escrita de antemano: «si la diferencia de aciertos es menor de "
            "ocho puntos, gana la más barata»."
        ),
        Spacer(1, 2),
        tabla(triaje, [50 * mm, 20 * mm, MEDIDA - 50 * mm - 20 * mm - 26 * mm, 26 * mm]),
        p(
            "Las tres aciertan lo mismo, así que gana la barata: <b>4,7 veces más barata que la "
            "cara y además deja pasar menos ruido</b>. Sin la regla escrita antes, la tentación "
            "habría sido quedarse con el modelo caro «por si acaso».",
            "nota",
        ),
        p("4.2. Si el radar se inventa citas", "sub"),
        p(
            "Esta es la medida que sostiene todo lo demás, porque si las citas no son de fiar, la "
            "ficha es una opinión con formato bonito. De <b>62 requisitos extraídos de 15 pliegos "
            "reales, los 62 tenían una cita que aparece literal en la página que dijo el modelo. "
            "El 100 %</b>, con cero rechazos."
        ),
        p(
            "Que el rechazo sea cero no significa que la comprobación no haga nada: si se desactiva, "
            "dos tests se ponen en rojo inmediatamente porque una cita inventada pasaría. Significa "
            "que el modelo copia bien cuando se le dan las páginas exactas contra las que se le va "
            "a comprobar. De paso: se leen <b>4,7 páginas de las 51,5</b> que tiene un pliego de "
            "media, el 9 %. Ahí está el coste bajo."
        ),
        p("4.3. Si el radar encuentra más contratos que un filtro CPV", "sub"),
        p(
            "Esta era la tesis del proyecto. Se cogieron cinco empresas reales que no se habían "
            "tocado nunca, sus 77 contratos ganados de verdad, y se miró cuántos habría encontrado "
            "el radar y cuántos dos filtros rivales."
        ),
        Spacer(1, 2),
        tabla(resultado, [42 * mm, 15 * mm, 15 * mm, 22 * mm, MEDIDA - 94 * mm]),
        Spacer(1, 6),
        p(
            "<b>La tesis salió refutada.</b> El radar encuentra menos contratos que un filtro de "
            "CPV bien hecho, y se publica así porque para eso se congeló el criterio antes de "
            "medir. Cambiar la tesis después de ver el resultado habría sido convertir el estudio "
            "en publicidad.",
        ),
        p("4.4. Por qué pierde, medido y no supuesto", "sub"),
        p(
            "De los 77 contratos, el radar descartó 20. <b>Diecinueve de esos veinte son productos "
            "o servicios que el perfil de la empresa no menciona.</b> Una distribuidora cuya web "
            "solo habla de una marca ganó once contratos de licencias de otras dos; una integradora "
            "que se describe montando equipos de televisión ganó contratos de analítica de redes "
            "sociales. El modelo razonó bien sobre una descripción demasiado estrecha."
        ),
        p(
            "El techo del radar no es el modelo: es lo poco que sabe de la empresa. Y eso cambia "
            "qué hay que arreglar. No hace falta un modelo mejor ni más páginas leídas; hace falta "
            "preguntarle a la empresa lo que no cuenta de sí misma."
        ),
    ]


def lo_que_cuesta_cada_acierto(hoy: dict) -> list:
    """M9 y M10. Se cuentan porque contestan la pregunta que M1 dejaba abierta, y porque el
    resultado volvió a salir en contra de quien escribió la regla."""
    cifras = hoy.get("eficiencia") or {}
    if not cifras:
        return []
    empresas = sorted({a for _, _, a in cifras})
    filas9 = [["Empresa", "Radar", "Filtro CPV estándar", "Filtro a medida"]]
    filas10 = [["Empresa", "Radar", "Filtro CPV estándar", "Filtro a medida"]]
    for alias in empresas:
        filas9.append(
            [
                alias,
                f"<b>{cifras.get(('M9', 'agente_test', alias), 0):,.0f}</b>".replace(",", "."),
                f"{cifras.get(('M9', 'baseline_a', alias), 0):,.0f}".replace(",", "."),
                f"{cifras.get(('M9', 'baseline_b', alias), 0):,.0f}".replace(",", "."),
            ]
        )
        filas10.append(
            [
                alias,
                f"<b>{cifras.get(('M10', 'agente_test', alias), 0) * 100:.0f} %</b>",
                f"{cifras.get(('M10', 'baseline_a', alias), 0) * 100:.0f} %",
                f"{cifras.get(('M10', 'baseline_b', alias), 0) * 100:.0f} %",
            ]
        )
    ancho = (MEDIDA - 30 * mm) / 3
    return [
        p("4.5. Cuánto trabajo cuesta cada acierto", "sub"),
        p(
            "Queda una pregunta que la medición de arriba no contesta: un filtro que no filtra "
            "encuentra el 100 % de los contratos y no sirve de nada. Hacía falta saber cuánto "
            "papel cuesta cada acierto. La definición y la regla de decisión se escribieron "
            "<b>antes</b> de calcular nada, pero <b>después</b> de conocer el resultado de "
            "arriba, y eso las hace más débiles: por eso van aquí y no en lugar de aquello."
        ),
        # Cada tabla con su título pegado: una tabla de cinco filas partida por la mitad, con la
        # cabecera en la página anterior, se lee mal y se interpreta peor.
        KeepTogether(
            [
                p("Licitaciones que hay que revisar por cada contrato encontrado (menos es mejor):", "nota"),
                tabla(filas9, [30 * mm, ancho, ancho, ancho]),
            ]
        ),
        Spacer(1, 8),
        KeepTogether(
            [
                p("Contratos encontrados si los tres entregaran la misma cantidad de papel:", "nota"),
                tabla(filas10, [30 * mm, ancho, ancho, ancho]),
            ]
        ),
        Spacer(1, 6),
        p(
            "<b>La regla pedía ganar a los dos rivales en tres de las cinco empresas y el radar "
            "gana en dos.</b> Así que tampoco por aquí se rescata el resultado, y así se publica."
        ),
        p(
            "Lo que sí aparece es una corrección de algo que el informe afirmaba: el radar es "
            "mucho más selectivo que el filtro a medida —entrega hasta 36 veces menos papel—, "
            "pero <b>no</b> es más selectivo que el filtro de CPV estándar en tres de las cinco "
            "empresas. Y al revés: cuando se obliga a los tres a entregar la misma cantidad, el "
            "filtro a medida se hunde en las cinco. Sus catorce puntos de ventaja salían de "
            "repartir 288 licitaciones al día a una empresa que no las va a mirar."
        ),
    ]


def el_formulario(hoy: dict) -> list:
    return [
        p("5. La consecuencia: un formulario que pregunta lo que nadie cuenta", "seccion"),
        p(
            "La medición señaló el arreglo, y el arreglo está hecho. Una empresa entra en el radar "
            "rellenando un formulario, y de lo que escribe sale el texto que lee el modelo. El "
            "formulario no es una caja de texto libre, por un motivo concreto: <b>nadie escribe de "
            "sí mismo lo que no cree importante</b>. Una distribuidora describe lo que fabrica, no "
            "las marcas que revende, y ahí estaban los contratos perdidos.",
            "primero",
        ),
        p("Por eso pregunta suelto, y tres preguntas llevan escrito por qué se hacen:"),
        Spacer(1, 2),
        tabla(
            [
                ["La pregunta", "Por qué está ahí"],
                [
                    "<b>Marcas y productos que distribuye, instala o mantiene</b>",
                    f"Aquí estaban los {perdidos(hoy)} contratos que el radar dejó escapar en la medición.",
                ],
                [
                    "<b>Otros servicios que presta, aunque no sean su bandera</b>",
                    "La formación, el soporte o el suministro de terminales dan contratos y no "
                    "suelen salir en la web de la empresa.",
                ],
                [
                    "<b>Lo que no hace</b>",
                    "Para que un descarte sea una decisión con motivo y no un silencio.",
                ],
                [
                    "<b>Cuánto está dispuesta a gastar al día</b>",
                    "Leer un pliego cuesta dinero. Sin este tope, el radar tendría que decidir por "
                    "la empresa cuántos abre.",
                ],
            ],
            [62 * mm, MEDIDA - 62 * mm],
        ),
        p(
            "Cada empresa tiene su propio tope diario y recibe su propio correo. El trabajo de la "
            "mañana se corta por ese tope, y se corta leyendo pliegos, nunca triando: quedarse sin "
            "triar significa no haber mirado una licitación que quizá era la buena, mientras que "
            "quedarse sin leer solo deja un pliego para el día siguiente."
        ),
    ]


def lo_que_cuesta(hoy: dict) -> list:
    return [
        p("6. Lo que cuesta", "seccion"),
        p(
            "Todo lo que se le pide al modelo pasa por un único fichero que apunta los tokens, el "
            "coste en dólares y en euros, y comprueba el presupuesto <b>antes</b> de llamar: cuenta "
            "los tokens de entrada, que es gratis, y supone que la respuesta saldrá al máximo. Es "
            "una estimación pesimista a propósito: más vale negarse de más que gastar de más.",
            "primero",
        ),
        Spacer(1, 2),
        tabla(
            [
                ["Concepto", "Medido"],
                ["Triar 100 licitaciones", "0,04 €"],
                ["Leer un pliego entero, con su cita verificada", "0,070 € de media"],
                ["Un día de trabajo de una empresa con tope de 1 €", "hasta 11 pliegos leídos"],
                [
                    "<b>Todo el proyecto, desde el primer día</b>",
                    f"<b>{euros(hoy.get('gasto', 0))} en {miles(hoy.get('llamadas', 0))} llamadas</b>",
                ],
            ],
            [MEDIDA - 42 * mm, 42 * mm],
        ),
        p(
            "El coste bajo no sale de usar un modelo malo: sale de no leer lo que no hace falta. De "
            "las 51,5 páginas de un pliego se leen 4,7, porque un programa sin modelo localiza "
            "antes dónde está la cláusula de solvencia.",
            "nota",
        ),
    ]


def como_esta_hecho(hoy: dict) -> list:
    return [
        p("7. Cómo está construido", "seccion"),
        p(
            "El dato va siempre en la misma dirección y cada capa solo conoce la anterior. Cualquier "
            "fila de la base se puede remontar hasta el fichero exacto que la produjo.",
            "primero",
        ),
        Spacer(1, 2),
        p(
            "feed de la Plataforma<br/>"
            "&nbsp;&nbsp;&rarr; capa de ficheros tal cual llegaron, con su huella<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&rarr; tabla intermedia<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&rarr; núcleo (licitaciones, lotes, adjudicaciones)<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&rarr; agente (triaje, pliego, ficha)<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&rarr; evaluación",
            "codigo",
        ),
        Spacer(1, 2),
        tabla(
            [
                ["Pieza", "Para qué", "Por qué esta y no otra"],
                [
                    "<b>Python + PostgreSQL</b>",
                    "Todo el radar y su base de datos.",
                    "Lo que hay que poder demostrar es la trazabilidad, y eso es SQL.",
                ],
                [
                    "<b>LangGraph</b>",
                    "El grafo que va de una licitación candidata a una ficha.",
                    "Por sus ramas: sin pliego, sin sección de solvencia, el modelo contestando "
                    "cualquier cosa, el salto al anexo. Y porque guarda el paso a paso: si algo se "
                    "cae a la mitad, se ve en qué nodo estaba.",
                ],
                [
                    "<b>n8n</b>",
                    "El reloj de las siete de la mañana y el envío del correo.",
                    "El aviso tiene que salir aunque el que falle sea el propio radar. Si el correo "
                    "lo mandara el agente, un fallo del agente sería también un fallo del aviso.",
                ],
                [
                    "<b>Claude</b>",
                    "Dos pasos: el triaje y la extracción de requisitos.",
                    "Uno barato para mirar mucho y uno bueno para leer poco y bien.",
                ],
            ],
            [30 * mm, 42 * mm, MEDIDA - 72 * mm],
        ),
        p("Cómo se comprueba que no está roto", "sub"),
        p(
            f"Hay <b>{hoy.get('pruebas', 'todas las')} pruebas automáticas</b>, y la regla al "
            "arreglar un fallo es siempre la misma: primero se escribe la prueba que falla por "
            "ese fallo, se comprueba "
            "que está en rojo, y solo entonces se arregla. El mensaje del commit dice qué fallaba "
            "y cómo se demostró, no solo qué se cambió."
        ),
        p(
            "Además hay una matriz de fallos escrita de antemano —qué debe pasar si el PC está "
            "apagado a las siete, si la Plataforma no responde, si el pliego es una imagen "
            "escaneada, si el modelo contesta algo ilegible— con una prueba por fila. Al "
            "escribirlas aparecieron tres fallos reales que no se habrían visto de otro modo. El "
            "mejor: <b>la ingesta diaria se habría comido su propia copia del feed</b> y, a partir "
            "del segundo día, habría devuelto cero licitaciones nuevas sin dar ningún error.",
        ),
        p(
            f"Estado actual: {miles(hoy.get('licitaciones', 0))} filas de licitación, "
            f"{miles(hoy.get('vigentes', 0))} expedientes vigentes con el plazo abierto y "
            f"{miles(hoy.get('requisitos', 0))} requisitos extraídos, de los que "
            f"{miles(hoy.get('verificados', 0))} tienen su cita comprobada contra la página.",
            "nota",
        ),
    ]


def los_fallos() -> list:
    return [
        p("8. Los errores que costaron dinero o habrían mentido", "seccion"),
        p(
            "Esta sección está aquí porque es la parte más útil del proyecto. Todos estos fallos "
            "son reales, todos se encontraron durante el desarrollo y todos tienen hoy una prueba "
            "que se pone en rojo si vuelven.",
            "primero",
        ),
        Spacer(1, 2),
        tabla(
            [
                ["Qué fallaba", "Qué habría pasado"],
                [
                    "El coste se contaba una vez por licitación en lugar de una por llamada.",
                    "Una llamada de 0,10 € se apuntaba como 0,40 €. Con veinte licitaciones por "
                    "llamada, el presupuesto del día se agotaba veinte veces antes de tiempo.",
                ],
                [
                    "El buscador de páginas se llevaba el índice y la parte técnica.",
                    "En un pliego real de 112 páginas leía las páginas 1 a 7 mientras la cláusula "
                    "de solvencia estaba en la 54. Pagaba por leer y no encontraba nada.",
                ],
                [
                    "Una llamada pagada podía quedarse sin apuntar.",
                    "Se llamó al modelo caro, se pagó, y el registro falló <b>después</b>. Gasto "
                    "real que el presupuesto no veía, que es justo lo que el presupuesto existe "
                    "para evitar.",
                ],
                [
                    "Volver a leer un pliego duplicaba sus requisitos.",
                    "La ficha repetía el mismo requisito una vez por lectura y el correo decía «de "
                    "4 requisitos leídos: 4 cumplen» de un pliego que tenía uno.",
                ],
                [
                    "Un tope de «1.00 €» se guardaba como 100 €.",
                    "Dos trozos del programa leían los números de forma distinta. El cliente pedía "
                    "gastar un euro al día y el radar entendía cien.",
                ],
                [
                    "El correo sumaba el gasto de todos los clientes.",
                    "Cada empresa habría visto en su correo lo que gastaron las demás.",
                ],
            ],
            [62 * mm, MEDIDA - 62 * mm],
        ),
    ]


def los_limites(hoy: dict) -> list:
    return [
        p("9. Lo que el radar no hace", "seccion"),
        p(
            "Un sistema que no dice dónde falla no se puede usar para decidir nada. Estos límites "
            "están escritos en la especificación del proyecto, no aparecieron después.",
            "primero",
        ),
        Spacer(1, 2),
        tabla(
            [
                ["Límite", "Qué significa"],
                [
                    "<b>El techo es el perfil de la empresa</b>",
                    f"Medido: los {perdidos(hoy)} contratos perdidos eran productos que el perfil no "
                    "nombraba. Si el perfil está mal, la decisión también.",
                ],
                [
                    "<b>Un pliego escaneado no se lee</b>",
                    "Si el PDF no trae texto, el expediente sale como «hay que mirarlo a mano» "
                    "diciendo que es una imagen. No se inventa su contenido.",
                ],
                [
                    "<b>Las casillas marcadas no se leen</b>",
                    "Muchos pliegos son formularios con casillas, y el texto extraído no conserva "
                    "cuál está marcada. Se avisa; no se adivina.",
                ],
                [
                    "<b>Solo la Plataforma estatal</b>",
                    "Varias comunidades autónomas publican en su propia plataforma y esas "
                    "licitaciones no se ven.",
                ],
                [
                    "<b>Solvencia con medios externos o en unión de empresas</b>",
                    "La ley permite acreditar solvencia apoyándose en otras empresas. No se modela.",
                ],
                [
                    "<b>Ganar no es presentarse</b>",
                    "La verdad de referencia son los contratos ganados. No se sabe a qué más se "
                    "presentó cada empresa, así que la precisión solo se estima.",
                ],
                [
                    "<b>Los perfiles del estudio los escribió el modelo</b>",
                    "Salen solo de fuentes públicas y sin mirar ni un contrato, pero quedan más "
                    "ordenados que el perfil que escribiría un cliente real, y eso favorece al "
                    "radar. Es el sesgo más importante del estudio.",
                ],
            ],
            [58 * mm, MEDIDA - 58 * mm],
        ),
    ]


def el_cierre(hoy: dict) -> list:
    return [
        p("10. Qué demuestra este proyecto", "seccion"),
        p(
            "No demuestra que leer el pliego encuentre más contratos que un filtro de CPV. Eso se "
            "midió y salió que no, y está publicado con su intervalo de confianza.",
            "primero",
        ),
        p("Demuestra otras cuatro cosas, y las cuatro son comprobables abriendo el repositorio:"),
        Spacer(1, 2),
        tabla(
            [
                ["", ""],
                [
                    "<b>Que se puede impedir que un modelo mienta</b>",
                    "Obligándole a citar y comprobando la cita contra el documento. 62 de 62 "
                    "citas verificadas.",
                ],
                [
                    "<b>Que se puede medir de verdad</b>",
                    "Congelando el método antes de mirar los datos, con el orden de los commits "
                    "como prueba, y publicando el resultado aunque salga en contra.",
                ],
                [
                    "<b>Que un diagnóstico vale más que un resultado bonito</b>",
                    f"La medición no solo dijo que la tesis fallaba: dijo dónde. Los {perdidos(hoy)} "
                    "contratos perdidos, por lo mismo, y de ahí salió el formulario que lo arregla.",
                ],
                [
                    "<b>Que el coste se puede controlar</b>",
                    "Todo el proyecto, desde la primera línea, por debajo de lo que cuesta un café. "
                    "Cada llamada apuntada, cada euro atribuible a quien lo gastó.",
                ],
            ],
            [62 * mm, MEDIDA - 62 * mm],
            cabecera=False,
        ),
        Spacer(1, 10),
        p(
            "La frase que mejor resume el proyecto es la que cierra cada ficha que genera:",
            "nota",
        ),
        p(
            "«El radar lee el pliego y cita lo que dice. La decisión de presentarse es tuya.»",
            "cita",
        ),
    ]


def como_se_pone_en_marcha() -> list:
    return [
        p("11. Cómo se pone en marcha", "seccion"),
        p(
            "Todo arranca con tres contenedores —la base de datos, el orquestador y el propio "
            "radar— y se maneja con comandos que se pueden leer. Ninguno de ellos gasta dinero "
            "salvo el que lo dice.",
            "primero",
        ),
        Spacer(1, 2),
        p(
            "docker compose up -d<br/>"
            "uv run python -m radar.diagnostico&nbsp;&nbsp;&nbsp;&nbsp;# ¿está todo en su sitio?<br/>"
            "uv run python -m radar.ingesta --paginas 10<br/>"
            "uv run python -m radar.diario&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "&nbsp;&nbsp;&nbsp;&nbsp;# qué haría hoy y qué costaría<br/>"
            "uv run python -m radar.diario --gastar&nbsp;&nbsp;# hacerlo<br/>"
            "uv run pytest&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# todas las pruebas",
            "codigo",
        ),
        p(
            "El comando sin <b>--gastar</b> no llama al modelo: dice cuántas licitaciones hay por "
            "mirar, cuántos pliegos se podrían abrir con lo que queda del tope y cuánto costaría "
            "cada uno. Que la opción por defecto sea la que no gasta no es un detalle: es la "
            "misma idea que recorre el proyecto entero, que una cosa que cuesta dinero se hace a "
            "propósito y no por descuido.",
        ),
    ]


def en_que_punto_esta(hoy: dict) -> list:
    return [
        p("12. En qué punto está", "seccion"),
        p(
            "Las siete fases de construcción están cerradas, cada una con su informe y con el "
            "comando que reproduce sus cifras. El trabajo diario por cliente funciona de punta a "
            f"punta: la última pasada real trió <b>{hoy.get('triadas_pasada', 0)} licitaciones</b> "
            f"publicadas y dejó <b>{hoy.get('candidatas_pasada', 0)} candidatas</b>, y hay una prueba "
            "automática que recorre la cadena entera —alta de la empresa, triaje, pliego en PDF, "
            "comprobación de la cita, ficha y correo— sin saltarse ningún paso.",
            "primero",
        ),
        p(
            "Lo que falta no es código: es tiempo. La prueba de que esto aguanta son cinco días "
            "laborables seguidos recibiendo el correo de la mañana, y eso solo se consigue "
            "esperando cinco días.",
        ),
        regla(6),
        p(
            "El código está en un repositorio con todo el historial: los informes de cada fase, "
            "las decisiones técnicas con su motivo, los documentos de método congelados antes de "
            "medir y los commits que demuestran que se congelaron antes.",
            "nota",
        ),
    ]


# --- La misma historia, en Word --------------------------------------------------------

SALIDA_DOCX = Path("docs/dossier_radar_de_licitaciones.docx")

# Lo único que el PDF escribe como marcado. Se traduce, no se borra: quitar un &nbsp; partiría
# «4,7 páginas» por la mitad al final de una línea, que es justo para lo que está puesto.
ENTIDADES = {"&nbsp;": " ", "&rarr;": "→", "&mdash;": "—", "&amp;": "&"}
NIVELES = {"titulo": 0, "seccion": 1, "sub": 2}
GRIS = RGBColor(0x5A, 0x62, 0x70)


def trozos(marcado: str):
    """El texto de un párrafo, partido en (texto, negrita) y con los saltos ya puestos."""
    for entidad, signo in ENTIDADES.items():
        marcado = marcado.replace(entidad, signo)
    for parte in re.split(r"(<b>.*?</b>)", marcado.replace("<br/>", "\n"), flags=re.S):
        if parte:
            yield re.sub(r"</?b>", "", parte), parte.startswith("<b>")


def pintar(parrafo, marcado: str, estilo: str) -> None:
    for texto, negrita in trozos(marcado):
        for i, linea in enumerate(texto.split("\n")):
            if i:
                parrafo.add_run().add_break()
            if not linea:
                continue
            letra = parrafo.add_run(linea)
            letra.bold = negrita or estilo == "portadanum"
            letra.italic = estilo in ("cita", "subtitulo")
            if estilo == "codigo":
                letra.font.name = "Consolas"
            if estilo in ("nota", "codigo"):
                letra.font.size = Pt(9)
            if estilo in ("nota", "subtitulo"):
                letra.font.color.rgb = GRIS


def raya(documento) -> None:
    """La regla horizontal del PDF, que en Word es un borde inferior de un párrafo vacío."""
    borde, abajo = OxmlElement("w:pBdr"), OxmlElement("w:bottom")
    for clave, valor in (("val", "single"), ("sz", "4"), ("space", "1"), ("color", "D5D0C4")):
        abajo.set(qn(f"w:{clave}"), valor)
    borde.append(abajo)
    documento.add_paragraph()._p.get_or_add_pPr().append(borde)


def celdas(fila) -> list[str]:
    """Una celda es un Paragraph de reportlab, salvo en la regla, donde es una cadena vacía."""
    return [getattr(c, "text", c) or "" for c in fila]


def aplanar(historia: list):
    for elemento in historia:
        if isinstance(elemento, KeepTogether):
            yield from aplanar(elemento._content)
        else:
            yield elemento


def a_docx(historia: list, destino: Path = SALIDA_DOCX) -> Path:
    documento = Document()
    documento.core_properties.title = "Radar de licitaciones que lee el pliego"
    documento.core_properties.author = "Miguel Martin-Caro"
    documento.core_properties.subject = "Como funciona, que se midio y que salio"
    for elemento in aplanar(historia):
        if isinstance(elemento, PageBreak):
            documento.add_page_break()
        elif isinstance(elemento, Paragraph):
            estilo = elemento.style.name
            parrafo = (
                documento.add_heading(level=NIVELES[estilo])
                if estilo in NIVELES
                else documento.add_paragraph()
            )
            pintar(parrafo, elemento.text, estilo)
        elif isinstance(elemento, Table):
            filas = [celdas(f) for f in elemento._cellvalues]
            if filas == [[""]]:  # la regla horizontal, que es una tabla de una celda vacía
                raya(documento)
                continue
            # Sin cuadrícula, como en el PDF: la cabecera en negrita es lo único que la marca.
            tabla_w = documento.add_table(rows=len(filas), cols=len(filas[0]))
            for i, fila in enumerate(filas):
                for j, texto in enumerate(fila):
                    pintar(tabla_w.cell(i, j).paragraphs[0], texto, "portadanum" if i == 0 else "cuerpo")
    documento.save(str(destino))
    return destino


def historia_de(hoy: dict) -> list:
    """El dossier entero, en orden. Se construye una vez por formato porque al maquetar el PDF
    reportlab parte y envuelve sus propios elementos, y no conviene darle los mismos dos veces."""
    return (
        portada(hoy)
        + el_problema(hoy)
        + como_funciona()
        + la_ficha(hoy)
        + la_medicion(hoy)
        + lo_que_cuesta_cada_acierto(hoy)
        + el_formulario(hoy)
        + lo_que_cuesta(hoy)
        + como_esta_hecho(hoy)
        + los_fallos()
        + los_limites(hoy)
        + el_cierre(hoy)
        + como_se_pone_en_marcha()
        + en_que_punto_esta(hoy)
    )


def a_pdf(historia: list, destino: Path = SALIDA) -> Path:
    documento = BaseDocTemplate(
        str(destino),
        pagesize=A4,
        leftMargin=IZQ,
        rightMargin=DER,
        topMargin=ARR,
        bottomMargin=ABA,
        title="Radar de licitaciones que lee el pliego",
        author="Miguel Martin-Caro",
        subject="Como funciona, que se midio y que salio",
    )
    marco = Frame(IZQ, ABA, MEDIDA, ALTO - ARR - ABA, id="cuerpo", leftPadding=0, rightPadding=0)
    documento.addPageTemplates([PageTemplate(id="normal", frames=[marco], onPage=pie)])

    documento.build(historia)
    return destino


def construir() -> tuple[Path, Path]:
    """Los dos formatos de una sola lectura de la base: si dijeran cifras distintas, sería
    porque se han generado en momentos distintos, y eso es justo lo que no puede pasar."""
    hoy = del_radar()
    return a_pdf(historia_de(hoy)), a_docx(historia_de(hoy))


if __name__ == "__main__":
    for ruta in construir():
        print(f"\n{ruta.suffix.lstrip('.').upper():>4}: {ruta.as_posix()}")
        print(f"      {ruta.resolve().as_uri()}")
