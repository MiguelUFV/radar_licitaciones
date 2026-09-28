"""El triaje: qué se le manda al modelo, qué se entiende de lo que contesta y qué se mide.

DATOS DE EJEMPLO — no usar en producción. Las licitaciones de aquí están inventadas y se quedan
en la base de pruebas. Ninguna llamada sale a la API: se le pasa un cliente falso.

Lo que se comprueba, en orden de importancia:

1. Que el triaje no ve quién ganó el contrato. Si lo viera, todo lo medido después sería mentira.
2. Que ninguna licitación se pierde por el camino cuando el modelo contesta mal.
3. Que el coste de una llamada que tría 20 licitaciones se cuenta **una** vez.
"""

import json
import types

import pytest

from radar import errores, llm, prompts, triaje
from radar.errores import ErrorRadar
from radar.evaluacion import triaje as experimento

PERFIL = "## Qué hace\nDesarrolla software de gestión de personal.\n"
CAMBIO = 0.87


class ApiFalsa:
    """Con la forma que usa radar/llm.py: messages.create y messages.count_tokens."""

    def __init__(self, texto: str):
        self.peticiones = []
        self.messages = types.SimpleNamespace(
            create=self._create,
            count_tokens=lambda **kw: types.SimpleNamespace(input_tokens=500),
        )
        self.texto = texto

    def _create(self, **peticion):
        self.peticiones.append(peticion)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=self.texto)],
            usage=types.SimpleNamespace(
                input_tokens=500,
                output_tokens=100,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            stop_reason="end_turn",
            _request_id="req_de_prueba",
            to_dict=lambda: {"content": [{"type": "text", "text": self.texto}]},
        )


@pytest.fixture
def entorno(monkeypatch):
    # load_dotenv volvería a poner las variables del .env de verdad justo después de quitarlas,
    # y el test pasaría (o fallaría) por el motivo equivocado.
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("TIPO_CAMBIO_USD_EUR", str(CAMBIO))
    monkeypatch.setenv("TIPO_CAMBIO_ORIGEN", "BCE, de prueba")
    monkeypatch.setenv("PRESUPUESTO_DIARIO_EUR", "2.00")


def licitacion(numero: int, objeto: str = "Servicio de mantenimiento de la aplicación de nóminas"):
    return {
        "id": numero,
        "entry_id": f"e{numero}",
        "objeto": objeto,
        "organo": "Ayuntamiento de ejemplo",
        "cpv": ["72267100"],
        "tipo_contrato": "Servicios",
    }


def respuesta_json(decisiones) -> str:
    return json.dumps({"decisiones": decisiones}, ensure_ascii=False)


# --- Los prompts llevan versión en el nombre -------------------------------------------


def test_todos_los_prompts_llevan_version_en_el_nombre():
    # Cambiar un prompt es crear triaje_v2.md, no editar triaje_v1.md: si un fichero no lleva
    # version, una cifra medida con el no se puede reproducir.
    sin_version = [n for n in prompts.todos() if not prompts.NOMBRE.match(n)]
    assert sin_version == []


def test_el_prompt_se_carga_con_su_huella():
    p = prompts.cargar("triaje_v1")
    assert (p.nombre, p.version) == ("triaje", "v1")
    assert len(p.sha256) == 64
    assert "JSON" in p.texto


def test_un_prompt_sin_version_se_rechaza():
    with pytest.raises(ErrorRadar) as fallo:
        prompts.cargar("triaje")
    assert "versión" in str(fallo.value)


# --- Lo que el modelo ve --------------------------------------------------------------


def test_el_triaje_no_ve_quien_gano_ni_el_importe():
    lic = licitacion(1) | {"adjudicatario": "B12345678", "importe_sin_iva": 50000}
    visto = triaje.como_se_ve(lic)
    assert "B12345678" not in visto
    assert "50000" not in visto
    assert "nóminas" in visto and "72267100" in visto


def test_una_licitacion_sin_objeto_se_manda_igual_diciendolo():
    visto = triaje.como_se_ve({"objeto": None, "organo": None, "cpv": []})
    assert "(sin objeto)" in visto and "sin CPV" in visto


def test_las_referencias_son_el_numero_de_orden():
    texto = triaje.mensaje([licitacion(7), licitacion(9)])
    assert "### 1" in texto and "### 2" in texto
    assert "e7" not in texto  # el expediente no hace falta y gastaría tokens


def test_el_perfil_va_detras_de_las_instrucciones():
    entero = triaje.sistema(PERFIL)
    assert entero.index("Eres el primer filtro") < entero.index("gestión de personal")


# --- Lo que se entiende de la respuesta ------------------------------------------------


def test_lee_el_json_limpio():
    r = triaje.interpretar(respuesta_json([{"ref": "1", "decision": "si", "motivo": "nóminas"}]), ["1"])
    assert r.decisiones == {"1": ("si", "nóminas")}
    assert r.faltan == [] and r.ilegible is None


def test_lee_el_json_con_vallas_y_una_frase_delante():
    texto = (
        "Aquí tienes el resultado:\n```json\n"
        + respuesta_json([{"ref": "1", "decision": "no", "motivo": "es obra civil"}])
        + "\n```\n"
    )
    r = triaje.interpretar(texto, ["1"])
    assert r.decisiones["1"][0] == "no"


def test_si_con_tilde_es_la_misma_decision():
    r = triaje.interpretar(respuesta_json([{"ref": "1", "decision": "Sí", "motivo": "x"}]), ["1"])
    assert r.decisiones["1"][0] == "si"


def test_una_licitacion_sin_contestar_se_dice():
    r = triaje.interpretar(respuesta_json([{"ref": "1", "decision": "si", "motivo": "x"}]), ["1", "2"])
    assert r.faltan == ["2"]


def test_una_decision_inventada_no_se_cuela():
    # "quizás" no está en la lista cerrada: esa licitación se queda sin decisión, no se adivina.
    r = triaje.interpretar(respuesta_json([{"ref": "1", "decision": "quizás", "motivo": "x"}]), ["1"])
    assert r.decisiones == {} and r.faltan == ["1"]


def test_una_referencia_que_no_se_pidio_se_apunta_aparte():
    r = triaje.interpretar(
        respuesta_json(
            [
                {"ref": "1", "decision": "si", "motivo": "x"},
                {"ref": "99", "decision": "si", "motivo": "de dónde sale esta"},
            ]
        ),
        ["1"],
    )
    assert r.inventadas == ["99"] and r.faltan == []


def test_si_la_respuesta_no_es_json_el_mensaje_lo_entiende_cualquiera():
    with pytest.raises(triaje.TriajeIlegible) as fallo:
        triaje.interpretar("Pues depende, no sabría decirte.", ["1"])
    mensaje = str(fallo.value)
    assert "a mano" in mensaje and "no se ha descartado" in mensaje.lower()
    assert "Traceback" not in mensaje and "json" not in mensaje.lower()


def test_un_json_sin_la_lista_de_decisiones_tampoco_se_adivina():
    with pytest.raises(triaje.TriajeIlegible):
        triaje.interpretar('{"resultado": "todas valen"}', ["1"])


# --- La llamada completa (con cliente falso y base de pruebas) --------------------------


def test_a_haiku_no_se_le_manda_esfuerzo_en_el_triaje(bd, entorno):
    with bd() as conexion:
        ids = montar(conexion)
    api = ApiFalsa(respuesta_json([{"ref": "1", "decision": "si", "motivo": "x"}]))
    respuesta, ficha, _ = triaje.triar(PERFIL, [licitacion(ids["t1"])], modelo="claude-haiku-4-5", api=api)
    assert "output_config" not in api.peticiones[0]
    assert respuesta.decisiones["1"][0] == "si"
    assert ficha["nodo"] == "triaje" and ficha["prompt_version"] == "triaje_v1"


def test_si_el_modelo_contesta_cualquier_cosa_la_llamada_queda_apuntada(bd, entorno):
    # La llamada se ha pagado: tiene que quedar registrada aunque no se entienda la respuesta, y
    # las licitaciones tienen que salir a revisión en lugar de desaparecer.
    with bd() as conexion:
        ids = montar(conexion)
    api = ApiFalsa("No me ha llegado ninguna licitación.")
    respuesta, ficha, _ = triaje.triar(
        PERFIL, [licitacion(ids["t1"]), licitacion(ids["t2"])], modelo="claude-haiku-4-5", api=api
    )
    assert respuesta.faltan == ["1", "2"]
    assert respuesta.ilegible and "a mano" in respuesta.ilegible
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM llm_llamadas WHERE nodo = 'triaje'")
        assert cur.fetchone()[0] == 1


def test_con_el_presupuesto_agotado_no_se_tria(bd, entorno, monkeypatch):
    # El corte es **antes** de llamar: si no, el aviso llega cuando ya se ha pagado.
    with bd() as conexion:
        ids = montar(conexion)
    monkeypatch.setenv("PRESUPUESTO_DIARIO_EUR", "0.00")
    api = ApiFalsa(respuesta_json([{"ref": "1", "decision": "si", "motivo": "x"}]))
    with pytest.raises(llm.PresupuestoAgotado) as fallo:
        triaje.triar(PERFIL, [licitacion(ids["t1"])], modelo="claude-haiku-4-5", api=api)
    assert "tope" in str(fallo.value) and "Traceback" not in str(fallo.value)
    assert api.peticiones == []


# --- Guardar: idempotente y sin perder nada -------------------------------------------

GANADORA = "B00000001"
OTRA = "B00000002"

# entry_id, cpv, fecha, quien gano
ESCENARIO = [
    ("t1", ["72267100"], "2025-03-01", GANADORA),
    ("t2", ["30213000"], "2025-03-01", GANADORA),
    ("t3", ["45000000"], "2025-03-02", OTRA),
    ("t4", ["79500000"], "2025-03-02", None),
]


def montar(conexion) -> dict[str, int]:
    """El escenario mínimo: 4 expedientes, 2 ganados por la empresa de desarrollo."""
    import hashlib

    ids = {}
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('d', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
            " ON CONFLICT DO NOTHING"
        )
        for numero, (entry, cpv, fecha, ganador) in enumerate(ESCENARIO):
            cur.execute(
                "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
                " VALUES (repeat('d', 64), %s, %s, %s) RETURNING id",
                (numero, entry, f"{fecha}T10:00:00+01:00"),
            )
            stg = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, objeto, organo, cpv)"
                " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (entry, f"{fecha}T10:00:00+01:00", stg, f"Objeto de {entry}", "Órgano", cpv),
            )
            ids[entry] = cur.fetchone()[0]
            if ganador:
                cur.execute(
                    "INSERT INTO adjudicaciones (licitacion, adjudicatario, es_pyme) VALUES (%s, %s, true)",
                    (ids[entry], ganador),
                )
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256, texto, texto_sha256, congelado_en)"
            " VALUES ('Empresa A', %s, 'desarrollo', 2, 2, '1', repeat('c', 64), %s, %s, now())",
            (GANADORA, PERFIL, hashlib.sha256(PERFIL.encode()).hexdigest()),
        )
    conexion.commit()
    return ids


def ficha_de_prueba(identificador: int | None = None) -> dict:
    return {"modelo": "claude-haiku-4-5", "esfuerzo": None, "id": identificador}


def test_lo_que_el_modelo_no_contesto_queda_para_mirar_a_mano(bd):
    with bd() as conexion:
        ids = montar(conexion)
        lote = [licitacion(ids["t1"]), licitacion(ids["t2"])]
        respuesta = triaje.Respuesta(decisiones={"1": ("si", "encaja")}, faltan=["2"])
        triaje.guardar(
            conexion, "Empresa A", lote, respuesta, ficha_de_prueba(), prompts.cargar("triaje_v1"), 20
        )
        with conexion.cursor() as cur:
            cur.execute("SELECT decision, motivo FROM triajes ORDER BY licitacion")
            filas = cur.fetchall()
    assert [f[0] for f in filas] == ["si", "revisar"]
    assert "no la contestó" in filas[1][1]


def test_repetir_el_triaje_no_duplica_ni_vuelve_a_pagar(bd):
    with bd() as conexion:
        ids = montar(conexion)
        lote = [licitacion(ids["t1"])]
        respuesta = triaje.Respuesta(decisiones={"1": ("si", "encaja")})
        prompt = prompts.cargar("triaje_v1")
        for _ in range(2):
            triaje.guardar(conexion, "Empresa A", lote, respuesta, ficha_de_prueba(), prompt, 20)
        with conexion.cursor() as cur:
            cur.execute("SELECT count(*) FROM triajes")
            assert cur.fetchone()[0] == 1


def test_un_perfil_manipulado_para_el_triaje(bd):
    with bd() as conexion:
        montar(conexion)
        with conexion.cursor() as cur:
            cur.execute("UPDATE perfiles SET texto = texto || 'y también obra civil'")
        conexion.commit()
        with pytest.raises(errores.PerfilCambiado) as fallo:
            triaje.perfil_de(conexion, "Empresa A")
    assert "volver a medir" in str(fallo.value)


# --- El experimento: la muestra y las cifras ------------------------------------------


def test_la_muestra_trae_los_ganados_y_una_parte_del_resto(bd):
    with bd() as conexion:
        montar(conexion)
        items = experimento.muestra(conexion, GANADORA, "2025-01-01", "2025-07-01", "2026-09-01", 1)
    assert sum(1 for i in items if i["ganado"]) == 2
    assert sum(1 for i in items if not i["ganado"]) == 1
    # Lo que se le va a mandar al modelo no incluye ninguna pista de quién ganó.
    assert "ganado" not in triaje.como_se_ve(items[0])


def test_la_muestra_sale_igual_dos_veces(bd):
    with bd() as conexion:
        montar(conexion)
        primera = experimento.muestra(conexion, GANADORA, "2025-01-01", "2025-07-01", "2026-09-01", 1)
        segunda = experimento.muestra(conexion, GANADORA, "2025-01-01", "2025-07-01", "2026-09-01", 1)
    assert [i["entry_id"] for i in primera] == [i["entry_id"] for i in segunda]


def triar_a_mano(conexion, ids, decisiones: dict[str, str], por_llamada: int, coste_eur: float) -> None:
    """Guarda triajes como si los hubiera hecho el modelo, con una sola llamada pagada."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_llamadas (nodo, modelo, coste_usd, coste_eur, tipo_cambio,"
            " tipo_cambio_origen) VALUES ('triaje', 'claude-haiku-4-5', %s, %s, %s, 'de prueba')"
            " RETURNING id",
            (coste_eur / CAMBIO, coste_eur, CAMBIO),
        )
        llamada = cur.fetchone()[0]
        for entry, decision in decisiones.items():
            cur.execute(
                "INSERT INTO triajes (licitacion, alias, modelo, por_llamada, prompt_version,"
                " decision, motivo, llm_llamada)"
                " VALUES (%s, 'Empresa A', 'claude-haiku-4-5', %s, 'triaje_v1', %s, 'x', %s)",
                (ids[entry], por_llamada, decision, llamada),
            )
    conexion.commit()


def test_el_recall_del_triaje_cuenta_los_si_y_las_dudas(bd):
    with bd() as conexion:
        ids = montar(conexion)
        # De los dos que ganó: uno pasa como duda y el otro se descarta. Recall = 0,5.
        triar_a_mano(conexion, ids, {"t1": "duda", "t2": "no", "t3": "si", "t4": "no"}, 20, 0.10)
        resultados = experimento.medir(conexion, ["haiku_lote20"], "2025-01-01", "2025-07-01", "2026-09-01")
    m1 = next(r for r in resultados if r["metrica"] == "M1")
    assert m1["valor"] == 0.5
    assert m1["detalle"] == {
        "ganados": 2,
        "en_la_lista": 1,
        "por_decision": {"si": 0, "no": 1, "duda": 1, "revisar": 0},
        "sin_decision_valida": 0,
    }


def test_el_volumen_se_estima_con_la_tasa_de_paso_de_los_no_ganados(bd):
    with bd() as conexion:
        ids = montar(conexion)
        triar_a_mano(conexion, ids, {"t1": "si", "t2": "si", "t3": "si", "t4": "no"}, 20, 0.10)
        resultados = experimento.medir(conexion, ["haiku_lote20"], "2025-01-01", "2025-07-01", "2026-09-01")
    m2 = next(r for r in resultados if r["metrica"] == "M2")
    # De los no ganados (t3, t4) pasa uno: tasa 0,5. Y se publicaron 4 expedientes en 2 dias.
    assert m2["detalle"]["tasa_de_paso_en_no_ganados"] == 0.5
    assert m2["detalle"]["publicadas_al_dia"] == 2.0
    assert m2["valor"] == 1.0


def test_el_coste_de_una_llamada_con_veinte_licitaciones_se_cuenta_una_vez(bd):
    # El fallo que esto impide: sumar coste_eur por licitación triada multiplica el coste por el
    # tamaño del lote, y con lotes de 1 no se notaría.
    with bd() as conexion:
        ids = montar(conexion)
        triar_a_mano(conexion, ids, {"t1": "si", "t2": "no", "t3": "no", "t4": "no"}, 20, 0.10)
        resultados = experimento.medir(conexion, ["haiku_lote20"], "2025-01-01", "2025-07-01", "2026-09-01")
    m8 = next(r for r in resultados if r["metrica"] == "M8")
    assert m8["detalle"] == {
        "eur_total": 0.1,
        "llamadas": 1,
        "licitaciones_triadas": 4,
        "unidad": "euros por 100 licitaciones triadas",
    }
    assert m8["valor"] == pytest.approx(2.5)  # 0,10 € / 4 licitaciones x 100


def test_lo_ya_triado_no_se_vuelve_a_triar(bd):
    with bd() as conexion:
        ids = montar(conexion)
        triar_a_mano(conexion, ids, {"t1": "si"}, 20, 0.10)
        plan = experimento.preparar(conexion, ["haiku_lote20"], "2025-01-01", "2025-07-01", "2026-09-01", 2)
    _, pendientes = plan["haiku_lote20"]["Empresa A"]
    assert ids["t1"] not in [p["id"] for p in pendientes]


def test_una_variante_desconocida_no_se_ejecuta():
    assert set(experimento.VARIANTES) == {"haiku_lote20", "haiku_individual", "opus_lote20"}
    for variante in experimento.VARIANTES.values():
        # Si un modelo del experimento no tiene precio, el coste que se publicaría sería inventado.
        assert variante["modelo"] in llm.MODELOS
