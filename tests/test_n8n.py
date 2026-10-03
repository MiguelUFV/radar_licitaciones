"""Lo que se exporta a n8n/workflows/ se versiona, así que no puede llevar datos personales.

El 03-10-2026, al revisar el repositorio antes de hacerlo público, apareció la dirección de
correo personal de su autor en los tres workflows exportados: `exportar()` escribía la
definición tal cual, y la dirección sale de `.env` a través de `correo_de()`. La contraseña de
Postgres ya se excluía a propósito (solo se guardan el id y el nombre de la credencial); el
correo se había quedado fuera de esa regla.
"""

from __future__ import annotations

import json

from radar import n8n


def test_el_correo_no_se_escribe_en_el_fichero_versionado(tmp_path, monkeypatch):
    monkeypatch.setattr(n8n, "CARPETA", tmp_path)
    definicion = {
        "name": "radar_prueba",
        "nodes": [
            {
                "parameters": {
                    "fromEmail": "persona@ejemplo.com",
                    "toEmail": "persona@ejemplo.com",
                    "subject": "Licitaciones de hoy",
                }
            }
        ],
    }

    destino = n8n.exportar(definicion)
    escrito = destino.read_text(encoding="utf-8")

    assert "persona@ejemplo.com" not in escrito
    assert n8n.CORREO_OCULTO in escrito
    # Lo demás se exporta tal cual: el objetivo es ocultar la dirección, no mutilar el workflow.
    assert "Licitaciones de hoy" in escrito


def test_exportar_no_cambia_la_definicion_que_recibe(tmp_path, monkeypatch):
    """La misma definición se usa para publicar en n8n, donde la dirección sí hace falta."""
    monkeypatch.setattr(n8n, "CARPETA", tmp_path)
    definicion = {"name": "radar_prueba", "nodes": [{"parameters": {"toEmail": "persona@ejemplo.com"}}]}

    n8n.exportar(definicion)

    assert definicion["nodes"][0]["parameters"]["toEmail"] == "persona@ejemplo.com"


def test_una_direccion_dentro_de_un_texto_largo_tambien_se_oculta(tmp_path, monkeypatch):
    """La dirección aparece además en el cuerpo de algún nodo, no solo en los campos de correo."""
    monkeypatch.setattr(n8n, "CARPETA", tmp_path)
    definicion = {
        "name": "radar_prueba",
        "nodes": [{"parameters": {"text": "Avisa a persona@ejemplo.com si algo falla."}}],
    }

    escrito = json.loads(n8n.exportar(definicion).read_text(encoding="utf-8"))

    assert "persona@ejemplo.com" not in escrito["nodes"][0]["parameters"]["text"]
