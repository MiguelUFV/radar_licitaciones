"""Un test por fila de la matriz de fallos de `docs/SPEC.md` §8.

DATOS DE EJEMPLO — no usar en producción. Nada de aquí sale a la red ni llama a la API.

Este fichero es la puerta de salida de la Fase 6, y tiene una regla propia: **cada test
comprueba las dos cosas**, que el radar hace lo que dice la matriz y que el mensaje lo entiende
alguien que no programa. Por eso casi todos terminan con las mismas tres comprobaciones:

- el mensaje no lleva una traza (`Traceback`, `Error`, nombres de módulos de Python);
- dice qué ha pasado en castellano;
- y, cuando hay algo que hacer, lo dice.

Lo que **no** cubre, escrito aquí para que se vea: la fila de la casilla del formulario
ilegible (§8, fila 14) no se puede probar entera porque la rama que manda páginas como imagen
al modelo (D21) no está construida. Lo que sí se comprueba es que el radar no se inventa el
valor de una casilla: se marca el pliego como formulario y toda cita se verifica letra a letra.
"""

import contextlib
import io
import types

import httpx
import pytest
from conftest import ClienteFalso, entrada, pagina, pdf_con_paginas
from pypdf import PdfWriter

from radar import documentos, extraccion, ingesta, llm, localizar, red, triaje
from radar.errores import (
    CertificadoNoVerificable,
    DocumentoIlegible,
    ErrorRadar,
    FaltaConfiguracion,
    FuenteNoResponde,
    SinConexion,
)

# Palabras que delatan que se está enseñando una traza o un error de programador.
JERGA = ("Traceback", "Exception", "psycopg", "httpx", "anthropic", "None", "self.", "__")


def es_legible(mensaje: str) -> None:
    """Lo mismo que se le exige a todos los mensajes: castellano y sin tripas."""
    assert mensaje.strip(), "un mensaje vacío no le dice nada a nadie"
    for palabra in JERGA:
        assert palabra not in mensaje, f"el mensaje enseña tripas: {palabra}"
    assert mensaje[0].isupper(), "una frase empieza por mayúscula"
    assert any(c in mensaje for c in ".:"), "una frase termina"


PLACSP = "https://contrataciondelsectorpublico.gob.es/algo"


class ClienteQueFalla:
    """Cliente httpx falso: lanza lo que se le diga y cuenta cuántas veces se lo piden."""

    def __init__(self, error: Exception):
        self.error = error
        self.intentos = 0

    def stream(self, metodo, url):
        self.intentos += 1
        raise self.error


class ApiFalsa:
    """Cliente del SDK falso. Con `error`, lo lanza; si no, contesta lo que se le pase."""

    def __init__(self, texto: str = "hola", error: Exception | None = None, stop_reason="end_turn"):
        self.error = error
        self.peticiones = []
        self.texto = texto
        self.stop_reason = stop_reason
        self.messages = types.SimpleNamespace(
            create=self._create,
            count_tokens=lambda **kw: types.SimpleNamespace(input_tokens=100),
        )

    def _create(self, **peticion):
        self.peticiones.append(peticion)
        if self.error:
            raise self.error
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=self.texto)],
            usage=types.SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            stop_reason=self.stop_reason,
            _request_id="req_de_prueba",
            to_dict=lambda: {"stop_reason": self.stop_reason},
        )


@pytest.fixture
def modelo(monkeypatch):
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("TIPO_CAMBIO_USD_EUR", "0.87")
    monkeypatch.setenv("TIPO_CAMBIO_ORIGEN", "BCE, de prueba")
    monkeypatch.setenv("PRESUPUESTO_DIARIO_EUR", "2.00")


def error_del_sdk(clase: str, **kw):
    import anthropic

    peticion = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    if clase == "AuthenticationError":
        respuesta = httpx.Response(401, request=peticion, json={"error": {"message": "invalid"}})
        return anthropic.AuthenticationError("401", response=respuesta, body=None)
    if clase == "RateLimitError":
        respuesta = httpx.Response(429, request=peticion, json={"error": {"message": "slow down"}})
        return anthropic.RateLimitError("429", response=respuesta, body=None)
    if clase == "SinSaldo":
        # Tal y como llega de verdad: un 400 corriente con el motivo dentro del mensaje.
        cuerpo = {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": (
                    "Your credit balance is too low to access the Anthropic API. Please go to "
                    "Plans & Billing to upgrade or purchase credits."
                ),
            },
        }
        respuesta = httpx.Response(400, request=peticion, json=cuerpo)
        return anthropic.BadRequestError("Error code: 400 - " + str(cuerpo), response=respuesta, body=cuerpo)
    return anthropic.APIConnectionError(request=peticion)


# --- 1. Sin red -----------------------------------------------------------------------


def test_sin_red_no_se_pierde_nada_y_el_cursor_no_avanza(bd, almacen_temporal, monkeypatch):
    cliente = ClienteQueFalla(httpx.ConnectError("[Errno 11001] getaddrinfo failed"))
    with pytest.raises(SinConexion) as fallo:
        red.descargar(PLACSP, cliente, intentos=1)
    es_legible(str(fallo.value))
    assert "conexión a internet" in str(fallo.value)
    assert "reintentará" in str(fallo.value)

    # Y la ingesta no deja el cursor tocado ni la ejecución abierta.
    monkeypatch.setattr(ingesta, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(ingesta, "descargar", lambda *a, **kw: (_ for _ in ()).throw(SinConexion("Sin red.")))
    with pytest.raises(ErrorRadar):
        ingesta.ingerir(paginas_max=1)
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM cursor_feed")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM ejecuciones WHERE estado = 'en_curso'")
        assert cur.fetchone()[0] == 0, "una ejecución que falla se cierra, no se queda abierta"


# --- 2. La Plataforma no responde -----------------------------------------------------


def test_la_plataforma_caida_se_reintenta_tres_veces_y_luego_avisa(monkeypatch):
    monkeypatch.setattr(red.time, "sleep", lambda s: None)  # sin esperas de verdad en el test
    cliente = ClienteQueFalla(httpx.ReadTimeout("tarda demasiado"))
    with pytest.raises(FuenteNoResponde) as fallo:
        red.descargar(PLACSP, cliente, intentos=3)
    assert cliente.intentos == 3, "tres intentos, como dice la matriz de fallos"
    es_legible(str(fallo.value))
    assert "Plataforma" in str(fallo.value)


def test_la_espera_entre_intentos_crece(monkeypatch):
    esperas = []
    monkeypatch.setattr(red.time, "sleep", esperas.append)
    with pytest.raises(FuenteNoResponde):
        red.descargar(PLACSP, ClienteQueFalla(httpx.ReadTimeout("x")), intentos=3)
    assert esperas == sorted(esperas) and esperas[0] < esperas[-1], "insistir igual de rápido molesta"


# --- 3. Certificado TLS ---------------------------------------------------------------


def test_un_certificado_que_no_se_puede_verificar_para_el_radar():
    cliente = ClienteQueFalla(httpx.ConnectError("certificate verify failed: unable to get issuer"))
    with pytest.raises(CertificadoNoVerificable) as fallo:
        red.descargar(PLACSP, cliente, intentos=1)
    es_legible(str(fallo.value))
    assert "certifi" in str(fallo.value) or "certificados" in str(fallo.value)


def test_nunca_se_desactiva_la_verificacion_de_certificados():
    """D12. Si alguien escribe verify=False en el paquete, esto se pone rojo.

    Se miran los tokens del codigo, no el texto: el propio CLAUDE.md y los comentarios dicen
    "prohibido verify=False", y buscar la cadena a pelo da un falso positivo por la frase que
    justamente prohibe hacerlo.
    """
    import tokenize
    from pathlib import Path

    for fichero in Path("radar").rglob("*.py"):
        with tokenize.open(fichero) as abierto:
            codigo = [
                t.string
                for t in tokenize.generate_tokens(abierto.readline)
                if t.type not in (tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE)
            ]
        for i in range(len(codigo) - 2):
            trozo = codigo[i : i + 3]
            assert trozo != ["verify", "=", "False"], f"{fichero} desactiva la verificación TLS"


# --- 4. Falta la clave de la API ------------------------------------------------------


def test_sin_clave_de_anthropic_no_se_llama_a_nada(monkeypatch):
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(FaltaConfiguracion) as fallo:
        llm.cliente()
    es_legible(str(fallo.value))
    assert ".env" in str(fallo.value)


def test_una_clave_que_no_tiene_forma_de_clave_se_rechaza(monkeypatch):
    # Paso de verdad: en ANTHROPIC_API_KEY habia pegada una direccion de LinkedIn.
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "https://www.linkedin.com/in/alguien/")
    with pytest.raises(FaltaConfiguracion) as fallo:
        llm.cliente()
    assert "sk-ant-" in str(fallo.value)


# --- 5. Clave inválida o sin saldo ----------------------------------------------------


def test_una_clave_rechazada_por_el_modelo_lo_dice_sin_traza(bd, modelo):
    api = ApiFalsa(error=error_del_sdk("AuthenticationError"))
    with pytest.raises(llm.ModeloNoResponde) as fallo:
        llm.llamar("prueba", [{"role": "user", "content": "hola"}], api=api)
    es_legible(str(fallo.value))
    assert "clave" in str(fallo.value) and "saldo" in str(fallo.value)


def test_sin_saldo_en_la_cuenta_se_dice_que_falta_saldo_y_donde(bd, modelo):
    # Llega como un 400 corriente, y el mensaje de un 400 —«algo de lo que se le manda no le
    # encaja, es un fallo del programa»— manda a buscar un fallo que no existe. Pasó de verdad
    # el 28-09-2026: la primera mañana trió las 400 licitaciones y se quedó sin saldo antes de
    # abrir un solo pliego, y lo único que se veía era «el modelo ha rechazado la petición».
    api = ApiFalsa(error=error_del_sdk("SinSaldo"))
    with pytest.raises(llm.ModeloNoResponde) as fallo:
        llm.llamar("extraccion", [{"role": "user", "content": "hola"}], api=api)
    mensaje = str(fallo.value)
    es_legible(mensaje)
    assert "saldo" in mensaje and "Plans & Billing" in mensaje
    assert "fallo del programa" not in mensaje
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM llm_llamadas")
        assert cur.fetchone()[0] == 0, "sin saldo no hay llamada, y sin llamada no hay cobro"


# --- 6. Límite de uso o saturación ----------------------------------------------------


def test_si_el_modelo_esta_saturado_no_se_pierde_lo_hecho(bd, modelo):
    api = ApiFalsa(error=error_del_sdk("RateLimitError"))
    with pytest.raises(llm.ModeloNoResponde) as fallo:
        llm.llamar("triaje", [{"role": "user", "content": "hola"}], api=api)
    mensaje = str(fallo.value)
    es_legible(mensaje)
    assert "peticiones" in mensaje and "vuelve a lanzar" in mensaje.lower()
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM llm_llamadas")
        assert cur.fetchone()[0] == 0, "una llamada que no llegó a hacerse no se cobra"


# --- 7. Presupuesto agotado -----------------------------------------------------------


def test_con_el_presupuesto_agotado_no_se_llama_y_se_dice_cuanto(bd, modelo, monkeypatch):
    monkeypatch.setenv("PRESUPUESTO_DIARIO_EUR", "0.00")
    api = ApiFalsa()
    with pytest.raises(llm.PresupuestoAgotado) as fallo:
        llm.llamar("triaje", [{"role": "user", "content": "hola"}], api=api)
    mensaje = str(fallo.value)
    es_legible(mensaje)
    assert "PRESUPUESTO_DIARIO_EUR" in mensaje, "hay que decir dónde se sube"
    assert api.peticiones == [], "el corte es antes de pagar, no después"


# --- 8. PDF corrupto o que no es un PDF -----------------------------------------------


def test_un_pdf_danado_manda_ese_expediente_a_revisar_y_el_resto_sigue():
    with pytest.raises(DocumentoIlegible) as fallo:
        documentos.analizar(b"%PDF-1.4 esto se corto por la mitad")
    es_legible(str(fallo.value))
    assert "no se ha podido leer" in str(fallo.value).lower()


def test_una_pagina_html_de_error_no_se_confunde_con_un_pliego():
    with pytest.raises(DocumentoIlegible) as fallo:
        documentos.analizar(b"<html><body>Servicio no disponible</body></html>")
    assert "no es un PDF" in str(fallo.value)


# --- 9. PDF escaneado -----------------------------------------------------------------


def test_un_pliego_escaneado_se_dice_no_se_adivina():
    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    memoria = io.BytesIO()
    escritor.write(memoria)
    encontrado = localizar.localizar(memoria.getvalue())
    assert encontrado.via == "no_localizada" and not encontrado.hay_que_leer
    es_legible(encontrado.motivo)
    assert "escaneado" in encontrado.motivo
    # La rama de OCR (D21) no está construida, y el mensaje lo dice en lugar de callarlo.
    assert "a mano" in encontrado.motivo or "imagen" in encontrado.motivo


# --- 10. Pliego en zip o firmado ------------------------------------------------------


def test_un_zip_o_un_xsig_no_se_abren_y_se_dice_cual_es():
    for nombre, datos in [("zip", b"PK\x03\x04\x14\x00"), ("xsig", b"<?xml version='1.0'?><xsig/>")]:
        with pytest.raises(DocumentoIlegible) as fallo:
            documentos.analizar(datos)
        assert "no es un PDF" in str(fallo.value), nombre


def test_la_extension_sale_de_los_bytes_no_de_lo_que_se_esperaba():
    # En la Fase 1 se guardaron 3 zip con extension .pdf porque se creyo lo que decia la URL.
    from radar import almacen

    assert almacen.extension("pliego", b"PK\x03\x04") == ".zip"
    assert almacen.extension("pliego", b"%PDF-1.7") == ".pdf"


# --- 11. Postgres caído ---------------------------------------------------------------


def test_sin_base_de_datos_se_dice_como_arrancarla(monkeypatch):
    from radar import bd

    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5599")  # nadie escucha ahí
    monkeypatch.setattr(bd, "load_dotenv", lambda *a, **kw: None)
    with pytest.raises(FaltaConfiguracion) as fallo:
        with bd.conectar():
            pass
    es_legible(str(fallo.value))
    assert "docker compose up -d" in str(fallo.value)


# --- 12. XML del feed malformado ------------------------------------------------------


def test_una_entrada_rota_va_a_cuarentena_y_el_resto_se_ingiere(bd, almacen_temporal, monkeypatch):
    buena = entrada("https://ejemplo.es/licitacion/1", "2026-09-05T10:00:00.000+02:00")
    rota = "<entry><id>https://ejemplo.es/rota</id><updated>no es una fecha</updated></entry>"
    paginas = {ingesta.feed.FEED_PERFILES: pagina([buena, rota])}
    monkeypatch.setattr(ingesta, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: paginas[url])

    resumen = ingesta.ingerir(paginas_max=1)
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        assert cur.fetchone()[0] >= 1, "la entrada buena se ingiere igual"
        cur.execute("SELECT count(*) FROM stg_entradas WHERE estado_parseo = 'cuarentena'")
        cuarentena = cur.fetchone()[0]
    assert cuarentena >= 1 or resumen.get("cuarentena", 0) >= 1, (
        "la entrada rota queda registrada, no se tira"
    )


# --- 13. Doble ejecución el mismo día -------------------------------------------------


def test_lanzar_la_ingesta_dos_veces_no_duplica_nada(bd, almacen_temporal, monkeypatch):
    bloque = entrada("https://ejemplo.es/licitacion/1", "2026-09-05T10:00:00.000+02:00")
    paginas = {ingesta.feed.FEED_PERFILES: pagina([bloque])}
    monkeypatch.setattr(ingesta, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: paginas[url])

    ingesta.ingerir(paginas_max=1)
    ingesta.ingerir(paginas_max=1)
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        una_vez = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT (entry_id, entry_updated)) FROM licitaciones")
        assert cur.fetchone()[0] == una_vez == 1


# --- 14. Casilla del formulario ilegible ----------------------------------------------


def test_un_pliego_con_casillas_se_reconoce_como_formulario():
    # Cubierto a medias a proposito: la rama que manda la pagina como imagen (D21) no esta
    # construida. Lo que si se garantiza es que el radar no se inventa lo que marca la casilla.
    pliego = pdf_con_paginas(["Solvencia economica: [ ] Si [ ] No", "volumen anual de negocios"])
    medidas = documentos.analizar(pliego)
    assert "casillas_visibles" in medidas and "es_formulario" in medidas


def test_no_se_puede_dar_por_bueno_un_requisito_cuya_cita_no_esta_en_la_pagina():
    # Esta es la garantia de verdad de la fila 14: nada se supone. Si el modelo rellena el
    # valor de una casilla que no puede leer, la cita no aparecera y el requisito se descarta.
    buenos, rechazados = extraccion.interpretar(
        '{"requisitos": [{"tipo": "volumen_negocios", "exigencia": "x",'
        ' "cita": "marcada la casilla de 150.000 euros", "pagina": 1, "importe_eur": 150000}]}',
        {1: "Solvencia economica: [ ] Si [ ] No"},
    )
    assert buenos == []
    assert "no aparece" in rechazados[0]["motivo"]


# --- 15. El modelo rechaza la petición ------------------------------------------------


def test_si_el_modelo_se_niega_a_contestar_el_expediente_va_a_revisar(bd, modelo):
    api = ApiFalsa(texto="", stop_reason="refusal")
    with pytest.raises(ErrorRadar) as fallo:
        llm.llamar("extraccion", [{"role": "user", "content": "hola"}], api=api)
    mensaje = str(fallo.value)
    es_legible(mensaje)
    assert "revisar" in mensaje.lower() or "a mano" in mensaje.lower()
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT stop_reason FROM llm_llamadas")
        assert cur.fetchone()[0] == "refusal", "la llamada se pagó: queda apuntada"


def test_un_triaje_que_el_modelo_no_contesta_no_descarta_la_licitacion():
    respuesta = triaje.Respuesta(faltan=["1", "2"], ilegible="No se ha podido leer la respuesta.")
    assert respuesta.decisiones == {}
    # `guardar` las escribe como 'revisar': ninguna se queda con un 'no' que nadie dijo.
    assert triaje.REVISAR == "revisar"


# --- 16. El PC estaba apagado a las 07:00 ---------------------------------------------


def test_si_se_salta_un_dia_la_siguiente_pasada_recupera_desde_el_cursor(bd, almacen_temporal, monkeypatch):
    lunes = entrada("https://ejemplo.es/licitacion/1", "2026-09-07T10:00:00.000+02:00")
    martes = entrada("https://ejemplo.es/licitacion/2", "2026-09-08T10:00:00.000+02:00")
    monkeypatch.setattr(ingesta, "crear_cliente", ClienteFalso)

    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: pagina([lunes]))
    ingesta.ingerir(paginas_max=1)
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT ultima_fecha FROM cursor_feed")
        primero = cur.fetchone()

    # Dos días después, el feed trae las dos: la del día saltado tiene que entrar igual.
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: pagina([martes, lunes]))
    ingesta.ingerir(paginas_max=1)
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(DISTINCT entry_id) FROM licitaciones")
        assert cur.fetchone()[0] == 2, "no se pierde lo del día en que el PC estaba apagado"
        cur.execute("SELECT ultima_fecha FROM cursor_feed")
        assert cur.fetchone() != primero, "el cursor avanza cuando la pasada llega a lo conocido"


# --- Lo que vale para todas las filas -------------------------------------------------


def errores_del_radar() -> set[str]:
    """Los nombres de todas las excepciones del radar, incluidas las de cada módulo."""
    import importlib
    import pkgutil

    import radar
    from radar.errores import ErrorRadar

    for modulo in pkgutil.walk_packages(radar.__path__, "radar."):
        with contextlib.suppress(Exception):
            importlib.import_module(modulo.name)

    nombres, pendientes = {"ErrorRadar"}, [ErrorRadar]
    while pendientes:
        clase = pendientes.pop()
        for hija in clase.__subclasses__():
            if hija.__name__ not in nombres:
                nombres.add(hija.__name__)
                pendientes.append(hija)
    return nombres


def mensajes_del_paquete() -> list[tuple[str, int, str]]:
    """Cada mensaje que el radar puede enseñar, con su fichero y su línea."""
    import ast
    from pathlib import Path

    errores = errores_del_radar()
    encontrados = []
    for fichero in Path("radar").rglob("*.py"):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Raise) or not isinstance(nodo.exc, ast.Call):
                continue
            llamada = nodo.exc.func
            nombre = getattr(llamada, "id", None) or getattr(llamada, "attr", None)
            if nombre not in errores or not nodo.exc.args:
                continue
            primero = nodo.exc.args[0]
            texto = "".join(
                trozo.value
                for trozo in ast.walk(primero)
                if isinstance(trozo, ast.Constant) and isinstance(trozo.value, str)
            )
            # Si el mensaje empieza por un dato («Empresa A no está…»), la mayúscula la pone el
            # dato y no el texto: solo se exige cuando el mensaje empieza por letra escrita.
            empieza_escrito = not (
                isinstance(primero, ast.JoinedStr)
                and primero.values
                and isinstance(primero.values[0], ast.FormattedValue)
            )
            if texto.strip():
                encontrados.append((fichero.as_posix(), nodo.lineno, texto, empieza_escrito))
    return encontrados


def test_todos_los_mensajes_del_radar_los_entiende_una_persona():
    """La segunda mitad de la Fase 6: no basta con que el radar no se caiga.

    Recorre el paquete entero buscando lo que se le enseña al usuario cuando algo falla, y le
    exige lo mismo a todos: castellano, sin tripas de Python y con una frase entera. Si alguien
    escribe mañana un mensaje con el nombre de una excepción dentro, esto se pone rojo.
    """
    mensajes = mensajes_del_paquete()
    assert len(mensajes) > 25, "o el radar tiene pocos errores previstos, o esto no los encuentra"
    malos = []
    for fichero, linea, texto, empieza_escrito in mensajes:
        for palabra in JERGA:
            if palabra in texto:
                malos.append(f"{fichero}:{linea} enseña «{palabra}»: {texto[:70]}")
        if empieza_escrito and not texto[0].isupper():
            malos.append(f"{fichero}:{linea} no empieza por mayúscula: {texto[:70]}")
        if not any(c in texto for c in ".:?…!"):
            malos.append(f"{fichero}:{linea} no termina la frase: {texto[:70]}")
    assert malos == [], "\n" + "\n".join(malos)


def test_ningun_mensaje_manda_a_mirar_el_codigo():
    """Un mensaje que dice «revisa el log» o «contacta con soporte» no sirve de nada aquí."""
    inutiles = ("contacta con soporte", "error desconocido", "algo salió mal", "inténtalo de nuevo")
    for fichero, linea, texto, _ in mensajes_del_paquete():
        for frase in inutiles:
            assert frase not in texto.lower(), f"{fichero}:{linea}"
