"""El experimento del triaje: qué modelo y de cuántas en cuántas (D06).

El diseño está congelado en `docs/EXPERIMENTO_TRIAJE.md`, escrito antes de hacer una llamada.
Aquí solo se ejecuta: este módulo no decide nada, igual que `radar/seleccion.py` no decide quién
entra en el estudio.

    uv run python -m radar.evaluacion.triaje              # estima el coste y no gasta nada
    uv run python -m radar.evaluacion.triaje --gastar     # llama al modelo de verdad
    uv run python -m radar.evaluacion.triaje --solo-medir # rehace las cifras de lo ya guardado
"""

from __future__ import annotations

import argparse
import json
import random

from radar import llm, prompts, triaje
from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.evaluacion.baselines import CORTE
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion, commit_actual

SEMILLA = "20260927"
NEGATIVOS_POR_EMPRESA = 88
DESDE, HASTA = "2025-01-01", "2025-07-01"

# Las tres variantes del experimento. Falta `opus_individual` a propósito (EXPERIMENTO_TRIAJE §2).
VARIANTES = {
    "haiku_lote20": {"modelo": "claude-haiku-4-5", "por_llamada": 20, "esfuerzo": "low"},
    "haiku_individual": {"modelo": "claude-haiku-4-5", "por_llamada": 1, "esfuerzo": "low"},
    "opus_lote20": {"modelo": "claude-opus-5", "por_llamada": 20, "esfuerzo": "low"},
}
# Las que siguen adelante y se les abre el pliego. Un 'no' es el final del camino.
PASAN = ("si", "duda")

PUBLICADAS = """
    SELECT entry_id FROM licitaciones
    GROUP BY entry_id HAVING min(entry_updated) >= %s AND min(entry_updated) < %s
"""
# La versión más antigua de cada expediente: lo que se sabía mientras el plazo seguía abierto (D30).
COMO_SE_PUBLICO = """
SELECT DISTINCT ON (l.entry_id) l.id, l.entry_id, l.objeto, l.organo, l.cpv, l.tipo_contrato
FROM licitaciones l
WHERE l.entry_id = ANY(%s)
ORDER BY l.entry_id, l.entry_updated
"""
GANADOS = f"""
SELECT DISTINCT l.entry_id
FROM adjudicaciones a
JOIN licitaciones l ON l.id = a.licitacion
WHERE a.adjudicatario = %s AND l.entry_updated < %s AND l.entry_id IN ({PUBLICADAS})
"""
# Muestra de los no ganados. El orden por md5 con la semilla sale igual siempre y no depende de
# que nadie guarde un fichero de números al azar.
NO_GANADOS = f"""
SELECT entry_id FROM ({PUBLICADAS}) AS pub
WHERE entry_id <> ALL(%s)
ORDER BY md5(entry_id || %s)
LIMIT %s
"""
UNIVERSO = """
SELECT count(*), count(DISTINCT primera::date) FROM (
    SELECT entry_id, min(entry_updated) AS primera FROM licitaciones
    GROUP BY entry_id HAVING min(entry_updated) >= %s AND min(entry_updated) < %s
) AS pub
"""


def desarrollo(conexion) -> list[tuple[str, str]]:
    with conexion.cursor() as cur:
        cur.execute("SELECT alias, nif FROM perfiles WHERE rol = 'desarrollo' ORDER BY alias")
        return cur.fetchall()


def como_diccionarios(filas) -> list[dict]:
    campos = ("id", "entry_id", "objeto", "organo", "cpv", "tipo_contrato")
    return [dict(zip(campos, fila, strict=True)) for fila in filas]


def universo(conexion, desde: str, hasta: str) -> tuple[int, int]:
    """Cuántos expedientes se publicaron en el periodo y en cuántos días distintos."""
    with conexion.cursor() as cur:
        cur.execute(UNIVERSO, (desde, hasta))
        expedientes, dias = cur.fetchone()
    if not expedientes:
        raise ErrorRadar("No hay licitaciones publicadas en ese periodo. ¿Está hecha la carga histórica?")
    return expedientes, max(dias, 1)


def muestra(
    conexion,
    nif: str,
    desde: str = DESDE,
    hasta: str = HASTA,
    corte: str = CORTE,
    negativos: int = NEGATIVOS_POR_EMPRESA,
) -> list[dict]:
    """Los ganados de esa empresa más una muestra al azar del resto (EXPERIMENTO_TRIAJE §3)."""
    with conexion.cursor() as cur:
        cur.execute(GANADOS, (nif, corte, desde, hasta))
        ganados = [fila[0] for fila in cur.fetchall()]
        if not ganados:
            raise ErrorRadar(
                f"Esa empresa no tiene ningún contrato ganado entre {desde} y {hasta}. Sin "
                "contratos ganados no hay recall que medir."
            )
        cur.execute(NO_GANADOS, (desde, hasta, ganados, SEMILLA, negativos))
        resto = [fila[0] for fila in cur.fetchall()]
        cur.execute(COMO_SE_PUBLICO, (ganados + resto,))
        filas = como_diccionarios(cur.fetchall())

    for fila in filas:
        fila["ganado"] = fila["entry_id"] in set(ganados)
    # Se mezclan para que los ganados no vayan todos en las primeras llamadas. Con semilla fija:
    # la misma muestra y el mismo orden cada vez que se ejecute.
    random.Random(SEMILLA).shuffle(filas)
    return filas


def ya_triadas(conexion, alias: str, variante: dict, version: str) -> set[int]:
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT licitacion FROM triajes WHERE alias = %s AND modelo = %s AND por_llamada = %s"
            " AND prompt_version = %s",
            (alias, variante["modelo"], variante["por_llamada"], version),
        )
        return {fila[0] for fila in cur.fetchall()}


def lotes(items: list[dict], por_llamada: int) -> list[list[dict]]:
    return [items[i : i + por_llamada] for i in range(0, len(items), por_llamada)]


def estimar(conexion, plan: dict, prompt: prompts.Prompt, api=None) -> list[dict]:
    """Cuánto costaría, contando los tokens de entrada (gratis) y suponiendo la salida al máximo.

    Es una estimación pesimista a propósito: la salida real es bastante menor que `max_tokens`.
    """
    api = api or llm.cliente()
    estimaciones = []
    for nombre, variante in VARIANTES.items():
        if nombre not in plan:
            continue
        tokens_entrada = tokens_salida = llamadas = 0
        for perfil, pendientes in plan[nombre].values():
            for lote in lotes(pendientes, variante["por_llamada"]):
                mensajes = [{"role": "user", "content": triaje.mensaje(lote)}]
                tokens_entrada += llm.contar_tokens(
                    variante["modelo"], mensajes, triaje.sistema(perfil, prompt), api
                )
                tokens_salida += max(triaje.TOKENS_MINIMOS, triaje.TOKENS_POR_LICITACION * len(lote))
                llamadas += 1
        uso = llm.Uso(entrada=tokens_entrada, salida=tokens_salida)
        cambio, _ = llm.tipo_de_cambio()
        estimaciones.append(
            {
                "variante": nombre,
                "llamadas": llamadas,
                "tokens_entrada": tokens_entrada,
                "tope_salida": tokens_salida,
                "eur_maximo": round(llm.coste_usd(variante["modelo"], uso) * cambio, 4),
            }
        )
    return estimaciones


def preparar(conexion, variantes: list[str], desde: str, hasta: str, corte: str, negativos: int) -> dict:
    """Qué queda por triar de cada variante y cada empresa. Lo ya hecho no se repite ni se paga."""
    empresas = desarrollo(conexion)
    if not empresas:
        raise ErrorRadar(
            "No hay empresas de desarrollo en la tabla perfiles. Antes hay que aplicar la regla: "
            "uv run python -m radar.seleccion"
        )
    # La muestra de una empresa es la misma para las tres variantes: se saca una vez.
    de_cada_empresa = {
        alias: (triaje.perfil_de(conexion, alias), muestra(conexion, nif, desde, hasta, corte, negativos))
        for alias, nif in empresas
    }
    plan: dict[str, dict[str, tuple[str, list[dict]]]] = {}
    for nombre in variantes:
        plan[nombre] = {}
        for alias, (perfil, items) in de_cada_empresa.items():
            hechas = ya_triadas(conexion, alias, VARIANTES[nombre], triaje.PROMPT)
            plan[nombre][alias] = (perfil, [i for i in items if i["id"] not in hechas])
    return plan


def ejecutar(conexion, plan: dict, prompt: prompts.Prompt, run_id, api=None) -> dict:
    """Las llamadas de verdad. Se para sola si se alcanza el presupuesto del día."""
    hecho = {nombre: 0 for nombre in plan}
    for nombre, por_empresa in plan.items():
        variante = VARIANTES[nombre]
        for alias, (perfil, pendientes) in por_empresa.items():
            for lote in lotes(pendientes, variante["por_llamada"]):
                respuesta, ficha, _ = triaje.triar(
                    perfil,
                    lote,
                    modelo=variante["modelo"],
                    esfuerzo=variante["esfuerzo"],
                    prompt=prompt,
                    api=api,
                    run_id=run_id,
                )
                triaje.guardar(
                    conexion, alias, lote, respuesta, ficha, prompt, variante["por_llamada"], run_id
                )
                hecho[nombre] += len(lote)
    return hecho


CIFRAS = """
SELECT t.decision, count(*), count(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM adjudicaciones a
    JOIN licitaciones v ON v.id = a.licitacion
    WHERE a.adjudicatario = %s AND v.entry_updated < %s AND v.entry_id = l.entry_id
))
FROM triajes t
JOIN licitaciones l ON l.id = t.licitacion
WHERE t.alias = %s AND t.modelo = %s AND t.por_llamada = %s AND t.prompt_version = %s
GROUP BY t.decision
"""
# El coste se suma por **llamada distinta**, no por licitación: con lotes de 20, una llamada paga
# 20 triajes y sumarla 20 veces multiplicaria el coste por 20. Con lotes de 1 no se notaría, que
# es lo que hace peligroso el error.
COSTE = """
WITH mias AS (
    SELECT llm_llamada FROM triajes
    WHERE modelo = %s AND por_llamada = %s AND prompt_version = %s
)
SELECT (SELECT coalesce(sum(coste_eur), 0) FROM llm_llamadas
        WHERE id IN (SELECT DISTINCT llm_llamada FROM mias)),
       (SELECT count(DISTINCT llm_llamada) FROM mias),
       (SELECT count(*) FROM mias)
"""


def cifras_de(conexion, alias: str, nif: str, variante: dict, version: str, corte: str) -> dict:
    with conexion.cursor() as cur:
        cur.execute(
            CIFRAS,
            (nif, corte, alias, variante["modelo"], variante["por_llamada"], version),
        )
        filas = cur.fetchall()
    total = {"si": 0, "no": 0, "duda": 0, "revisar": 0}
    ganados = dict.fromkeys(total, 0)
    for decision, cuantas, cuantas_ganadas in filas:
        total[decision] = cuantas
        ganados[decision] = cuantas_ganadas
    return {"total": total, "ganados": ganados}


def medir(conexion, variantes: list[str], desde: str, hasta: str, corte: str) -> list[dict]:
    """M1, M2 y M8 de cada variante, a partir de lo guardado en `triajes`. No llama al modelo."""
    version = triaje.PROMPT
    expedientes, dias = universo(conexion, desde, hasta)
    por_dia = expedientes / dias
    resultados = []
    for nombre in variantes:
        variante = VARIANTES[nombre]
        for alias, nif in desarrollo(conexion):
            c = cifras_de(conexion, alias, nif, variante, version, corte)
            ganados = sum(c["ganados"].values())
            if not ganados:
                continue
            pasan_ganados = sum(c["ganados"][d] for d in PASAN)
            no_ganados = sum(c["total"].values()) - ganados
            pasan_no_ganados = sum(c["total"][d] - c["ganados"][d] for d in PASAN)
            tasa = (pasan_no_ganados / no_ganados) if no_ganados else 0.0
            resultados.append(
                {
                    "metrica": "M1",
                    "variante": f"triaje_{nombre}",
                    "alias": alias,
                    "valor": round(pasan_ganados / ganados, 4),
                    "n": ganados,
                    "detalle": {
                        "ganados": ganados,
                        "en_la_lista": pasan_ganados,
                        "por_decision": c["ganados"],
                        "sin_decision_valida": c["total"]["revisar"],
                    },
                }
            )
            resultados.append(
                {
                    "metrica": "M2",
                    "variante": f"triaje_{nombre}",
                    "alias": alias,
                    "valor": round(tasa * por_dia, 4),
                    "n": no_ganados,
                    "detalle": {
                        "tasa_de_paso_en_no_ganados": round(tasa, 4),
                        "no_ganados_de_la_muestra": no_ganados,
                        "publicadas_al_dia": round(por_dia, 2),
                        "estimacion": "tasa de paso x publicadas al dia",
                    },
                }
            )
        with conexion.cursor() as cur:
            cur.execute(COSTE, (variante["modelo"], variante["por_llamada"], version))
            eur, llamadas, triadas = cur.fetchone()
        if triadas:
            resultados.append(
                {
                    "metrica": "M8",
                    "variante": f"triaje_{nombre}",
                    "alias": None,
                    "valor": round(float(eur) / triadas * 100, 6),
                    "n": triadas,
                    "detalle": {
                        "eur_total": round(float(eur), 6),
                        "llamadas": llamadas,
                        "licitaciones_triadas": triadas,
                        "unidad": "euros por 100 licitaciones triadas",
                    },
                }
            )
    return resultados


def guardar_cifras(conexion, run_id, desde, hasta, comando, resultados) -> None:
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
                    desde,
                    hasta,
                    r["valor"],
                    r["n"],
                    json.dumps(r["detalle"], ensure_ascii=False),
                    commit,
                    comando,
                    run_id,
                ),
            )
    conexion.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimento del modelo de triaje (D06)")
    parser.add_argument("--desde", default=DESDE)
    parser.add_argument("--hasta", default=HASTA)
    parser.add_argument("--corte", default=CORTE)
    parser.add_argument("--negativos", type=int, default=NEGATIVOS_POR_EMPRESA)
    parser.add_argument("--variantes", default=",".join(VARIANTES))
    parser.add_argument("--gastar", action="store_true", help="llama al modelo de verdad")
    parser.add_argument("--solo-medir", action="store_true", help="rehace las cifras sin llamar")
    args = parser.parse_args()

    pedidas = [v.strip() for v in args.variantes.split(",") if v.strip()]
    desconocidas = [v for v in pedidas if v not in VARIANTES]
    if desconocidas:
        print(f"\nVariantes que no existen: {', '.join(desconocidas)}. Hay: {', '.join(VARIANTES)}")
        return 1

    comando = (
        f"uv run python -m radar.evaluacion.triaje --desde {args.desde} --hasta {args.hasta}"
        f" --corte {args.corte} --negativos {args.negativos} --variantes {','.join(pedidas)}"
    )
    try:
        prompt = prompts.cargar(triaje.PROMPT)
        with conectar() as conexion:
            if args.solo_medir:
                return informe(conexion, pedidas, args, comando)

            plan = preparar(conexion, pedidas, args.desde, args.hasta, args.corte, args.negativos)
            pendientes = {n: sum(len(p) for _, p in e.values()) for n, e in plan.items()}
            print("\nQueda por triar:")
            for nombre, cuantas in pendientes.items():
                print(f"  {nombre:18} {cuantas} licitaciones")
            if not sum(pendientes.values()):
                print("\nNo queda nada por triar. Las cifras, con --solo-medir.")
                return informe(conexion, pedidas, args, comando)

            print("\nCoste máximo estimado (tokens de entrada reales, salida al tope):")
            total = 0.0
            for e in estimar(conexion, plan, prompt):
                total += e["eur_maximo"]
                print(
                    f"  {e['variante']:18} {e['llamadas']:4} llamadas  "
                    f"{e['tokens_entrada']:>8} tokens de entrada  hasta {e['eur_maximo']:.4f} €"
                )
            print(f"  {'total':18} {'':>4}           {'':>8}                   hasta {total:.4f} €")
            if not args.gastar:
                print("\nNo se ha llamado al modelo. Para hacerlo de verdad: --gastar")
                return 0

            run_id = abrir_ejecucion(conexion, "evaluacion", None)
            try:
                hecho = ejecutar(conexion, plan, prompt, run_id)
                cerrar_ejecucion(conexion, run_id, "ok")
            except ErrorRadar as e:
                cerrar_ejecucion(conexion, run_id, "error", e.mensaje)
                print(f"\n{e}")
                print("\nLo triado hasta aquí queda guardado. Al volver a ejecutarlo sigue donde iba.")
                return 1
            except Exception as e:
                cerrar_ejecucion(conexion, run_id, "error", "Fallo no previsto al triar.")
                raise ErrorRadar("Fallo no previsto al triar.", detalle=repr(e)) from e
            print("\nTriado:", ", ".join(f"{n}={c}" for n, c in hecho.items()))
            return informe(conexion, pedidas, args, comando, run_id)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1


def informe(conexion, pedidas: list[str], args, comando: str, run_id=None) -> int:
    resultados = medir(conexion, pedidas, args.desde, args.hasta, args.corte)
    if not resultados:
        print("\nTodavía no hay ningún triaje guardado con este prompt.")
        return 1
    if run_id is None:
        run_id = abrir_ejecucion(conexion, "evaluacion", None)
        guardar_cifras(conexion, run_id, args.desde, args.hasta, comando, resultados)
        cerrar_ejecucion(conexion, run_id, "ok")
    else:
        guardar_cifras(conexion, run_id, args.desde, args.hasta, comando, resultados)

    print(f"\nCifras del experimento (run_id {run_id}):\n")
    print(f"{'métrica':8} {'variante':26} {'empresa':12} {'valor':>10}   n")
    for r in resultados:
        print(
            f"{r['metrica']:8} {r['variante']:26} {(r['alias'] or 'todas'):12} {r['valor']:>10.4f}   {r['n']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
