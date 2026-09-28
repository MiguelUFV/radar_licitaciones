"""El correo del día: lo que el radar ha hecho, en una pantalla.

    uv run python -m radar.correo --empresa "Empresa A"          # lo escribe y lo enseña
    uv run python -m radar.correo --empresa "Empresa A" --fecha 2026-09-28

Aquí **no se envía nada**. Este módulo compone el asunto, el HTML y la versión en texto; quien
los manda es n8n con su credencial SMTP (D25: el correo sale de n8n, no del agente, porque si el
que falla es el agente el aviso tiene que salir igual). La API lo sirve en `/correo/hoy`.

**Qué tiene que conseguir el correo.** Que en diez segundos se sepa si hay que hacer algo hoy.
Por eso lo primero no es un saludo ni un resumen de la jornada: es la lista de licitaciones, una
por línea, con lo que el radar ha decidido. Lo que ha costado y cuántas se han mirado va al pie,
que es donde va lo que solo se consulta cuando se duda.

El correo se lee en clientes que recortan CSS y en pantallas de móvil, así que va con tabla y
estilos en línea, sin tipografías externas y sin imágenes.
"""

from __future__ import annotations

import argparse
import html
from datetime import date

from radar import empresas
from radar.bd import conectar
from radar.errores import ErrorRadar
from radar.fechas import el_dia, hoy
from radar.ficha import VEREDICTOS, en_una_linea, euros, resumen_de

DEL_DIA = f"""
SELECT f.licitacion, f.veredicto, f.motivos, l.expediente, l.objeto, l.organo,
       l.importe_sin_iva, l.plazo_presentacion
FROM fichas f
JOIN licitaciones l ON l.id = f.licitacion
WHERE f.alias = %s AND {el_dia("f.creada_en")} = %s
ORDER BY array_position(ARRAY['apta', 'no_apta', 'revisar'], f.veredicto), l.expediente
"""

TRIADAS = f"""
SELECT count(*) FILTER (WHERE decision IN ('si', 'duda')), count(*)
FROM triajes WHERE alias = %s AND {el_dia("triada_en")} = %s
"""

# Los mismos papeles que en la ficha: la cita es la voz del pliego, el resto la del radar.
SERIF = "Georgia, 'Times New Roman', serif"
SANS = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
TINTA, APUNTE, REGLA, SELLO = "#1c1e22", "#5a6270", "#d5d0c4", "#1f3a6e"


def del_dia(conexion, alias: str, dia: date) -> list[dict]:
    with conexion.cursor() as cur:
        cur.execute(DEL_DIA, (alias, dia))
        campos = (
            "licitacion",
            "veredicto",
            "motivos",
            "expediente",
            "objeto",
            "organo",
            "importe",
            "plazo",
        )
        return [dict(zip(campos, fila, strict=True)) for fila in cur.fetchall()]


def numeros_del_dia(conexion, alias: str, dia: date) -> dict:
    with conexion.cursor() as cur:
        cur.execute(TRIADAS, (alias, dia))
        candidatas, triadas = cur.fetchone()
    llamadas, gasto = empresas.gastado_hoy(conexion, alias, dia)
    return {
        "triadas": triadas,
        "candidatas": candidatas,
        "llamadas": llamadas,
        "gasto": gasto,
    }


def asunto_de(fichas: list[dict], dia: date) -> str:
    """Lo que se lee en la bandeja de entrada sin abrir el correo."""
    if not fichas:
        return f"Radar de licitaciones · {dia:%d-%m}: nada nuevo"
    aptas = sum(1 for f in fichas if f["veredicto"] == "apta")
    if aptas:
        return f"Radar de licitaciones · {dia:%d-%m}: {aptas} para presentarse, {len(fichas)} en total"
    return f"Radar de licitaciones · {dia:%d-%m}: {len(fichas)} para revisar"


def linea_texto(f: dict) -> str:
    objeto = en_una_linea(f["objeto"] or "")
    return (
        f"- {VEREDICTOS.get(f['veredicto'], f['veredicto']).upper()}\n"
        f"  {objeto[:90]}\n"
        f"  {f['organo'] or ''} · expediente {f['expediente'] or 'sin número'}\n"
        f"  {resumen_de(f['motivos'] or [])}\n"
    )


def como_texto(fichas: list[dict], numeros: dict, alias: str, dia: date) -> str:
    """La versión sin formato, que es la que se lee cuando el cliente no abre el HTML."""
    if not fichas:
        cuerpo = (
            "Hoy no ha salido ninguna licitación para ti.\n\n"
            f"Se han mirado {numeros['triadas']} licitaciones publicadas.\n"
        )
    else:
        cuerpo = "".join(linea_texto(f) + "\n" for f in fichas)
    return (
        f"Radar de licitaciones · {alias} · {dia:%d-%m-%Y}\n\n"
        f"{cuerpo}\n"
        f"Se han mirado {numeros['triadas']} licitaciones, {numeros['candidatas']} pasaron el "
        f"primer filtro. El día ha costado {euros(numeros['gasto'])} en "
        f"{numeros['llamadas']} llamadas al modelo.\n\n"
        "El radar lee el pliego y cita lo que dice. La decisión de presentarse es tuya.\n"
    )


def fila_html(f: dict) -> str:
    objeto = html.escape(en_una_linea(f["objeto"] or ""))
    detalle = [html.escape(f["organo"] or "")]
    if f.get("importe"):
        detalle.append(euros(f["importe"]))
    if f.get("plazo"):
        detalle.append(f"plazo hasta el {f['plazo']:%d-%m-%Y}")
    return f"""
  <tr><td style="padding:22px 0;border-top:1px solid {REGLA}">
    <div style="font:600 13px/1.4 {SANS};color:{SELLO}">
      {html.escape(VEREDICTOS.get(f["veredicto"], f["veredicto"]))}
    </div>
    <div style="font:400 18px/1.35 {SERIF};color:{TINTA};margin:6px 0 4px;max-width:34em">
      {objeto}
    </div>
    <div style="font:400 13px/1.5 {SANS};color:{APUNTE};max-width:34em">
      {" &middot; ".join(d for d in detalle if d)}
    </div>
    <div style="font:400 14px/1.5 {SANS};color:{TINTA};margin-top:8px;max-width:34em">
      {html.escape(resumen_de(f["motivos"] or []))}
    </div>
  </td></tr>"""


def como_html(fichas: list[dict], numeros: dict, alias: str, dia: date) -> str:
    if fichas:
        lista = "".join(fila_html(f) for f in fichas)
    else:
        lista = f"""
  <tr><td style="padding:22px 0;border-top:1px solid {REGLA};font:400 16px/1.5 {SANS};color:{TINTA}">
    Hoy no ha salido ninguna licitación para ti.
  </td></tr>"""
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(asunto_de(fichas, dia))}</title></head>
<body style="margin:0;background:#fcfbf8">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background:#fcfbf8;padding:32px 16px">
 <tr><td align="center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="max-width:620px;text-align:left">
   <tr><td style="font:400 13px/1.5 {SANS};color:{APUNTE};padding-bottom:4px">
     Radar de licitaciones &middot; {html.escape(alias)} &middot; {dia:%d-%m-%Y}
   </td></tr>
   {lista}
   <tr><td style="padding:22px 0 0;border-top:1px solid {REGLA};
                  font:400 13px/1.6 {SANS};color:{APUNTE};max-width:34em">
     <p style="margin:0 0 6px">Se han mirado {numeros["triadas"]} licitaciones publicadas;
        {numeros["candidatas"]} pasaron el primer filtro.</p>
     <p style="margin:0 0 6px">El día ha costado {euros(numeros["gasto"])} en
        {numeros["llamadas"]} llamadas al modelo.</p>
     <p style="margin:0">El radar lee el pliego y cita lo que dice. La decisión de presentarse
        es tuya.</p>
   </td></tr>
  </table>
 </td></tr>
</table>
</body></html>
"""


def del_correo(alias: str, dia: date | None = None) -> dict:
    """Asunto, HTML y texto del correo del día. No envía nada."""
    dia = dia or hoy()
    with conectar() as conexion:
        empresa = empresas.la_de(conexion, alias, con_candado=False)
        fichas = del_dia(conexion, alias, dia)
        numeros = numeros_del_dia(conexion, alias, dia)
    return {
        "para": alias,
        # A dónde va. n8n no sabe de clientes: manda a la dirección que le dé el agente.
        "destinatario": empresa["correo"],
        "fecha": dia.isoformat(),
        "asunto": asunto_de(fichas, dia),
        "html": como_html(fichas, numeros, alias, dia),
        "texto": como_texto(fichas, numeros, alias, dia),
        "licitaciones": len(fichas),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compone el correo del día (no lo envía)")
    parser.add_argument("--empresa", required=True)
    parser.add_argument("--fecha", default=None, help="AAAA-MM-DD; por defecto, hoy")
    parser.add_argument("--html", action="store_true", help="enseña el HTML en lugar del texto")
    args = parser.parse_args()
    try:
        correo = del_correo(args.empresa, date.fromisoformat(args.fecha) if args.fecha else None)
    except ErrorRadar as e:
        print(f"\n{e}")
        return 1
    print(f"\nAsunto: {correo['asunto']}\n")
    print(correo["html"] if args.html else correo["texto"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
