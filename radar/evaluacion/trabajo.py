"""M7: cuánto trabajo se ahorra. No cuesta nada: sale de lo que ya está descargado.

M7 no mide minutos (para eso estaba M7b, que no se hizo y se dice en `docs/PLAN_MEDICION.md`
§7). Mide lo que sí se puede contar sin cronómetro y sin opinión:

- **Páginas que hay que leer.** Sin el radar, para saber qué solvencia pide un pliego hay que
  abrirlo y buscar; el radar señala las páginas exactas y cita la frase.
- **Documentos que hay que abrir.** Un expediente trae varios (pliego administrativo, técnico,
  anexos). El radar abre el PCAP y, si hace falta, salta a su anexo.
- **Saltos entre documentos** que el radar deja por hacer: cuando el anexo con las cifras va en
  otro fichero, el radar lo dice y ahí se para. Es trabajo que **no** ahorra, y se cuenta.

    uv run python -m radar.evaluacion.trabajo
"""

from __future__ import annotations

import argparse
import json

from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.evaluacion.baselines import CORTE
from radar.evaluacion.triaje import DESDE, HASTA
from radar.ingesta import abrir_ejecucion, cerrar_ejecucion, commit_actual

PAGINAS = """
SELECT le.id, le.paginas_totales, array_length(le.paginas, 1), le.via, le.estado,
       -- DISTINCT url a proposito: un expediente aparece en el feed una vez por cada cambio
       -- de estado, y el mismo documento se repite en cada version. Contarlas todas inflaria
       -- el "antes" y dejaria al radar mejor de lo que esta.
       (SELECT count(DISTINCT d.url) FROM documentos d
        JOIN licitaciones s ON s.id = d.licitacion
        JOIN licitaciones m ON m.id = le.licitacion AND m.entry_id = s.entry_id) AS documentos,
       (SELECT count(*) FROM requisitos r WHERE r.lectura = le.id AND r.verificada) AS requisitos
FROM lecturas le
WHERE le.prompt_version = %s
"""


def medir(prompt_version: str) -> list[dict]:
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(PAGINAS, (prompt_version,))
        filas = cur.fetchall()
    if not filas:
        raise ErrorRadar(
            "No hay ningún pliego leído todavía, así que no hay M7 que contar. "
            "Lánzalo con: uv run python -m radar.evaluacion.pliegos --gastar"
        )

    leidas = [f for f in filas if f[4] == "leido" and f[2]]
    if not leidas:
        raise ErrorRadar("Hay lecturas, pero ninguna llegó a señalar páginas. No hay M7 que contar.")

    paginas_pliego = sum(f[1] or 0 for f in leidas)
    paginas_senaladas = sum(f[2] or 0 for f in leidas)
    documentos = sum(f[5] or 0 for f in leidas)
    con_salto = sum(1 for f in leidas if "anexo" in (f[3] or ""))
    sin_anexo = sum(1 for f in filas if f[4] == "leido" and not f[6])
    return [
        {
            "metrica": "M7",
            "variante": f"agente_{prompt_version}",
            "alias": None,
            "valor": round(paginas_pliego / paginas_senaladas, 2) if paginas_senaladas else 0,
            "n": len(leidas),
            "detalle": {
                "unidad": "veces menos páginas que hay que leer",
                "pliegos": len(leidas),
                "paginas_del_pliego": paginas_pliego,
                "paginas_senaladas_por_el_radar": paginas_senaladas,
                "paginas_por_pliego": round(paginas_pliego / len(leidas), 1),
                "paginas_senaladas_por_pliego": round(paginas_senaladas / len(leidas), 1),
                "documentos_del_expediente_de_media": round(documentos / len(leidas), 1),
                "documentos_que_abre_el_radar": 1,
                "pliegos_con_salto_al_anexo": con_salto,
                "pliegos_leidos_sin_sacar_ningun_requisito": sin_anexo,
            },
        }
    ]


def guardar(resultados: list[dict], comando: str) -> None:
    commit = commit_actual()
    with conectar() as conexion:
        run_id = abrir_ejecucion(conexion, "evaluacion", None)
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
        cerrar_ejecucion(conexion, run_id, "ok")


def main() -> int:
    parser = argparse.ArgumentParser(description="M7: trabajo evitado, contado sin cronómetro")
    parser.add_argument("--prompt", default="extraccion_v1")
    parser.add_argument("--corte", default=CORTE)
    args = parser.parse_args()
    comando = f"uv run python -m radar.evaluacion.trabajo --prompt {args.prompt}"
    try:
        resultados = medir(args.prompt)
        guardar(resultados, comando)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    d = resultados[0]["detalle"]
    print(f"\nM7 — trabajo evitado, sobre {d['pliegos']} pliegos leídos\n")
    print(f"  Páginas del pliego, de media                {d['paginas_por_pliego']}")
    print(f"  Páginas que señala el radar, de media       {d['paginas_senaladas_por_pliego']}")
    print(f"  Se lee {resultados[0]['valor']} veces menos página")
    print(f"  Documentos del expediente, de media         {d['documentos_del_expediente_de_media']}")
    print(f"  Documentos que abre el radar                {d['documentos_que_abre_el_radar']}")
    print(f"  Pliegos en los que hubo que salir al anexo  {d['pliegos_con_salto_al_anexo']}")
    print(f"  Pliegos leídos sin sacar ningún requisito   {d['pliegos_leidos_sin_sacar_ningun_requisito']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
