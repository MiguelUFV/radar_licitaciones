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
