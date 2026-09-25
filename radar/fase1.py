"""Fase 1: medir los datos reales antes de construir nada.

Descarga páginas del feed, mide qué trae y qué no, baja una muestra de pliegos y escribe un
informe con las cifras que deciden si el proyecto sigue (docs/ROADMAP.md, Fase 1).

Uso:
    uv run python -m radar.fase1 --paginas 30 --pliegos 120
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from radar import almacen, documentos, feed
from radar.errores import DocumentoIlegible, ErrorRadar
from radar.red import crear_cliente, descargar

INFORME_JSON = Path("data/informes/fase1_datos.json")
INFORME_MD = Path("docs/informes/fase1_datos.md")


def obtener(url: str, tipo: str, manifiesto: str, cliente, intentos: int = 3) -> tuple[bytes, bool]:
    """Devuelve el contenido y si venía de una descarga anterior. Repetir la medición no gasta red."""
    guardado = almacen.buscar_por_url(url, manifiesto)
    if guardado is not None:
        return guardado, True
    datos = descargar(url, cliente, intentos=intentos)
    almacen.guardar(datos, tipo, url, manifiesto)
    return datos, False


def recoger_feed(paginas: int, cliente) -> tuple[list[feed.Licitacion], dict]:
    url = feed.FEED_PERFILES
    licitaciones: list[feed.Licitacion] = []
    descargadas = 0
    bytes_totales = 0

    reutilizadas = 0
    while url and descargadas < paginas:
        contenido, del_disco = obtener(url, "feed", "fase1_feed", cliente)
        bytes_totales += len(contenido)
        reutilizadas += del_disco
        lote, url = feed.parsear_pagina(contenido.decode("utf-8", "ignore"))
        licitaciones.extend(lote)
        descargadas += 1
        print(
            f"  página {descargadas}/{paginas}: {len(lote)} licitaciones{' (de disco)' if del_disco else ''}",
            flush=True,
        )

    fechas = [feed.fecha(lic.actualizada) for lic in licitaciones]
    fechas = sorted(f for f in fechas if f)
    resumen = {
        "paginas_descargadas": descargadas,
        "paginas_reutilizadas_de_disco": reutilizadas,
        "megabytes": round(bytes_totales / 1024 / 1024, 1),
        "entradas": len(licitaciones),
        "desde": fechas[0].isoformat() if fechas else None,
        "hasta": fechas[-1].isoformat() if fechas else None,
        "dias_cubiertos": (fechas[-1] - fechas[0]).days + 1 if fechas else 0,
    }
    return licitaciones, resumen


def medir_feed(licitaciones: list[feed.Licitacion], resumen: dict) -> dict:
    estados = Counter(lic.estado for lic in licitaciones)
    informatica = [lic for lic in licitaciones if feed.es_informatica(lic)]
    adjudicadas = [lic for lic in licitaciones if lic.estado in {"ADJ", "RES"}]
    con_nif = [lic for lic in adjudicadas if lic.adjudicatario_nif]
    con_solvencia = [lic for lic in licitaciones if lic.solvencia_feed]
    con_cifras = [lic for lic in con_solvencia if lic.solvencia_con_cifras]
    remiten = [lic for lic in con_solvencia if lic.solvencia_remite_al_pliego]
    dias = max(resumen["dias_cubiertos"], 1)

    def pct(parte: int, total: int) -> float | None:
        return round(100 * parte / total, 1) if total else None

    return {
        **resumen,
        "estados": dict(estados.most_common()),
        "con_pliego_administrativo": pct(sum(1 for lic in licitaciones if lic.pcap), len(licitaciones)),
        "informatica": len(informatica),
        "informatica_pct": pct(len(informatica), len(licitaciones)),
        "informatica_por_dia": round(len(informatica) / dias, 1),
        "entradas_por_dia": round(len(licitaciones) / dias, 1),
        "adjudicadas": len(adjudicadas),
        "adjudicadas_con_nif_pct": pct(len(con_nif), len(adjudicadas)),
        "con_solvencia_en_feed_pct": pct(len(con_solvencia), len(licitaciones)),
        "solvencia_con_cifras_pct": pct(len(con_cifras), len(con_solvencia)),
        "solvencia_remite_al_pliego_pct": pct(len(remiten), len(con_solvencia)),
        "sin_cifra_en_el_feed_pct": pct(len(licitaciones) - len(con_cifras), len(licitaciones)),
        "con_lotes_pct": pct(sum(1 for lic in licitaciones if lic.lotes), len(licitaciones)),
    }


def medir_pliegos(licitaciones: list[feed.Licitacion], cuantos: int, semilla: int, cliente) -> dict:
    candidatas = [lic for lic in licitaciones if feed.es_informatica(lic) and lic.pcap]
    vistos: set[str] = set()
    unicas = []
    for lic in candidatas:
        if lic.pcap not in vistos:
            vistos.add(lic.pcap)
            unicas.append(lic)

    random.Random(semilla).shuffle(unicas)
    muestra = unicas[:cuantos]

    analisis, fallos = [], []
    for i, lic in enumerate(muestra, start=1):
        try:
            datos, _ = obtener(lic.pcap, "pliego", "fase1_pliegos", cliente, intentos=2)
            medida = documentos.analizar(datos)
            medida["expediente"] = lic.expediente
            analisis.append(medida)
        except (ErrorRadar, DocumentoIlegible) as e:
            fallos.append({"expediente": lic.expediente, "motivo": str(e)})
        if i % 10 == 0:
            print(f"  pliegos {i}/{len(muestra)} (fallos: {len(fallos)})", flush=True)

    if not analisis:
        return {"intentados": len(muestra), "descargados": 0, "fallos": fallos}

    paginas = [a["paginas"] for a in analisis]
    a_leer = [a["paginas_a_leer"] for a in analisis if a["paginas_a_leer"]]
    requisitos = Counter()
    for a in analisis:
        requisitos.update(a["requisitos_encontrados"])

    def pct(parte: int) -> float:
        return round(100 * parte / len(analisis), 1)

    return {
        "intentados": len(muestra),
        "descargados": len(analisis),
        "descargados_pct": round(100 * len(analisis) / len(muestra), 1) if muestra else 0,
        "fallos": fallos[:20],
        "paginas_mediana": statistics.median(paginas),
        "paginas_p90": sorted(paginas)[int(0.9 * len(paginas)) - 1],
        "paginas_max": max(paginas),
        "con_capa_de_texto_pct": pct(sum(1 for a in analisis if not a["escaneado"])),
        "escaneados_pct": pct(sum(1 for a in analisis if a["escaneado"])),
        "formularios_con_casillas_pct": pct(sum(1 for a in analisis if a["es_formulario"])),
        "solvencia_localizada_pct": pct(sum(1 for a in analisis if a["pagina_solvencia"])),
        "cifra_junto_a_solvencia_pct": pct(sum(1 for a in analisis if a["cifra_junto_a_solvencia"])),
        "remiten_a_anexo_o_anuncio_pct": pct(sum(1 for a in analisis if a["remite_a_anexo_o_anuncio"])),
        "paginas_a_leer_mediana": statistics.median(a_leer) if a_leer else None,
        "requisitos_frecuencia": {k: pct(v) for k, v in requisitos.most_common()},
        "caracteres_mediana": statistics.median([a["caracteres"] for a in analisis]),
    }


def estimar_coste(pliegos: dict, feed_medido: dict) -> dict:
    """Estimación de coste, no medición. Los tokens reales se cuentan en la Fase 4."""
    caracteres_pagina = (pliegos.get("caracteres_mediana") or 0) / max(pliegos.get("paginas_mediana") or 1, 1)
    paginas_leer = pliegos.get("paginas_a_leer_mediana") or 4
    tokens_pliego = int(caracteres_pagina * paginas_leer / 4) + 2500
    tokens_triaje = 400 + 150
    usd_eur = 0.8726
    precios = {  # USD por millón de tokens (entrada, salida)
        "claude-opus-5": (5, 25),
        "claude-haiku-4-5": (1, 5),
    }
    por_dia = feed_medido["informatica_por_dia"]
    coste = {}
    for modelo, (entrada, salida) in precios.items():
        triaje = (tokens_triaje * entrada / 1e6) * feed_medido["entradas_por_dia"]
        extraccion = ((tokens_pliego * entrada + 1500 * salida) / 1e6) * por_dia
        coste[modelo] = {
            "triaje_dia_eur": round(triaje * usd_eur, 2),
            "extraccion_dia_eur": round(extraccion * usd_eur, 2),
            "total_dia_eur": round((triaje + extraccion) * usd_eur, 2),
        }
    return {
        "aviso": "Estimación con 4 caracteres por token. Los tokens reales se cuentan en la Fase 4.",
        "tokens_por_pliego_estimados": tokens_pliego,
        "paginas_a_leer_por_pliego": paginas_leer,
        "por_modelo": coste,
    }


def veredicto(feed_medido: dict, pliegos: dict) -> dict:
    puertas = {
        "1. Adjudicadas con NIF del ganador ≥ 80 %": (feed_medido.get("adjudicadas_con_nif_pct") or 0) >= 80,
        "2. Pliegos descargables y legibles ≥ 70 %": (pliegos.get("descargados_pct") or 0) >= 70,
        "3. Solvencia con cifras ausente del feed ≥ 50 %": (feed_medido.get("sin_cifra_en_el_feed_pct") or 0)
        >= 50,
    }
    return {"puertas": puertas, "decision": "GO" if all(puertas.values()) else "REVISAR"}


def escribir_informe(datos: dict) -> None:
    INFORME_JSON.parent.mkdir(parents=True, exist_ok=True)
    INFORME_MD.parent.mkdir(parents=True, exist_ok=True)
    INFORME_JSON.write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")

    f, p, c, v = datos["feed"], datos["pliegos"], datos["coste"], datos["veredicto"]
    lineas = [
        "# Informe de la Fase 1 — datos reales",
        "",
        f"Generado el {datos['generado']} con `uv run python -m radar.fase1`.",
        "Todas las cifras salen de ese comando; se reproducen volviendo a ejecutarlo.",
        "",
        "## Qué se ha descargado",
        "",
        "| Medida | Valor |",
        "|---|---|",
        f"| Páginas del feed | {f['paginas_descargadas']} ({f['megabytes']} MB) |",
        f"| Licitaciones leídas | {f['entradas']} |",
        f"| Periodo cubierto | {f['desde']} a {f['hasta']} ({f['dias_cubiertos']} días) |",
        f"| Licitaciones por día | {f['entradas_por_dia']} |",
        f"| De informática (CPV 72 o 48) | {f['informatica']} ({f['informatica_pct']} %), "
        f"{f['informatica_por_dia']} al día |",
        f"| Con pliego administrativo enlazado | {f['con_pliego_administrativo']} % |",
        f"| Con lotes | {f['con_lotes_pct']} % |",
        "",
        "## La tesis, medida sobre el feed",
        "",
        "| Medida | Valor |",
        "|---|---|",
        f"| Traen bloque de solvencia en el feed | {f['con_solvencia_en_feed_pct']} % |",
        f"| De esos, con cifras | {f['solvencia_con_cifras_pct']} % |",
        f"| De esos, remiten al pliego | {f['solvencia_remite_al_pliego_pct']} % |",
        f"| **Licitaciones sin la cifra en el feed** | **{f['sin_cifra_en_el_feed_pct']} %** |",
        "",
        "## Los pliegos",
        "",
        "| Medida | Valor |",
        "|---|---|",
        f"| Pliegos intentados | {p['intentados']} |",
        f"| Descargados y legibles | {p.get('descargados', 0)} ({p.get('descargados_pct', 0)} %) |",
        f"| Páginas (mediana / p90 / máximo) | {p.get('paginas_mediana')} / {p.get('paginas_p90')} / "
        f"{p.get('paginas_max')} |",
        f"| Con capa de texto | {p.get('con_capa_de_texto_pct')} % |",
        f"| Escaneados | {p.get('escaneados_pct')} % |",
        f"| Formularios con casillas | {p.get('formularios_con_casillas_pct')} % |",
        f"| Sección de solvencia localizada | {p.get('solvencia_localizada_pct')} % |",
        f"| Con una cifra junto a la solvencia | {p.get('cifra_junto_a_solvencia_pct')} % |",
        f"| Remiten a un anexo o al anuncio | {p.get('remiten_a_anexo_o_anuncio_pct')} % |",
        f"| Páginas que hay que leer (mediana) | {p.get('paginas_a_leer_mediana')} |",
        "",
        "### Qué requisitos aparecen (porcentaje de pliegos)",
        "",
        "| Requisito | % de pliegos |",
        "|---|---|",
        *[f"| {k} | {v} % |" for k, v in p.get("requisitos_frecuencia", {}).items()],
        "",
        "## Coste estimado por día",
        "",
        f"_{c['aviso']}_",
        "",
        "| Modelo | Triaje | Extracción | Total |",
        "|---|---|---|---|",
        *[
            f"| {m} | {d['triaje_dia_eur']} € | {d['extraccion_dia_eur']} € | {d['total_dia_eur']} € |"
            for m, d in c["por_modelo"].items()
        ],
        "",
        "## Decisión",
        "",
        "| Puerta | ¿Se cumple? |",
        "|---|---|",
        *[f"| {k} | {'sí' if ok else 'NO'} |" for k, ok in v["puertas"].items()],
        "",
        f"**Veredicto: {v['decision']}**",
        "",
    ]
    INFORME_MD.write_text("\n".join(lineas), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fase 1: medir los datos reales")
    parser.add_argument("--paginas", type=int, default=30, help="páginas del feed a descargar")
    parser.add_argument("--pliegos", type=int, default=120, help="pliegos de la muestra")
    parser.add_argument("--semilla", type=int, default=20260925, help="semilla del muestreo")
    args = parser.parse_args()

    try:
        with crear_cliente() as cliente:
            print("Descargando el feed...", flush=True)
            licitaciones, resumen = recoger_feed(args.paginas, cliente)
            medido = medir_feed(licitaciones, resumen)
            print(f"Analizando {args.pliegos} pliegos...", flush=True)
            pliegos = medir_pliegos(licitaciones, args.pliegos, args.semilla, cliente)
    except ErrorRadar as e:
        print(f"\n{e}", file=sys.stderr)
        return 1

    datos = {
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "parametros": vars(args),
        "feed": medido,
        "pliegos": pliegos,
        "coste": estimar_coste(pliegos, medido),
    }
    datos["veredicto"] = veredicto(medido, pliegos)
    escribir_informe(datos)
    print(f"\nInforme escrito en {INFORME_MD}. Veredicto: {datos['veredicto']['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
