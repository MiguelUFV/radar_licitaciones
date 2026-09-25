"""Crea y exporta los workflows de n8n desde código.

Los workflows no se montan a mano en la pantalla: se definen aquí, se publican con la API
de n8n y se exportan a n8n/workflows/ para que queden versionados (CLAUDE.md, apartado Git).

    uv run python -m radar.n8n --publicar
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from radar.errores import FaltaConfiguracion

CARPETA = Path("n8n/workflows")
# Dentro de la red de Docker, el servicio se llama por su nombre; no hace falta salir al host.
URL_AGENTE = "http://agente:8000"


def cliente() -> httpx.Client:
    load_dotenv()
    clave = os.getenv("N8N_API_KEY")
    if not clave:
        raise FaltaConfiguracion(
            "Falta N8N_API_KEY en .env. Créala en n8n: Settings, n8n API, Create an API key."
        )
    base = os.getenv("N8N_URL", "http://127.0.0.1:5679")
    return httpx.Client(base_url=f"{base}/api/v1", headers={"X-N8N-API-KEY": clave}, timeout=30)


def workflow_diario() -> dict:
    """07:00 de lunes a viernes: ingesta del feed y registro del resultado."""
    return {
        "name": "radar_diario",
        "settings": {"executionOrder": "v1", "timezone": "Europe/Madrid"},
        "nodes": [
            {
                "parameters": {
                    "rule": {"interval": [{"field": "cronExpression", "expression": "0 7 * * 1-5"}]}
                },
                "id": "disparador",
                "name": "Cada dia laborable a las 07:00",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            {
                "parameters": {
                    "url": f"{URL_AGENTE}/salud",
                    "options": {"timeout": 10000},
                },
                "id": "salud",
                "name": "Comprobar que el radar responde",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [220, 0],
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{URL_AGENTE}/ingesta",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": (
                        "={{ JSON.stringify({ paginas: 10, tipo: 'diaria',"
                        " n8n_execution_id: $execution.id }) }}"
                    ),
                    "options": {"timeout": 900000},
                },
                "id": "ingesta",
                "name": "Ingerir el feed",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [440, 0],
            },
        ],
        "connections": {
            "Cada dia laborable a las 07:00": {
                "main": [[{"node": "Comprobar que el radar responde", "type": "main", "index": 0}]]
            },
            "Comprobar que el radar responde": {
                "main": [[{"node": "Ingerir el feed", "type": "main", "index": 0}]]
            },
        },
    }


def publicar(definicion: dict, activar: bool = True) -> dict:
    with cliente() as api:
        existentes = api.get("/workflows").json().get("data", [])
        anterior = next((w for w in existentes if w["name"] == definicion["name"]), None)
        if anterior:
            respuesta = api.put(f"/workflows/{anterior['id']}", json=definicion)
        else:
            respuesta = api.post("/workflows", json=definicion)
        respuesta.raise_for_status()
        creado = respuesta.json()
        if activar:
            api.post(f"/workflows/{creado['id']}/activate")
        return creado


def exportar(definicion: dict) -> Path:
    CARPETA.mkdir(parents=True, exist_ok=True)
    destino = CARPETA / f"{definicion['name']}.json"
    destino.write_text(json.dumps(definicion, indent=2, ensure_ascii=False), encoding="utf-8")
    return destino


def main() -> int:
    parser = argparse.ArgumentParser(description="Workflows de n8n")
    parser.add_argument("--publicar", action="store_true", help="crear o actualizar en n8n")
    args = parser.parse_args()

    definicion = workflow_diario()
    destino = exportar(definicion)
    print(f"Exportado a {destino}")

    if args.publicar:
        try:
            creado = publicar(definicion)
        except FaltaConfiguracion as e:
            print(e)
            return 1
        print(f"Publicado en n8n: {creado['name']} (id {creado['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
