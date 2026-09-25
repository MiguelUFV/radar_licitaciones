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
CREDENCIAL = CARPETA / "credencial_postgres.json"
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


def credencial_postgres(api: httpx.Client) -> dict:
    """La credencial que usa n8n para dejar constancia de un fallo en la base de datos.

    La API pública de n8n no permite listar credenciales, así que el identificador se guarda
    en n8n/workflows/credencial_postgres.json (solo el id y el nombre, nunca la contraseña).
    """
    if CREDENCIAL.exists():
        return json.loads(CREDENCIAL.read_text(encoding="utf-8"))

    contrasena = os.getenv("POSTGRES_PASSWORD")
    if not contrasena:
        raise FaltaConfiguracion("Falta POSTGRES_PASSWORD en .env para crear la credencial en n8n.")
    respuesta = api.post(
        "/credentials",
        json={
            "name": "radar_postgres",
            "type": "postgres",
            "data": {
                # n8n habla con Postgres por la red de Docker, no por localhost.
                "host": "postgres",
                "port": 5432,
                "database": os.getenv("POSTGRES_DB", "radar"),
                "user": os.getenv("POSTGRES_USER", "radar"),
                "password": contrasena,
                "ssl": "disable",
            },
        },
    )
    respuesta.raise_for_status()
    creada = respuesta.json()
    ficha = {"id": creada["id"], "name": creada["name"]}
    CARPETA.mkdir(parents=True, exist_ok=True)
    CREDENCIAL.write_text(json.dumps(ficha, indent=2), encoding="utf-8")
    return ficha


def workflow_errores(credencial: dict) -> dict:
    """Recoge el fallo de cualquier workflow del radar y lo anota en la tabla incidencias.

    Escribe directo en Postgres a propósito: si lo que falla es que el agente no responde,
    un aviso que pasara por el agente no llegaría nunca.
    """
    # El mensaje de n8n viene en inglés y en su jerga. Se guarda, pero dentro de una frase
    # que se entienda sin saber qué es un workflow (CLAUDE.md, innegociable 3).
    consulta = (
        "INSERT INTO incidencias (workflow, n8n_execution_id, nodo, mensaje)"
        " VALUES ($1, $2, $3,"
        " 'El radar no ha podido terminar su tarea automática: se paró en el paso «'"
        " || coalesce($3, 'desconocido') || '». Lo ya guardado no se pierde y se reintenta"
        " en la próxima ejecución. Detalle técnico: ' || coalesce($4, '(sin detalle)'))"
    )
    valores = (
        "={{ $json.workflow?.name }},{{ $json.execution?.id }},"
        "{{ $json.execution?.lastNodeExecuted }},{{ $json.execution?.error?.message }}"
    )
    return {
        "name": "radar_errores",
        "settings": {"executionOrder": "v1", "timezone": "Europe/Madrid"},
        "nodes": [
            {
                "parameters": {},
                "id": "fallo",
                "name": "Cuando falla un workflow del radar",
                "type": "n8n-nodes-base.errorTrigger",
                "typeVersion": 1,
                "position": [0, 0],
            },
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": consulta,
                    "options": {"queryReplacement": valores},
                },
                "id": "anotar",
                "name": "Anotar la incidencia",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.6,
                "position": [240, 0],
                "credentials": {"postgres": credencial},
            },
        ],
        "connections": {
            "Cuando falla un workflow del radar": {
                "main": [[{"node": "Anotar la incidencia", "type": "main", "index": 0}]]
            }
        },
    }


def workflow_diario(errores_id: str | None = None) -> dict:
    """07:00 de lunes a viernes: ingesta del feed, descarga de pliegos y registro."""
    ajustes = {"executionOrder": "v1", "timezone": "Europe/Madrid"}
    if errores_id:
        ajustes["errorWorkflow"] = errores_id
    return {
        "name": "radar_diario",
        "settings": ajustes,
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
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{URL_AGENTE}/pliegos",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": (
                        "={{ JSON.stringify({ limite: 20, tipo: 'diaria',"
                        " n8n_execution_id: $execution.id }) }}"
                    ),
                    "options": {"timeout": 900000},
                },
                "id": "pliegos",
                "name": "Bajar los pliegos pendientes",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [660, 0],
            },
        ],
        "connections": {
            "Cada dia laborable a las 07:00": {
                "main": [[{"node": "Comprobar que el radar responde", "type": "main", "index": 0}]]
            },
            "Comprobar que el radar responde": {
                "main": [[{"node": "Ingerir el feed", "type": "main", "index": 0}]]
            },
            "Ingerir el feed": {
                "main": [[{"node": "Bajar los pliegos pendientes", "type": "main", "index": 0}]]
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

    if not args.publicar:
        # Sin conexión con n8n solo se puede exportar el diario: el de errores necesita el
        # identificador de la credencial.
        print(f"Exportado a {exportar(workflow_diario())}")
        return 0

    try:
        with cliente() as api:
            credencial = credencial_postgres(api)
        errores = publicar(workflow_errores(credencial), activar=True)
        diario = publicar(workflow_diario(errores["id"]), activar=True)
    except FaltaConfiguracion as e:
        print(e)
        return 1

    for definicion in (workflow_errores(credencial), workflow_diario(errores["id"])):
        print(f"Exportado a {exportar(definicion)}")
    print(f"Publicado en n8n: {errores['name']} (id {errores['id']})")
    print(f"Publicado en n8n: {diario['name']} (id {diario['id']}), avisos a {errores['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
