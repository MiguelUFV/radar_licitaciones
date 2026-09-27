"""Cómo va el radar, en castellano y de un vistazo.

Está pensado para mirarlo sin saber SQL ni abrir nada: dice qué hay descargado, qué falta,
si hay algo en marcha ahora mismo y si algo necesita atención.

    uv run python -m radar.estado
"""

from __future__ import annotations

from datetime import UTC, datetime

from radar import llm, personas
from radar.bd import conectar
from radar.errores import ErrorRadar

VENTANA = ("2025-01", "2025-06")
POSTERIORES = ("2025-07", "2026-08")


def hace_cuanto(momento: datetime | None) -> str:
    if momento is None:
        return "nunca"
    minutos = int((datetime.now(UTC) - momento).total_seconds() // 60)
    if minutos < 1:
        return "ahora mismo"
    if minutos < 60:
        return f"hace {minutos} min"
    horas = minutos // 60
    if horas < 24:
        return f"hace {horas} h"
    return f"hace {horas // 24} días"


def cuantos_meses(cur, desde: str, hasta: str) -> int:
    cur.execute("SELECT count(*) FROM historico_meses WHERE mes >= %s AND mes <= %s", (desde, hasta))
    return cur.fetchone()[0]


def meses_totales(desde: str, hasta: str) -> int:
    a, b = (int(desde[:4]), int(desde[5:])), (int(hasta[:4]), int(hasta[5:]))
    return (b[0] - a[0]) * 12 + (b[1] - a[1]) + 1


def barra(hechos: int, total: int, ancho: int = 24) -> str:
    llenos = round(ancho * hechos / total) if total else 0
    return f"[{'#' * llenos}{'.' * (ancho - llenos)}] {hechos} de {total}"


def informe() -> str:
    lineas = [f"Radar de licitaciones — {datetime.now().strftime('%d-%m-%Y %H:%M')}", ""]
    with conectar() as conexion, conexion.cursor() as cur:
        lineas.append("DESCARGA DEL HISTÓRICO")
        for titulo, (desde, hasta) in [
            ("Periodo de estudio (ene-jun 2025)", VENTANA),
            ("Meses posteriores (jul 2025-ago 2026)", POSTERIORES),
        ]:
            hechos = cuantos_meses(cur, desde, hasta)
            total = meses_totales(desde, hasta)
            marca = "  completo" if hechos == total else ""
            lineas.append(f"  {titulo:38} {barra(hechos, total)}{marca}")

        cur.execute("SELECT mes, cargado_en FROM historico_meses ORDER BY cargado_en DESC LIMIT 1")
        ultimo = cur.fetchone()
        if ultimo:
            lineas.append(f"  {'Último mes cargado':38} {ultimo[0]}, {hace_cuanto(ultimo[1])}")

        cur.execute(
            "SELECT inicio FROM ejecuciones WHERE estado = 'en_curso' AND tipo = 'historica'"
            " ORDER BY inicio DESC LIMIT 1"
        )
        en_marcha = cur.fetchone()
        estado = f"sí, empezó {hace_cuanto(en_marcha[0])}" if en_marcha else "no"
        lineas += [f"  {'Descargando ahora mismo':38} {estado}", "", "LO QUE HAY EN LA BASE"]

        for titulo, consulta in [
            ("Licitaciones", "SELECT count(*) FROM licitaciones"),
            ("Expedientes distintos", "SELECT count(DISTINCT entry_id) FROM licitaciones"),
            ("Adjudicaciones (quién ganó)", "SELECT count(*) FROM adjudicaciones"),
            ("Pliegos descargados", "SELECT count(*) FROM documentos WHERE estado_descarga = 'descargado'"),
            ("Empresas del estudio", "SELECT count(*) FROM perfiles"),
        ]:
            cur.execute(consulta)
            lineas.append(f"  {titulo:38} {cur.fetchone()[0]:>10,}".replace(",", "."))

        lineas += ["", "INGESTA DIARIA"]
        cur.execute(
            "SELECT inicio, estado, n8n_execution_id FROM ejecuciones"
            " WHERE tipo = 'diaria' ORDER BY inicio DESC LIMIT 1"
        )
        diaria = cur.fetchone()
        if diaria:
            quien = "lanzada por n8n" if diaria[2] else "lanzada a mano"
            resultado = "correcta" if diaria[1] == "ok" else diaria[1]
            lineas.append(f"  {'Última vez':38} {hace_cuanto(diaria[0])}, {resultado} ({quien})")
        else:
            lineas.append(f"  {'Última vez':38} todavía no se ha lanzado ninguna")

        cur.execute("SELECT count(DISTINCT licitacion), count(DISTINCT alias), count(*) FROM triajes")
        miradas, empresas, decisiones = cur.fetchone()
        if decisiones:
            lineas += ["", "TRIAJE (el filtro que lee el modelo)"]
            lineas.append(
                f"  {'Decisiones del triaje':38} {decisiones} sobre {miradas} licitaciones"
                f" y {empresas} empresa(s)"
            )
            cur.execute(
                "SELECT count(*), coalesce(sum(coste_eur), 0) FROM llm_llamadas"
                " WHERE llamada_en >= date_trunc('day', now())"
            )
            llamadas, gastado = cur.fetchone()
            try:
                tope = f"de {llm.presupuesto_diario():.2f} EUR de tope".replace(".", ",")
            except ErrorRadar:
                tope = "sin tope puesto en .env"
            euros = f"{float(gastado):.4f}".replace(".", ",")
            lineas.append(f"  {'Gasto en el modelo hoy':38} {euros} EUR, {tope} ({llamadas} llamadas)")

        cur.execute("SELECT count(*) FROM lecturas WHERE estado = 'leido'")
        leidos = cur.fetchone()[0]
        if leidos:
            cur.execute(
                "SELECT count(*) FILTER (WHERE verificada), count(*),"
                " coalesce(sum(CASE WHEN verificada THEN 1 ELSE 0 END), 0) FROM requisitos"
            )
            verificadas, extracciones, _ = cur.fetchone()
            cur.execute("SELECT veredicto, count(*) FROM fichas GROUP BY 1 ORDER BY 1")
            veredictos = cur.fetchall()
            lineas += ["", "PLIEGOS LEÍDOS (lo que el modelo ha sacado del PDF)"]
            lineas.append(f"  {'Pliegos leídos':38} {leidos}")
            porcentaje = 100 * verificadas / extracciones if extracciones else 0
            lineas.append(
                f"  {'Requisitos con cita comprobada':38} {verificadas} de {extracciones}"
                f" ({porcentaje:.0f} %)"
            )
            nombres = {"apta": "puede presentarse", "no_apta": "no puede", "revisar": "a revisar"}
            reparto = ", ".join(f"{n} {nombres.get(v, v)}" for v, n in veredictos)
            lineas.append(f"  {'Fichas':38} {reparto}")

        lineas += ["", "AVISOS"]
        avisos = []
        cur.execute(f"SELECT count(*) FROM adjudicaciones WHERE {personas.SQL_EN_CLARO}")
        en_claro = cur.fetchone()[0]
        if en_claro:
            avisos.append(
                f"{en_claro} datos personales guardados en claro. Se arregla con:"
                " uv run python -m radar.personas --anonimizar"
            )
        cur.execute(
            "SELECT count(*) FROM ejecuciones WHERE estado = 'en_curso'"
            " AND inicio < now() - interval '2 hours'"
        )
        colgadas = cur.fetchone()[0]
        if colgadas:
            avisos.append(f"{colgadas} proceso(s) empezados hace horas y sin terminar: se cortaron.")
        cur.execute("SELECT count(*) FROM incidencias WHERE ocurrida_en > now() - interval '7 days'")
        incidencias = cur.fetchone()[0]
        if incidencias:
            avisos.append(f"{incidencias} fallo(s) del proceso automático esta semana (tabla incidencias).")

        lineas += [f"  - {a}" for a in avisos] or ["  Ninguno."]
    return "\n".join(lineas)


def main() -> int:
    try:
        print(informe())
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
