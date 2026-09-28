"""El trabajo de cada mañana, cliente a cliente.

    uv run python -m radar.diario                     # qué hay que hacer y qué costaría
    uv run python -m radar.diario --gastar            # hacerlo
    uv run python -m radar.diario --empresa "Empresa del Norte" --gastar

Dos pasos por cliente, en este orden y no en otro:

1. **Triar** lo que se ha publicado y ese cliente todavía no ha visto. Es el filtro barato: una
   llamada por cada veinte licitaciones, con el texto que la empresa escribió en su alta.
2. **Leer el pliego** de las que pasaron el filtro, hasta donde llegue **su tope diario**.

El orden importa porque el triaje decide de qué expedientes se abre el pliego, que es lo caro.
Si el tope se agota, se agota leyendo pliegos, nunca triando: quedarse sin triar significa no
haber mirado una licitación que quizá era la buena.

**El tope es del cliente, no del radar.** Cada empresa lo pone en el formulario de alta y es lo
único que impide que un día con muchas licitaciones se coma su presupuesto. Antes de abrir un
pliego se comprueba que lo que queda da para uno; la reserva sale de lo que han costado los
pliegos ya leídos, no de una cifra inventada. Por encima sigue estando el tope global del
`.env`, que para el radar entero (`radar/llm.py`).

Un fallo en un expediente no para la mañana: se apunta en `incidencias` con su traza y se sigue
con el siguiente. Lo que no se llegue a hacer hoy sigue pendiente mañana, porque nada de esto
depende de la fecha: se busca lo que no está hecho.
"""

from __future__ import annotations

import argparse
from datetime import date

from radar import empresas, incidencias, llm, prompts, triaje
from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.grafo import analizar, checkpointer_de_postgres, coste_de
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion

# La configuración que ganó la medición de D06: Haiku en lotes de veinte. Las tres variantes
# acertaron lo mismo (24/24) y esta costó 4,7 veces menos.
MODELO = "claude-haiku-4-5"
ESFUERZO = "low"
PASAN = ("si", "duda")

# Cuántas licitaciones se tría como mucho en una pasada. No es un límite de dinero —el triaje de
# 400 licitaciones cuesta céntimos—, es un límite de tiempo: una mañana no puede quedarse
# colgada porque el histórico traiga miles.
TOPE_TRIAJE = 400

# Lo que se reserva para abrir un pliego cuando todavía no hay ninguno leído con el que
# calcularlo. Sale de la Fase 4: 0,070 € de media por pliego, 4,7 páginas leídas de 51,5.
RESERVA_INICIAL = 0.15

SIN_TRIAR = """
SELECT DISTINCT ON (v.entry_id) v.id, v.entry_id, v.objeto, v.organo, v.cpv, v.tipo_contrato
FROM v_licitaciones_vigentes v
WHERE NOT v.anulada
  AND (v.plazo_presentacion IS NULL OR v.plazo_presentacion >= current_date)
  AND NOT EXISTS (
      SELECT 1 FROM triajes t JOIN licitaciones l ON l.id = t.licitacion
      WHERE t.alias = %s AND l.entry_id = v.entry_id
  )
ORDER BY v.entry_id, v.plazo_presentacion NULLS LAST
LIMIT %s
"""

# Lo que el triaje dejó pasar y todavía no tiene ficha. Se pide el pliego descargado aquí y no
# dentro del grafo para no pagar el arranque de un expediente del que no hay nada que leer.
SIN_FICHA = """
SELECT DISTINCT ON (v.entry_id) v.id, v.expediente, v.objeto, v.plazo_presentacion
FROM triajes t
JOIN licitaciones l ON l.id = t.licitacion
JOIN v_licitaciones_vigentes v ON v.entry_id = l.entry_id
JOIN documentos d ON d.licitacion = l.id AND d.tipo = 'PCAP' AND d.estado_descarga = 'descargado'
WHERE t.alias = %s
  AND t.decision = ANY(%s)
  AND NOT v.anulada
  AND (v.plazo_presentacion IS NULL OR v.plazo_presentacion >= current_date)
  AND NOT EXISTS (
      SELECT 1 FROM fichas f JOIN licitaciones fl ON fl.id = f.licitacion
      WHERE f.alias = %s AND fl.entry_id = v.entry_id
  )
ORDER BY v.entry_id, v.plazo_presentacion NULLS LAST
LIMIT %s
"""

# Lo que ha costado leer un pliego, por lectura, de las que ya se han hecho. El percentil 90 y
# no la media: la reserva tiene que dar para un pliego caro, no para el pliego medio.
#
# El `DISTINCT` de dentro no es un adorno. Una lectura deja varios requisitos y todos salen de
# la **misma** respuesta del modelo: sumando por requisito, un pliego con cinco requisitos
# parecía costar cinco veces lo que costó. Con la reserva inflada el radar se cree que no le
# caben pliegos que su tope sí paga, y deja al cliente sin fichas creyendo que le ahorra. Es el
# mismo fallo que el 27-09-2026 hizo que un triaje de veinte pareciera veinte triajes.
COSTE_DE_UN_PLIEGO = """
SELECT percentile_cont(0.9) WITHIN GROUP (ORDER BY total)
FROM (
    SELECT lectura, sum(coste_eur) AS total
    FROM (
        SELECT DISTINCT r.lectura, r.llm_llamada, c.coste_eur
        FROM requisitos r JOIN llm_llamadas c ON c.id = r.llm_llamada
    ) AS llamadas_de_la_lectura
    GROUP BY lectura
) AS por_lectura
"""


def sin_triar(conexion, alias: str, limite: int = TOPE_TRIAJE) -> list[dict]:
    """Licitaciones vigentes con el plazo abierto que esta empresa no ha visto todavía."""
    campos = ("id", "entry_id", "objeto", "organo", "cpv", "tipo_contrato")
    with conexion.cursor() as cur:
        cur.execute(SIN_TRIAR, (alias, limite))
        return [dict(zip(campos, fila, strict=True)) for fila in cur.fetchall()]


def sin_ficha(conexion, alias: str, limite: int = 100) -> list[dict]:
    """Candidatas con pliego descargado y sin ficha. Primero las que antes vencen."""
    campos = ("id", "expediente", "objeto", "plazo")
    with conexion.cursor() as cur:
        cur.execute(SIN_FICHA, (alias, list(PASAN), alias, limite))
        filas = [dict(zip(campos, fila, strict=True)) for fila in cur.fetchall()]
    return sorted(filas, key=lambda f: (f["plazo"] is None, f["plazo"]))


def reserva_por_pliego(conexion) -> float:
    """Cuánto hay que tener libre para atreverse a abrir un pliego."""
    with conexion.cursor() as cur:
        cur.execute(COSTE_DE_UN_PLIEGO)
        medido = cur.fetchone()[0]
    return round(float(medido), 4) if medido else RESERVA_INICIAL


def triar_lo_nuevo(conexion, empresa: dict, run_id, tope: float, gastado: float, api=None) -> dict:
    """Tría lo que esta empresa no ha visto. Devuelve lo hecho y lo que ha costado."""
    hecho = {"triadas": 0, "candidatas": 0, "coste_eur": 0.0}
    pendientes = sin_triar(conexion, empresa["alias"])
    if not pendientes:
        return hecho
    prompt = prompts.cargar(triaje.PROMPT)
    for desde in range(0, len(pendientes), triaje.POR_LLAMADA):
        if gastado + hecho["coste_eur"] >= tope:
            hecho["parado"] = "Se ha alcanzado el tope diario de esta empresa triando."
            break
        lote = pendientes[desde : desde + triaje.POR_LLAMADA]
        try:
            respuesta, ficha, _ = triaje.triar(
                empresa["texto"],
                lote,
                modelo=MODELO,
                esfuerzo=ESFUERZO,
                prompt=prompt,
                api=api,
                run_id=run_id,
            )
        except llm.PresupuestoAgotado as e:
            hecho["parado"] = e.mensaje
            break
        triaje.guardar(conexion, empresa["alias"], lote, respuesta, ficha, prompt, triaje.POR_LLAMADA, run_id)
        hecho["triadas"] += len(lote)
        hecho["candidatas"] += sum(1 for d, _ in respuesta.decisiones.values() if d in PASAN)
        hecho["coste_eur"] += float(ficha["coste_eur"])
    hecho["coste_eur"] = round(hecho["coste_eur"], 4)
    return hecho


def leer_pliegos(conexion, empresa: dict, run_id, tope: float, gastado: float, guardado=None) -> dict:
    """Abre pliegos de las candidatas mientras quede tope. Un fallo no para la mañana.

    El checkpointer se recibe hecho: es uno por mañana, no uno por cliente. Abrirlo aquí dentro
    además colgaba la pasada, porque su `setup()` espera a que terminen las transacciones que
    haya abiertas y la de quien llama es una de ellas.
    """
    hecho = {"leidos": 0, "fichas": 0, "coste_eur": 0.0}
    candidatas = sin_ficha(conexion, empresa["alias"])
    if not candidatas:
        return hecho
    reserva = reserva_por_pliego(conexion)
    for candidata in candidatas:
        if gastado + hecho["coste_eur"] + reserva > tope:
            hecho["parado"] = (
                f"Quedan {len(candidatas) - hecho['leidos']} pliegos por abrir; el tope de "
                f"{tope:.2f} € de esta empresa no da para hoy."
            )
            break
        try:
            estado = analizar(
                candidata["id"],
                empresa["alias"],
                run_id=run_id,
                checkpointer=guardado,
                empresa={
                    "alias": empresa["alias"],
                    "perfil": empresa["texto"],
                    "cifra_negocio": empresa["cifra_negocio"],
                    "cifra_fuente": empresa["cifra_fuente"],
                },
            )
        except llm.PresupuestoAgotado as e:
            hecho["parado"] = e.mensaje
            break
        except Exception as e:  # noqa: BLE001  un pliego malo no puede costar la mañana
            incidencias.apuntar(
                "diario",
                f"No se pudo leer el pliego del expediente {candidata['expediente']} "
                f"para {empresa['alias']}.",
                e,
            )
            continue
        hecho["leidos"] += 1
        hecho["fichas"] += 1 if estado.get("veredicto") else 0
        hecho["coste_eur"] += coste_de(estado)
    hecho["coste_eur"] = round(hecho["coste_eur"], 4)
    return hecho


def de_una_empresa(conexion, empresa: dict, run_id, dia: date, guardado=None, api=None) -> dict:
    """La mañana de un cliente: triar lo nuevo y leer lo que dé su tope."""
    tope = float(empresa["tope_diario_eur"] or 0)
    _, gastado = empresas.gastado_hoy(conexion, empresa["alias"], dia)
    resumen = {"alias": empresa["alias"], "tope_eur": tope, "gastado_antes_eur": round(gastado, 4)}
    if gastado >= tope:
        resumen["parado"] = f"Esta empresa ya ha gastado hoy sus {tope:.2f} €."
        return resumen
    triado = triar_lo_nuevo(conexion, empresa, run_id, tope, gastado, api=api)
    gastado += triado["coste_eur"]
    leido = leer_pliegos(conexion, empresa, run_id, tope, gastado, guardado)
    resumen.update(triado)
    resumen["leidos"] = leido["leidos"]
    resumen["coste_eur"] = round(triado["coste_eur"] + leido["coste_eur"], 4)
    parado = triado.get("parado") or leido.get("parado")
    if parado:
        resumen["parado"] = parado
    return resumen


def lo_que_falta(conexion, empresa: dict, dia: date) -> dict:
    """Lo mismo, sin gastar: qué hay pendiente y qué costaría, con cifras medidas."""
    pendientes = sin_triar(conexion, empresa["alias"])
    candidatas = sin_ficha(conexion, empresa["alias"])
    reserva = reserva_por_pliego(conexion)
    _, gastado = empresas.gastado_hoy(conexion, empresa["alias"], dia)
    tope = float(empresa["tope_diario_eur"] or 0)
    caben = max(0, int((tope - gastado) / reserva)) if reserva else 0
    return {
        "alias": empresa["alias"],
        "tope_eur": tope,
        "gastado_antes_eur": round(gastado, 4),
        "por_triar": len(pendientes),
        "llamadas_de_triaje": -(-len(pendientes) // triaje.POR_LLAMADA),
        "pliegos_por_abrir": len(candidatas),
        "reserva_por_pliego_eur": reserva,
        "pliegos_que_caben": min(caben, len(candidatas)),
    }


def del_dia(alias: str | None = None, gastar: bool = False, dia: date | None = None) -> dict:
    """El trabajo de la mañana, de un cliente o de todos los activos."""
    dia = dia or date.today()
    with conectar() as conexion:
        lista = [empresas.la_de(conexion, alias)] if alias else empresas.activas(conexion)
        if not lista:
            raise ErrorRadar("No hay ninguna empresa dada de alta. El formulario está en /alta.")
        if not gastar:
            return {"dia": dia.isoformat(), "empresas": [lo_que_falta(conexion, e, dia) for e in lista]}
        run_id = abrir_ejecucion(conexion, "diaria", None)
        hecho = []
        try:
            # Un checkpointer para toda la mañana. Es el paso a paso de LangGraph: si algo se
            # cae a mitad de un pliego, se ve en qué nodo estaba.
            with checkpointer_de_postgres() as guardado:
                guardado.setup()
                for empresa in lista:
                    hecho.append(de_una_empresa(conexion, empresa, run_id, dia, guardado))
        except Exception as e:
            cerrar_ejecucion(conexion, run_id, "error", str(e)[:500])
            raise
        cerrar_ejecucion(conexion, run_id, "ok", None)
    return {"dia": dia.isoformat(), "run_id": str(run_id), "empresas": hecho}


def como_se_lee(resultado: dict, gastar: bool) -> str:
    lineas = [f"\nRadar · {resultado['dia']}"]
    for empresa in resultado["empresas"]:
        lineas.append(f"\n{empresa['alias']}  ·  tope {empresa['tope_eur']:.2f} €/día")
        if gastar:
            lineas.append(
                f"  Triadas {empresa.get('triadas', 0)}, de las que pasan "
                f"{empresa.get('candidatas', 0)}. Pliegos leídos: {empresa.get('leidos', 0)}."
            )
            lineas.append(f"  Ha costado {empresa.get('coste_eur', 0):.4f} €.")
        else:
            lineas.append(
                f"  Por triar {empresa['por_triar']} licitaciones ({empresa['llamadas_de_triaje']} llamadas)."
            )
            lineas.append(
                f"  Pliegos por abrir: {empresa['pliegos_por_abrir']}; con lo que queda de su "
                f"tope caben {empresa['pliegos_que_caben']} "
                f"(a {empresa['reserva_por_pliego_eur']:.4f} € cada uno)."
            )
        if empresa.get("parado"):
            lineas.append(f"  Se ha parado: {empresa['parado']}")
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description="El trabajo diario del radar, cliente a cliente")
    parser.add_argument("--empresa", default=None, help="solo esta; por defecto, todas las activas")
    parser.add_argument("--gastar", action="store_true", help="hacerlo de verdad (llama al modelo)")
    args = parser.parse_args()
    try:
        resultado = del_dia(args.empresa, gastar=args.gastar)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print(como_se_lee(resultado, args.gastar))
    if not args.gastar:
        print("\nNo se ha llamado al modelo. Para hacerlo: --gastar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
