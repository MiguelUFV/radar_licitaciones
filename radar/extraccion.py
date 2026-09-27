"""El modelo copia los requisitos del pliego; Python comprueba que la cita existe.

Esta es la pieza de la que depende que el proyecto sea creíble. Un modelo puede escribir un
requisito verosímil que el pliego no dice, y nadie lo notaría: la defensa es que **toda
extracción viene con una cita literal y una página, y la cita se busca en el texto de esa
página antes de usarla** (`docs/DECISIONES.md` D08).

Qué se acepta como «literal»: se comparan los textos después de normalizar espacios, guiones
de partición de palabra, comillas tipográficas y la forma unicode (NFKC). Nada más. Las
mayúsculas y las palabras se comparan tal cual, porque el modelo está copiando de un texto que
tiene delante: si cambia una palabra, no estaba copiando.

Un requisito cuya cita no aparece **no se usa**: se pide una segunda vez diciendo cuál falló y,
si vuelve a fallar, ese requisito queda como no verificado y el expediente va a una persona.
Nunca se guarda un requisito sin comprobar (métrica M5).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

from radar import llm, prompts
from radar.errores import ErrorRadar
from radar.localizar import Localizacion, como_se_manda

PROMPT = "extraccion_v1"
MODELO = "claude-opus-5"  # D06: un error aquí descarta un contrato que la empresa podía ganar
INTENTOS = 2
MAXIMO_REQUISITOS = 8
CITA_MINIMA, CITA_MAXIMA = 10, 400

TIPOS = (
    "volumen_negocios",
    "trabajos_similares",
    "certificaciones",
    "clasificacion",
    "habilitacion",
    "adscripcion",
    "remite",
    # Muy frecuente en contratos por procedimiento simplificado: el pliego dice que no exige
    # solvencia economica. Es una respuesta con evidencia, no una ausencia de datos, y cambia
    # la decision: sin este tipo, el 60 % de los pliegos acabaria en "revisar" sin motivo.
    "no_se_exige",
)

_ESPACIOS = re.compile(r"\s+")
_SOBRAN = str.maketrans(
    {
        "­": "",  # guion de partición invisible
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        " ": " ",
    }
)


class ExtraccionIlegible(ErrorRadar):
    """El modelo no devolvió un JSON del que se puedan sacar requisitos."""


@dataclass
class Requisito:
    tipo: str
    exigencia: str
    cita: str
    pagina: int
    importe_eur: float | None = None
    anios: int | None = None


@dataclass
class Extraccion:
    requisitos: list[Requisito] = field(default_factory=list)
    rechazados: list[dict] = field(default_factory=list)
    llamadas: list[dict] = field(default_factory=list)
    ilegible: str | None = None

    @property
    def verificadas(self) -> int:
        return len(self.requisitos)

    @property
    def total(self) -> int:
        return len(self.requisitos) + len(self.rechazados)


def normalizar(texto: str) -> str:
    """Lo que se ignora al comparar: forma unicode, espacios, guiones y comillas."""
    limpio = unicodedata.normalize("NFKC", texto or "").translate(_SOBRAN)
    return _ESPACIOS.sub(" ", limpio).strip()


def cita_esta_en(cita: str, texto_pagina: str) -> bool:
    cita = normalizar(cita)
    return bool(cita) and cita in normalizar(texto_pagina)


def json_de(texto: str) -> dict:
    candidatos = [texto.strip()]
    candidatos += [t.strip() for t in re.findall(r"```(?:json)?\s*(.+?)```", texto, re.S)]
    primero, ultimo = texto.find("{"), texto.rfind("}")
    if primero != -1 and ultimo > primero:
        candidatos.append(texto[primero : ultimo + 1])
    for candidato in candidatos:
        try:
            cuerpo = json.loads(candidato)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(cuerpo, dict):
            return cuerpo
    raise ExtraccionIlegible(
        "El modelo no ha contestado con el formato que se le pidió al leer el pliego, así que "
        "este expediente queda sin requisitos y hay que mirarlo a mano.",
        detalle=f"respuesta: {texto[:500]!r}",
    )


def motivo_del_rechazo(dato: dict, paginas: dict[int, str]) -> str | None:
    """Por qué no se puede usar un requisito. None significa que se puede usar."""
    if dato.get("tipo") not in TIPOS:
        return f"el tipo «{dato.get('tipo')}» no está en la lista de tipos de requisito"
    try:
        pagina = int(dato.get("pagina"))
    except (TypeError, ValueError):
        return "no dice en qué página está la cita"
    if pagina not in paginas:
        return f"dice que está en la página {pagina}, que no es una de las que se le enviaron"
    cita = str(dato.get("cita") or "")
    if len(normalizar(cita)) < CITA_MINIMA:
        return "la cita es demasiado corta para demostrar nada"
    if len(cita) > CITA_MAXIMA:
        return f"la cita tiene {len(cita)} caracteres y el máximo son {CITA_MAXIMA}"
    if not cita_esta_en(cita, paginas[pagina]):
        return f"la cita no aparece en el texto de la página {pagina}"
    return None


def como_numero(valor) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def interpretar(texto: str, paginas: dict[int, str]) -> tuple[list[Requisito], list[dict]]:
    """Separa lo que se puede usar de lo que no, con el motivo de cada rechazo."""
    lista = json_de(texto).get("requisitos")
    if not isinstance(lista, list):
        raise ExtraccionIlegible(
            "El modelo ha contestado un JSON sin la lista de requisitos, así que este "
            "expediente queda sin requisitos y hay que mirarlo a mano.",
            detalle=f"claves: {list(json_de(texto))[:10]}",
        )

    buenos: list[Requisito] = []
    rechazados: list[dict] = []
    for dato in lista[:MAXIMO_REQUISITOS]:
        if not isinstance(dato, dict):
            rechazados.append({"motivo": "el elemento no es un requisito", "dato": repr(dato)[:200]})
            continue
        motivo = motivo_del_rechazo(dato, paginas)
        if motivo:
            rechazados.append(
                {
                    "motivo": motivo,
                    "tipo": dato.get("tipo"),
                    "pagina": dato.get("pagina"),
                    "cita": str(dato.get("cita") or "")[:300],
                }
            )
            continue
        entero = como_numero(dato.get("anios"))
        buenos.append(
            Requisito(
                tipo=dato["tipo"],
                exigencia=str(dato.get("exigencia") or "").strip()[:500],
                cita=str(dato["cita"]).strip(),
                pagina=int(dato["pagina"]),
                importe_eur=como_numero(dato.get("importe_eur")),
                anios=int(entero) if entero else None,
            )
        )
    return buenos, rechazados


def aviso_de_reintento(rechazados: list[dict]) -> str:
    """Lo que se le dice al modelo en el segundo intento. Se le nombra lo que falló."""
    fallos = "\n".join(f"- {r['motivo']}: «{r.get('cita', '')[:120]}»" for r in rechazados)
    return (
        "La comprobación automática ha rechazado estos requisitos de tu respuesta anterior:\n"
        f"{fallos}\n\n"
        "Vuelve a darme la lista completa de requisitos. Copia las citas carácter a carácter del "
        "texto de la página que indicas: se comparan letra por letra, solo se ignoran los espacios "
        "y las comillas. Si una cita no puedes copiarla exacta, deja fuera ese requisito."
    )


def extraer(
    localizacion: Localizacion,
    modelo: str | None = None,
    esfuerzo: str = "high",
    prompt: prompts.Prompt | None = None,
    api=None,
    run_id=None,
    licitacion: int | None = None,
) -> Extraccion:
    """Pide los requisitos y solo devuelve los que tienen una cita comprobada."""
    if not localizacion.hay_que_leer:
        raise ErrorRadar("No hay páginas que leer en este pliego.")
    prompt = prompt or prompts.cargar(PROMPT)
    paginas = dict(localizacion.paginas)
    mensajes = [{"role": "user", "content": como_se_manda(localizacion)}]
    resultado = Extraccion()

    for intento in range(1, INTENTOS + 1):
        respuesta, ficha = llm.llamar(
            nodo="extraccion",
            mensajes=mensajes,
            modelo=modelo or MODELO,
            sistema=prompt.texto,
            # Medido: la respuesta de un pliego de 6 paginas son unas 1.700 fichas. 4.000 deja
            # holgura de mas del doble, y con 8.000 el freno del presupuesto se pasaba de
            # prudente y rechazaba llamadas de 0,07 EUR como si fueran de 0,21 EUR.
            max_tokens=4000,
            esfuerzo=esfuerzo,
            prompt_version=f"{prompt.nombre}_{prompt.version}",
            run_id=run_id,
            licitacion=licitacion,
            api=api,
        )
        resultado.llamadas.append(ficha)
        try:
            buenos, rechazados = interpretar(llm.texto_de(respuesta), paginas)
        except ExtraccionIlegible as e:
            # La llamada está pagada y apuntada. Se devuelve el fallo, no se levanta: el grafo
            # manda el expediente a revisión y lo cuenta.
            resultado.ilegible = e.mensaje
            return resultado

        resultado.requisitos, resultado.rechazados = buenos, rechazados
        if not rechazados or intento == INTENTOS:
            return resultado
        mensajes = [
            *mensajes,
            {"role": "assistant", "content": llm.texto_de(respuesta)},
            {"role": "user", "content": aviso_de_reintento(rechazados)},
        ]
    return resultado


def como_datos(leido: Extraccion) -> dict:
    """La lectura como tipos básicos, para que quepa en el checkpointer del grafo.

    El estado de LangGraph se guarda en Postgres, y guardar ahí objetos de Python es pedir que
    se rompa: la propia librería avisa de que dejará de deserializar clases desconocidas. Con
    diccionarios y listas, el paso a paso guardado se puede leer dentro de un año.
    """
    return {
        "requisitos": [vars(r) for r in leido.requisitos],
        "rechazados": leido.rechazados,
        "coste_eur": sum(float(f["coste_eur"]) for f in leido.llamadas),
        "llamadas": [f.get("id") for f in leido.llamadas],
        "ilegible": leido.ilegible,
    }


def desde_datos(datos: dict) -> list[Requisito]:
    """Los requisitos de una lectura guardada, otra vez como objetos, para las reglas."""
    return [Requisito(**dato) for dato in datos.get("requisitos", [])]
