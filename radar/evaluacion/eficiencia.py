"""M9 y M10: cuánto trabajo cuesta cada acierto.

    uv run python -m radar.evaluacion.eficiencia            # calcula y enseña
    uv run python -m radar.evaluacion.eficiencia --guardar  # además lo apunta en eval_resultados

La definición y la regla de decisión están congeladas en `docs/METRICA_EFICIENCIA.md`, escritas
antes de calcular nada. Este módulo solo las ejecuta y **no decide nada**.

**Aquí no se llama al modelo.** Es aritmética sobre M1 y M2, que ya se midieron y se pagaron en
la Fase 5. Se puede repetir las veces que haga falta sin gastar un céntimo.
"""

from __future__ import annotations

import argparse
import json

from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.evaluacion.agente import guardar_cifras
from radar.evaluacion.triaje import DESDE, HASTA
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion

COMANDO = "uv run python -m radar.evaluacion.eficiencia --guardar"

# Los días del semestre en los que hubo publicaciones (docs/informes/fase4_triaje.md §1). No son
# los días naturales: en fin de semana la Plataforma no publica, y dividir por días naturales
# repartiría entre días vacíos un trabajo que no existe.
DIAS_CON_PUBLICACIONES = 181

RIVALES = ("baseline_a", "baseline_b")

# La última medición de cada empresa. El detalle del agente trae las tres variantes calculadas
# sobre la misma base, que es el único conjunto comparable (METRICA_EFICIENCIA.md, Cambios).
M1_Y_M2 = """
SELECT DISTINCT ON (metrica, variante, alias) metrica, variante, alias, valor, n, detalle
FROM eval_resultados
WHERE metrica IN ('M1', 'M2') AND alias IS NOT NULL
ORDER BY metrica, variante, alias, calculada_en DESC
"""


def leer(conexion) -> dict:
    """Recall y volumen de cada empresa de test, con las tres variantes sobre la misma base."""
    with conexion.cursor() as cur:
        cur.execute(M1_Y_M2)
        filas = cur.fetchall()

    recall = {(v, a): float(valor) for m, v, a, valor, _, _ in filas if m == "M1"}
    contratos = {a: n for m, v, a, _, n, _ in filas if m == "M1" and v == "agente_test"}
    empresas = {}
    for metrica, variante, alias, valor, _, detalle in filas:
        if metrica != "M2" or variante != "agente_test":
            continue
        del_detalle = (detalle or {}).get("volumen_baselines_al_dia") or {}
        empresas[alias] = {
            "contratos": contratos.get(alias),
            "recall": {"agente": recall.get(("agente_test", alias))},
            "volumen": {"agente": float(valor)},
        }
        for rival in RIVALES:
            empresas[alias]["recall"][rival] = recall.get((rival, alias))
            empresas[alias]["volumen"][rival] = del_detalle.get(rival)
    return empresas


def revisadas(volumen_al_dia: float) -> float:
    """Licitaciones que pasan por delante en todo el periodo."""
    return volumen_al_dia * DIAS_CON_PUBLICACIONES


def m9(recall: float, volumen_al_dia: float, contratos: int) -> float | None:
    """Licitaciones que hay que revisar por cada contrato encontrado. Menos es mejor."""
    encontrados = recall * contratos
    if not encontrados:
        return None  # no encuentra ninguno: M9 no está definida, y no es infinito
    return revisadas(volumen_al_dia) / encontrados


def m10(recall_rival: float, volumen_rival: float, volumen_agente: float) -> float:
    """El recall del rival si solo pudiera entregar tantas licitaciones como el agente.

    Sin ranking no hay forma de recortar por relevancia, así que se recorta al azar y se supone
    que los aciertos están repartidos de forma uniforme. La suposición es fuerte y va escrita al
    lado del número en el informe (`docs/METRICA_EFICIENCIA.md` §2).
    """
    if not volumen_rival:
        return recall_rival
    return recall_rival * min(1.0, volumen_agente / volumen_rival)


def calcular(empresas: dict) -> list[dict]:
    resultados = []
    for alias, datos in sorted(empresas.items()):
        contratos = datos["contratos"]
        if not contratos:
            continue
        for quien in ("agente", *RIVALES):
            recall, volumen = datos["recall"].get(quien), datos["volumen"].get(quien)
            if recall is None or volumen is None:
                continue
            valor = m9(recall, volumen, contratos)
            resultados.append(
                {
                    "metrica": "M9",
                    "variante": "agente_test" if quien == "agente" else quien,
                    "alias": alias,
                    "valor": None if valor is None else round(valor, 4),
                    "n": contratos,
                    "detalle": {
                        "licitaciones_revisadas": round(revisadas(volumen), 1),
                        "contratos_encontrados": round(recall * contratos, 2),
                        "volumen_al_dia": volumen,
                        "recall": recall,
                        "dias_con_publicaciones": DIAS_CON_PUBLICACIONES,
                    },
                }
            )
        for rival in RIVALES:
            recall, volumen = datos["recall"].get(rival), datos["volumen"].get(rival)
            if recall is None or volumen is None:
                continue
            resultados.append(
                {
                    "metrica": "M10",
                    "variante": rival,
                    "alias": alias,
                    "valor": round(m10(recall, volumen, datos["volumen"]["agente"]), 4),
                    "n": contratos,
                    "detalle": {
                        "recall_sin_recortar": recall,
                        "recorte": round(min(1.0, datos["volumen"]["agente"] / volumen), 4),
                        "suposicion": "recorte al azar; aciertos repartidos de forma uniforme",
                    },
                }
            )
        resultados.append(
            {
                "metrica": "M10",
                "variante": "agente_test",
                "alias": alias,
                "valor": round(datos["recall"]["agente"], 4),
                "n": contratos,
                "detalle": {"recorte": 1.0, "suposicion": "ninguna: es su propio volumen"},
            }
        )
    return [r for r in resultados if r["valor"] is not None]


def veredicto(resultados: list[dict]) -> str:
    """La regla de decisión, tal y como se escribió antes de mirar (§4 del documento)."""
    por_empresa: dict[str, dict[str, float]] = {}
    for r in resultados:
        if r["metrica"] == "M9":
            por_empresa.setdefault(r["alias"], {})[r["variante"]] = r["valor"]
    gana = sum(
        1
        for v in por_empresa.values()
        if "agente_test" in v and all(v["agente_test"] < v[riv] for riv in RIVALES if riv in v)
    )
    if gana >= 3:
        return (
            f"El agente encuentra un contrato revisando menos licitaciones que los dos rivales "
            f"en {gana} de las {len(por_empresa)} empresas. M1 sigue refutada."
        )
    return (
        f"El agente solo gana en eficiencia en {gana} de las {len(por_empresa)} empresas: "
        "tampoco hay nada que rescatar por este lado."
    )


def como_se_lee(resultados: list[dict]) -> str:
    lineas = ["\nM9 — licitaciones que hay que revisar por cada contrato encontrado (menos es mejor)\n"]
    lineas.append(f"  {'Empresa':<12} {'Agente':>10} {'Baseline A':>12} {'Baseline B':>12}")
    por_empresa: dict[str, dict[str, float]] = {}
    for r in resultados:
        por_empresa.setdefault(r["alias"], {})[f"{r['metrica']}_{r['variante']}"] = r["valor"]
    for alias, v in sorted(por_empresa.items()):
        lineas.append(
            f"  {alias:<12} {v.get('M9_agente_test', 0):>10,.0f} "
            f"{v.get('M9_baseline_a', 0):>12,.0f} {v.get('M9_baseline_b', 0):>12,.0f}"
        )
    lineas.append("\nM10 — recall si todos entregaran el mismo volumen que el agente\n")
    lineas.append(f"  {'Empresa':<12} {'Agente':>10} {'Baseline A':>12} {'Baseline B':>12}")
    for alias, v in sorted(por_empresa.items()):
        lineas.append(
            f"  {alias:<12} {v.get('M10_agente_test', 0) * 100:>9.1f}% "
            f"{v.get('M10_baseline_a', 0) * 100:>11.1f}% {v.get('M10_baseline_b', 0) * 100:>11.1f}%"
        )
    return "\n".join(lineas) + f"\n\n{veredicto(resultados)}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="M9 y M10: el trabajo que cuesta cada acierto")
    parser.add_argument("--guardar", action="store_true", help="apuntarlo en eval_resultados")
    parser.add_argument("--json", action="store_true", help="sacarlo en crudo")
    args = parser.parse_args()
    try:
        with conectar() as conexion:
            empresas = leer(conexion)
            if not empresas:
                raise ErrorRadar(
                    "No hay M1 ni M2 guardadas todavía. Antes hay que medir la Fase 5: "
                    "uv run python -m radar.evaluacion.agente --solo-medir"
                )
            resultados = calcular(empresas)
            if args.guardar:
                run_id = abrir_ejecucion(conexion, "evaluacion", None)
                guardar_cifras(conexion, run_id, COMANDO, resultados, DESDE, HASTA)
                cerrar_ejecucion(conexion, run_id, "ok", None)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print(json.dumps(resultados, ensure_ascii=False, indent=2) if args.json else como_se_lee(resultados))
    if args.guardar:
        print("Apuntado en eval_resultados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
