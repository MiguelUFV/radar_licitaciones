"""De un PDF a una ficha: localizar, extraer con cita, verificarla y decidir.

DATOS DE EJEMPLO — no usar en producción. Los pliegos de aquí son PDF construidos en el propio
test, y ninguna prueba llama a la API: el modelo se sustituye por un cliente falso que devuelve
lo que el test quiera, incluida una cita inventada.

Lo que se comprueba, en orden de importancia:

1. **Una cita que no está en la página no se usa.** Es la única defensa contra que el modelo
   escriba un requisito verosímil que el pliego no dice.
2. **Ningún camino descarta una licitación en silencio**: sin pliego, sin sección de solvencia,
   con el modelo contestando cualquier cosa… siempre sale una ficha con su motivo.
3. **El coste está acotado**: se leen unas pocas páginas y se sigue el remite una sola vez.
"""

import types

import pytest
from conftest import pdf_con_paginas

from radar import documentos, extraccion, grafo, localizar, reglas
from radar.errores import DocumentoIlegible

CLAUSULA = (
    "CLAUSULA 12. Solvencia economica y financiera\n"
    "Volumen anual de negocios referido al mejor ejercicio de los tres ultimos:\n"
    "150.000 euros. Se acreditara segun lo indicado en este pliego."
)
INDICE = "INDICE\n1. Objeto ...... 3\n2. Solvencia economica ...... 12\n3. Anexos ...... 40\n"
TECNICA = "Requisitos tecnicos del sistema. Certificacion ISO 9001 del fabricante del equipo.\n"
RELLENO = "Texto de relleno sobre plazos de entrega y forma de pago del contrato.\n"
REMITE = (
    "CLAUSULA 12. Solvencia\n"
    "Los requisitos de solvencia economica exigidos son los que figuran en el Anexo N. 1.\n"
)
ANEXO = (
    "ANEXO N. 1 - CUADRO DE CARACTERISTICAS\n"
    "Solvencia economica: volumen anual de negocios de 90.000 euros en el mejor ejercicio.\n"
)


def requisito(tipo="volumen_negocios", cita="150.000 euros", pagina=1, importe=150000.0):
    return {
        "tipo": tipo,
        "exigencia": "volumen anual de 150.000 euros",
        "cita": cita,
        "pagina": pagina,
        "importe_eur": importe,
        "anios": 3,
    }


class ApiFalsa:
    """Devuelve una respuesta por llamada. Cuenta lo que se le pide."""

    def __init__(self, *respuestas: dict):
        self.respuestas = list(respuestas)
        self.peticiones = []
        self.messages = types.SimpleNamespace(
            create=self._create,
            count_tokens=lambda **kw: types.SimpleNamespace(input_tokens=1000),
        )

    def _create(self, **peticion):
        import json

        self.peticiones.append(peticion)
        cuerpo = self.respuestas[min(len(self.peticiones) - 1, len(self.respuestas) - 1)]
        texto = json.dumps(cuerpo, ensure_ascii=False)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=texto)],
            usage=types.SimpleNamespace(
                input_tokens=1000,
                output_tokens=200,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            stop_reason="end_turn",
            _request_id="req_de_prueba",
            to_dict=lambda: {"content": [{"type": "text", "text": texto}]},
        )


@pytest.fixture
def entorno(monkeypatch):
    from radar import llm

    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("TIPO_CAMBIO_USD_EUR", "0.87")
    monkeypatch.setenv("TIPO_CAMBIO_ORIGEN", "BCE, de prueba")
    monkeypatch.setenv("PRESUPUESTO_DIARIO_EUR", "2.00")


# --- Qué páginas se leen ---------------------------------------------------------------


def test_no_se_lleva_el_indice_ni_la_parte_tecnica():
    # El fallo que esto impide, visto en un pliego real de 112 paginas: el patron de
    # certificaciones (ISO) aparece en 20 paginas tecnicas y en el indice, y la solvencia
    # estaba en la 54. La ventana se iba a las primeras y no la veia.
    pliego = pdf_con_paginas([INDICE, TECNICA, TECNICA, RELLENO, CLAUSULA, RELLENO])
    encontrado = localizar.localizar(pliego)
    assert encontrado.via == "solvencia"
    assert 5 in encontrado.numeros(), "la pagina con la solvencia tiene que estar"
    assert 1 not in encontrado.numeros(), "el indice no"


def test_se_leen_pocas_paginas_y_seguidas():
    pliego = pdf_con_paginas([RELLENO] * 3 + [CLAUSULA] + [RELLENO] * 20)
    numeros = localizar.localizar(pliego).numeros()
    assert len(numeros) <= localizar.TOPE_PAGINAS
    assert numeros == list(range(numeros[0], numeros[0] + len(numeros)))


def test_un_pliego_sin_solvencia_no_se_manda_al_modelo():
    encontrado = localizar.localizar(pdf_con_paginas([RELLENO, RELLENO]))
    assert encontrado.via == "no_localizada"
    assert not encontrado.hay_que_leer
    assert "a mano" in encontrado.motivo


def test_un_pliego_escaneado_lo_dice_sin_traza():
    # Paginas en blanco: es lo que se ve cuando el PDF es una imagen.
    import io

    from pypdf import PdfWriter

    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    memoria = io.BytesIO()
    escritor.write(memoria)
    encontrado = localizar.localizar(memoria.getvalue())
    assert encontrado.via == "no_localizada"
    assert "escaneado" in encontrado.motivo


def test_un_fichero_que_no_es_pdf_lo_dice():
    with pytest.raises(DocumentoIlegible) as fallo:
        localizar.localizar(b"PK\x03\x04 esto es un zip")
    assert "no es un PDF" in str(fallo.value)


def test_la_pagina_se_marca_para_poder_exigirla_despues():
    encontrado = localizar.localizar(pdf_con_paginas([CLAUSULA]))
    assert "=== Página 1 ===" in localizar.como_se_manda(encontrado)


# --- El anexo al que remite el pliego --------------------------------------------------


def test_el_anexo_se_busca_donde_hay_cifras_no_donde_se_menciona():
    # Un pliego real de 86 paginas nombraba "Anexo N. 1" en dos clausulas identicas y el anexo
    # iba en otro fichero. La primera version pagaba una segunda llamada para leer la otra
    # mencion: 0,06 EUR por los mismos requisitos genericos.
    pliego = pdf_con_paginas([REMITE, RELLENO, REMITE, RELLENO])
    encontrado = localizar.localizar_anexo(pliego, "1", ya_leidas={1})
    assert not encontrado.hay_que_leer
    assert "otro fichero" in encontrado.motivo


def test_si_el_anexo_esta_dentro_se_lee():
    pliego = pdf_con_paginas([REMITE, RELLENO, ANEXO, RELLENO])
    encontrado = localizar.localizar_anexo(pliego, "1", ya_leidas={1})
    assert encontrado.via == "anexos" and 3 in encontrado.numeros()


def test_se_reconoce_a_que_anexo_remite():
    assert localizar.anexo_citado(["figuran en el Anexo N. 1.", "del citado Anexo N. 1"]) == "1"
    assert localizar.anexo_citado(["segun el ANEXO III"]) == "III"
    assert localizar.anexo_citado(["sin referencia"]) is None


# --- La cita: lo que hace creíble al radar ---------------------------------------------


def test_una_cita_que_no_esta_en_la_pagina_no_se_usa():
    paginas = {1: CLAUSULA}
    buenos, rechazados = extraccion.interpretar(
        '{"requisitos": [' + _json(requisito(cita="300.000 euros de volumen")) + "]}", paginas
    )
    assert buenos == []
    assert "no aparece en el texto de la página 1" in rechazados[0]["motivo"]


def test_una_cita_literal_se_acepta_aunque_cambien_los_espacios():
    # El PDF parte las frases con saltos de linea; el modelo copia con un espacio. Es la misma
    # cita, y exigir el salto de linea seria exigir un error de extraccion del PDF.
    paginas = {1: "volumen anual de negocios:\n150.000  euros"}
    buenos, rechazados = extraccion.interpretar(
        '{"requisitos": [' + _json(requisito(cita="volumen anual de negocios: 150.000 euros")) + "]}",
        paginas,
    )
    assert rechazados == [] and len(buenos) == 1


def test_una_pagina_que_no_se_le_envio_se_rechaza():
    buenos, rechazados = extraccion.interpretar(
        '{"requisitos": [' + _json(requisito(pagina=99)) + "]}", {1: CLAUSULA}
    )
    assert buenos == []
    assert "no es una de las que se le enviaron" in rechazados[0]["motivo"]


def test_un_tipo_de_requisito_inventado_se_rechaza():
    buenos, rechazados = extraccion.interpretar(
        '{"requisitos": [' + _json(requisito(tipo="lo_que_sea")) + "]}", {1: CLAUSULA}
    )
    assert buenos == [] and "no está en la lista" in rechazados[0]["motivo"]


def test_una_cita_de_tres_palabras_no_demuestra_nada():
    buenos, rechazados = extraccion.interpretar(
        '{"requisitos": [' + _json(requisito(cita="150.000")) + "]}", {1: CLAUSULA}
    )
    assert buenos == [] and "demasiado corta" in rechazados[0]["motivo"]


def test_si_la_respuesta_no_es_json_el_mensaje_es_legible():
    with pytest.raises(extraccion.ExtraccionIlegible) as fallo:
        extraccion.interpretar("no he podido leer el pliego", {1: CLAUSULA})
    assert "a mano" in str(fallo.value) and "Traceback" not in str(fallo.value)


def test_una_cita_mala_se_pide_otra_vez_y_solo_una(bd, entorno):
    mal = {"requisitos": [requisito(cita="esto no está en el pliego")]}
    api = ApiFalsa(mal, mal)
    leido = extraccion.extraer(localizar.localizar(pdf_con_paginas([CLAUSULA])), api=api)
    assert len(api.peticiones) == extraccion.INTENTOS == 2
    assert leido.requisitos == [] and len(leido.rechazados) == 1
    # En el segundo intento se le dice qué falló, no se repite la misma petición a ciegas.
    assert "rechazado" in api.peticiones[1]["messages"][-1]["content"]


def test_si_al_segundo_intento_la_cita_es_buena_se_acepta(bd, entorno):
    api = ApiFalsa(
        {"requisitos": [requisito(cita="esto no está")]},
        {"requisitos": [requisito(cita="150.000 euros")]},
    )
    leido = extraccion.extraer(localizar.localizar(pdf_con_paginas([CLAUSULA])), api=api)
    assert len(leido.requisitos) == 1 and leido.rechazados == []


def _json(dato: dict) -> str:
    import json

    return json.dumps(dato, ensure_ascii=False)


# --- Las reglas: el modelo extrae, Python decide ---------------------------------------


def test_si_la_empresa_factura_menos_de_lo_exigido_es_no_apta():
    v = reglas.cargar("v1")
    requisitos = [extraccion.Requisito("volumen_negocios", "150.000 €", "cita", 4, 150000.0)]
    decision = v.evaluar(requisitos, {"cifra_negocio": 90000, "cifra_fuente": "cuentas 2024"})
    assert decision.veredicto == v.NO_APTA
    assert "90.000" in decision.bloqueos[0].texto and decision.bloqueos[0].pagina == 4


def test_sin_cifra_de_negocio_no_se_descarta_a_nadie():
    v = reglas.cargar("v1")
    requisitos = [extraccion.Requisito("volumen_negocios", "150.000 €", "cita", 4, 150000.0)]
    decision = v.evaluar(requisitos, {"cifra_negocio": None})
    assert decision.veredicto == v.REVISAR and not decision.bloqueos


def test_una_certificacion_que_el_perfil_no_declara_manda_a_revisar_no_a_descartar():
    # Puede tenerla y no publicarla en su web: descartar por esto seria un falso negativo.
    v = reglas.cargar("v1")
    requisitos = [extraccion.Requisito("certificaciones", "ISO 27001", "exige ISO 27001", 2)]
    decision = v.evaluar(requisitos, {"perfil": "Tenemos la ISO 9001 desde 2015."})
    assert decision.veredicto == v.REVISAR
    assert "puede tenerla" in decision.motivos[0].texto.lower()


def test_si_el_pliego_no_exige_solvencia_es_apta():
    v = reglas.cargar("v1")
    requisitos = [extraccion.Requisito("no_se_exige", "no se exige solvencia", "cita literal", 3)]
    assert v.evaluar(requisitos, {}).veredicto == v.APTA


def test_sin_requisitos_no_se_decide_nada():
    v = reglas.cargar("v1")
    decision = v.evaluar([], {})
    assert decision.veredicto == v.REVISAR and "a mano" in decision.motivos[0].texto


def test_las_reglas_llevan_version_y_una_inventada_no_se_carga():
    from radar.errores import ErrorRadar

    assert reglas.cargar().VERSION == reglas.VERSION_ACTUAL
    with pytest.raises(ErrorRadar):
        reglas.cargar("la_que_sea")


# --- El grafo: ningún camino se queda sin ficha ----------------------------------------


def lectura(*requisitos) -> dict:
    """Una lectura como la guarda el estado del grafo: datos planos, no objetos."""
    return extraccion.como_datos(extraccion.Extraccion(requisitos=list(requisitos)))


def test_los_requisitos_de_las_dos_pasadas_se_juntan():
    uno = lectura(extraccion.Requisito("remite", "x", "cita", 1))
    dos = lectura(extraccion.Requisito("volumen_negocios", "x", "c", 9))
    assert len(grafo.requisitos_de([uno, dos])) == 2


def test_el_estado_del_grafo_solo_lleva_datos_planos():
    # LangGraph guarda el estado en Postgres y avisa de que dejara de deserializar clases
    # propias. Si esto se rompe, el paso a paso guardado deja de poder leerse.
    import json

    json.dumps(lectura(extraccion.Requisito("remite", "x", "cita", 1)))


def test_el_remite_se_sigue_una_sola_vez():
    estado = {"lecturas": [lectura(extraccion.Requisito("remite", "x", "cita", 1))], "saltos": 0}
    assert grafo.hay_que_seguir_el_remite(estado)
    assert not grafo.hay_que_seguir_el_remite({**estado, "saltos": 1})


def test_si_ya_hay_una_cifra_no_se_paga_por_el_anexo():
    con_cifra = lectura(
        extraccion.Requisito("remite", "x", "cita", 1),
        extraccion.Requisito("volumen_negocios", "x", "cita", 1, importe_eur=150000.0),
    )
    assert not grafo.hay_que_seguir_el_remite({"lecturas": [con_cifra], "saltos": 0})


def test_el_minimo_de_texto_por_pagina_es_el_mismo_en_todo_el_radar():
    # localizar descarta las paginas sin capa de texto con el criterio de documentos: si cada
    # modulo usara el suyo, un pliego podria ser "escaneado" para uno y no para el otro.
    assert documentos.MINIMO_TEXTO == 50
    assert localizar.con_texto([(1, "x" * 10), (2, "y" * 80)]) == [(2, "y" * 80)]


def test_el_coste_se_lee_del_estado_plano():
    # El fallo de la incidencia 3 del 27-09-2026: `coste_de` hacia `leido.llamadas` sobre un
    # objeto, y al reanudar un expediente el checkpointer devolvia ese objeto como diccionario.
    # La tanda se cortaba a la mitad con un AttributeError.
    uno = extraccion.Extraccion(requisitos=[], llamadas=[{"coste_eur": 0.05, "id": 1}])
    dos = extraccion.Extraccion(requisitos=[], llamadas=[{"coste_eur": 0.02, "id": 2}])
    estado = {"lecturas": [extraccion.como_datos(uno), extraccion.como_datos(dos)]}
    assert grafo.coste_de(estado) == pytest.approx(0.07)
    assert grafo.coste_de({}) == 0.0
