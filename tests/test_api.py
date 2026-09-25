"""Servicio HTTP: ante un fallo, n8n tiene que recibir un mensaje legible, no una traza.

El texto de estas respuestas acaba en el correo de aviso, así que lo lee una persona
(CLAUDE.md, innegociable 3).
"""

from fastapi.testclient import TestClient

from radar import api
from radar.errores import FaltaConfiguracion, FuenteNoResponde


def cliente() -> TestClient:
    return TestClient(api.app, raise_server_exceptions=False)


def _base_caida():
    raise FaltaConfiguracion("La base de datos no está disponible. Arráncala con: docker compose up -d")


def test_la_salud_con_la_base_caida_responde_un_mensaje_legible(monkeypatch):
    monkeypatch.setattr(api, "conectar", _base_caida)
    respuesta = cliente().get("/salud")
    assert respuesta.status_code == 503
    assert "base de datos" in respuesta.json()["mensaje"]


def test_el_resumen_con_la_base_caida_no_muestra_una_traza(monkeypatch):
    monkeypatch.setattr(api, "conectar", _base_caida)
    respuesta = cliente().get("/resumen/hoy")
    assert respuesta.status_code == 503
    assert "Traceback" not in respuesta.text
    assert "base de datos" in respuesta.json()["mensaje"]


def test_la_ingesta_traduce_el_fallo_de_la_fuente(monkeypatch):
    def sin_fuente(*args, **kwargs):
        raise FuenteNoResponde("La Plataforma de Contratación no responde.")

    monkeypatch.setattr(api.ingesta, "ingerir", sin_fuente)
    respuesta = cliente().post("/ingesta", json={"paginas": 1})
    assert respuesta.status_code == 503
    assert "no responde" in respuesta.json()["mensaje"]


def test_pedir_mas_paginas_de_la_cuenta_se_rechaza_con_claridad():
    respuesta = cliente().post("/ingesta", json={"paginas": 999})
    assert respuesta.status_code == 422
    assert "Traceback" not in respuesta.text
