"""La puerta al modelo: precios, presupuesto y registro.

Ningún test llama a la API de Anthropic: se le pasa un cliente falso. Los precios son los
oficiales del 27-09-2026 y se comprueban a mano, porque de ellos sale el coste que se publica.
"""

import types

import pytest

from radar import llm
from radar.errores import FaltaConfiguracion

CAMBIO = 0.87


class RespuestaFalsa:
    """Con la misma forma que la del SDK: content, usage, stop_reason y _request_id."""

    def __init__(self, entrada=1000, salida=500, cache_escritura=0, cache_lectura=0, texto="hola"):
        self.content = [
            types.SimpleNamespace(type="thinking", thinking=""),
            types.SimpleNamespace(type="text", text=texto),
        ]
        self.usage = types.SimpleNamespace(
            input_tokens=entrada,
            output_tokens=salida,
            cache_creation_input_tokens=cache_escritura,
            cache_read_input_tokens=cache_lectura,
        )
        self.stop_reason = "end_turn"
        self._request_id = "req_de_prueba"

    def to_dict(self):
        return {"stop_reason": self.stop_reason, "content": [{"type": "text", "text": "hola"}]}


class ApiFalsa:
    def __init__(self, respuesta=None, tokens_entrada=1000):
        self.respuesta = respuesta or RespuestaFalsa()
        self.peticiones = []
        contar = types.SimpleNamespace(input_tokens=tokens_entrada)
        self.messages = types.SimpleNamespace(
            create=self._create,
            count_tokens=lambda **kw: contar,
        )

    def _create(self, **peticion):
        self.peticiones.append(peticion)
        return self.respuesta


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("TIPO_CAMBIO_USD_EUR", str(CAMBIO))
    monkeypatch.setenv("TIPO_CAMBIO_ORIGEN", "BCE, 27-09-2026")
    monkeypatch.setenv("PRESUPUESTO_DIARIO_EUR", "2.00")
    monkeypatch.setenv("MODELO_EXTRACCION", "claude-opus-5")


# --- Precios: se comprueban a mano porque de aqui sale la cifra que se publica ----------


def test_el_coste_de_opus_5_sale_a_mano():
    # 1.000.000 de entrada a 5 $ y 1.000.000 de salida a 25 $ = 30 $.
    uso = llm.Uso(entrada=1_000_000, salida=1_000_000)
    assert llm.coste_usd("claude-opus-5", uso) == pytest.approx(30.0)


def test_cada_modelo_tiene_su_precio():
    uso = llm.Uso(entrada=1_000_000, salida=0)
    assert llm.coste_usd("claude-opus-5", uso) == pytest.approx(5.0)
    assert llm.coste_usd("claude-sonnet-5", uso) == pytest.approx(2.0)
    assert llm.coste_usd("claude-haiku-4-5", uso) == pytest.approx(1.0)


def test_la_cache_abarata_la_lectura_y_encarece_la_escritura():
    normal = llm.coste_usd("claude-opus-5", llm.Uso(entrada=1_000_000))
    leida = llm.coste_usd("claude-opus-5", llm.Uso(cache_lectura=1_000_000))
    escrita = llm.coste_usd("claude-opus-5", llm.Uso(cache_escritura=1_000_000))
    assert leida == pytest.approx(normal * 0.10)
    assert escrita == pytest.approx(normal * 1.25)


def test_la_batch_api_cuesta_la_mitad():
    uso = llm.Uso(entrada=1_000_000, salida=1_000_000)
    assert llm.coste_usd("claude-opus-5", uso, batch=True) == pytest.approx(15.0)


def test_un_modelo_sin_precio_no_se_usa():
    with pytest.raises(llm.ModeloDesconocido) as fallo:
        llm.coste_usd("claude-inventado-9", llm.Uso(entrada=10))
    assert "no tiene precio" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


# --- Presupuesto: se comprueba antes de gastar ------------------------------------------


def test_sin_tope_de_gasto_no_se_llama(monkeypatch):
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("PRESUPUESTO_DIARIO_EUR", raising=False)
    with pytest.raises(FaltaConfiguracion) as fallo:
        llm.presupuesto_diario()
    assert "tope de gasto" in str(fallo.value)


def test_sin_tipo_de_cambio_no_se_llama(monkeypatch, bd):
    # Hay que silenciar tambien el load_dotenv de radar.bd: conectar() lo llama por su cuenta, y
    # como load_dotenv rellena lo que falta, resucitaria la variable que acabamos de borrar.
    import radar.bd

    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setattr(radar.bd, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("TIPO_CAMBIO_USD_EUR", raising=False)
    with pytest.raises(FaltaConfiguracion) as fallo:
        llm.tipo_de_cambio()
    assert "en euros" in str(fallo.value)


def test_el_presupuesto_corta_antes_de_gastar(bd, entorno):
    api = ApiFalsa(tokens_entrada=1000)
    # Una llamada con 200.000 tokens de salida a 25 $/millón son 5 $, mas de los 2 € del tope.
    with pytest.raises(llm.PresupuestoAgotado) as fallo:
        llm.llamar("prueba", [{"role": "user", "content": "hola"}], max_tokens=200_000, api=api)
    assert "tope" in str(fallo.value)
    assert "No se llama" in str(fallo.value)
    assert api.peticiones == []  # y no se ha pedido nada


def test_el_gasto_del_dia_se_acumula(bd, entorno):
    api = ApiFalsa()
    for _ in range(3):
        llm.llamar("prueba", [{"role": "user", "content": "hola"}], max_tokens=1000, api=api)

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*), sum(coste_eur) FROM llm_llamadas")
        cuantas, total = cur.fetchone()
    with bd() as conexion:
        assert float(total) == pytest.approx(llm.gastado_hoy(conexion), abs=1e-6)
    assert cuantas == 3


def test_lo_gastado_antes_cuenta_para_el_tope(bd, entorno):
    api = ApiFalsa(respuesta=RespuestaFalsa(entrada=100_000, salida=60_000))
    llm.llamar("prueba", [{"role": "user", "content": "hola"}], max_tokens=1000, api=api)
    with bd() as conexion:
        gastado = llm.gastado_hoy(conexion)
    assert gastado > 1.0  # ya se ha comido mas de la mitad del tope de 2 €

    # La siguiente, con la misma forma, no cabe.
    with pytest.raises(llm.PresupuestoAgotado):
        llm.llamar("prueba", [{"role": "user", "content": "hola"}], max_tokens=100_000, api=api)


# --- Registro: nada se llama sin quedar apuntado ----------------------------------------


def test_la_llamada_queda_apuntada_con_todo(bd, entorno):
    api = ApiFalsa(respuesta=RespuestaFalsa(entrada=2000, salida=800, cache_lectura=500))
    respuesta, ficha = llm.llamar(
        "extraer_solvencia",
        [{"role": "user", "content": "¿cuánto hay que facturar?"}],
        sistema="Eres un lector de pliegos.",
        max_tokens=1000,
        esfuerzo="low",
        prompt_version="solvencia_v1",
        api=api,
    )
    assert llm.texto_de(respuesta) == "hola"

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "SELECT nodo, modelo, esfuerzo, prompt_version, request_id, tokens_entrada,"
            " tokens_salida, tokens_cache_lectura, coste_usd, coste_eur, tipo_cambio,"
            " tipo_cambio_origen, stop_reason, respuesta, prompt_sha256 FROM llm_llamadas"
        )
        fila = cur.fetchone()
    assert fila[0] == "extraer_solvencia"
    assert fila[1] == "claude-opus-5"
    assert fila[2] == "low"
    assert fila[3] == "solvencia_v1"
    assert fila[4] == "req_de_prueba"
    assert (fila[5], fila[6], fila[7]) == (2000, 800, 500)
    assert float(fila[9]) == pytest.approx(float(fila[8]) * CAMBIO, abs=1e-6)
    assert float(fila[10]) == pytest.approx(CAMBIO)
    assert "BCE" in fila[11]
    assert fila[12] == "end_turn"
    assert fila[13]["stop_reason"] == "end_turn"  # la respuesta entera, para no volver a pagar
    assert len(fila[14]) == 64  # huella del prompt


def test_el_esfuerzo_viaja_en_output_config_y_no_hay_budget_tokens(bd, entorno):
    api = ApiFalsa()
    llm.llamar("prueba", [{"role": "user", "content": "hola"}], max_tokens=1000, esfuerzo="max", api=api)
    peticion = api.peticiones[0]
    assert peticion["output_config"] == {"effort": "max"}
    # budget_tokens devuelve un 400 en estos modelos: no puede colarse nunca.
    assert "budget_tokens" not in peticion
    assert "thinking" not in peticion


def test_un_esfuerzo_inventado_se_rechaza(bd, entorno):
    with pytest.raises(Exception) as fallo:
        llm.llamar("prueba", [{"role": "user", "content": "x"}], esfuerzo="altisimo", api=ApiFalsa())
    assert "Esfuerzo" in str(fallo.value)


def test_el_tipo_de_cambio_de_la_base_manda_sobre_el_de_env(bd, entorno):
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO tipos_cambio (fecha, usd_eur, origen) VALUES (current_date, 0.9, 'BCE del dia')"
        )
        conexion.commit()
    cambio, origen = llm.tipo_de_cambio()
    assert cambio == pytest.approx(0.9)
    assert origen == "BCE del dia"


def test_sin_clave_no_se_construye_el_cliente(monkeypatch):
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "https://www.linkedin.com/in/alguien/")
    with pytest.raises(FaltaConfiguracion) as fallo:
        llm.cliente()
    assert "sk-ant-" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_a_haiku_no_se_le_manda_el_esfuerzo(bd, entorno):
    # Comprobado contra la API el 27-09-2026: Haiku 4.5 devuelve
    # "This model does not support the effort parameter" (400). Y es justo el modelo con el
    # que se compara en el experimento de triaje (D06), asi que esto tenia que fallar antes.
    api = ApiFalsa()
    _, ficha = llm.llamar(
        "prueba",
        [{"role": "user", "content": "hola"}],
        modelo="claude-haiku-4-5",
        max_tokens=100,
        api=api,
    )
    assert "output_config" not in api.peticiones[0]
    assert ficha["esfuerzo"] is None  # no se apunta un esfuerzo que no se ha usado


def test_a_opus_y_sonnet_si_se_le_manda(bd, entorno):
    for modelo in ("claude-opus-5", "claude-sonnet-5"):
        api = ApiFalsa()
        llm.llamar(
            "prueba",
            [{"role": "user", "content": "hola"}],
            modelo=modelo,
            max_tokens=100,
            esfuerzo="low",
            api=api,
        )
        assert api.peticiones[0]["output_config"] == {"effort": "low"}


def test_acepta_esfuerzo_dice_lo_que_admite_cada_modelo():
    assert llm.acepta_esfuerzo("claude-opus-5") is True
    assert llm.acepta_esfuerzo("claude-sonnet-5") is True
    assert llm.acepta_esfuerzo("claude-haiku-4-5") is False


def test_una_respuesta_cortada_a_medias_no_pasa_en_silencio(bd, entorno):
    # Comprobado con la API el 27-09-2026: Opus 5 piensa por defecto, asi que con max_tokens
    # pequeno se gasta el presupuesto pensando y devuelve texto vacio con stop_reason
    # max_tokens. Quien pidiera una extraccion recibiria "" y seguiria como si nada.
    cortada = RespuestaFalsa(texto="")
    cortada.content = [types.SimpleNamespace(type="thinking", thinking="")]
    cortada.stop_reason = "max_tokens"
    api = ApiFalsa(respuesta=cortada)

    with pytest.raises(llm.RespuestaCortada) as fallo:
        llm.llamar("prueba", [{"role": "user", "content": "hola"}], max_tokens=16, api=api)
    assert "max_tokens" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)

    # Pero la llamada queda apuntada: se ha pagado, asi que se registra.
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT stop_reason FROM llm_llamadas")
        assert cur.fetchone()[0] == "max_tokens"


def test_una_respuesta_sin_texto_por_uso_de_herramienta_si_pasa(bd, entorno):
    # Sin texto pero con stop_reason tool_use es normal: el modelo quiere llamar a una
    # herramienta. Eso no se corta.
    con_herramienta = RespuestaFalsa(texto="")
    con_herramienta.content = [types.SimpleNamespace(type="tool_use", name="buscar")]
    con_herramienta.stop_reason = "tool_use"
    api = ApiFalsa(respuesta=con_herramienta)

    respuesta, _ = llm.llamar("prueba", [{"role": "user", "content": "hola"}], max_tokens=100, api=api)
    assert llm.texto_de(respuesta) == ""
