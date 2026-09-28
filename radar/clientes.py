"""Las empresas que usan el radar, y lo que el radar sabe de cada una.

Una empresa se da de alta rellenando un formulario, y de esos campos sale **el texto que lee el
modelo en el triaje**. Ese texto es el techo del radar: la Fase 5 midió que de los 20 contratos
que se le escaparon, **19 eran productos que el perfil de la empresa no mencionaba** — una
distribuidora de software cuya web solo hablaba de una marca, una integradora de equipos que
también vendía servicios de red (`docs/informes/fase5_diagnostico.md`).

Por eso el formulario no es una caja de texto libre. Pregunta por separado las cosas que el
radar necesita saber y que una empresa no cuenta si no se le pregunta:

- **las marcas que distribuye o mantiene**, aunque no sean suyas;
- **lo que hace aunque no sea su bandera**, que es donde estaban los contratos perdidos;
- **lo que no hace**, para que un descarte sea una decisión y no un silencio.

Esto **no** es la tabla `perfiles`, que es la del estudio y está bajo candado (`docs/DECISIONES.md`
D38). Aquí el cliente edita cuando quiere; allí nadie toca nada después de medir.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from radar.bd import conectar
from radar.errores import ErrorRadar

CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
ALIAS = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 .,&'-]{2,40}$")
TOPE_MAXIMO = 20.00


@dataclass(frozen=True)
class Campo:
    nombre: str
    etiqueta: str
    ayuda: str
    obligatorio: bool = False
    largo: bool = False
    ejemplo: str = ""


# El formulario, en el orden en que se pregunta. El orden importa: primero lo que la empresa
# tiene claro, y las preguntas incómodas —lo que no hace, lo que factura— al final.
CAMPOS = (
    Campo(
        "nombre",
        "Nombre de la empresa",
        "Como aparece en sus facturas. No sale en ninguna parte pública.",
        obligatorio=True,
        ejemplo="Soluciones Informáticas del Norte, S.L.",
    ),
    Campo(
        "alias",
        "Cómo llamarla en los informes",
        "Lo único que aparece en cualquier cosa que se publique.",
        obligatorio=True,
        ejemplo="Empresa del Norte",
    ),
    Campo(
        "correo",
        "Correo donde recibir el aviso diario",
        "Llega un correo al día, también los días en que no hay nada.",
        obligatorio=True,
        ejemplo="contratacion@ejemplo.es",
    ),
    Campo(
        "que_hace",
        "¿A qué se dedica?",
        "En sus palabras, como se lo contaría a un cliente nuevo.",
        obligatorio=True,
        largo=True,
        ejemplo="Desarrollamos e implantamos software de control horario y gestión de personal "
        "para ayuntamientos y empresas.",
    ),
    Campo(
        "productos",
        "Marcas y productos que distribuye, instala o mantiene",
        "Aunque no sean suyos. Este es el campo que más contratos hace ganar o perder: los "
        "pliegos nombran la marca, no la categoría.",
        largo=True,
        ejemplo="Autodesk, Adobe Creative Cloud, PRESTO, Microsoft 365. Mantenemos también "
        "instalaciones de terceros.",
    ),
    Campo(
        "servicios",
        "¿Qué más hace, aunque no sea su bandera?",
        "Lo que aparece en su facturación pero no en su web: mantenimientos, formación, "
        "suministro de equipos, servicios que presta de paso.",
        largo=True,
        ejemplo="Formación a usuarios, suministro de terminales, soporte telefónico, migraciones de datos.",
    ),
    Campo(
        "no_hace",
        "¿Qué NO hace?",
        "Sirve para descartar con motivo en lugar de por silencio. Si no lo dice, el radar solo "
        "puede suponer.",
        largo=True,
        ejemplo="Obra civil, instalaciones eléctricas, seguridad física, limpieza.",
    ),
    Campo(
        "certificaciones",
        "Certificaciones que tiene",
        "Muchos pliegos las exigen. Si no constan, esos requisitos quedan sin resolver.",
        ejemplo="ISO 9001, ISO 27001, Esquema Nacional de Seguridad nivel medio",
    ),
    Campo(
        "ambito",
        "¿Dónde trabaja?",
        "Comunidades o provincias donde se presenta. Déjelo vacío si es toda España.",
        ejemplo="Asturias, Cantabria y Castilla y León",
    ),
    Campo(
        "cifra_negocio",
        "Cifra anual de negocio, en euros",
        "Solo se usa para comparar con lo que exige cada pliego. Si no la pone, el radar no "
        "podrá descartar por solvencia económica y todo quedará «por comprobar».",
        ejemplo="850000",
    ),
    Campo(
        "tope_diario_eur",
        "Cuánto se puede gastar al día en leer pliegos, en euros",
        "Leer un pliego cuesta unos 0,07 €. Con 1 € al día se leen unos catorce.",
        ejemplo="1.00",
    ),
)

OBLIGATORIOS = tuple(c.nombre for c in CAMPOS if c.obligatorio)


def limpiar(valores: dict) -> dict:
    return {c.nombre: " ".join(str(valores.get(c.nombre, "") or "").split()) for c in CAMPOS}


def validar(valores: dict) -> dict[str, str]:
    """Devuelve un error por campo, en castellano. Vacío significa que está bien."""
    errores: dict[str, str] = {}
    for nombre in OBLIGATORIOS:
        if not valores.get(nombre):
            errores[nombre] = "Hace falta rellenar esto."
    if valores.get("correo") and not CORREO.match(valores["correo"]):
        errores["correo"] = "Eso no parece una dirección de correo."
    if valores.get("alias") and not ALIAS.match(valores["alias"]):
        errores["alias"] = "Use entre 2 y 40 letras, números o espacios."
    if valores.get("que_hace") and len(valores["que_hace"]) < 30:
        errores["que_hace"] = "Cuéntelo con un poco más de detalle: con una línea el radar acierta poco."

    if valores.get("cifra_negocio"):
        cifra = numero(valores["cifra_negocio"])
        if cifra is None or cifra <= 0:
            errores["cifra_negocio"] = "Escriba solo el número, por ejemplo 850000."

    if valores.get("tope_diario_eur"):
        tope = numero(valores["tope_diario_eur"])
        if tope is None:
            errores["tope_diario_eur"] = "Escriba solo el número, por ejemplo 1.00."
        elif tope < 0:
            errores["tope_diario_eur"] = "No puede ser negativo."
        elif tope > TOPE_MAXIMO:
            errores["tope_diario_eur"] = (
                f"El máximo son {TOPE_MAXIMO:.0f} € al día. Si necesita más, hablemos antes."
            )
    return errores


def numero(texto: str | None) -> float | None:
    """Lee un número como lo escribe una persona: 850.000, 1.234,56, 1.00, 0,50.

    La regla es la que usa cualquiera en castellano sin pensarlo: **si hay coma, la coma es el
    decimal** y los puntos separan miles; **si solo hay puntos**, son miles cuando dejan grupos
    de tres cifras (850.000) y decimales cuando no (1.00, 0.07).

    Esta función es la única que lee números en el formulario, y eso es lo importante. Antes
    había dos: `validar` leía «1.00» como un euro y esta lo leía como cien, así que un cliente
    que pedía gastar un euro al día acababa con un tope de cien. Validar un número y guardar
    otro es el peor fallo que puede tener un formulario que decide cuánto se gasta.
    """
    if texto is None:
        return None
    limpio = str(texto).strip().replace(" ", "")
    if not limpio:
        return None
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif "." in limpio:
        entero, _, ultimo = limpio.rpartition(".")
        if len(ultimo) == 3 and entero and entero.replace(".", "").isdigit():
            limpio = limpio.replace(".", "")
    try:
        return float(limpio)
    except ValueError:
        return None


def como_lo_lee_el_modelo(valores: dict) -> str:
    """Los campos del formulario convertidos en el texto del perfil que recibe el triaje.

    Mismo formato que los perfiles del estudio, para que el prompt no tenga que distinguir de
    dónde viene lo que lee. Los apartados vacíos no se escriben: una sección con un guion
    dentro le dice al modelo menos que no estar.
    """
    secciones = [
        ("Qué hace", valores.get("que_hace")),
        ("Marcas y productos que distribuye, instala o mantiene", valores.get("productos")),
        ("Otros servicios que presta", valores.get("servicios")),
        ("Lo que no hace", valores.get("no_hace")),
        ("Certificaciones", valores.get("certificaciones")),
        ("Ámbito geográfico", valores.get("ambito")),
    ]
    cifra = numero(valores.get("cifra_negocio"))
    if cifra:
        euros = f"{cifra:,.0f}".replace(",", ".")
        secciones.append(("Cifra anual de negocio", f"{euros} euros, declarada por la empresa"))

    partes = [f"# {valores.get('alias', 'Empresa')}", ""]
    for titulo, contenido in secciones:
        if contenido:
            partes += [f"## {titulo}", contenido.strip(), ""]
    return "\n".join(partes).strip() + "\n"


def huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


GUARDAR = """
INSERT INTO clientes (alias, nombre, correo, que_hace, productos, servicios, no_hace,
    certificaciones, ambito, cifra_negocio, cifra_fuente, tope_diario_eur, texto, texto_sha256)
VALUES (%(alias)s, %(nombre)s, %(correo)s, %(que_hace)s, %(productos)s, %(servicios)s,
    %(no_hace)s, %(certificaciones)s, %(ambito)s, %(cifra_negocio)s, %(cifra_fuente)s,
    %(tope_diario_eur)s, %(texto)s, %(texto_sha256)s)
ON CONFLICT (alias) DO UPDATE SET
    nombre = EXCLUDED.nombre, correo = EXCLUDED.correo, que_hace = EXCLUDED.que_hace,
    productos = EXCLUDED.productos, servicios = EXCLUDED.servicios, no_hace = EXCLUDED.no_hace,
    certificaciones = EXCLUDED.certificaciones, ambito = EXCLUDED.ambito,
    cifra_negocio = EXCLUDED.cifra_negocio, cifra_fuente = EXCLUDED.cifra_fuente,
    tope_diario_eur = EXCLUDED.tope_diario_eur, texto = EXCLUDED.texto,
    texto_sha256 = EXCLUDED.texto_sha256, actualizado_en = now()
RETURNING id, (xmax = 0) AS nuevo
"""


def dar_de_alta(valores: dict) -> dict:
    """Guarda o actualiza un cliente. Devuelve qué se ha hecho y con qué texto."""
    valores = limpiar(valores)
    errores = validar(valores)
    if errores:
        raise ErrorRadar(
            "El formulario tiene campos por corregir: " + "; ".join(sorted(errores)),
            detalle=str(errores),
        )
    texto = como_lo_lee_el_modelo(valores)
    fila = {
        **valores,
        "cifra_negocio": numero(valores.get("cifra_negocio")),
        "cifra_fuente": "declarada por la empresa en el alta" if valores.get("cifra_negocio") else None,
        "tope_diario_eur": numero(valores.get("tope_diario_eur")) or 1.00,
        "texto": texto,
        "texto_sha256": huella(texto),
    }
    for nombre in ("productos", "servicios", "no_hace", "certificaciones", "ambito"):
        fila[nombre] = fila.get(nombre) or None
    with conectar() as conexion, conexion.cursor() as cur:
        # El alias no puede ser el de una empresa del estudio: son aliases publicados en los
        # informes, y si coincidieran el cliente leería en su correo decisiones que no son
        # suyas. La base lo impide también (migración 012); aquí se dice con palabras.
        cur.execute("SELECT 1 FROM perfiles WHERE alias = %s", (valores["alias"],))
        if cur.fetchone():
            raise ErrorRadar(
                f"Ya hay una empresa que se llama «{valores['alias']}» en el radar. "
                "Hace falta otro nombre para los informes."
            )
        cur.execute(GUARDAR, fila)
        identificador, nuevo = cur.fetchone()
        conexion.commit()
    return {"id": identificador, "alias": valores["alias"], "nuevo": nuevo, "texto": texto}


# `de_alias` y `activos` vivían aquí y se han ido a `radar/empresas.py`. Eran una segunda forma
# de preguntar «¿quién es esta empresa?», con los mismos datos y otros nombres de campo, y eso
# ya costó un fallo: un diccionario de aquí llegó a una función que esperaba el de allí y se
# cayó con `KeyError: 'huella'`. Una sola forma de preguntarlo.
