"""Pasar el grafo por las candidatas del triaje y medir M5 (citas verificadas).

M5 es la puerta de salida de la Fase 4: **≥ 98 % de las extracciones tienen que tener una cita
que aparece literal en la página que dice el modelo** (`docs/SPEC.md` §6). Se calcula contando
filas de `requisitos`, donde están tanto las verificadas como las rechazadas con su motivo.

    uv run python -m radar.evaluacion.pliegos                 # dice qué haría y qué costaría
    uv run python -m radar.evaluacion.pliegos --gastar --tope 1.00
    uv run python -m radar.evaluacion.pliegos --solo-medir    # M5 de lo ya leído, sin pagar

El tope es un segundo freno **además** del presupuesto diario de `.env`: sirve para decir «esta
tanda, un euro» sin tocar la configuración del proyecto.
"""

from __future__ import annotations

import argparse
import json

from radar import grafo, incidencias, llm, prompts, reglas
from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.evaluacion.baselines import CORTE
from radar.extraccion import PROMPT, Requisito
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion, commit_actual

DESDE, HASTA = "2025-01-01", "2025-07-01"

# Las candidatas: lo que el triaje dejó pasar, con pliego descargado y sin leer todavía con
# esta versión del prompt. Los contratos ganados primero: son los que miden de verdad, porque
# de ellos se sabe la respuesta.
CANDIDATAS = """
SELECT t.licitacion, t.alias, t.decision, g.ganado
FROM triajes t
JOIN licitaciones l ON l.id = t.licitacion
JOIN perfiles p ON p.alias = t.alias
CROSS JOIN LATERAL (
    SELECT EXISTS (
        SELECT 1 FROM adjudicaciones a
        JOIN licitaciones v ON v.id = a.licitacion
        WHERE a.adjudicatario = p.nif AND v.entry_updated < %s AND v.entry_id = l.entry_id
    ) AS ganado
) g
WHERE t.decision IN ('si', 'duda')
  AND t.modelo = %s AND t.por_llamada = %s
  AND EXISTS (
      SELECT 1 FROM documentos d
      JOIN licitaciones s ON s.id = d.licitacion
      WHERE s.entry_id = l.entry_id AND d.tipo = 'PCAP' AND d.estado_descarga = 'descargado'
  )
  AND NOT EXISTS (
      SELECT 1 FROM lecturas le
      WHERE le.licitacion = t.licitacion AND le.alias = t.alias AND le.prompt_version = %s
  )
ORDER BY g.ganado DESC, t.licitacion
LIMIT %s
"""

M5 = """
SELECT count(*) FILTER (WHERE verificada), count(*)
FROM requisitos r
JOIN lecturas le ON le.id = r.lectura
WHERE le.prompt_version = %s
"""

RESUMEN = """
SELECT le.estado, count(DISTINCT le.id), count(r.id) FILTER (WHERE r.verificada)
FROM lecturas le LEFT JOIN requisitos r ON r.lectura = le.id
WHERE le.prompt_version = %s
GROUP BY le.estado
"""

VEREDICTOS = """
SELECT f.veredicto, count(*)
FROM fichas f WHERE f.reglas_version = %s GROUP BY f.veredicto ORDER BY 1
"""


def version_del_prompt() -> str:
    prompt = prompts.cargar(PROMPT)
    return f"{prompt.nombre}_{prompt.version}"


def candidatas(conexion, limite: int, corte: str = CORTE) -> list[tuple]:
    from radar.evaluacion.triaje import VARIANTES

    elegida = VARIANTES["haiku_lote20"]  # el modelo de triaje decidido en D06
    with conexion.cursor() as cur:
        cur.execute(
            CANDIDATAS,
            (corte, elegida["modelo"], elegida["por_llamada"], version_del_prompt(), limite),
        )
        return cur.fetchall()


def gastado_hoy() -> float:
    with conectar() as conexion:
        return llm.gastado_hoy(conexion)


def leer(limite: int, tope_eur: float, corte: str = CORTE) -> dict:
    """Pasa el grafo por las candidatas hasta agotar la lista o el tope de la tanda."""
    resumen = {"leidas": 0, "sin_pliego": 0, "sin_localizar": 0, "coste_eur": 0.0, "veredictos": {}}
    with conectar() as conexion:
        cola = candidatas(conexion, limite, corte)
        run_id = abrir_ejecucion(conexion, "evaluacion", None)
    if not cola:
        with conectar() as conexion:
            cerrar_ejecucion(conexion, run_id, "ok")
        return resumen

    checkpointer = grafo.checkpointer_de_postgres()
    try:
        with checkpointer as guardador:
            guardador.setup()
            empresas = {}
            for licitacion, alias, _decision, _ganado in cola:
                if resumen["coste_eur"] >= tope_eur:
                    resumen["parado_por_el_tope"] = True
                    break
                if alias not in empresas:
                    with conectar() as conexion:
                        empresas[alias] = grafo.empresa_de(conexion, alias)
                estado = grafo.analizar(
                    licitacion,
                    alias,
                    run_id=run_id,
                    checkpointer=guardador,
                    empresa=empresas[alias],
                )
                resumen["coste_eur"] += grafo.coste_de(estado)
                clave = {"leido": "leidas"}.get(estado.get("estado"), estado.get("estado", "otro"))
                resumen[clave] = resumen.get(clave, 0) + 1
                veredicto = estado.get("veredicto") or "revisar"
                resumen["veredictos"][veredicto] = resumen["veredictos"].get(veredicto, 0) + 1
        with conectar() as conexion:
            cerrar_ejecucion(conexion, run_id, "ok")
    except ErrorRadar as e:
        with conectar() as conexion:
            cerrar_ejecucion(conexion, run_id, "error", e.mensaje)
        resumen["error"] = e.mensaje
    except Exception as e:
        # La traza va a `incidencias`, no a la pantalla (innegociable 3). Sin esto, un fallo no
        # previsto dejaba el mensaje «Fallo no previsto» y ninguna forma de arreglarlo.
        ficha = incidencias.apuntar("evaluacion.pliegos", "Fallo no previsto al leer los pliegos", e)
        with conectar() as conexion:
            cerrar_ejecucion(conexion, run_id, "error", "Fallo no previsto al leer los pliegos.")
        raise ErrorRadar(
            "Ha fallado algo no previsto al leer los pliegos. Lo leído hasta ahora queda "
            "guardado y se puede continuar con el mismo comando."
            + (f" El detalle técnico está en la incidencia {ficha}." if ficha else ""),
            detalle=repr(e),
        ) from e

    resumen["coste_eur"] = round(resumen["coste_eur"], 4)
    resumen["run_id"] = str(run_id)
    return resumen


LECTURAS_GUARDADAS = """
SELECT le.id, le.licitacion, le.alias, le.estado, le.motivo
FROM lecturas le WHERE le.prompt_version = %s ORDER BY le.id
"""


def rehacer_fichas() -> dict:
    """Vuelve a decidir con los requisitos ya guardados. **No llama al modelo: es gratis.**

    Esto es para lo que sirve tener la extracción y la decisión separadas (D09). Si cambian las
    reglas, o si se rellena un dato de la empresa que faltaba, la decisión se recalcula sin
    volver a leer ningún pliego y sin pagar nada.
    """
    version = version_del_prompt()
    hecho = {"fichas": 0, "veredictos": {}}
    with conectar() as conexion:
        with conexion.cursor() as cur:
            cur.execute(LECTURAS_GUARDADAS, (version,))
            lecturas = cur.fetchall()
        empresas = {}
        version_reglas = reglas.cargar()
        for lectura, licitacion, alias, estado, motivo in lecturas:
            if alias not in empresas:
                empresas[alias] = grafo.empresa_de(conexion, alias)
            with conexion.cursor() as cur:
                cur.execute(
                    "SELECT tipo, exigencia, cita, pagina, importe_eur, anios FROM requisitos"
                    " WHERE lectura = %s AND verificada ORDER BY id",
                    (lectura,),
                )
                requisitos = [
                    Requisito(
                        tipo=f[0],
                        exigencia=f[1] or "",
                        cita=f[2],
                        pagina=f[3],
                        importe_eur=float(f[4]) if f[4] is not None else None,
                        anios=f[5],
                    )
                    for f in cur.fetchall()
                ]
            decision = version_reglas.evaluar(requisitos, empresas[alias])
            motivos = [vars(m) for m in decision.motivos]
            if not requisitos and motivo:
                motivos[0]["texto"] = motivo  # el motivo de por qué no se pudo leer, si lo hay
            del estado
            with conexion.cursor() as cur:
                cur.execute(
                    "INSERT INTO fichas (licitacion, alias, lectura, veredicto, reglas_version,"
                    " motivos) VALUES (%s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (licitacion, alias, reglas_version, lectura) DO UPDATE"
                    " SET veredicto = excluded.veredicto, motivos = excluded.motivos,"
                    " creada_en = now()",
                    (
                        licitacion,
                        alias,
                        lectura,
                        decision.veredicto,
                        reglas.VERSION_ACTUAL,
                        json.dumps(motivos, ensure_ascii=False),
                    ),
                )
            hecho["fichas"] += 1
            hecho["veredictos"][decision.veredicto] = hecho["veredictos"].get(decision.veredicto, 0) + 1
        conexion.commit()
    return hecho


def medir(conexion) -> list[dict]:
    """M5 y el reparto de lo leído, de lo que hay guardado. No llama al modelo."""
    version = version_del_prompt()
    with conexion.cursor() as cur:
        cur.execute(M5, (version,))
        verificadas, total = cur.fetchone()
        cur.execute(RESUMEN, (version,))
        por_estado = {estado: (lecturas, reqs) for estado, lecturas, reqs in cur.fetchall()}
        cur.execute(VEREDICTOS, (reglas.VERSION_ACTUAL,))
        veredictos = dict(cur.fetchall())
        cur.execute(
            "SELECT count(*), coalesce(sum(coste_eur), 0) FROM llm_llamadas WHERE nodo = 'extraccion'"
        )
        llamadas, eur = cur.fetchone()
        cur.execute(
            "SELECT coalesce(avg(array_length(paginas, 1)), 0), coalesce(avg(paginas_totales), 0)"
            " FROM lecturas WHERE prompt_version = %s AND estado = 'leido'",
            (version,),
        )
        paginas_leidas, paginas_totales = cur.fetchone()

    if not total:
        raise ErrorRadar(
            "Todavía no hay ningún requisito extraído, así que no hay M5 que medir. "
            "Lánzalo con: uv run python -m radar.evaluacion.pliegos --gastar"
        )
    lecturas = sum(n for n, _ in por_estado.values())
    return [
        {
            "metrica": "M5",
            "variante": f"agente_{version}",
            "alias": None,
            "valor": round(verificadas / total, 4),
            "n": total,
            "detalle": {
                "citas_verificadas": verificadas,
                "extracciones": total,
                "rechazadas": total - verificadas,
                "lecturas": lecturas,
                "por_estado": {e: n for e, (n, _) in por_estado.items()},
                "veredictos": veredictos,
                "paginas_leidas_de_media": round(float(paginas_leidas), 1),
                "paginas_del_pliego_de_media": round(float(paginas_totales), 1),
                "llamadas_de_extraccion": llamadas,
                "coste_eur": round(float(eur), 4),
                "reglas": reglas.VERSION_ACTUAL,
            },
        }
    ]


def guardar_cifras(conexion, run_id, comando: str, resultados: list[dict]) -> None:
    commit = commit_actual()
    with conexion.cursor() as cur:
        for r in resultados:
            cur.execute(
                "INSERT INTO eval_resultados (metrica, variante, alias, periodo_desde,"
                " periodo_hasta, valor, n, detalle, git_commit, comando, run_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    r["metrica"],
                    r["variante"],
                    r["alias"],
                    DESDE,
                    HASTA,
                    r["valor"],
                    r["n"],
                    json.dumps(r["detalle"], ensure_ascii=False),
                    commit,
                    comando,
                    run_id,
                ),
            )
    conexion.commit()


def informe(comando: str) -> int:
    with conectar() as conexion:
        resultados = medir(conexion)
        run_id = abrir_ejecucion(conexion, "evaluacion", None)
        guardar_cifras(conexion, run_id, comando, resultados)
        cerrar_ejecucion(conexion, run_id, "ok")
    for r in resultados:
        d = r["detalle"]
        print(f"\nM5, citas verificadas: {r['valor'] * 100:.1f} %  ({d['citas_verificadas']}/{r['n']})")
        print(f"  pliegos leídos:            {d['por_estado']}")
        print(f"  veredictos ({d['reglas']}):        {d['veredictos']}")
        print(
            f"  páginas leídas de media:   {d['paginas_leidas_de_media']}"
            f" de {d['paginas_del_pliego_de_media']} del pliego"
        )
        print(f"  coste de la extracción:    {d['coste_eur']} € en {d['llamadas_de_extraccion']} llamadas")
        if r["valor"] < 0.98:
            print("\n  M5 por debajo del 98 %: la Fase 4 no puede cerrarse con esta cifra.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Lee los pliegos de las candidatas y mide M5")
    parser.add_argument("--limite", type=int, default=40, help="cuántas licitaciones como máximo")
    parser.add_argument("--tope", type=float, default=1.00, help="euros como máximo en esta tanda")
    parser.add_argument("--corte", default=CORTE)
    parser.add_argument("--gastar", action="store_true", help="llama al modelo de verdad")
    parser.add_argument("--solo-medir", action="store_true")
    parser.add_argument(
        "--rehacer-fichas",
        action="store_true",
        help="vuelve a decidir con lo ya extraído, sin llamar al modelo (gratis)",
    )
    args = parser.parse_args()

    comando = (
        f"uv run python -m radar.evaluacion.pliegos --limite {args.limite} --tope {args.tope}"
        f" --corte {args.corte}"
    )
    try:
        if args.rehacer_fichas:
            print(f"\nFichas rehechas con las reglas {reglas.VERSION_ACTUAL}: {rehacer_fichas()}")
            return informe(comando)
        if args.solo_medir:
            return informe(comando)
        with conectar() as conexion:
            cola = candidatas(conexion, args.limite, args.corte)
        print(f"\nPendientes de leer con {version_del_prompt()}: {len(cola)} licitaciones")
        print(f"Gastado hoy: {gastado_hoy():.4f} €   ·   tope de esta tanda: {args.tope:.2f} €")
        if not cola:
            print("\nNo queda nada por leer. Las cifras, con --solo-medir.")
            return informe(comando)
        if not args.gastar:
            print(
                "\nCada pliego son una o dos llamadas a Opus 5 (unos 0,05-0,13 € cada una, "
                "medido). No se ha llamado a nada. Para hacerlo de verdad: --gastar"
            )
            return 0
        resumen = leer(args.limite, args.tope, args.corte)
        print(f"\nResumen de la tanda: {resumen}")
        return informe(comando)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
