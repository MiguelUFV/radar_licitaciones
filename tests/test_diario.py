"""El trabajo de cada día, cliente a cliente.

DATOS DE EJEMPLO — no usar en producción. El escenario se monta aquí y no sale a ningún sitio.

Lo que se comprueba, en orden de importancia:

1. **Que una empresa dada de alta por el formulario pueda de verdad entrar en el radar.** El
   formulario le promete que «a partir de mañana entra en el aviso diario», y hasta el
   28-09-2026 eso era mentira: `triajes.alias`, `lecturas.alias` y `fichas.alias` eran claves
   foráneas a `perfiles`, la tabla del estudio, así que la base rechazaba la primera fila.
2. **Que a cada cliente le llegue lo suyo y solo lo suyo.** El correo contaba el gasto del día
   entero, de todos los clientes: uno veía en su pie lo que habían gastado los demás.
3. **Que nadie gaste más de su tope.** El tope diario lo pone el cliente en el formulario y es
   lo único que impide que un día con muchas licitaciones se coma el presupuesto.
"""

import hashlib
import json
import types
from datetime import date, timedelta

import pytest

from radar import clientes, correo, diario, empresas, llm, prompts, triaje
from radar.errores import ErrorRadar

CLIENTE = {
    "nombre": "Soluciones del Norte, S.L.",
    "alias": "Empresa del Norte",
    "correo": "contratacion@ejemplo.es",
    "que_hace": "Desarrollamos software de control horario para ayuntamientos y empresas.",
    "productos": "Autodesk, PRESTO",
    "servicios": "Formación, suministro de terminales",
    "no_hace": "Obra civil",
    "certificaciones": "ISO 9001",
    "ambito": "Asturias",
    "cifra_negocio": "850000",
    "tope_diario_eur": "0.50",
}

PERFIL_ESTUDIO = "## Qué hace\nMantenimiento de equipos informáticos.\n"


def licitacion(
    conexion,
    numero: int,
    objeto: str = "Suministro de licencias de software",
    plazo: str = "2026-12-01",
) -> int:
    """Una licitación vigente, con su rastro hasta la capa raw."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('f', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
            " ON CONFLICT DO NOTHING"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('f', 64), %s, %s, '2026-09-28T10:00:00+02:00') RETURNING id",
            (numero, f"e{numero}"),
        )
        stg = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, expediente, objeto,"
            " organo, importe_sin_iva, plazo_presentacion)"
            " VALUES (%s, '2026-09-28T10:00:00+02:00', %s, %s, %s, 'Ayuntamiento de ejemplo',"
            " 40000, %s) RETURNING id",
            (f"e{numero}", stg, f"2026/{numero}", objeto, plazo),
        )
        return cur.fetchone()[0]


def empresa_del_estudio(conexion, alias: str = "Empresa A") -> None:
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256, texto, texto_sha256, congelado_en)"
            " VALUES (%s, 'B00000001', 'desarrollo', 2, 2, '1', repeat('c', 64), %s, %s, now())"
            " ON CONFLICT (alias) DO NOTHING",
            (alias, PERFIL_ESTUDIO, hashlib.sha256(PERFIL_ESTUDIO.encode()).hexdigest()),
        )
    conexion.commit()


def con_pliego(conexion, licitacion: int) -> None:
    """Le cuelga un PCAP ya descargado, que es lo que el trabajo diario exige para leerlo."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO documentos (licitacion, tipo, url, raw_fichero, estado_descarga)"
            " VALUES (%s, 'PCAP', 'https://ejemplo.es/pliego.pdf', repeat('f', 64), 'descargado')",
            (licitacion,),
        )
    conexion.commit()


def ficha_de_prueba(identificador: int | None = None) -> dict:
    return {"modelo": "claude-haiku-4-5", "esfuerzo": None, "id": identificador}


def triar_a_mano(conexion, alias: str, licitaciones: list[int], decision: str = "si") -> None:
    """Apunta un triaje ya hecho, sin llamar al modelo ni pagar nada."""
    lote = [{"id": i} for i in licitaciones]
    respuesta = triaje.Respuesta(decisiones={str(n): (decision, "encaja") for n in range(1, len(lote) + 1)})
    triaje.guardar(conexion, alias, lote, respuesta, ficha_de_prueba(), prompts.cargar("triaje_v1"), 20)


# --- 1. Que un cliente pueda entrar en el radar ---------------------------------------


def test_una_empresa_dada_de_alta_puede_quedar_triada(bd):
    """El fallo de verdad: el alias tenía que estar en `perfiles`, y un cliente nunca lo está."""
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        una = licitacion(conexion, 1)
        triar_a_mano(conexion, "Empresa del Norte", [una])
        with conexion.cursor() as cur:
            cur.execute("SELECT decision FROM triajes WHERE alias = 'Empresa del Norte'")
            assert cur.fetchone()[0] == "si"


def test_un_alias_que_no_es_de_nadie_se_rechaza(bd):
    """Sin la clave foránea hace falta otra cosa: un triaje de un alias fantasma no se avisa."""
    import psycopg

    with bd() as conexion:
        una = licitacion(conexion, 1)
        with pytest.raises(psycopg.errors.RaiseException):
            triar_a_mano(conexion, "Empresa que no existe", [una])


def test_un_cliente_no_puede_llamarse_como_una_empresa_del_estudio(bd):
    """Si coincidieran, el cliente leería las decisiones del estudio y al revés."""
    with bd() as conexion:
        empresa_del_estudio(conexion, "Empresa A")
    with pytest.raises(ErrorRadar) as e:
        clientes.dar_de_alta({**CLIENTE, "alias": "Empresa A"})
    assert "Empresa A" in str(e.value)


# --- 2. Que a cada uno le llegue lo suyo ----------------------------------------------


def test_el_correo_de_un_cliente_va_a_su_direccion(bd):
    clientes.dar_de_alta(CLIENTE)
    escrito = correo.del_correo("Empresa del Norte", date.today())
    assert escrito["destinatario"] == "contratacion@ejemplo.es"
    assert escrito["para"] == "Empresa del Norte"


def test_el_gasto_del_correo_es_solo_el_de_esa_empresa(bd):
    """El pie decía «el día ha costado X» con el gasto de todos los clientes juntos."""
    clientes.dar_de_alta(CLIENTE)
    clientes.dar_de_alta({**CLIENTE, "alias": "Otra Empresa", "correo": "otra@ejemplo.es"})
    with bd() as conexion:
        una, otra = licitacion(conexion, 1), licitacion(conexion, 2)
        with conexion.cursor() as cur:
            for cuanto in (0.01, 0.40):
                cur.execute(
                    "INSERT INTO llm_llamadas (nodo, modelo, coste_usd, coste_eur, tipo_cambio,"
                    " tipo_cambio_origen) VALUES ('triaje', 'claude-haiku-4-5', %s, %s, 1,"
                    " 'prueba') RETURNING id",
                    (cuanto, cuanto),
                )
                cur.fetchone()
        conexion.commit()
        triar_a_mano(conexion, "Empresa del Norte", [una])
        triar_a_mano(conexion, "Otra Empresa", [otra])
        with conexion.cursor() as cur:
            cur.execute(
                "UPDATE triajes SET llm_llamada = (SELECT min(id) FROM llm_llamadas)"
                " WHERE alias = 'Empresa del Norte'"
            )
            cur.execute(
                "UPDATE triajes SET llm_llamada = (SELECT max(id) FROM llm_llamadas)"
                " WHERE alias = 'Otra Empresa'"
            )
            conexion.commit()
    escrito = correo.del_correo("Empresa del Norte", date.today())
    assert "0,01" in escrito["texto"]
    assert "0,41" not in escrito["texto"]
    assert "0,40" not in escrito["texto"]


# --- 3. Que nadie gaste más de su tope ------------------------------------------------


class ApiFalsa:
    """Con la forma que usa radar/llm.py. Cuenta las llamadas: aquí eso es cuánto se gasta."""

    def __init__(self, decisiones: str = "si"):
        self.peticiones = []
        self.decisiones = decisiones
        self.texto_fijo = None
        self.messages = types.SimpleNamespace(
            create=self._create,
            count_tokens=lambda **kw: types.SimpleNamespace(input_tokens=500),
        )

    def _create(self, **peticion):
        self.peticiones.append(peticion)
        cuantas = peticion["messages"][0]["content"].count("### ") or 1
        texto = self.texto_fijo or json.dumps(
            {
                "decisiones": [
                    {"ref": str(n), "decision": self.decisiones, "motivo": "encaja"}
                    for n in range(1, cuantas + 1)
                ]
            },
            ensure_ascii=False,
        )
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=texto)],
            usage=types.SimpleNamespace(
                input_tokens=500,
                output_tokens=100,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            stop_reason="end_turn",
            _request_id="req_de_prueba",
            to_dict=lambda: {"content": [{"type": "text", "text": texto}]},
        )


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("TIPO_CAMBIO_USD_EUR", "0.8726")
    monkeypatch.setenv("TIPO_CAMBIO_ORIGEN", "BCE, de prueba")
    monkeypatch.setenv("PRESUPUESTO_DIARIO_EUR", "2.00")


def test_cada_empresa_solo_ve_lo_que_no_ha_triado_ella(bd):
    clientes.dar_de_alta(CLIENTE)
    clientes.dar_de_alta({**CLIENTE, "alias": "Otra Empresa", "correo": "otra@ejemplo.es"})
    with bd() as conexion:
        una, otra = licitacion(conexion, 1), licitacion(conexion, 2)
        conexion.commit()
        triar_a_mano(conexion, "Empresa del Norte", [una])
        pendientes = [lic["id"] for lic in diario.sin_triar(conexion, "Empresa del Norte")]
        assert pendientes == [otra]
        assert len(diario.sin_triar(conexion, "Otra Empresa")) == 2


def test_una_licitacion_con_el_plazo_pasado_no_se_tria(bd):
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        vencida = licitacion(conexion, 1)
        with conexion.cursor() as cur:
            cur.execute(
                "UPDATE licitaciones SET plazo_presentacion = %s WHERE id = %s",
                (date.today() - timedelta(days=1), vencida),
            )
        conexion.commit()
        assert diario.sin_triar(conexion, "Empresa del Norte") == []


def test_sin_pliego_descargado_no_se_intenta_leer(bd):
    """Abrir el grafo de un expediente sin pliego cuesta tiempo y no da nada."""
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        una = licitacion(conexion, 1)
        conexion.commit()
        triar_a_mano(conexion, "Empresa del Norte", [una])
        assert diario.sin_ficha(conexion, "Empresa del Norte") == []
        con_pliego(conexion, una)
        assert [c["id"] for c in diario.sin_ficha(conexion, "Empresa del Norte")] == [una]


def test_lo_que_dijo_que_no_no_se_lee(bd):
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        una = licitacion(conexion, 1)
        conexion.commit()
        triar_a_mano(conexion, "Empresa del Norte", [una], decision="no")
        con_pliego(conexion, una)
        assert diario.sin_ficha(conexion, "Empresa del Norte") == []


def test_el_triaje_se_para_al_llegar_al_tope_de_la_empresa(bd, entorno):
    # Cada llamada de triaje deja su coste apuntado; en cuanto lo gastado alcanza el tope del
    # cliente, no se hace ni una más. Sin esto, un día con muchas licitaciones se lo come.
    clientes.dar_de_alta({**CLIENTE, "tope_diario_eur": "0.0005"})
    with bd() as conexion:
        for numero in range(1, 45):
            licitacion(conexion, numero)
        conexion.commit()
        empresa = empresas.la_de(conexion, "Empresa del Norte")
        empresa["texto"] = "## Qué hace\nSoftware.\n"
        api = ApiFalsa()
        hecho = diario.triar_lo_nuevo(conexion, empresa, None, tope=0.0005, gastado=0.0, api=api)
    assert hecho["triadas"] == 20, "se pasó de una llamada con el tope ya alcanzado"
    assert len(api.peticiones) == 1
    assert "tope" in hecho["parado"]


def test_una_empresa_que_ya_gasto_lo_suyo_no_vuelve_a_empezar(bd, entorno):
    clientes.dar_de_alta({**CLIENTE, "tope_diario_eur": "0.50"})
    with bd() as conexion:
        una = licitacion(conexion, 1)
        conexion.commit()
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO llm_llamadas (nodo, modelo, coste_usd, coste_eur, tipo_cambio,"
                " tipo_cambio_origen) VALUES ('triaje', 'claude-haiku-4-5', 0.6, 0.6, 1, 'x')"
                " RETURNING id"
            )
            llamada = cur.fetchone()[0]
        conexion.commit()
        triar_a_mano(conexion, "Empresa del Norte", [una])
        with conexion.cursor() as cur:
            cur.execute("UPDATE triajes SET llm_llamada = %s", (llamada,))
        conexion.commit()
        empresa = empresas.la_de(conexion, "Empresa del Norte")
        hecho = diario.de_una_empresa(conexion, empresa, None, date.today())
    assert "ya ha gastado" in hecho["parado"]
    assert "triadas" not in hecho


def test_la_reserva_por_pliego_sale_de_lo_que_costaron_los_leidos(bd):
    # Sin ningún pliego leído no hay nada que medir y se usa la cifra de la Fase 4. En cuanto
    # hay lecturas, la reserva sale de ellas: es el p90, no la media, porque tiene que dar para
    # un pliego caro y no para el pliego medio.
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        assert diario.reserva_por_pliego(conexion) == diario.RESERVA_INICIAL
        for numero, coste in enumerate((0.02, 0.04, 0.30), start=1):
            una = licitacion(conexion, numero)
            con_pliego(conexion, una)
            with conexion.cursor() as cur:
                cur.execute(
                    "INSERT INTO llm_llamadas (nodo, modelo, coste_usd, coste_eur, tipo_cambio,"
                    " tipo_cambio_origen) VALUES ('extraccion', 'claude-opus-5', %s, %s, 1, 'x')"
                    " RETURNING id",
                    (coste, coste),
                )
                llamada = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO lecturas (documento, licitacion, alias, via, prompt_version,"
                    " estado) VALUES ((SELECT id FROM documentos WHERE licitacion = %s LIMIT 1),"
                    " %s, 'Empresa del Norte', 'solvencia', 'extraccion_v1', 'leido') RETURNING id",
                    (una, una),
                )
                lectura = cur.fetchone()[0]
                # Dos requisitos de la misma llamada: un pliego deja varios, y todos salen
                # de una sola respuesta del modelo. Sumar por requisito multiplicaba el coste
                # —el mismo fallo que el 27-09-2026 hizo que un triaje pareciera veinte—, y
                # con la reserva inflada el radar se cree que no le caben pliegos que sí paga.
                cur.executemany(
                    "INSERT INTO requisitos (lectura, tipo, cita, verificada, llm_llamada)"
                    " VALUES (%s, 'volumen_negocios', 'x', true, %s)",
                    [(lectura, llamada), (lectura, llamada)],
                )
            conexion.commit()
        reserva = diario.reserva_por_pliego(conexion)
        assert reserva > 0.04, "la reserva tiene que cubrir el caro"
        assert reserva <= 0.30, f"la reserva ({reserva}) cuenta dos veces la misma llamada"


def test_no_se_abre_un_pliego_si_lo_que_queda_no_da_para_uno(bd, monkeypatch):
    # Este es el corte que importa: leer un pliego es lo caro. Comprobarlo **antes** de abrirlo
    # es lo único que impide pasarse del tope que puso el cliente.
    clientes.dar_de_alta({**CLIENTE, "tope_diario_eur": "0.10"})
    abiertos = []
    monkeypatch.setattr(diario, "analizar", lambda *a, **kw: abiertos.append(a) or {})
    monkeypatch.setattr(diario, "reserva_por_pliego", lambda conexion: 0.08)
    with bd() as conexion:
        for numero in (1, 2, 3):
            con_pliego(conexion, licitacion(conexion, numero))
        conexion.commit()
        with conexion.cursor() as cur:
            cur.execute("SELECT id FROM licitaciones ORDER BY id")
            todas = [fila[0] for fila in cur.fetchall()]
        triar_a_mano(conexion, "Empresa del Norte", todas)
        empresa = empresas.la_de(conexion, "Empresa del Norte")
        hecho = diario.leer_pliegos(conexion, empresa, None, tope=0.10, gastado=0.05)
    assert abiertos == [], "quedaban 0,05 € y un pliego se reserva a 0,08: no cabía ninguno"
    assert "no da para hoy" in hecho["parado"]


def test_sin_ninguna_empresa_de_alta_se_dice_con_palabras(bd):
    with pytest.raises(ErrorRadar) as fallo:
        diario.del_dia()
    assert "/alta" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


# --- La frontera con n8n --------------------------------------------------------------


def test_la_lista_de_empresas_no_ensena_nada_de_mas(bd):
    # n8n solo necesita a quién escribir. El texto del perfil, la cifra de negocio y el nombre
    # fiscal son de la empresa y no tienen por qué salir de la base.
    from fastapi.testclient import TestClient

    from radar import api

    clientes.dar_de_alta(CLIENTE)
    respuesta = TestClient(api.app, raise_server_exceptions=False).get("/clientes")
    assert respuesta.status_code == 200
    empresas = respuesta.json()["empresas"]
    assert empresas == [{"alias": "Empresa del Norte", "correo": "contratacion@ejemplo.es"}]
    entero = respuesta.text
    assert "Soluciones del Norte" not in entero and "850000" not in entero


def test_el_trabajo_diario_no_gasta_si_no_se_le_dice(bd):
    from fastapi.testclient import TestClient

    from radar import api

    clientes.dar_de_alta(CLIENTE)
    respuesta = TestClient(api.app, raise_server_exceptions=False).post("/diario", json={})
    assert respuesta.status_code == 200
    empresa = respuesta.json()["empresas"][0]
    assert "por_triar" in empresa and "triadas" not in empresa
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM llm_llamadas")
        assert cur.fetchone()[0] == 0


def test_el_workflow_diario_recorre_las_empresas_y_manda_a_cada_una_la_suya():
    from radar import n8n

    trabajo = n8n.workflow_diario()
    nombres = [nodo["name"] for nodo in trabajo["nodes"]]
    assert "Preguntar que empresas hay" in nombres, "la lista no puede estar escrita en n8n"
    assert nombres.index("Triar y leer para esa empresa") < nombres.index("Pedir el correo del dia")
    envio = trabajo["nodes"][-1]["parameters"]
    assert envio["toEmail"] == "={{ $json.destinatario }}", "cada empresa recibe en su direccion"


# --- 4. Lo que se mira primero cuando no cabe todo -------------------------------------


def test_se_tria_antes_lo_que_antes_vence(bd):
    # Cuando hay más licitaciones que sitio en la pasada, las que entran tienen que ser las que
    # antes cierran plazo. Con el orden mal puesto entraban las primeras por identificador, que
    # es un orden sin ningún sentido para quien tiene que presentarse.
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        licitacion(conexion, 1, plazo="2026-12-31")
        licitacion(conexion, 2, plazo="2026-10-05")
        licitacion(conexion, 3, plazo="2026-11-10")
        conexion.commit()
        elegidas = diario.sin_triar(conexion, "Empresa del Norte", limite=2)
    assert [lic["entry_id"] for lic in elegidas] == ["e2", "e3"]


def test_se_lee_antes_el_pliego_que_antes_vence(bd):
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        for numero, plazo in ((1, "2026-12-31"), (2, "2026-10-05"), (3, "2026-11-10")):
            con_pliego(conexion, licitacion(conexion, numero, plazo=plazo))
        conexion.commit()
        with conexion.cursor() as cur:
            cur.execute("SELECT id FROM licitaciones ORDER BY id")
            triar_a_mano(conexion, "Empresa del Norte", [f[0] for f in cur.fetchall()])
        elegidas = diario.sin_ficha(conexion, "Empresa del Norte", limite=2)
    assert [lic["expediente"] for lic in elegidas] == ["2026/2", "2026/3"]


# --- 5. Que un fallo no se lleve por delante la mañana de los demás --------------------


def test_si_una_empresa_falla_las_demas_reciben_lo_suyo(bd, entorno, monkeypatch):
    clientes.dar_de_alta(CLIENTE)
    clientes.dar_de_alta({**CLIENTE, "alias": "Otra Empresa", "correo": "otra@ejemplo.es"})
    with bd() as conexion:
        licitacion(conexion, 1)
        conexion.commit()

    def falla_para_la_primera(conexion, empresa, run_id, tope, gastado, api=None):
        if empresa["alias"] == "Empresa del Norte":
            raise RuntimeError("algo que nadie previó")
        return {"triadas": 1, "candidatas": 0, "coste_eur": 0.0}

    monkeypatch.setattr(diario, "triar_lo_nuevo", falla_para_la_primera)
    monkeypatch.setattr(diario, "leer_pliegos", lambda *a, **kw: {"leidos": 0, "coste_eur": 0.0})
    resultado = diario.del_dia(gastar=True)
    por_alias = {e["alias"]: e for e in resultado["empresas"]}
    assert por_alias["Otra Empresa"]["triadas"] == 1, "la segunda empresa se quedó sin su mañana"
    assert "no previsto" in por_alias["Empresa del Norte"]["fallo"].lower()
    assert "Traceback" not in json.dumps(resultado)
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM incidencias WHERE nodo = 'diario'")
        assert cur.fetchone()[0] == 1, "la traza tiene que quedar apuntada"


def test_una_empresa_del_estudio_no_es_un_cliente(bd):
    # Tienen perfil pero no tope ni dirección: no se les puede mandar nada. Decirlo con
    # palabras evita el mensaje absurdo de «ya ha gastado hoy sus 0,00 €».
    with bd() as conexion:
        empresa_del_estudio(conexion, "Empresa A")
    with pytest.raises(ErrorRadar) as fallo:
        diario.del_dia("Empresa A", gastar=True)
    assert "Empresa A" in str(fallo.value) and "estudio" in str(fallo.value)


def test_una_empresa_que_no_existe_lo_dice_sin_traza(bd):
    with pytest.raises(ErrorRadar) as fallo:
        diario.del_dia("Empresa Fantasma")
    assert "Empresa Fantasma" in str(fallo.value) and "Traceback" not in str(fallo.value)


# --- 6. Que se pueda explicar una decisión de hace tres semanas ------------------------


def test_el_triaje_apunta_con_que_version_del_perfil_se_decidio(bd, entorno):
    # Un cliente edita su ficha cuando quiere. Sin esta huella no se puede explicar por qué el
    # radar descartó algo hace tres semanas. D38 decía que se guardaba, la columna existía
    # desde la migración 011, y nadie la escribía.
    alta = clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        licitacion(conexion, 1)
        conexion.commit()
        empresa = empresas.la_de(conexion, "Empresa del Norte")
        diario.triar_lo_nuevo(conexion, empresa, None, tope=1.0, gastado=0.0, api=ApiFalsa())
        with conexion.cursor() as cur:
            cur.execute("SELECT perfil_sha256 FROM triajes")
            assert cur.fetchone()[0] == clientes.huella(alta["texto"])


# --- 7. Fallos que no pueden salir de su sitio ----------------------------------------


def test_un_perfil_manipulado_no_deja_sin_correo_a_los_demas(bd, entorno, monkeypatch):
    # El candado tiene que saltar para esa empresa, no para la mañana entera. Comprobarlo al
    # hacer la lista dejaba a todos los clientes sin trabajo por culpa de una fila tocada.
    clientes.dar_de_alta(CLIENTE)
    clientes.dar_de_alta({**CLIENTE, "alias": "Otra Empresa", "correo": "otra@ejemplo.es"})
    with bd() as conexion:
        licitacion(conexion, 1)
        with conexion.cursor() as cur:
            cur.execute(
                "UPDATE clientes SET texto = texto || 'y tambien obra civil' WHERE alias = %s",
                ("Empresa del Norte",),
            )
        conexion.commit()
    monkeypatch.setattr(diario, "triar_lo_nuevo", lambda *a, **kw: {"triadas": 1, "coste_eur": 0.0})
    monkeypatch.setattr(diario, "leer_pliegos", lambda *a, **kw: {"leidos": 0, "coste_eur": 0.0})
    resultado = diario.del_dia(gastar=True)
    por_alias = {e["alias"]: e for e in resultado["empresas"]}
    assert por_alias["Otra Empresa"]["triadas"] == 1
    assert "huella" in por_alias["Empresa del Norte"]["fallo"]
    assert "Traceback" not in json.dumps(resultado)


def test_una_respuesta_ilegible_del_modelo_queda_apuntada(bd, entorno):
    # La llamada se ha pagado y las licitaciones salen a revisión, pero si nadie apunta que el
    # modelo contestó cualquier cosa, no hay forma de enterarse de que está pasando.
    clientes.dar_de_alta(CLIENTE)
    with bd() as conexion:
        licitacion(conexion, 1)
        conexion.commit()
        empresa = empresas.la_de(conexion, "Empresa del Norte")
        api = ApiFalsa()
        api.texto_fijo = "No me ha llegado ninguna licitacion."
        diario.triar_lo_nuevo(conexion, empresa, None, tope=1.0, gastado=0.0, api=api)
        with conexion.cursor() as cur:
            cur.execute("SELECT mensaje FROM incidencias WHERE nodo = 'diario'")
            fila = cur.fetchone()
    assert fila is not None, "una respuesta ilegible tiene que quedar apuntada"
    assert "Empresa del Norte" in fila[0]


def test_la_api_no_manda_una_traza_a_n8n(bd, monkeypatch):
    from fastapi.testclient import TestClient

    from radar import api

    monkeypatch.setattr(api.diario, "del_dia", _revienta)
    respuesta = TestClient(api.app, raise_server_exceptions=False).post("/diario", json={})
    assert respuesta.status_code == 503
    assert "Traceback" not in respuesta.text and "ZeroDivision" not in respuesta.text
    assert "no previsto" in respuesta.json()["mensaje"].lower()


def _revienta(*a, **kw):
    raise ZeroDivisionError("algo que nadie previó")


def test_el_alta_con_el_nombre_de_una_empresa_del_estudio_vuelve_al_formulario(bd):
    from fastapi.testclient import TestClient

    from radar import api

    with bd() as conexion:
        empresa_del_estudio(conexion, "Empresa A")
    respuesta = TestClient(api.app, raise_server_exceptions=False).post(
        "/alta", data={**CLIENTE, "alias": "Empresa A"}
    )
    assert respuesta.status_code == 200
    assert "Empresa A" in respuesta.text and "otro nombre" in respuesta.text
    # Lo que ya había escrito no se pierde.
    assert "Autodesk" in respuesta.text


# --- 8. La cadena entera, de una vez --------------------------------------------------

CLAUSULA = (
    "CLAUSULA 12. Solvencia economica y financiera\n"
    "Volumen anual de negocios referido al mejor ejercicio de los tres ultimos:\n"
    "150.000 euros. Se acreditara segun lo indicado en este pliego."
)
RELLENO = "Texto de relleno sobre plazos de entrega y forma de pago del contrato.\n"


class ApiDeTodaLaManana:
    """Contesta lo que toca según lo que se le pregunte: triaje o extracción.

    No adivina: mira si el mensaje trae licitaciones que triar o páginas de un pliego. Así una
    sola api falsa vale para la mañana entera, que es lo que se quiere probar.
    """

    def __init__(self):
        self.peticiones = []
        self.messages = types.SimpleNamespace(
            create=self._create,
            count_tokens=lambda **kw: types.SimpleNamespace(input_tokens=500),
        )

    def _create(self, **peticion):
        self.peticiones.append(peticion)
        contenido = peticion["messages"][0]["content"]
        if "licitaciones que hay que triar" in contenido or "licitación que hay que triar" in contenido:
            cuantas = contenido.count("### ") or 1
            texto = json.dumps(
                {
                    "decisiones": [
                        {"ref": str(n), "decision": "si", "motivo": "encaja"} for n in range(1, cuantas + 1)
                    ]
                },
                ensure_ascii=False,
            )
        else:
            texto = json.dumps(
                {
                    "requisitos": [
                        {
                            "tipo": "volumen_negocios",
                            "exigencia": "volumen anual de 150.000 euros",
                            "cita": "150.000 euros",
                            "pagina": 1,
                            "importe_eur": 150000.0,
                            "anios": 3,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=texto)],
            usage=types.SimpleNamespace(
                input_tokens=500,
                output_tokens=100,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            stop_reason="end_turn",
            _request_id="req_de_prueba",
            to_dict=lambda: {"content": [{"type": "text", "text": texto}]},
        )


def test_del_alta_al_correo_sin_tocar_nada_por_el_camino(bd, entorno, monkeypatch, tmp_path):
    """Una empresa se da de alta y esa misma mañana recibe una ficha con su cita y su página.

    Es la prueba que falta cuando todas las piezas pasan por separado: aquí se comprueba que
    encajan. Con el modelo falseado, pero con un PDF de verdad, la base de verdad y el grafo
    de verdad, ramas incluidas.
    """
    from conftest import pdf_con_paginas

    from radar import llm

    api = ApiDeTodaLaManana()
    monkeypatch.setattr(llm, "cliente", lambda: api)
    clientes.dar_de_alta({**CLIENTE, "tope_diario_eur": "1.00"})

    pliego = tmp_path / "pliego.pdf"
    pliego.write_bytes(pdf_con_paginas([CLAUSULA, RELLENO]))
    with bd() as conexion:
        una = licitacion(conexion, 1)
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
                " VALUES (repeat('a', 64), 'pliego', 'https://ejemplo.es/p.pdf', %s, %s, now())",
                (str(pliego), pliego.stat().st_size),
            )
            cur.execute(
                "INSERT INTO documentos (licitacion, tipo, url, raw_fichero, estado_descarga,"
                " paginas) VALUES (%s, 'PCAP', 'https://ejemplo.es/p.pdf', repeat('a', 64),"
                " 'descargado', 2)",
                (una,),
            )
        conexion.commit()

    resultado = diario.del_dia(gastar=True)
    empresa = resultado["empresas"][0]
    assert empresa.get("fallo") is None, empresa.get("fallo")
    assert empresa["triadas"] == 1 and empresa["candidatas"] == 1
    assert empresa["leidos"] == 1, "el pliego tenía que abrirse"
    assert 0 < empresa["coste_eur"] <= 1.00

    escrito = correo.del_correo("Empresa del Norte", date.today())
    assert escrito["destinatario"] == "contratacion@ejemplo.es"
    assert escrito["licitaciones"] == 1
    assert "PUEDE PRESENTARSE" in escrito["texto"]
    assert "1 requisito leído del pliego: 1 cumple" in escrito["texto"], (
        "el modelo devolvió un requisito: uno tiene que salir, ni ninguno ni cuatro"
    )
    assert escrito["asunto"].startswith("Radar de licitaciones")

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT veredicto FROM fichas WHERE alias = 'Empresa del Norte'")
        assert cur.fetchone()[0] in ("apta", "revisar")
        cur.execute("SELECT pagina, verificada FROM requisitos")
        pagina, verificada = cur.fetchone()
        assert verificada, "la cita tiene que estar comprobada contra la página"
        assert pagina == 1
        cur.execute("SELECT count(*) FROM incidencias")
        assert cur.fetchone()[0] == 0, "una mañana limpia no deja incidencias"


def test_leer_dos_veces_el_mismo_pliego_no_duplica_los_requisitos(bd, entorno, monkeypatch, tmp_path):
    """El paso a paso de LangGraph guarda el estado con la clave `licitacion:empresa:reglas`.

    Al volver a leer el mismo pliego —porque la vez anterior se cortó a la mitad, que es
    justamente para lo que está el checkpointer— el grafo reanudaba aquel estado y **sumaba**
    los requisitos nuevos a los viejos. La ficha salía con el mismo requisito repetido tantas
    veces como se hubiera leído, y el correo decía «de 4 requisitos leídos, 4 cumplen» de un
    pliego que solo tenía uno.
    """
    from conftest import pdf_con_paginas

    from radar import grafo, llm

    monkeypatch.setattr(llm, "cliente", lambda: ApiDeTodaLaManana())
    clientes.dar_de_alta(CLIENTE)
    pliego = tmp_path / "pliego.pdf"
    pliego.write_bytes(pdf_con_paginas([CLAUSULA, RELLENO]))
    with bd() as conexion:
        una = licitacion(conexion, 1)
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
                " VALUES (repeat('a', 64), 'pliego', 'https://ejemplo.es/p.pdf', %s, 1, now())",
                (str(pliego),),
            )
            cur.execute(
                "INSERT INTO documentos (licitacion, tipo, url, raw_fichero, estado_descarga,"
                " paginas) VALUES (%s, 'PCAP', 'https://ejemplo.es/p.pdf', repeat('a', 64),"
                " 'descargado', 2)",
                (una,),
            )
        conexion.commit()
        empresa = empresas.la_de(conexion, "Empresa del Norte")

    datos = {
        "alias": empresa["alias"],
        "perfil": empresa["texto"],
        "cifra_negocio": empresa["cifra_negocio"],
        "cifra_fuente": empresa["cifra_fuente"],
    }
    with grafo.checkpointer_de_postgres() as guardado:
        guardado.setup()
        for _ in range(3):
            estado = grafo.analizar(una, empresa["alias"], checkpointer=guardado, empresa=datos)
    assert len(estado["motivos"]) == 1, "la ficha repite el mismo requisito una vez por lectura"
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM requisitos")
        assert cur.fetchone()[0] == 1


def test_la_manana_baja_los_pliegos_de_lo_que_acaba_de_triar(bd, entorno, monkeypatch):
    """Sin esto, el primer día de un cliente se tría y no se lee nada.

    El workflow baja pliegos **antes** del triaje, así que el día 1 no hay ningún candidato del
    que bajar nada, y las candidatas de hoy no tendrían pliego hasta mañana. La mañana cierra
    el círculo: tría, baja lo que ha pasado el filtro y lo lee.
    """
    clientes.dar_de_alta({**CLIENTE, "tope_diario_eur": "1.00"})
    pedidos = []
    monkeypatch.setattr(
        diario.pliegos,
        "descargar_pendientes",
        lambda **kw: pedidos.append(kw) or {"descargados": 2, "desde_disco": 1},
    )
    monkeypatch.setattr(diario, "leer_pliegos", lambda *a, **kw: {"leidos": 0, "coste_eur": 0.0})
    with bd() as conexion:
        licitacion(conexion, 1)
        conexion.commit()
        empresa = empresas.la_de(conexion, "Empresa del Norte")
        hecho = diario.de_una_empresa(conexion, empresa, None, date.today(), api=ApiFalsa())
    assert hecho["pliegos_bajados"] == 3
    assert pedidos[0]["del_triaje"] is True, "solo lo que el triaje ha dejado pasar"
    # Con 1 € de tope y la reserva inicial de 0,15 €, caben seis pliegos: no se bajan más.
    assert 0 < pedidos[0]["limite"] <= 7


def test_si_la_plataforma_no_contesta_se_leen_los_pliegos_que_ya_estan(bd, entorno, monkeypatch):
    clientes.dar_de_alta(CLIENTE)

    def no_contesta(**kw):
        from radar.errores import FuenteNoResponde

        raise FuenteNoResponde("La Plataforma de Contratación no responde.")

    monkeypatch.setattr(diario.pliegos, "descargar_pendientes", no_contesta)
    monkeypatch.setattr(diario, "leer_pliegos", lambda *a, **kw: {"leidos": 1, "coste_eur": 0.08})
    with bd() as conexion:
        licitacion(conexion, 1)
        conexion.commit()
        empresa = empresas.la_de(conexion, "Empresa del Norte")
        hecho = diario.de_una_empresa(conexion, empresa, None, date.today(), api=ApiFalsa())
        assert hecho["pliegos_bajados"] == 0
        assert hecho["leidos"] == 1, "lo que ya estaba bajado se lee igual"
        with conexion.cursor() as cur:
            cur.execute("SELECT count(*) FROM incidencias WHERE nodo = 'diario'")
            assert cur.fetchone()[0] == 1
