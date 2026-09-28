"""La ficha y el correo: lo único del radar que ve una persona que no programa.

DATOS DE EJEMPLO — no usar en producción. El escenario se monta aquí y no sale a ningún sitio.

Lo que se comprueba, en orden de importancia:

1. **Que la cita se pueda comprobar.** La página va al lado de la cita y el enlace al PDF está.
   Una ficha sin eso no es una ficha: es una opinión.
2. **Que no se enseñe de más.** Ni el NIF de la empresa, ni nombres de personas, ni jerga.
3. **Que el texto del pliego se escape.** Un pliego puede traer `<`, `&` o comillas, y eso no
   puede romper la página ni inyectar nada.
"""

import json
from datetime import date

import pytest

from radar import correo, ficha
from radar.errores import ErrorRadar

NIF = "B00000001"
CITA = "El volumen anual de negocios referido al mejor ejercicio será de, al menos, 93.000 euros"

MOTIVOS = [
    {
        "tipo": "volumen_negocios",
        "resultado": "cumple",
        "texto": "El pliego pide 93.000 € de volumen anual y la empresa declara 600.000 €.",
        "cita": CITA,
        "pagina": 52,
    },
    {
        "tipo": "clasificacion",
        "resultado": "no_se_puede_saber",
        "texto": "Hay que comprobar la clasificación empresarial en el registro oficial.",
        "cita": "La solvencia podrá acreditarse mediante la clasificación del grupo V, subgrupo 2",
        "pagina": 53,
    },
]


def montar(conexion, veredicto: str = "revisar", motivos=None, cuando: date | None = None) -> int:
    """El escenario. Se puede llamar varias veces: cada expediente lleva su propio número."""
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        n = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('f', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
            " ON CONFLICT DO NOTHING"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('f', 64), %s, %s, '2025-03-01T10:00:00+01:00') RETURNING id",
            (n, f"i{n}"),
        )
        stg = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, expediente, objeto,"
            " organo, importe_sin_iva, plazo_presentacion, ficha_url)"
            " VALUES (%s, '2025-03-01T10:00:00+01:00', %s, '2025/AB & CD',"
            " 'Servicio de venta de entradas <con símbolos> para el teatro', 'Ayuntamiento de"
            " ejemplo', 93000, '2025-04-01', 'https://ejemplo.es/expediente') RETURNING id",
            (f"i{n}", stg),
        )
        licitacion = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO documentos (licitacion, tipo, url, raw_fichero, estado_descarga)"
            " VALUES (%s, 'PCAP', 'https://ejemplo.es/pliego.pdf', repeat('f', 64), 'descargado')",
            (licitacion,),
        )
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256) VALUES ('Empresa A', %s, 'desarrollo', 3, 3, '1', repeat('c', 64))"
            " ON CONFLICT (alias) DO NOTHING",
            (NIF,),
        )
        cur.execute(
            "INSERT INTO lecturas (documento, licitacion, alias, via, paginas, paginas_totales,"
            " prompt_version, estado) VALUES ((SELECT id FROM documentos WHERE licitacion = %s"
            " LIMIT 1), %s, 'Empresa A',"
            " 'solvencia', ARRAY[52, 53], 81, 'extraccion_v1', 'leido') RETURNING id",
            (licitacion, licitacion),
        )
        lectura = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO fichas (licitacion, alias, lectura, veredicto, reglas_version, motivos,"
            " creada_en) VALUES (%s, 'Empresa A', %s, %s, 'v1', %s, %s)",
            (
                licitacion,
                lectura,
                veredicto,
                json.dumps(MOTIVOS if motivos is None else motivos, ensure_ascii=False),
                cuando or date.today(),
            ),
        )
    conexion.commit()
    return licitacion


# --- La ficha -------------------------------------------------------------------------


def test_la_ficha_lleva_la_cita_con_su_pagina_y_el_enlace_al_pdf(bd):
    with bd() as conexion:
        licitacion = montar(conexion)
        pagina = ficha.como_html(ficha.datos(conexion, licitacion, "Empresa A"), "Empresa A")
    assert "pág. 52" in pagina and "pág. 53" in pagina
    assert "93.000 euros" in pagina, "la cita literal tiene que estar"
    assert "https://ejemplo.es/pliego.pdf" in pagina, "sin enlace al PDF no se puede comprobar"
    assert "páginas 52, 53 de 81" in pagina


def test_la_ficha_no_ensena_el_nif_ni_jerga(bd):
    with bd() as conexion:
        licitacion = montar(conexion)
        pagina = ficha.como_html(ficha.datos(conexion, licitacion, "Empresa A"), "Empresa A")
    assert NIF not in pagina, "el NIF identifica a la empresa y no pinta nada en la ficha"
    for palabra in ("no_se_puede_saber", "volumen_negocios", "Traceback", "None"):
        assert palabra not in pagina, f"jerga interna en la ficha: {palabra}"


def test_lo_que_venga_del_pliego_se_escapa(bd):
    with bd() as conexion:
        licitacion = montar(
            conexion,
            motivos=[
                {
                    "tipo": "volumen_negocios",
                    "resultado": "cumple",
                    "texto": "x",
                    "cita": '<script>alert("pliego")</script> & más',
                    "pagina": 1,
                }
            ],
        )
        pagina = ficha.como_html(ficha.datos(conexion, licitacion, "Empresa A"), "Empresa A")
    assert "<script>" not in pagina
    assert "&lt;script&gt;" in pagina
    assert "2025/AB &amp; CD" in pagina, "el expediente lleva un & y tiene que salir escapado"


def test_el_veredicto_se_dice_en_castellano(bd):
    for veredicto, esperado in [
        ("apta", "Puede presentarse"),
        ("no_apta", "No puede presentarse"),
        ("revisar", "Hay que revisarlo a mano"),
    ]:
        with bd() as conexion:
            licitacion = montar(conexion, veredicto=veredicto)
            pagina = ficha.como_html(ficha.datos(conexion, licitacion, "Empresa A"), "Empresa A")
        assert esperado in pagina


def test_el_resumen_cuenta_bien_y_concuerda():
    uno = [{"resultado": "no_se_puede_saber"}]
    assert ficha.resumen_de(uno) == "De 1 requisito leído del pliego: 1 queda por comprobar a mano."
    dos = [{"resultado": "cumple"}, {"resultado": "cumple"}, {"resultado": "no_cumple"}]
    assert ficha.resumen_de(dos) == "De 3 requisitos leídos del pliego: 2 cumplen; 1 no cumple."
    assert ficha.resumen_de([]) == "No se ha podido leer ningún requisito del pliego."


def test_sin_ficha_guardada_lo_dice_sin_traza(bd):
    with bd() as conexion:
        montar(conexion)
        with pytest.raises(ErrorRadar) as fallo:
            ficha.datos(conexion, 999999, "Empresa A")
    assert "Traceback" not in str(fallo.value)
    assert "leyendo su pliego" in str(fallo.value)


def test_el_titulo_se_corta_por_una_palabra_entera():
    largo = "Servicio integral de mantenimiento y soporte de las aplicaciones informáticas municipales"
    corto = ficha.titulo_corto(largo, tope=40)
    assert len(corto) <= 41 and not corto[:-1].endswith(" ")
    assert corto.endswith("…") and " " in corto
    assert ficha.titulo_corto("Corto") == "Corto"


# --- El correo ------------------------------------------------------------------------


def test_el_asunto_dice_cuantas_se_pueden_presentar(bd):
    with bd() as conexion:
        montar(conexion, veredicto="apta")
    assert "1 para presentarse" in correo.del_correo("Empresa A")["asunto"]


def test_si_no_hay_ninguna_apta_el_asunto_no_promete_nada(bd):
    with bd() as conexion:
        montar(conexion, veredicto="revisar")
    assert "para revisar" in correo.del_correo("Empresa A")["asunto"]


def test_un_dia_sin_nada_tambien_manda_correo_y_lo_dice(bd):
    with bd() as conexion:
        montar(conexion, cuando=date(2020, 1, 1))  # la ficha es de otro día
    salida = correo.del_correo("Empresa A")
    assert "nada nuevo" in salida["asunto"]
    assert "no ha salido ninguna licitación" in salida["texto"]
    assert "no ha salido ninguna licitación" in salida["html"]


def test_el_correo_va_en_html_y_en_texto(bd):
    with bd() as conexion:
        montar(conexion)
    salida = correo.del_correo("Empresa A")
    assert salida["html"].startswith("<!doctype html>")
    assert "<" not in salida["texto"].replace("<", "", 0) or "<table" not in salida["texto"]
    assert "Ayuntamiento de ejemplo" in salida["texto"]
    assert "decisión de presentarse es tuya" in salida["texto"]


def test_el_correo_no_lleva_tipografias_externas_ni_imagenes(bd):
    # Un cliente de correo las bloquea o las recorta: si el correo depende de ellas, llega roto.
    with bd() as conexion:
        montar(conexion)
    html = correo.del_correo("Empresa A")["html"]
    for prohibido in ("fonts.googleapis", "<img", "background-image", "<script"):
        assert prohibido not in html, f"el correo no puede depender de {prohibido}"


def test_el_correo_dice_lo_que_ha_costado_el_dia(bd):
    # El gasto tiene que estar atado a la empresa. Una llamada suelta, de nadie, no sale en el
    # pie de nadie: desde que hay más de un cliente, cada uno paga lo suyo.
    with bd() as conexion:
        licitacion = montar(conexion)
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO llm_llamadas (nodo, modelo, coste_usd, coste_eur, tipo_cambio,"
                " tipo_cambio_origen) VALUES ('triaje', 'claude-haiku-4-5', 0.1, 0.0870, 0.87, 'x')"
                " RETURNING id"
            )
            llamada = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO triajes (licitacion, alias, modelo, por_llamada, prompt_version,"
                " decision, llm_llamada) VALUES (%s, 'Empresa A', 'claude-haiku-4-5', 20,"
                " 'triaje_v1', 'si', %s)",
                (licitacion, llamada),
            )
        conexion.commit()
    salida = correo.del_correo("Empresa A")
    assert "0,09 €" in salida["texto"] or "0,09 €" in salida["html"]


def test_una_empresa_que_no_existe_lo_dice(bd):
    with bd() as conexion:
        montar(conexion)
    with pytest.raises(ErrorRadar) as fallo:
        correo.del_correo("Empresa Z")
    assert "Empresa Z" in str(fallo.value) and "Traceback" not in str(fallo.value)


# --- Los workflows de n8n --------------------------------------------------------------


def test_el_workflow_diario_pide_el_correo_al_agente_y_lo_envia():
    from radar import n8n

    diario = n8n.workflow_diario()
    nombres = [nodo["name"] for nodo in diario["nodes"]]
    assert "Pedir el correo del dia" in nombres and "Enviar el correo del dia" in nombres
    # El envío va detrás de la ingesta y de los pliegos, no al revés.
    assert nombres.index("Enviar el correo del dia") > nombres.index("Bajar los pliegos pendientes")


def test_el_aviso_de_fallo_sale_por_correo_despues_de_quedar_anotado():
    from radar import n8n

    errores = n8n.workflow_errores({"id": "x", "name": "radar_postgres"})
    conexiones = errores["connections"]
    assert conexiones["Anotar la incidencia"]["main"][0][0]["node"] == "Avisar por correo", (
        "primero se anota en la base y luego se avisa: si el correo falla, la incidencia queda"
    )


def test_ninguna_contrasena_viaja_en_los_workflows():
    from radar import n8n

    definiciones = json.dumps(
        [n8n.workflow_diario(), n8n.workflow_errores({"id": "x", "name": "y"})], ensure_ascii=False
    )
    for nodo in n8n.workflow_errores({"id": "x", "name": "y"})["nodes"]:
        credenciales = nodo.get("credentials", {})
        for datos in credenciales.values():
            assert set(datos) <= {"id", "name"}, "una credencial solo se referencia por id y nombre"
    for prohibido in ("password", "contrasena", "contraseña", "apppassword"):
        assert prohibido not in definiciones.lower()
