"""Primer nodo del grafo: el triaje.

Mira una licitación tal y como se publicó en el feed (objeto, órgano, CPV, tipo de contrato) y el
perfil de la empresa, y dice si merece la pena abrir el pliego. Es el filtro barato: de aquí sale
la lista corta que después se lee de verdad.

Tres reglas gobiernan este módulo:

1. **El modelo clasifica; Python decide qué hacer con eso** (D09). Aquí no se interpreta el texto
   libre del modelo: se le exige un JSON con una decisión de una lista cerrada, y lo que no encaje
   no se adivina, se manda a revisar.
2. **Nada se pierde en silencio.** Si el modelo se deja una licitación sin contestar, o contesta
   algo que no es una decisión válida, esa licitación queda como `revisar` y se cuenta. Un triaje
   que pierde licitaciones sin avisar es peor que uno que falla.
3. **El triaje nunca ve quién ganó.** Lo que se le manda se arma en `como_se_ve()`, que solo toca
   campos del feed anteriores a la adjudicación.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from radar import llm, prompts
from radar.errores import ErrorRadar

PROMPT = "triaje_v1"
POR_LLAMADA = 20
# Sitio para la respuesta: unas 200 fichas por licitación, y un mínimo que deje razonar a los
# modelos que piensan por defecto. Quedarse corto devuelve texto vacío (ver llm.RespuestaCortada).
TOKENS_POR_LICITACION = 220
TOKENS_MINIMOS = 900

DECISIONES = ("si", "no", "duda")
REVISAR = "revisar"
# El modelo escribe en castellano: "sí" con tilde es lo natural, y es la misma decisión.
EQUIVALENTES = {"si": "si", "sí": "si", "no": "no", "duda": "duda"}


class TriajeIlegible(ErrorRadar):
    """El modelo no ha devuelto un JSON del que se pueda sacar ninguna decisión."""


class PerfilCambiado(ErrorRadar):
    """El texto del perfil no coincide con la huella con la que se congeló."""


@dataclass
class Respuesta:
    """Lo que se ha entendido de una llamada de triaje."""

    decisiones: dict[str, tuple[str, str]] = field(default_factory=dict)
    faltan: list[str] = field(default_factory=list)
    inventadas: list[str] = field(default_factory=list)
    # Si la respuesta no se pudo leer en absoluto, el motivo legible. Las licitaciones de esa
    # llamada quedan todas en `faltan`, es decir, para mirar a mano.
    ilegible: str | None = None


def perfil_de(conexion, alias: str) -> str:
    """El perfil congelado de una empresa, comprobando que no se ha tocado.

    El candado es el mismo que en `radar/perfiles.py`: si el texto no cuadra con su sha256, algo
    ha cambiado después de medir y hay que volver a medir, no seguir como si nada.
    """
    with conexion.cursor() as cur:
        cur.execute("SELECT texto, texto_sha256 FROM perfiles WHERE alias = %s", (alias,))
        fila = cur.fetchone()
    if not fila:
        raise ErrorRadar(f"No hay ninguna empresa con el alias «{alias}» en la tabla perfiles.")
    texto, huella = fila
    if not texto or not huella:
        raise ErrorRadar(
            f"El perfil de {alias} no está congelado todavía. Antes de triar nada: "
            "uv run python -m radar.perfiles --congelar"
        )
    if hashlib.sha256(texto.encode("utf-8")).hexdigest() != huella:
        raise PerfilCambiado(
            f"El perfil de {alias} no coincide con la huella con la que se congeló. Eso obliga a "
            "volver a medir todo lo que se haya medido con él: no se tría hasta aclararlo."
        )
    return texto


def como_se_ve(licitacion: dict) -> str:
    """Lo que el modelo ve de una licitación. Solo campos del feed, nunca el adjudicatario."""
    cpv = ", ".join(licitacion.get("cpv") or []) or "sin CPV"
    lineas = [
        f"Objeto: {(licitacion.get('objeto') or '(sin objeto)').strip()}",
        f"Órgano: {(licitacion.get('organo') or '(sin órgano)').strip()}",
        f"CPV: {cpv}",
    ]
    if licitacion.get("tipo_contrato"):
        lineas.append(f"Tipo de contrato: {licitacion['tipo_contrato']}")
    return "\n".join(lineas)


def sistema(perfil: str, prompt: prompts.Prompt | None = None) -> str:
    prompt = prompt or prompts.cargar(PROMPT)
    return f"{prompt.texto.rstrip()}\n\n{perfil.strip()}\n"


def mensaje(licitaciones: list[dict]) -> str:
    """Las licitaciones numeradas. La referencia es el número, no el expediente: gasta menos."""
    bloques = [f"### {i}\n{como_se_ve(lic)}" for i, lic in enumerate(licitaciones, start=1)]
    cabecera = (
        f"Estas son las {len(bloques)} licitaciones que hay que triar. Contesta con una decisión "
        "por cada una, con su misma ref."
        if len(bloques) > 1
        else "Esta es la licitación que hay que triar."
    )
    return f"{cabecera}\n\n" + "\n\n".join(bloques)


def json_de(texto: str) -> dict:
    """El JSON de la respuesta, aunque venga con vallas de código o una frase alrededor."""
    candidatos = [texto.strip()]
    for trozo in re.findall(r"```(?:json)?\s*(.+?)```", texto, re.S):
        candidatos.append(trozo.strip())
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
    raise TriajeIlegible(
        "El modelo no ha contestado con el formato que se le pidió, así que estas licitaciones "
        "quedan sin triar y hay que mirarlas a mano. No se ha descartado ninguna.",
        detalle=f"respuesta: {texto[:500]!r}",
    )


def interpretar(texto: str, refs: list[str]) -> Respuesta:
    """Saca las decisiones del texto del modelo. Lo que no sea válido no se adivina."""
    cuerpo = json_de(texto)
    lista = cuerpo.get("decisiones")
    if not isinstance(lista, list):
        raise TriajeIlegible(
            "El modelo ha contestado un JSON sin la lista de decisiones, así que estas "
            "licitaciones quedan sin triar y hay que mirarlas a mano.",
            detalle=f"claves: {list(cuerpo)[:10]}",
        )

    respuesta = Respuesta()
    esperadas = set(refs)
    for elemento in lista:
        if not isinstance(elemento, dict):
            continue
        ref = str(elemento.get("ref", "")).strip()
        decision = EQUIVALENTES.get(str(elemento.get("decision", "")).strip().lower())
        if ref not in esperadas:
            respuesta.inventadas.append(ref)
            continue
        if not decision or ref in respuesta.decisiones:
            continue  # sin decisión válida, o repetida: se queda sin contestar y se ve más abajo
        respuesta.decisiones[ref] = (decision, str(elemento.get("motivo", "")).strip())
    respuesta.faltan = [r for r in refs if r not in respuesta.decisiones]
    return respuesta


def triar(
    perfil: str,
    licitaciones: list[dict],
    modelo: str | None = None,
    esfuerzo: str = "low",
    prompt: prompts.Prompt | None = None,
    api=None,
    run_id=None,
) -> tuple[Respuesta, dict, prompts.Prompt]:
    """Tría un grupo de licitaciones en una sola llamada. Devuelve (respuesta, ficha, prompt)."""
    if not licitaciones:
        raise ErrorRadar("No hay ninguna licitación que triar.")
    prompt = prompt or prompts.cargar(PROMPT)
    refs = [str(i) for i in range(1, len(licitaciones) + 1)]
    respuesta, ficha = llm.llamar(
        nodo="triaje",
        mensajes=[{"role": "user", "content": mensaje(licitaciones)}],
        modelo=modelo,
        sistema=sistema(perfil, prompt),
        max_tokens=max(TOKENS_MINIMOS, TOKENS_POR_LICITACION * len(licitaciones)),
        esfuerzo=esfuerzo,
        prompt_version=f"{prompt.nombre}_{prompt.version}",
        run_id=run_id,
        licitacion=licitaciones[0]["id"] if len(licitaciones) == 1 else None,
        api=api,
    )
    try:
        entendida = interpretar(llm.texto_de(respuesta), refs)
    except TriajeIlegible as e:
        # La llamada ya está pagada y apuntada. Devolver el fallo en lugar de levantarlo deja que
        # quien llame decida: el experimento lo cuenta, y el grafo diario abrirá una incidencia.
        entendida = Respuesta(faltan=list(refs), ilegible=e.mensaje)
    return entendida, ficha, prompt


def guardar(
    conexion,
    alias: str,
    licitaciones: list[dict],
    respuesta: Respuesta,
    ficha: dict,
    prompt: prompts.Prompt,
    por_llamada: int,
    run_id=None,
) -> int:
    """Apunta una decisión por licitación. Lo que el modelo no contestó queda como 'revisar'."""
    filas = []
    for i, lic in enumerate(licitaciones, start=1):
        decision, motivo = respuesta.decisiones.get(str(i), (REVISAR, "El modelo no la contestó."))
        filas.append(
            (
                lic["id"],
                alias,
                ficha["modelo"],
                ficha.get("esfuerzo"),
                por_llamada,
                f"{prompt.nombre}_{prompt.version}",
                decision,
                motivo[:1000],
                ficha.get("id"),
                run_id,
            )
        )
    with conexion.cursor() as cur:
        cur.executemany(
            "INSERT INTO triajes (licitacion, alias, modelo, esfuerzo, por_llamada,"
            " prompt_version, decision, motivo, llm_llamada, run_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (licitacion, alias, modelo, por_llamada, prompt_version) DO NOTHING",
            filas,
        )
    conexion.commit()
    return len(filas)
