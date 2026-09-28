"""Regenera el informe de resultados desde la base, sin llamar a la API.

    uv run python -m radar.evaluacion --informe

Es la puerta de salida de la Fase 5: otra persona con el repositorio y la base restaurada
ejecuta este comando y obtiene el mismo informe, con el commit de git con el que se calculó cada
cifra. Aquí no se calcula nada nuevo: se lee `eval_resultados` y se escribe el documento. Si una
métrica falta, el informe lo dice en lugar de dejar el hueco.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from radar import fechas
from radar.bd import conectar
from radar.errores import ErrorRadar

DESTINO = Path("docs/informes/fase5_resultados.md")

# La última fila de cada métrica: la medición más reciente manda, y las anteriores se quedan en
# la tabla para poder ver que la cifra no ha cambiado a conveniencia.
ULTIMAS = """
SELECT DISTINCT ON (metrica, variante, alias)
       metrica, variante, alias, valor, ic_inferior, ic_superior, n, detalle, git_commit,
       comando, calculada_en
FROM eval_resultados
ORDER BY metrica, variante, alias, calculada_en DESC
"""


# Los contratos que la empresa gano de verdad y el triaje descarto, con el motivo que dio. Es
# la parte mas util del informe cuando el resultado es malo: dice **donde** falla.
FALLOS = """
WITH publicadas AS (
    SELECT entry_id FROM licitaciones
    GROUP BY entry_id HAVING min(entry_updated) >= %s AND min(entry_updated) < %s
), ganados AS (
    SELECT DISTINCT p.alias, l.entry_id
    FROM adjudicaciones a
    JOIN licitaciones l ON l.id = a.licitacion
    JOIN perfiles p ON p.nif = a.adjudicatario AND p.rol = 'test'
    WHERE l.entry_updated < %s AND l.entry_id IN (SELECT entry_id FROM publicadas)
)
SELECT t.alias, l.objeto, t.motivo
FROM triajes t
JOIN licitaciones l ON l.id = t.licitacion
JOIN ganados g ON g.alias = t.alias AND g.entry_id = l.entry_id
WHERE t.decision = 'no'
ORDER BY t.alias, l.objeto
"""


def fallos(conexion, desde: str, hasta: str, corte: str) -> list[tuple[str, str, str]]:
    with conexion.cursor() as cur:
        cur.execute(FALLOS, (desde, hasta, corte))
        return cur.fetchall()


def tabla_fallos(filas: list[tuple[str, str, str]], por_empresa: int = 4) -> list[str]:
    """Los contratos perdidos, unos pocos por empresa, con el motivo que dio el triaje."""
    if not filas:
        return ["_El agente no descartó ningún contrato que la empresa ganara._", ""]
    lineas = [
        "| Empresa | Contrato que ganó y el agente descartó | Motivo que dio el agente |",
        "|---|---|---|",
    ]
    vistos: dict[str, int] = {}
    for alias, objeto, motivo in filas:
        vistos[alias] = vistos.get(alias, 0) + 1
        if vistos[alias] > por_empresa:
            continue
        objeto = " ".join((objeto or "").split())[:90]
        motivo = " ".join((motivo or "").split())[:130]
        lineas.append(f"| {alias} | {objeto} | {motivo} |")
    resto = {a: n - por_empresa for a, n in vistos.items() if n > por_empresa}
    if resto:
        cola = ", ".join(f"{a}: {n} más" for a, n in sorted(resto.items()))
        lineas += ["", f"Se muestran {por_empresa} por empresa. Hay {cola}."]
    total = ", ".join(f"{a} {n}" for a, n in sorted(vistos.items()))
    return lineas + ["", f"Contratos perdidos por empresa: {total}.", ""]


def leer(conexion) -> list[dict]:
    campos = (
        "metrica",
        "variante",
        "alias",
        "valor",
        "ic_inferior",
        "ic_superior",
        "n",
        "detalle",
        "git_commit",
        "comando",
        "calculada_en",
    )
    with conexion.cursor() as cur:
        cur.execute(ULTIMAS)
        return [dict(zip(campos, fila, strict=True)) for fila in cur.fetchall()]


def de(filas: list[dict], metrica: str, variante: str | None = None) -> list[dict]:
    return [
        f
        for f in filas
        if f["metrica"] == metrica and (variante is None or f["variante"].startswith(variante))
    ]


def porcentaje(valor) -> str:
    return "—" if valor is None else f"{float(valor) * 100:.1f} %"


def numero(valor, decimales: int = 1) -> str:
    return "—" if valor is None else f"{float(valor):.{decimales}f}".replace(".", ",")


def tabla_m1(filas: list[dict]) -> list[str]:
    """Recall del agente frente a los dos baselines, empresa por empresa."""
    agente = sorted(de(filas, "M1", "agente_test"), key=lambda f: f["alias"] or "")
    if not agente:
        return ["_Todavía no hay M1 del agente sobre las empresas de test._", ""]
    lineas = [
        "| Empresa | Contratos | Baseline A | Baseline B | **Agente** |",
        "|---|---|---|---|---|",
    ]
    for f in agente:
        b = (f["detalle"] or {}).get("baselines", {})
        lineas.append(
            f"| {f['alias']} | {f['n']} | {porcentaje(b.get('baseline_a'))} |"
            f" {porcentaje(b.get('baseline_b'))} | **{porcentaje(f['valor'])}** |"
        )
    return lineas + [""]


def tabla_diferencia(filas: list[dict]) -> list[str]:
    diferencias = de(filas, "M1_diferencia")
    if not diferencias:
        return ["_Todavía no hay diferencia calculada._", ""]
    lineas = [
        "| Comparación | Agente | Rival | Diferencia | IC 95 % | n | Veredicto |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in sorted(diferencias, key=lambda f: f["variante"]):
        d = f["detalle"] or {}
        rival = f["variante"].split("_menos_")[-1].replace("_test", "").replace("_", " ")
        lineas.append(
            f"| frente a {rival} | {porcentaje(d.get('recall_agente'))} |"
            f" {porcentaje(d.get('recall_baseline'))} | {porcentaje(f['valor'])} |"
            f" [{porcentaje(f['ic_inferior'])}, {porcentaje(f['ic_superior'])}] | {f['n']} |"
            f" **{(d.get('veredicto') or '—').upper()}** |"
        )
    return lineas + [""]


def tabla_m2(filas: list[dict]) -> list[str]:
    agente = sorted(de(filas, "M2", "agente_test"), key=lambda f: f["alias"] or "")
    if not agente:
        return ["_Todavía no hay M2 del agente: falta triar los no ganados de la muestra._", ""]
    lineas = [
        "| Empresa | Baseline A | Baseline B | **Agente** | Muestra |",
        "|---|---|---|---|---|",
    ]
    for f in agente:
        v = (f["detalle"] or {}).get("volumen_baselines_al_dia", {})
        lineas.append(
            f"| {f['alias']} | {numero(v.get('baseline_a'))} | {numero(v.get('baseline_b'))} |"
            f" **{numero(f['valor'])}** | {f['n']} no ganados |"
        )
    return lineas + [""]


def veredicto_global(filas: list[dict]) -> str:
    veredictos = {(f["detalle"] or {}).get("veredicto") for f in de(filas, "M1_diferencia")}
    veredictos.discard(None)
    if not veredictos:
        return "sin medir todavía"
    if veredictos == {"sostenida"}:
        return "sostenida frente a los dos baselines"
    if "refutada" in veredictos and "sostenida" not in veredictos:
        return "refutada"
    if "sostenida" in veredictos:
        return "sostenida frente a un baseline y no concluyente frente al otro"
    return "no concluyente"


def escribir(filas: list[dict], destino: Path = DESTINO, perdidos: list | None = None) -> Path:
    m5 = de(filas, "M5")
    m7 = de(filas, "M7")
    m8 = de(filas, "M8")
    commits = {f["git_commit"] for f in filas if f["git_commit"]}
    texto = [
        "# Fase 5 — Resultados",
        "",
        "**Este fichero lo genera un comando. No se edita a mano:**",
        "",
        "```bash",
        "uv run python -m radar.evaluacion --informe",
        "```",
        "",
        f"Regenerado el {fechas.hoy().strftime('%d-%m-%Y')} desde la tabla `eval_resultados`, sin",
        "llamar a la API. El procedimiento estaba congelado antes de medir en",
        "`docs/PLAN_MEDICION.md`; los criterios, en `docs/SPEC.md` §6.",
        "",
        f"Commits con los que se calcularon estas cifras: {', '.join(sorted(commits)) or '—'}.",
        "",
        "## La tesis",
        "",
        f"> **{veredicto_global(filas).capitalize()}.**",
        "",
        "La tesis se sostiene solo si la diferencia de recall es positiva **y** su intervalo de",
        "confianza al 95 % excluye el 0. Una diferencia positiva con un intervalo que cruza el 0 es",
        "«no concluyente», y se publica como tal.",
        "",
        *tabla_diferencia(filas),
        "## M1 — recall: de los contratos que la empresa ganó, cuántos estaban en la lista",
        "",
        *tabla_m1(filas),
        "El recall se mide sobre **todos** los contratos ganados del periodo, no sobre una muestra.",
        "",
        "## M2 — volumen: cuántas licitaciones al día deja pasar cada uno",
        "",
        *tabla_m2(filas),
        "El volumen del agente es una **estimación** a partir de la muestra de no ganados",
        "(`docs/PLAN_MEDICION.md` §3).",
        "",
        "## M5 — citas verificadas",
        "",
    ]
    if m5:
        f = m5[0]
        d = f["detalle"] or {}
        texto += [
            f"**{porcentaje(f['valor'])}** de las {f['n']} extracciones tienen una cita que aparece",
            f"literal en la página que dijo el modelo. Rechazadas: {d.get('rechazadas', '—')}.",
            f"Pliegos leídos: {d.get('lecturas', '—')}. El criterio de fiabilidad es ≥ 98 %.",
            "",
        ]
    else:
        texto += ["_Sin medir._", ""]

    texto += ["## M7 — trabajo evitado", ""]
    if m7:
        d = m7[0]["detalle"] or {}
        texto += [
            f"Se leen **{numero(m7[0]['valor'], 2)} veces menos páginas**:",
            f"{numero(d.get('paginas_senaladas_por_pliego'))} páginas señaladas por el radar frente a",
            f"{numero(d.get('paginas_por_pliego'))} que tiene el pliego, sobre {d.get('pliegos')} pliegos.",
            f"Y un documento abierto en lugar de {numero(d.get('documentos_del_expediente_de_media'))}",
            "que trae el expediente.",
            "",
            "No hay cifra de minutos: había que cronometrarla antes de construir el agente y no se",
            "hizo (`docs/PLAN_MEDICION.md` §7).",
            "",
        ]
    else:
        texto += ["_Sin medir._", ""]

    texto += ["## M8 — coste", ""]
    if m8:
        for f in sorted(m8, key=lambda f: f["variante"]):
            d = f["detalle"] or {}
            texto.append(
                f"- `{f['variante']}`: **{numero(f['valor'], 4)} €** por 100 licitaciones triadas"
                f" ({d.get('licitaciones_triadas', '—')} triadas en {d.get('llamadas', '—')} llamadas,"
                f" {numero(d.get('eur_total'), 4)} € en total)."
            )
        texto.append("")
    else:
        texto += ["_Sin medir._", ""]

    faltan = [
        nombre
        for nombre, hay in [
            ("M2 (volumen del agente)", bool(de(filas, "M2", "agente_test"))),
            ("M3 (exclusiones erróneas por solvencia)", bool(de(filas, "M3"))),
            ("M4 (exactitud de la extracción)", bool(de(filas, "M4"))),
            ("M6 (precisión, etiquetado a ciegas)", bool(de(filas, "M6"))),
        ]
        if not hay
    ]
    texto += [
        "## Dónde falla: los contratos que la empresa ganó y el agente descartó",
        "",
        *tabla_fallos(perdidos or []),
        "## Lo que falta por medir",
        "",
    ]
    texto += [f"- {nombre}" for nombre in faltan] or ["Nada: están las ocho."]
    texto += [
        "",
        "---",
        "",
        "Cada cifra de este informe sale de una fila de `eval_resultados` con su `run_id`, su",
        "comando y su commit. Para verlas todas:",
        "",
        "```sql",
        "SELECT metrica, variante, alias, valor, ic_inferior, ic_superior, n, git_commit",
        "FROM eval_resultados ORDER BY calculada_en DESC;",
        "```",
        "",
    ]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(texto), encoding="utf-8")
    return destino


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenera el informe de resultados")
    parser.add_argument("--informe", action="store_true")
    parser.add_argument("--destino", type=Path, default=DESTINO)
    parser.add_argument("--desde", default="2025-01-01")
    parser.add_argument("--hasta", default="2025-07-01")
    parser.add_argument("--corte", default="2026-09-01")
    args = parser.parse_args()
    if not args.informe:
        parser.print_help()
        return 0
    try:
        with conectar() as conexion:
            filas = leer(conexion)
            if not filas:
                raise ErrorRadar("La tabla eval_resultados está vacía: no hay nada que publicar.")
            perdidos = fallos(conexion, args.desde, args.hasta, args.corte)
        destino = escribir(filas, args.destino, perdidos)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print(f"\nInforme regenerado: {destino.as_posix()}")
    print(f"Tesis: {veredicto_global(filas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
