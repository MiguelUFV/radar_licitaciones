"""M1 y M2 del agente sobre las empresas de test: el "después" del estudio.

El procedimiento está congelado en `docs/PLAN_MEDICION.md`, escrito antes de mirar un contrato de
las empresas de test. Este módulo solo lo ejecuta.

    uv run python -m radar.evaluacion.agente              # qué falta y qué costaría
    uv run python -m radar.evaluacion.agente --gastar     # tría de verdad
    uv run python -m radar.evaluacion.agente --solo-medir # M1, M2 y el intervalo, sin pagar

**Orden de gasto:** primero los contratos ganados, que son los que deciden la tesis (M1) y cuestan
cuatro céntimos; después los no ganados, que solo sirven para estimar el volumen (M2). Si el
presupuesto corta la tanda, lo que queda sin medir es lo menos importante.
"""

from __future__ import annotations

import argparse
import json
import random

from radar import baseline, llm, prompts, triaje
from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.evaluacion import baselines
from radar.evaluacion.baselines import CORTE
from radar.evaluacion.triaje import (
    DESDE,
    GANADOS,
    HASTA,
    NEGATIVOS_POR_EMPRESA,
    NO_GANADOS,
    SEMILLA,
    VARIANTES,
    como_diccionarios,
    universo,
)
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion, commit_actual

# La configuración del triaje que decidió D06. No se cambia para medir: es lo que se mide.
VARIANTE = VARIANTES["haiku_lote20"]
PASAN = ("si", "duda")
REMUESTREOS = 2000
ROLES = ("test", "desarrollo")  # se publica test; desarrollo se mide aparte y se marca

COMO_SE_PUBLICO = """
SELECT DISTINCT ON (l.entry_id) l.id, l.entry_id, l.objeto, l.organo, l.cpv, l.tipo_contrato
FROM licitaciones l
WHERE l.entry_id = ANY(%s)
ORDER BY l.entry_id, l.entry_updated
"""

DECISIONES = """
SELECT l.entry_id, t.decision, l.cpv
FROM triajes t
JOIN licitaciones l ON l.id = t.licitacion
WHERE t.alias = %s AND t.modelo = %s AND t.por_llamada = %s AND t.prompt_version = %s
"""


def empresas(conexion, rol: str) -> list[tuple[str, str]]:
    with conexion.cursor() as cur:
        cur.execute("SELECT alias, nif FROM perfiles WHERE rol = %s ORDER BY alias", (rol,))
        return cur.fetchall()


def ganados_de(conexion, nif: str, desde: str, hasta: str, corte: str) -> list[str]:
    with conexion.cursor() as cur:
        cur.execute(GANADOS, (nif, corte, desde, hasta))
        return [fila[0] for fila in cur.fetchall()]


def no_ganados_de(conexion, ganados: list[str], desde: str, hasta: str, cuantos: int) -> list[str]:
    with conexion.cursor() as cur:
        cur.execute(NO_GANADOS, (desde, hasta, ganados, SEMILLA, cuantos))
        return [fila[0] for fila in cur.fetchall()]


def licitaciones_de(conexion, entradas: list[str], ganados: set[str]) -> list[dict]:
    if not entradas:
        return []
    with conexion.cursor() as cur:
        cur.execute(COMO_SE_PUBLICO, (entradas,))
        filas = como_diccionarios(cur.fetchall())
    for fila in filas:
        fila["ganado"] = fila["entry_id"] in ganados
    return filas


def por_triar(conexion, alias: str, licitaciones: list[dict]) -> list[dict]:
    """Las que todavía no se han triado con esta configuración. Repetir no vuelve a pagar."""
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT licitacion FROM triajes WHERE alias = %s AND modelo = %s AND por_llamada = %s"
            " AND prompt_version = %s",
            (alias, VARIANTE["modelo"], VARIANTE["por_llamada"], triaje.PROMPT),
        )
        hechas = {fila[0] for fila in cur.fetchall()}
    return [lic for lic in licitaciones if lic["id"] not in hechas]


def plan(conexion, rol: str, desde: str, hasta: str, corte: str, negativos: int) -> list[dict]:
    """Qué queda por triar, **los ganados primero** (PLAN_MEDICION §4)."""
    plantilla = empresas(conexion, rol)
    if not plantilla:
        raise ErrorRadar(f"No hay empresas con el papel «{rol}» en la tabla perfiles.")
    tareas = []
    for alias, nif in plantilla:
        ganados = ganados_de(conexion, nif, desde, hasta, corte)
        if not ganados:
            continue
        resto = no_ganados_de(conexion, ganados, desde, hasta, negativos)
        marcados = set(ganados)
        suyas = licitaciones_de(conexion, ganados + resto, marcados)
        pendientes = por_triar(conexion, alias, suyas)
        # Mezcla con semilla fija para que los ganados no vayan todos en la misma llamada, y
        # después se ordenan por estrato: ganados primero.
        random.Random(SEMILLA).shuffle(pendientes)
        pendientes.sort(key=lambda lic: not lic["ganado"])
        if pendientes:
            tareas.append({"alias": alias, "nif": nif, "pendientes": pendientes})
    return tareas


def triar(conexion, tareas: list[dict], run_id, api=None) -> dict:
    """Tría lo pendiente. Si se alcanza el presupuesto, para y lo dice: es reanudable."""
    hecho = {"triadas": 0, "ganados": 0, "coste_eur": 0.0}
    prompt = prompts.cargar(triaje.PROMPT)
    for tarea in tareas:
        perfil = triaje.perfil_de(conexion, tarea["alias"])
        pendientes = tarea["pendientes"]
        for desde in range(0, len(pendientes), VARIANTE["por_llamada"]):
            lote = pendientes[desde : desde + VARIANTE["por_llamada"]]
            try:
                respuesta, ficha, _ = triaje.triar(
                    perfil,
                    lote,
                    modelo=VARIANTE["modelo"],
                    esfuerzo=VARIANTE["esfuerzo"],
                    prompt=prompt,
                    api=api,
                    run_id=run_id,
                )
            except llm.PresupuestoAgotado as e:
                hecho["parado"] = e.mensaje
                return hecho
            triaje.guardar(
                conexion, tarea["alias"], lote, respuesta, ficha, prompt, VARIANTE["por_llamada"], run_id
            )
            hecho["triadas"] += len(lote)
            hecho["ganados"] += sum(1 for lic in lote if lic["ganado"])
            hecho["coste_eur"] += float(ficha["coste_eur"])
    hecho["coste_eur"] = round(hecho["coste_eur"], 4)
    return hecho


# --- Medición -------------------------------------------------------------------------


def indicadores(conexion, alias: str, nif: str, filtros: dict, desde, hasta, corte) -> dict:
    """Por cada contrato ganado, si lo vio el agente y si lo vio cada baseline.

    Son los pares que necesita el bootstrap: tres indicadores 0/1 sobre el **mismo** contrato.
    """
    ganados = set(ganados_de(conexion, nif, desde, hasta, corte))
    with conexion.cursor() as cur:
        cur.execute(DECISIONES, (alias, VARIANTE["modelo"], VARIANTE["por_llamada"], triaje.PROMPT))
        decisiones = {fila[0]: (fila[1], fila[2] or []) for fila in cur.fetchall()}

    filas = []
    for entrada in sorted(ganados):
        if entrada not in decisiones:
            continue  # todavía sin triar: no se cuenta ni a favor ni en contra
        decision, cpv = decisiones[entrada]
        fila = {"entry_id": entrada, "agente": int(decision in PASAN)}
        for nombre, prefijos in filtros.items():
            fila[nombre] = int(baseline.pasa_el_filtro(cpv, prefijos))
        filas.append(fila)

    no_ganados = [(e, d, c) for e, (d, c) in decisiones.items() if e not in ganados]
    return {
        "alias": alias,
        "contratos": filas,
        "ganados_totales": len(ganados),
        "no_ganados_triados": len(no_ganados),
        "no_ganados_que_pasan": sum(1 for _, d, _ in no_ganados if d in PASAN),
        "no_ganados_baselines": {
            nombre: sum(1 for _, _, c in no_ganados if baseline.pasa_el_filtro(c or [], prefijos))
            for nombre, prefijos in filtros.items()
        },
    }


def recall(filas: list[dict], clave: str) -> float | None:
    return (sum(f[clave] for f in filas) / len(filas)) if filas else None


def bootstrap(filas: list[dict], contra: str, semilla: str = SEMILLA) -> dict:
    """Intervalo al 95 % de la diferencia de recall (agente − baseline), pareado por contrato."""
    if not filas:
        return {"diferencia": None, "ic_inferior": None, "ic_superior": None, "n": 0}
    azar = random.Random(semilla)
    diferencias = []
    for _ in range(REMUESTREOS):
        muestra = [filas[azar.randrange(len(filas))] for _ in filas]
        diferencias.append(
            sum(f["agente"] for f in muestra) / len(muestra) - sum(f[contra] for f in muestra) / len(muestra)
        )
    diferencias.sort()
    bajo = diferencias[int(0.025 * REMUESTREOS)]
    alto = diferencias[min(int(0.975 * REMUESTREOS), REMUESTREOS - 1)]
    return {
        "diferencia": round(recall(filas, "agente") - recall(filas, contra), 4),
        "ic_inferior": round(bajo, 4),
        "ic_superior": round(alto, 4),
        "n": len(filas),
        "remuestreos": REMUESTREOS,
    }


def veredicto_de(intervalo: dict) -> str:
    """Sostenida, refutada o no concluyente, con el criterio de SPEC §6 y PLAN_MEDICION §1."""
    if intervalo["diferencia"] is None:
        return "sin datos"
    if intervalo["ic_inferior"] > 0:
        return "sostenida"
    if intervalo["ic_superior"] < 0:
        return "refutada"
    return "no concluyente"


def medir(rol: str = "test", desde=DESDE, hasta=HASTA, corte=CORTE) -> list[dict]:
    """M1, M2 y la diferencia con su intervalo. No llama al modelo."""
    filtros_por_variante = baselines.prefijos_de_los_baselines(baselines.Path("docs/baselines"))
    resultados = []
    with conectar() as conexion:
        expedientes, dias = universo(conexion, desde, hasta)
        por_dia = expedientes / dias
        plantilla = empresas(conexion, rol)
        todos = []
        for alias, nif in plantilla:
            filtros = {
                nombre: (por_empresa.get(None) or por_empresa.get(alias) or [])
                for nombre, por_empresa in filtros_por_variante.items()
            }
            datos = indicadores(conexion, alias, nif, filtros, desde, hasta, corte)
            if not datos["contratos"]:
                continue
            todos += datos["contratos"]
            resultados.append(
                {
                    "metrica": "M1",
                    "variante": f"agente_{rol}",
                    "alias": alias,
                    "valor": round(recall(datos["contratos"], "agente"), 4),
                    "n": len(datos["contratos"]),
                    "detalle": {
                        "en_la_lista": sum(f["agente"] for f in datos["contratos"]),
                        "contratos_triados": len(datos["contratos"]),
                        "contratos_ganados": datos["ganados_totales"],
                        "baselines": {
                            nombre: round(recall(datos["contratos"], nombre), 4) for nombre in filtros
                        },
                    },
                }
            )
            if datos["no_ganados_triados"]:
                tasa = datos["no_ganados_que_pasan"] / datos["no_ganados_triados"]
                resultados.append(
                    {
                        "metrica": "M2",
                        "variante": f"agente_{rol}",
                        "alias": alias,
                        "valor": round(tasa * por_dia, 4),
                        "n": datos["no_ganados_triados"],
                        "detalle": {
                            "tasa_de_paso_en_no_ganados": round(tasa, 4),
                            "publicadas_al_dia": round(por_dia, 2),
                            "volumen_baselines_al_dia": {
                                nombre: round(
                                    datos["no_ganados_baselines"][nombre]
                                    / datos["no_ganados_triados"]
                                    * por_dia,
                                    2,
                                )
                                for nombre in filtros
                            },
                            "estimacion": "tasa de paso x publicadas al dia",
                        },
                    }
                )

        if not todos:
            raise ErrorRadar(
                "No hay ningún contrato ganado triado todavía, así que no hay M1 que medir. "
                "Lánzalo con: uv run python -m radar.evaluacion.agente --gastar"
            )
        for nombre in filtros_por_variante:
            intervalo = bootstrap(todos, nombre)
            resultados.append(
                {
                    "metrica": "M1_diferencia",
                    "variante": f"agente_menos_{nombre}_{rol}",
                    "alias": None,
                    "valor": intervalo["diferencia"],
                    "ic_inferior": intervalo["ic_inferior"],
                    "ic_superior": intervalo["ic_superior"],
                    "n": intervalo["n"],
                    "detalle": {
                        "recall_agente": round(recall(todos, "agente"), 4),
                        "recall_baseline": round(recall(todos, nombre), 4),
                        "veredicto": veredicto_de(intervalo),
                        "remuestreos": REMUESTREOS,
                        "semilla": SEMILLA,
                        "metodo": "bootstrap pareado por contrato, percentiles 2,5 y 97,5",
                    },
                }
            )
    return resultados


def guardar_cifras(conexion, run_id, comando, resultados, desde, hasta) -> None:
    commit = commit_actual()
    with conexion.cursor() as cur:
        for r in resultados:
            cur.execute(
                "INSERT INTO eval_resultados (metrica, variante, alias, periodo_desde,"
                " periodo_hasta, valor, ic_inferior, ic_superior, n, detalle, git_commit, comando,"
                " run_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    r["metrica"],
                    r["variante"],
                    r["alias"],
                    desde,
                    hasta,
                    r["valor"],
                    r.get("ic_inferior"),
                    r.get("ic_superior"),
                    r["n"],
                    json.dumps(r["detalle"], ensure_ascii=False),
                    commit,
                    comando,
                    run_id,
                ),
            )
    conexion.commit()


def informe(rol: str, comando: str, desde=DESDE, hasta=HASTA, corte=CORTE) -> int:
    resultados = medir(rol, desde, hasta, corte)
    with conectar() as conexion:
        run_id = abrir_ejecucion(conexion, "evaluacion", None)
        guardar_cifras(conexion, run_id, comando, resultados, desde, hasta)
        cerrar_ejecucion(conexion, run_id, "ok")

    print(f"\nM1 — recall del agente sobre las empresas de {rol} (run_id {run_id})\n")
    print(f"{'empresa':12} {'agente':>8} {'base A':>8} {'base B':>8}   contratos")
    for r in (x for x in resultados if x["metrica"] == "M1"):
        b = r["detalle"]["baselines"]
        print(
            f"{r['alias']:12} {r['valor'] * 100:7.1f}% {b.get('baseline_a', 0) * 100:7.1f}%"
            f" {b.get('baseline_b', 0) * 100:7.1f}%   {r['n']}"
        )
    print(f"\n{'M2 — licitaciones al día':40}")
    for r in (x for x in resultados if x["metrica"] == "M2"):
        v = r["detalle"]["volumen_baselines_al_dia"]
        print(
            f"{r['alias']:12} agente {r['valor']:7.1f}   base A {v.get('baseline_a', 0):7.1f}"
            f"   base B {v.get('baseline_b', 0):7.1f}"
        )
    print("\nDiferencia de M1 con intervalo al 95 % (bootstrap pareado por contrato):\n")
    for r in (x for x in resultados if x["metrica"] == "M1_diferencia"):
        d = r["detalle"]
        print(
            f"  frente a {r['variante'].split('_menos_')[1].replace('_' + rol, ''):12}"
            f" {d['recall_agente'] * 100:5.1f}% - {d['recall_baseline'] * 100:5.1f}%"
            f" = {r['valor'] * 100:+5.1f} puntos"
            f"   IC [{r['ic_inferior'] * 100:+.1f}, {r['ic_superior'] * 100:+.1f}]"
            # Sin flechas ni comillas tipograficas: la consola de Windows es cp1252 y una
            # sola de esas rompe el informe entero. Ya paso con radar.estado el 26-09-2026.
            f"   n={r['n']}   TESIS: {d['veredicto'].upper()}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 y M2 del agente (el 'después')")
    parser.add_argument("--rol", default="test", choices=ROLES)
    parser.add_argument("--desde", default=DESDE)
    parser.add_argument("--hasta", default=HASTA)
    parser.add_argument("--corte", default=CORTE)
    parser.add_argument("--negativos", type=int, default=NEGATIVOS_POR_EMPRESA)
    parser.add_argument("--gastar", action="store_true")
    parser.add_argument("--solo-medir", action="store_true")
    args = parser.parse_args()

    comando = (
        f"uv run python -m radar.evaluacion.agente --rol {args.rol} --desde {args.desde}"
        f" --hasta {args.hasta} --corte {args.corte} --negativos {args.negativos}"
    )
    try:
        if args.solo_medir:
            return informe(args.rol, comando, args.desde, args.hasta, args.corte)
        with conectar() as conexion:
            tareas = plan(conexion, args.rol, args.desde, args.hasta, args.corte, args.negativos)
            gastado = llm.gastado_hoy(conexion)
        pendientes = sum(len(t["pendientes"]) for t in tareas)
        ganados = sum(sum(1 for lic in t["pendientes"] if lic["ganado"]) for t in tareas)
        print(f"\nEmpresas de {args.rol}: {len(tareas)} con algo pendiente")
        print(f"Por triar: {pendientes} licitaciones, de las que {ganados} son contratos ganados")
        print(f"Gastado hoy: {gastado:.4f} € de {llm.presupuesto_diario():.2f} € de tope")
        if not pendientes:
            print("\nNo queda nada por triar.")
            return informe(args.rol, comando, args.desde, args.hasta, args.corte)
        if not args.gastar:
            coste = pendientes / 100 * 0.0403  # coste medido en la Fase 4, EUR por 100 triajes
            print(f"\nCostaría unos {coste:.3f} €. No se ha llamado a nada. Para hacerlo: --gastar")
            return 0

        with conectar() as conexion:
            run_id = abrir_ejecucion(conexion, "evaluacion", None)
            try:
                hecho = triar(conexion, tareas, run_id)
                cerrar_ejecucion(conexion, run_id, "ok")
            except ErrorRadar as e:
                cerrar_ejecucion(conexion, run_id, "error", e.mensaje)
                raise
        print(f"\nTriado: {hecho}")
        if hecho.get("parado"):
            print(f"\n{hecho['parado']}\nSe puede continuar con el mismo comando.")
        return informe(args.rol, comando, args.desde, args.hasta, args.corte)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
