"""El grafo del agente: de una licitación candidata a una ficha con su evidencia.

LangGraph está aquí por lo que aporta de verdad (D04): **ramas condicionales y un paso a paso
que se guarda**. Cada nodo deja su huella en el checkpointer de Postgres, así que si el proceso
se cae a la mitad de un pliego se puede ver en qué paso estaba y por qué.

    documento ──► localizar ──► extraer ──► decidir ──► ficha
        │             │            │
        └─────────────┴────────────┴──────────► ficha (con el motivo escrito)

Las tres flechas de abajo son las ramas que importan, y son el motivo de que el grafo exista:

1. **No hay pliego descargado** para ese expediente.
2. **El pliego no tiene sección de solvencia** ni cuadro resumen, o es un escaneado sin texto.
3. **El modelo no contestó algo que se pueda usar**, ni al segundo intento.

En los tres casos el expediente **no se descarta**: sale una ficha que dice «revisar» con el
motivo en castellano. Descartar en silencio es el fallo que este proyecto no se permite.

Cada paso decide con lo que tiene delante; el modelo solo entra en `extraer`, y lo que devuelve
pasa por la comprobación de la cita antes de que `decidir` lo mire.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from radar import documentos, empresas, extraccion, llm, localizar, prompts, reglas
from radar.bd import cadena_conexion, conectar
from radar.errores import DocumentoIlegible, ErrorRadar

SIN_PLIEGO = "sin_pliego"
# Un pliego puede remitir a un anexo; ese anexo ya no remite a ningún sitio. Con un salto
# basta, y con más el coste por expediente dejaría de estar acotado.
SALTOS_MAXIMOS = 1


class Estado(TypedDict, total=False):
    """Lo que se pasan los nodos.

    Sin reductores a propósito: en un TypedDict de LangGraph, cada clave sin reductor se
    sobrescribe con lo último que escriba un nodo, que es justo lo que hace falta aquí. Poner
    `Annotated[object, ...]` costó un rato de depuración: LangGraph inicializa esos canales
    con el valor por defecto del tipo, así que `run_id` llegaba a la base como `object()` en
    lugar de `None` y el INSERT de la llamada al modelo fallaba **después** de pagarla.
    """

    licitacion: int
    alias: str
    empresa: dict
    run_id: object | None
    documento: int | None
    ruta: str | None
    paginas_totales: int | None
    via: str | None
    paginas: list[int]  # las que se van a leer o se han leído: números, no texto
    lecturas: list  # un diccionario por pasada: la cláusula y, si hace falta, el anexo
    saltos: int  # cuántas veces se ha seguido un «remite». Tope: UN salto
    estado: str
    motivo: str | None
    veredicto: str | None
    motivos: list
    por_leer: list[int] | None  # las páginas de la pasada que toca (el anexo, si hubo salto)
    encontrado_el_anexo: bool
    lectura: int | None
    ficha: int | None


PLIEGO = """
SELECT d.id, r.ruta, d.paginas
FROM documentos d
JOIN raw_ficheros r ON r.sha256 = d.raw_fichero
JOIN licitaciones mia ON mia.id = %s
JOIN licitaciones suya ON suya.id = d.licitacion AND suya.entry_id = mia.entry_id
WHERE d.tipo = 'PCAP' AND d.estado_descarga = 'descargado'
ORDER BY d.paginas DESC NULLS LAST, d.id
LIMIT 1
"""


def nodo_documento(estado: Estado) -> dict:
    """Busca el PCAP descargado del expediente. Vale el de cualquier versión: es el mismo pliego."""
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(PLIEGO, (estado["licitacion"],))
        fila = cur.fetchone()
    if not fila:
        return {
            "estado": SIN_PLIEGO,
            "motivo": (
                "No hay pliego descargado de este expediente, así que no se ha podido leer nada. "
                "Puede que el enlace del anuncio no funcione o que el documento no sea un PDF."
            ),
        }
    documento, ruta, paginas = fila
    return {"documento": documento, "ruta": ruta, "paginas_totales": paginas}


def nodo_localizar(estado: Estado) -> dict:
    try:
        encontrado = localizar.localizar(Path(estado["ruta"]).read_bytes())
    except DocumentoIlegible as e:
        return {"estado": "ilegible", "via": "no_localizada", "motivo": e.mensaje}
    except OSError:
        return {
            "estado": "ilegible",
            "via": "no_localizada",
            "motivo": (
                "El fichero del pliego no está donde debería en el disco. Se puede volver a "
                "descargar con: uv run python -m radar.pliegos --del-triaje"
            ),
        }
    if not encontrado.hay_que_leer:
        return {"estado": "sin_localizar", "via": encontrado.via, "motivo": encontrado.motivo}
    return {
        "via": encontrado.via,
        "paginas": encontrado.numeros(),
        "motivo": encontrado.motivo or None,
    }


def paginas_para_leer(estado: Estado) -> localizar.Localizacion:
    """Rearma lo que hay que leer a partir del fichero y de los números de página.

    El texto de las páginas no viaja en el estado a propósito: el estado se guarda en Postgres
    y son 20 KB por pliego que ya están en el disco. Volver a abrir el PDF es gratis.
    """
    paginas = dict(documentos.paginas_de(Path(estado["ruta"]).read_bytes()))
    quiere = estado.get("por_leer") or estado.get("paginas") or []
    return localizar.Localizacion(
        via=estado.get("via") or "solvencia",
        paginas=[(n, paginas[n]) for n in quiere if n in paginas],
    )


def nodo_extraer(estado: Estado) -> dict:
    leido = extraccion.extraer(
        paginas_para_leer(estado),
        run_id=estado.get("run_id"),
        licitacion=estado["licitacion"],
    )
    lecturas = [*(estado.get("lecturas") or []), extraccion.como_datos(leido)]
    if leido.ilegible and not requisitos_de(lecturas):
        return {"estado": "ilegible_respuesta", "lecturas": lecturas, "motivo": leido.ilegible}
    return {"estado": "leido", "lecturas": lecturas, "por_leer": None}


def requisitos_de(lecturas: list) -> list:
    """Todos los requisitos verificados, de las dos pasadas si hubo dos."""
    return [r for datos in lecturas or [] for r in extraccion.desde_datos(datos)]


def nodo_anexo(estado: Estado) -> dict:
    """El pliego no decía los requisitos: remite a un anexo. Se busca ese anexo y se lee.

    Es la rama `ANX` del grafo de `docs/SPEC.md` §4, y en los pliegos reales es el caso
    frecuente: la cláusula dice «la solvencia exigida es la del Anexo Nº 1» y las cifras están
    en ese anexo. Sin esta rama, la mayoría de los expedientes acabarían en «revisar» teniendo
    el dato a veinte páginas de distancia.

    Un solo salto: si el anexo remite a otro sitio, se para y va a una persona.
    """
    citas = [r.cita for r in requisitos_de(estado.get("lecturas")) if r.tipo == "remite"]
    anexo = localizar.anexo_citado(citas)
    ya_leidas = set(estado.get("paginas") or [])
    if not anexo:
        return {"saltos": estado.get("saltos", 0) + 1}
    encontrado = localizar.localizar_anexo(Path(estado["ruta"]).read_bytes(), anexo, ya_leidas)
    if not encontrado.hay_que_leer:
        return {"saltos": estado.get("saltos", 0) + 1, "motivo": encontrado.motivo}
    return {
        "saltos": estado.get("saltos", 0) + 1,
        "via": f"{estado.get('via')}+anexo",
        "paginas": sorted(ya_leidas | set(encontrado.numeros())),
        "por_leer": encontrado.numeros(),
        "encontrado_el_anexo": True,
        "motivo": encontrado.motivo,
    }


def nodo_decidir(estado: Estado) -> dict:
    version = reglas.cargar(reglas.VERSION_ACTUAL)
    decision = version.evaluar(requisitos_de(estado.get("lecturas")), estado["empresa"])
    return {
        "veredicto": decision.veredicto,
        "motivos": [vars(m) for m in decision.motivos],
    }


def nodo_ficha(estado: Estado) -> dict:
    """Guarda la lectura, los requisitos (verificados y no) y la ficha con su decisión."""
    lecturas = estado.get("lecturas") or []
    with conectar() as conexion:
        lectura = None
        if estado.get("documento"):
            lectura = guardar_lectura(conexion, estado, lecturas)
        veredicto = estado.get("veredicto") or reglas.cargar().REVISAR
        motivos = estado.get("motivos") or [
            {
                "tipo": "ninguno",
                "resultado": reglas.cargar().NO_SE_SABE,
                "texto": estado.get("motivo") or "No se ha podido leer el pliego.",
                "cita": "",
                "pagina": None,
            }
        ]
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO fichas (licitacion, alias, lectura, veredicto, reglas_version,"
                " motivos, run_id) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (licitacion, alias, reglas_version, lectura) DO UPDATE"
                " SET veredicto = excluded.veredicto, motivos = excluded.motivos,"
                " creada_en = now() RETURNING id",
                (
                    estado["licitacion"],
                    estado["alias"],
                    lectura,
                    veredicto,
                    reglas.VERSION_ACTUAL,
                    json.dumps(motivos, ensure_ascii=False),
                    estado.get("run_id"),
                ),
            )
            ficha = cur.fetchone()[0]
        conexion.commit()
    return {"lectura": lectura, "ficha": ficha, "veredicto": veredicto, "motivos": motivos}


def guardar_lectura(conexion, estado: Estado, lecturas: list) -> int:
    prompt = prompts.cargar(extraccion.PROMPT)
    version = f"{prompt.nombre}_{prompt.version}"
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO lecturas (documento, licitacion, alias, via, paginas, paginas_totales,"
            " modelo, prompt_version, estado, motivo, intentos, run_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (documento, alias, prompt_version) DO UPDATE"
            " SET via = excluded.via, paginas = excluded.paginas, estado = excluded.estado,"
            " motivo = excluded.motivo, intentos = excluded.intentos, leida_en = now()"
            " RETURNING id",
            (
                estado["documento"],
                estado["licitacion"],
                estado["alias"],
                estado.get("via") or "no_localizada",
                estado.get("paginas") or [],
                estado.get("paginas_totales"),
                extraccion.MODELO,
                version,
                estado.get("estado", "sin_localizar"),
                estado.get("motivo"),
                sum(len(leido.get("llamadas") or []) for leido in lecturas) or 1,
                estado.get("run_id"),
            ),
        )
        lectura = cur.fetchone()[0]
        # Los requisitos se rehacen: una lectura repetida no deja los de la vez anterior.
        cur.execute("DELETE FROM requisitos WHERE lectura = %s", (lectura,))
        for leido in lecturas:
            llamadas = [i for i in leido.get("llamadas") or [] if i]
            llamada = llamadas[-1] if llamadas else None
            for r in extraccion.desde_datos(leido):
                cur.execute(
                    "INSERT INTO requisitos (lectura, tipo, exigencia, importe_eur, anios, cita,"
                    " pagina, verificada, llm_llamada) VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s)",
                    (lectura, r.tipo, r.exigencia, r.importe_eur, r.anios, r.cita, r.pagina, llamada),
                )
            for r in leido.get("rechazados") or []:
                cur.execute(
                    "INSERT INTO requisitos (lectura, tipo, exigencia, cita, pagina, verificada,"
                    " motivo_rechazo, llm_llamada) VALUES (%s, %s, NULL, %s, %s, false, %s, %s)",
                    (
                        lectura,
                        r.get("tipo") or "desconocido",
                        r.get("cita") or "",
                        r.get("pagina"),
                        r.get("motivo"),
                        llamada,
                    ),
                )
    conexion.commit()
    return lectura


def hay_pliego(estado: Estado) -> str:
    return "ficha" if estado.get("estado") == SIN_PLIEGO else "localizar"


def hay_que_leer(estado: Estado) -> str:
    return "ficha" if estado.get("estado") in ("sin_localizar", "ilegible") else "extraer"


def se_ha_entendido(estado: Estado) -> str:
    if estado.get("estado") == "ilegible_respuesta":
        return "ficha"
    return "anexo" if hay_que_seguir_el_remite(estado) else "decidir"


def hay_que_seguir_el_remite(estado: Estado) -> bool:
    """Se sigue el «remite» solo si no hay ninguna cifra y no se ha saltado ya una vez."""
    if estado.get("saltos", 0) >= SALTOS_MAXIMOS:
        return False
    requisitos = requisitos_de(estado.get("lecturas"))
    if not any(r.tipo == "remite" for r in requisitos):
        return False
    return not any(r.importe_eur for r in requisitos)


def se_ha_encontrado_el_anexo(estado: Estado) -> str:
    """Si el anexo no apareció, se decide con lo que haya; nunca se da otra vuelta."""
    return "extraer" if estado.get("encontrado_el_anexo") else "decidir"


def construir(checkpointer=None):
    """El grafo. Sin checkpointer también funciona: así los tests no necesitan Postgres."""
    grafo = StateGraph(Estado)
    grafo.add_node("documento", nodo_documento)
    grafo.add_node("localizar", nodo_localizar)
    grafo.add_node("extraer", nodo_extraer)
    grafo.add_node("anexo", nodo_anexo)
    grafo.add_node("decidir", nodo_decidir)
    grafo.add_node("ficha", nodo_ficha)

    grafo.add_edge(START, "documento")
    grafo.add_conditional_edges("documento", hay_pliego, ["localizar", "ficha"])
    grafo.add_conditional_edges("localizar", hay_que_leer, ["extraer", "ficha"])
    grafo.add_conditional_edges("extraer", se_ha_entendido, ["decidir", "anexo", "ficha"])
    grafo.add_conditional_edges("anexo", se_ha_encontrado_el_anexo, ["extraer", "decidir"])
    grafo.add_edge("decidir", "ficha")
    grafo.add_edge("ficha", END)
    return grafo.compile(checkpointer=checkpointer)


def empresa_de(conexion, alias: str) -> dict:
    """Lo que el grafo necesita saber de la empresa: su texto y su cifra de negocio.

    Da igual que sea un cliente o una empresa del estudio (`radar/empresas.py`).
    """
    empresa = empresas.la_de(conexion, alias)
    return {
        "alias": empresa["alias"],
        "perfil": empresa["texto"],
        "cifra_negocio": empresa["cifra_negocio"],
        "cifra_fuente": empresa["cifra_fuente"],
    }


def analizar(licitacion: int, alias: str, run_id=None, checkpointer=None, empresa: dict | None = None):
    """Una licitación, una empresa, una ficha. Devuelve el estado final del grafo."""
    if empresa is None:
        with conectar() as conexion:
            empresa = empresa_de(conexion, alias)
    agente = construir(checkpointer)
    # Cada análisis empieza de cero, aunque el checkpointer tenga guardado el de la vez
    # anterior. El `thread_id` es `licitacion:empresa:reglas`, así que volver a leer el mismo
    # pliego reanudaba aquel estado y `nodo_extraer` sumaba los requisitos nuevos a los viejos:
    # la ficha salía con el mismo requisito repetido una vez por lectura, y el correo decía «de
    # 4 requisitos leídos, 4 cumplen» de un pliego que tenía uno. Descubierto el 28-09-2026.
    #
    # Lo que se pierde es reanudar una lectura cortada a la mitad sin volver a pagarla; lo que
    # se gana es que nunca se repita un requisito. Repetir una extracción cuesta unos céntimos
    # y pasa solo si el proceso se cayó; una ficha con el mismo requisito cuatro veces la lee
    # el cliente. El paso a paso sigue guardándose, que es para lo que está (D04).
    entrada = {
        "licitacion": licitacion,
        "alias": alias,
        "empresa": empresa,
        "run_id": run_id,
        "paginas": [],
        "lecturas": [],
        "saltos": 0,
        "por_leer": None,
        "encontrado_el_anexo": False,
        "motivo": None,
        "veredicto": None,
        "motivos": [],
    }
    configuracion = {"configurable": {"thread_id": f"{licitacion}:{alias}:{reglas.VERSION_ACTUAL}"}}
    return agente.invoke(entrada, configuracion)


def checkpointer_de_postgres():
    """El checkpointer de LangGraph sobre la misma base. Crea sus tablas la primera vez.

    Son tablas suyas (`checkpoints`, `checkpoint_writes`…), no del radar: las gestiona
    LangGraph y no se tocan a mano.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    return PostgresSaver.from_conn_string(cadena_conexion())


def coste_de(estado) -> float:
    """Lo que ha costado analizar una licitación, en euros, de las llamadas que se hicieron.

    Lee del estado, que solo lleva datos planos. La versión anterior hacía `leido.llamadas`
    sobre un objeto, y al reanudar un expediente ya empezado el checkpointer devolvía ese
    objeto convertido en diccionario: `AttributeError` a mitad de una tanda, con lo pagado ya
    guardado pero la tanda cortada. Está en la incidencia 3 del 27-09-2026.
    """
    return sum(float(leido.get("coste_eur") or 0) for leido in estado.get("lecturas") or [])


__all__ = ["analizar", "construir", "checkpointer_de_postgres", "coste_de", "llm"]


CABECERA = """
SELECT l.expediente, l.objeto, l.organo, l.plazo_presentacion, l.importe_sin_iva
FROM licitaciones l WHERE l.id = %s
"""


def como_se_lee(estado: dict) -> str:
    """La ficha en texto, para leerla en la terminal.

    Es la misma información que llevará el correo de la Fase 7: qué licitación es, qué se ha
    decidido, y por cada requisito la frase del pliego y su página. Sin adornos: quien la lee
    tiene que poder ir al PDF y comprobarlo.
    """
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(CABECERA, (estado["licitacion"],))
        expediente, objeto, organo, plazo, importe = cur.fetchone()

    veredicto = {
        "apta": "PUEDE PRESENTARSE",
        "no_apta": "NO PUEDE PRESENTARSE",
        "revisar": "HAY QUE REVISARLO A MANO",
    }.get(estado.get("veredicto"), "SIN DECIDIR")

    lineas = [
        "",
        f"{veredicto}   ·   {estado.get('alias')}",
        "",
        f"  Expediente   {expediente or '(sin número)'}",
        f"  Objeto       {(objeto or '').strip()[:300]}",
        f"  Órgano       {(organo or '').strip()}",
    ]
    if importe:
        lineas.append(f"  Importe      {float(importe):,.2f} EUR".replace(",", "."))
    if plazo:
        lineas.append(f"  Plazo        {plazo}")
    paginas = estado.get("paginas") or []
    if paginas:
        lineas.append(
            f"  Leído        páginas {', '.join(str(p) for p in paginas)} de "
            f"{estado.get('paginas_totales')} del pliego"
        )
    lineas.append(f"  Coste        {coste_de(estado):.4f} EUR")

    etiquetas = {"cumple": "cumple", "no_cumple": "NO CUMPLE", "no_se_puede_saber": "por comprobar"}
    lineas += ["", "  Requisitos del pliego:"]
    for motivo in estado.get("motivos") or []:
        lineas.append(f"    [{etiquetas.get(motivo['resultado'], motivo['resultado'])}] {motivo['texto']}")
        if motivo.get("cita"):
            cita = " ".join(motivo["cita"].split())
            lineas.append(f"        pág. {motivo.get('pagina')}: «{cita[:160]}»")
    return "\n".join(lineas) + "\n"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Lee el pliego de una licitación para una empresa")
    parser.add_argument("--licitacion", type=int, required=True)
    parser.add_argument("--empresa", required=True, help='alias, por ejemplo "Empresa A"')
    args = parser.parse_args()
    try:
        with checkpointer_de_postgres() as guardador:
            guardador.setup()
            estado = analizar(args.licitacion, args.empresa, checkpointer=guardador)
        print(como_se_lee(estado))
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
