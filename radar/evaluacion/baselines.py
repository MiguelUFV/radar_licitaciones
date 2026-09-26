"""M1 y M2 del "antes": qué encuentran los filtros CPV con los que se compara el radar.

M1, recall: de los contratos que la empresa ganó de verdad, ¿cuántos habría visto el filtro?
M2, volumen: cuántas licitaciones al día deja pasar.

Los dos se calculan sobre la versión **más antigua** de cada expediente, que es la que estaba
publicada mientras el plazo seguía abierto. Usar la última sería hacer trampa: puede traer
datos que solo se supieron al adjudicar.

    uv run python -m radar.evaluacion.baselines --desde 2025-01-01 --hasta 2025-07-01
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar import baseline
from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion, commit_actual

# La versión más antigua de cada expediente publicado en el periodo: lo que se sabía mientras
# se podía presentar una oferta.
COMO_SE_PUBLICO = """
SELECT DISTINCT ON (l.entry_id) l.entry_id, l.cpv, l.entry_updated::date
FROM licitaciones l
WHERE l.entry_id IN (
    SELECT entry_id FROM licitaciones
    GROUP BY entry_id HAVING min(entry_updated) >= %s AND min(entry_updated) < %s
)
ORDER BY l.entry_id, l.entry_updated
"""

GANADOS = """
SELECT DISTINCT l.entry_id
FROM adjudicaciones a
JOIN licitaciones l ON l.id = a.licitacion
WHERE a.adjudicatario = %s
  AND l.entry_id IN (
    SELECT entry_id FROM licitaciones
    GROUP BY entry_id HAVING min(entry_updated) >= %s AND min(entry_updated) < %s
  )
"""


def universo(conexion, desde: str, hasta: str) -> list[tuple[str, list[str], object]]:
    with conexion.cursor() as cur:
        cur.execute(COMO_SE_PUBLICO, (desde, hasta))
        return cur.fetchall()


def ganados_por(conexion, nif: str, desde: str, hasta: str) -> set[str]:
    with conexion.cursor() as cur:
        cur.execute(GANADOS, (nif, desde, hasta))
        return {fila[0] for fila in cur.fetchall()}


def empresas(conexion) -> list[tuple[str, str, str]]:
    with conexion.cursor() as cur:
        cur.execute("SELECT alias, nif, rol FROM perfiles ORDER BY alias")
        return cur.fetchall()


def filtrar(publicadas, prefijos: list[str]) -> set[str]:
    return {e for e, cpv, _ in publicadas if baseline.pasa_el_filtro(cpv or [], prefijos)}


def dias_del_periodo(publicadas) -> int:
    fechas = {fecha for _, _, fecha in publicadas}
    return max(len(fechas), 1)


def medir(desde: str, hasta: str, prefijos_por_variante: dict[str, list[str]]) -> list[dict]:
    """Calcula M1 (por empresa) y M2 (global) para cada filtro."""
    comando = f"uv run python -m radar.evaluacion.baselines --desde {desde} --hasta {hasta}"
    resultados = []
    with conectar() as conexion:
        run_id = abrir_ejecucion(conexion, "evaluacion", None)
        try:
            publicadas = universo(conexion, desde, hasta)
            if not publicadas:
                raise ErrorRadar(
                    "No hay licitaciones publicadas en ese periodo. ¿Está hecha la carga histórica?"
                )
            plantilla = empresas(conexion)
            if not plantilla:
                raise ErrorRadar(
                    "No hay empresas seleccionadas todavía. Antes hay que aplicar la regla: "
                    "uv run python -m radar.seleccion"
                )
            dias = dias_del_periodo(publicadas)

            for variante, prefijos in prefijos_por_variante.items():
                pasan = filtrar(publicadas, prefijos)
                resultados.append(
                    {
                        "metrica": "M2",
                        "variante": variante,
                        "alias": None,
                        "valor": round(len(pasan) / dias, 4),
                        "n": len(publicadas),
                        "detalle": {
                            "licitaciones_que_pasan": len(pasan),
                            "dias_con_publicaciones": dias,
                            "prefijos": prefijos,
                        },
                    }
                )
                for alias, nif, rol in plantilla:
                    ganados = ganados_por(conexion, nif, desde, hasta)
                    vistos = ganados & pasan
                    resultados.append(
                        {
                            "metrica": "M1",
                            "variante": variante,
                            "alias": alias,
                            "valor": round(len(vistos) / len(ganados), 4) if ganados else None,
                            "n": len(ganados),
                            "detalle": {"ganados": len(ganados), "en_la_lista": len(vistos), "rol": rol},
                        }
                    )

            guardar(conexion, run_id, desde, hasta, comando, resultados)
            cerrar_ejecucion(conexion, run_id, "ok")
        except Exception as e:
            legible = e.mensaje if isinstance(e, ErrorRadar) else "Fallo no previsto al medir."
            conexion.rollback()
            cerrar_ejecucion(conexion, run_id, "error", legible)
            if isinstance(e, ErrorRadar):
                raise
            raise ErrorRadar(legible, detalle=repr(e)) from e
    return resultados


def guardar(conexion, run_id, desde, hasta, comando, resultados) -> None:
    commit = commit_actual()
    with conexion.cursor() as cur:
        for r in resultados:
            if r["valor"] is None:  # empresa sin contratos ganados en el periodo: no hay recall
                continue
            cur.execute(
                "INSERT INTO eval_resultados (metrica, variante, alias, periodo_desde, periodo_hasta,"
                " valor, n, detalle, git_commit, comando, run_id)"
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


def prefijos_de_los_baselines(carpeta: Path) -> dict[str, list[str]]:
    """Baseline A son dos divisiones fijas; el B sale del perfil de cada empresa."""
    variantes = {"baseline_a": list(baseline.PREFIJOS_OBVIOS)}
    amplios: set[str] = set()
    for fichero in sorted(carpeta.glob("*.md")) if carpeta.exists() else []:
        for linea in fichero.read_text(encoding="utf-8").splitlines():
            if linea.startswith("| ") and linea.count("|") >= 3:
                codigo = linea.split("|")[1].strip()
                if codigo.isdigit():
                    amplios.update(baseline.prefijos([codigo]))
    if amplios:
        variantes["baseline_b"] = sorted(amplios)
    return variantes


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 y M2 de los filtros de referencia")
    parser.add_argument("--desde", default="2025-01-01")
    parser.add_argument("--hasta", default="2025-07-01")
    parser.add_argument("--baselines", type=Path, default=Path("docs/baselines"))
    args = parser.parse_args()
    try:
        resultados = medir(args.desde, args.hasta, prefijos_de_los_baselines(args.baselines))
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    for r in resultados:
        quien = r["alias"] or "todas"
        print(f"{r['metrica']:3} {r['variante']:12} {quien:12} {r['valor']}  (n={r['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
