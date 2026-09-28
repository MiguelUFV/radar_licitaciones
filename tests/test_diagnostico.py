"""El diagnostico del entorno.

Nace de un fallo real del 27-09-2026: en ANTHROPIC_API_KEY habia pegada la direccion de un
perfil de LinkedIn, y el diagnostico la daba por buena porque solo miraba que no estuviera
vacia. Una clave mal puesta se descubriria en la primera llamada al modelo, pagando.
"""

from radar import diagnostico


def test_una_clave_con_la_forma_correcta_se_acepta():
    assert diagnostico.parece_clave_anthropic("sk-ant-api03-" + "x" * 90) is True


def test_una_direccion_web_pegada_por_error_no_pasa():
    assert diagnostico.parece_clave_anthropic("https://www.linkedin.com/in/alguien/") is False


def test_tampoco_pasa_algo_demasiado_corto_ni_vacio():
    assert diagnostico.parece_clave_anthropic("sk-ant-api03-corta") is False
    assert diagnostico.parece_clave_anthropic("") is False
    assert diagnostico.parece_clave_anthropic(None) is False


def test_el_diagnostico_lo_dice_con_claridad(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "https://www.linkedin.com/in/alguien/")
    monkeypatch.setattr(diagnostico, "load_dotenv", lambda *a, **kw: None)
    mensajes = [m for _, m, _ in diagnostico.comprobar_env() if "ANTHROPIC" in m]
    assert mensajes
    assert "no parece una clave" in mensajes[0]
    assert "sk-ant-" in mensajes[0]


def test_avisa_si_la_regla_del_sorteo_ha_cambiado(bd, monkeypatch):
    # `perfiles.regla_sha256` guarda la huella que tenía el documento el día del sorteo, y
    # hasta el 29-09-2026 nadie la volvía a mirar. Un candado que no se comprueba no es un
    # candado. Cambiarlo está permitido —con su entrada en Cambios—, así que esto avisa.
    from radar import diagnostico, seleccion

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256) VALUES ('Empresa A', 'B00000001', 'test', 1, 1, '1', repeat('a', 64))"
        )
        conexion.commit()

    monkeypatch.setattr(seleccion, "huella_de_la_regla", lambda: "a" * 64)
    correcto, mensaje = diagnostico.comprobar_regla_congelada()
    assert correcto and "la misma" in mensaje

    monkeypatch.setattr(seleccion, "huella_de_la_regla", lambda: "b" * 64)
    correcto, mensaje = diagnostico.comprobar_regla_congelada()
    assert not correcto
    assert "Cambios" in mensaje and "Traceback" not in mensaje


def test_avisa_si_el_universo_del_estudio_ya_no_es_el_medido(bd):
    # Las cifras publicadas se calcularon sobre un numero concreto de expedientes. Cargar mas
    # historico lo cambio de verdad el 29-09-2026: expedientes que parecian publicados por
    # primera vez en 2025 tenian una version en 2024 y salieron del periodo. Una medicion que
    # ya no corresponde a los datos que hay tiene que saltar sola.
    from radar import diagnostico

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO eval_resultados (metrica, variante, periodo_desde, periodo_hasta,"
            " valor, n, git_commit, comando) VALUES ('M2', 'baseline_a', '2025-01-01',"
            " '2025-07-01', 49.9, 120656, 'x', 'cmd')"
        )
        conexion.commit()

    correcto, mensaje = diagnostico.comprobar_universo_del_estudio()
    assert not correcto, "la base de pruebas no tiene 120.656 expedientes: tiene que avisar"
    assert "120656" in mensaje and "Traceback" not in mensaje
    assert "no corresponde" in mensaje


def test_sin_mediciones_publicadas_no_hay_nada_que_comparar(bd):
    from radar import diagnostico

    correcto, mensaje = diagnostico.comprobar_universo_del_estudio()
    assert correcto and "Todavía no" in mensaje
