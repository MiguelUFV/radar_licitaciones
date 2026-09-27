"""La única puerta al modelo.

Ningún otro módulo llama al SDK de Anthropic (CLAUDE.md, innegociable 7). Aquí se cuentan los
tokens, se calcula el coste en dólares y en euros, se comprueba el presupuesto **antes** de
gastar y queda todo en la tabla `llm_llamadas`, con la respuesta íntegra para poder rehacer la
evaluación sin volver a pagar.

Precios oficiales por millón de tokens, consultados el 27-09-2026:

| Modelo             | Entrada | Salida |
|--------------------|---------|--------|
| `claude-opus-5`    | 5,00 $  | 25,00 $|
| `claude-sonnet-5`  | 2,00 $  | 10,00 $|
| `claude-haiku-4-5` | 1,00 $  | 5,00 $ |

Escribir en la caché cuesta 1,25 veces la entrada; leerla, 0,1 veces. La Batch API, la mitad.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import date

from dotenv import load_dotenv

from radar.bd import conectar
from radar.errores import ErrorRadar, FaltaConfiguracion

# USD por millón de tokens y qué admite cada modelo.
#
# El esfuerzo no vale para todos: Haiku 4.5 devuelve "This model does not support the effort
# parameter" (400), comprobado contra la API el 27-09-2026 en la primera llamada real. Y es
# justo el modelo con el que se compara el triaje (D06), así que no es un detalle.
MODELOS = {
    "claude-opus-5": {"entrada": 5.00, "salida": 25.00, "esfuerzo": True},
    "claude-sonnet-5": {"entrada": 2.00, "salida": 10.00, "esfuerzo": True},
    "claude-haiku-4-5": {"entrada": 1.00, "salida": 5.00, "esfuerzo": False},
}
PRECIOS = {nombre: (d["entrada"], d["salida"]) for nombre, d in MODELOS.items()}
POR_MILLON = 1_000_000
ESCRITURA_CACHE = 1.25
LECTURA_CACHE = 0.10
DESCUENTO_BATCH = 0.50
# Ningún modelo del proyecto usa `budget_tokens`: en Opus 5 y Sonnet 5 devuelve un 400. La
# profundidad se controla con el esfuerzo.
ESFUERZOS = ("low", "medium", "high", "xhigh", "max")


class PresupuestoAgotado(ErrorRadar):
    """Se ha alcanzado el tope de gasto del día. No se llama al modelo."""


class RespuestaCortada(ErrorRadar):
    """El modelo se quedó sin tokens antes de escribir nada."""


class ModeloDesconocido(ErrorRadar):
    """Un modelo sin precio en la tabla: no se puede saber lo que cuesta, así que no se usa."""


@dataclass
class Uso:
    entrada: int = 0
    salida: int = 0
    cache_escritura: int = 0
    cache_lectura: int = 0

    @classmethod
    def de_la_respuesta(cls, usage) -> Uso:
        return cls(
            entrada=getattr(usage, "input_tokens", 0) or 0,
            salida=getattr(usage, "output_tokens", 0) or 0,
            cache_escritura=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_lectura=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )


def precio_de(modelo: str) -> tuple[float, float]:
    if modelo not in PRECIOS:
        raise ModeloDesconocido(
            f"El modelo «{modelo}» no tiene precio en la tabla de radar/llm.py, así que no se "
            "puede saber cuánto cuesta una llamada. Añádelo antes de usarlo.",
            detalle=f"conocidos: {', '.join(PRECIOS)}",
        )
    return PRECIOS[modelo]


def acepta_esfuerzo(modelo: str) -> bool:
    """Si el modelo admite `output_config.effort`. Mandárselo a quien no lo admite es un 400."""
    return bool(MODELOS.get(modelo, {}).get("esfuerzo"))


def coste_usd(modelo: str, uso: Uso, batch: bool = False) -> float:
    """Lo que cuesta una llamada, en dólares, con la caché y el descuento de batch aplicados."""
    entrada, salida = precio_de(modelo)
    total = (
        uso.entrada * entrada
        + uso.cache_escritura * entrada * ESCRITURA_CACHE
        + uso.cache_lectura * entrada * LECTURA_CACHE
        + uso.salida * salida
    ) / POR_MILLON
    return total * (DESCUENTO_BATCH if batch else 1.0)


def tipo_de_cambio() -> tuple[float, str]:
    """Cuántos euros vale un dólar, y de dónde sale ese número.

    Primero se busca el del día en la tabla `tipos_cambio`. Si no está, se usa el de `.env`,
    que lleva su fuente y su fecha escritas al lado. Nunca se inventa: el coste en euros es
    una cifra que se publica.
    """
    try:
        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute("SELECT usd_eur, origen FROM tipos_cambio WHERE fecha = %s", (date.today(),))
            fila = cur.fetchone()
            if fila:
                return float(fila[0]), fila[1]
    except ErrorRadar:
        pass  # sin base de datos se usa el de .env; el fallo de la base ya se verá al registrar

    load_dotenv()
    valor = os.getenv("TIPO_CAMBIO_USD_EUR")
    origen = os.getenv("TIPO_CAMBIO_ORIGEN", "TIPO_CAMBIO_USD_EUR de .env")
    if not valor:
        raise FaltaConfiguracion(
            "Falta TIPO_CAMBIO_USD_EUR en .env. Sin el cambio no se puede decir lo que cuesta "
            "una ejecución en euros, y ese dato se publica."
        )
    return float(valor), origen


def presupuesto_diario() -> float:
    load_dotenv()
    valor = os.getenv("PRESUPUESTO_DIARIO_EUR")
    if not valor:
        raise FaltaConfiguracion(
            "Falta PRESUPUESTO_DIARIO_EUR en .env. Sin tope de gasto no se llama al modelo."
        )
    return float(valor)


def gastado_hoy(conexion) -> float:
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT coalesce(sum(coste_eur), 0) FROM llm_llamadas"
            " WHERE llamada_en >= date_trunc('day', now())"
        )
        return float(cur.fetchone()[0])


def comprobar_presupuesto(conexion, coste_previsto_eur: float) -> None:
    tope = presupuesto_diario()
    gastado = gastado_hoy(conexion)
    if gastado + coste_previsto_eur > tope:
        raise PresupuestoAgotado(
            f"El radar ha gastado hoy {gastado:.2f} € y esta llamada costaría hasta "
            f"{coste_previsto_eur:.2f} €, que pasa del tope de {tope:.2f} € al día. No se llama "
            "al modelo. Si hace falta más, súbelo en PRESUPUESTO_DIARIO_EUR."
        )


def cliente():
    """El cliente del SDK. Es lo único que toca la clave."""
    load_dotenv()
    clave = os.getenv("ANTHROPIC_API_KEY")
    if not clave or not clave.startswith("sk-ant-"):
        raise FaltaConfiguracion(
            "Falta la clave de Anthropic en el fichero .env (ANTHROPIC_API_KEY), o lo que hay "
            "no es una clave: empiezan por sk-ant-."
        )
    import anthropic

    return anthropic.Anthropic(api_key=clave)


def contar_tokens(modelo: str, mensajes: list[dict], sistema: str | None = None, api=None) -> int:
    """Cuántos tokens de entrada tiene una petición. Es gratis, así que se usa para presupuestar."""
    api = api or cliente()
    peticion = {"model": modelo, "messages": mensajes}
    if sistema:
        peticion["system"] = sistema
    return api.messages.count_tokens(**peticion).input_tokens


def registrar(conexion, fila: dict) -> int:
    columnas = ", ".join(fila)
    huecos = ", ".join(["%s"] * len(fila))
    with conexion.cursor() as cur:
        cur.execute(
            f"INSERT INTO llm_llamadas ({columnas}) VALUES ({huecos}) RETURNING id",  # noqa: S608
            tuple(fila.values()),
        )
        identificador = cur.fetchone()[0]
    conexion.commit()
    return identificador


# Las columnas sin las que la contabilidad no sirve. Si la fila completa no entra en la tabla,
# se apunta al menos esto: lo que costó y qué la pidió.
IMPRESCINDIBLES = (
    "nodo",
    "modelo",
    "request_id",
    "tokens_entrada",
    "tokens_salida",
    "tokens_cache_escritura",
    "tokens_cache_lectura",
    "batch",
    "coste_usd",
    "coste_eur",
    "tipo_cambio",
    "tipo_cambio_origen",
    "latencia_ms",
    "stop_reason",
)


def comprobar_identificadores(run_id, licitacion) -> None:
    """Que lo que se va a guardar sea guardable, **antes** de pagar la llamada.

    Un identificador mal pasado no se descubría hasta el INSERT, que es después de gastar.
    """
    if run_id is not None and not isinstance(run_id, str | uuid.UUID):
        raise ErrorRadar(
            "El run_id de la llamada al modelo no es un identificador, así que no se podría "
            "apuntar el gasto. No se llama al modelo.",
            detalle=f"run_id={run_id!r}",
        )
    if licitacion is not None and not isinstance(licitacion, int):
        raise ErrorRadar(
            "El número de licitación de la llamada al modelo no es un número, así que no se "
            "podría apuntar el gasto. No se llama al modelo.",
            detalle=f"licitacion={licitacion!r}",
        )


def registrar_sin_perder_la_cuenta(conexion, fila: dict) -> tuple[int, str | None]:
    """Apunta la llamada; si la fila completa no entra, apunta lo imprescindible.

    El presupuesto del día se calcula sumando `llm_llamadas`, así que una llamada pagada y sin
    fila es gasto invisible: el radar creería que le queda más presupuesto del que le queda.
    """
    try:
        return registrar(conexion, fila), None
    except Exception as e:  # noqa: BLE001  cualquier fallo de la base, la cuenta no se pierde
        conexion.rollback()
        minima = {c: fila[c] for c in IMPRESCINDIBLES if c in fila}
        minima["nodo"] = f"{fila.get('nodo', '?')} (registro incompleto)"
        identificador = registrar(conexion, minima)
        return identificador, (
            "La llamada al modelo se ha hecho y se ha apuntado su coste, pero no se han podido "
            "guardar todos sus datos. Es un fallo del programa, no del modelo: avisa de esto."
            f" Detalle: {type(e).__name__}"
        )


def llamar(
    nodo: str,
    mensajes: list[dict],
    modelo: str | None = None,
    sistema: str | None = None,
    max_tokens: int = 16000,
    esfuerzo: str = "high",
    prompt_version: str | None = None,
    run_id=None,
    licitacion: int | None = None,
    api=None,
    **extra,
):
    """Llama al modelo, lo apunta todo y devuelve (respuesta, ficha de coste).

    Comprueba el presupuesto **antes** de gastar, contando los tokens de entrada (gratis) y
    suponiendo que la salida llega al máximo. Es la estimación pesimista a propósito: más vale
    negarse de más que gastar de más.
    """
    load_dotenv()
    modelo = modelo or os.getenv("MODELO_EXTRACCION", "claude-opus-5")
    precio_de(modelo)
    if acepta_esfuerzo(modelo) and esfuerzo not in ESFUERZOS:
        raise ErrorRadar(f"Esfuerzo «{esfuerzo}» desconocido. Válidos: {', '.join(ESFUERZOS)}.")

    comprobar_identificadores(run_id, licitacion)
    api = api or cliente()
    cambio, origen_cambio = tipo_de_cambio()

    with conectar() as conexion:
        entrada_prevista = contar_tokens(modelo, mensajes, sistema, api)
        previsto = Uso(entrada=entrada_prevista, salida=max_tokens)
        comprobar_presupuesto(conexion, coste_usd(modelo, previsto) * cambio)

        peticion = {
            "model": modelo,
            "max_tokens": max_tokens,
            "messages": mensajes,
            **extra,
        }
        if acepta_esfuerzo(modelo):
            # El esfuerzo sustituye al budget_tokens, que en estos modelos devuelve un 400.
            peticion["output_config"] = {"effort": esfuerzo}
        else:
            esfuerzo = None  # no se apunta un esfuerzo que no se ha usado
        if sistema:
            peticion["system"] = sistema

        arranque = time.monotonic()
        respuesta = api.messages.create(**peticion)
        latencia = int((time.monotonic() - arranque) * 1000)

        uso = Uso.de_la_respuesta(respuesta.usage)
        usd = coste_usd(modelo, uso, batch=bool(extra.get("batch")))
        ficha = {
            "nodo": nodo,
            "modelo": modelo,
            "esfuerzo": esfuerzo,
            "prompt_version": prompt_version,
            "prompt_sha256": hashlib.sha256((sistema or "").encode()).hexdigest() if sistema else None,
            "request_id": getattr(respuesta, "_request_id", None),
            "tokens_entrada": uso.entrada,
            "tokens_salida": uso.salida,
            "tokens_cache_escritura": uso.cache_escritura,
            "tokens_cache_lectura": uso.cache_lectura,
            "batch": bool(extra.get("batch")),
            "coste_usd": round(usd, 6),
            "coste_eur": round(usd * cambio, 6),
            "tipo_cambio": cambio,
            "tipo_cambio_origen": origen_cambio,
            "latencia_ms": latencia,
            "stop_reason": getattr(respuesta, "stop_reason", None),
            "respuesta": json.dumps(cuerpo_de(respuesta), ensure_ascii=False),
            "run_id": run_id,
            "licitacion": licitacion,
        }
        ficha["id"], aviso = registrar_sin_perder_la_cuenta(conexion, ficha)

    if aviso:
        raise ErrorRadar(aviso, detalle=f"nodo={nodo} modelo={modelo} id={ficha['id']}")

    # Opus 5 piensa por defecto, y el pensamiento gasta tokens de salida: con un max_tokens
    # corto se queda sin sitio y devuelve texto vacío. Se avisa, porque quien pidiera una
    # extracción recibiría "" y seguiría como si nada. La llamada ya queda apuntada: se pagó.
    if ficha["stop_reason"] == "max_tokens" and not texto_de(respuesta):
        raise RespuestaCortada(
            f"El modelo se ha quedado sin espacio antes de escribir nada (max_tokens="
            f"{max_tokens}). Sube max_tokens o baja el esfuerzo.",
            detalle=f"nodo={nodo} modelo={modelo} request_id={ficha['request_id']}",
        )
    return respuesta, ficha


def cuerpo_de(respuesta) -> dict:
    """La respuesta como diccionario, para guardarla entera."""
    for metodo in ("to_dict", "model_dump"):
        if hasattr(respuesta, metodo):
            try:
                return getattr(respuesta, metodo)()
            except Exception:  # noqa: BLE001  guardar la respuesta no puede tumbar la llamada
                continue
    return {"repr": repr(respuesta)}


def texto_de(respuesta) -> str:
    """El texto de la respuesta. Los bloques de pensamiento se ignoran: vienen vacíos."""
    trozos = []
    for bloque in getattr(respuesta, "content", []) or []:
        if getattr(bloque, "type", None) == "text":
            trozos.append(bloque.text)
    return "\n".join(trozos)
