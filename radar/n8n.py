"""Crea y exporta los workflows de n8n desde código.

Los workflows no se montan a mano en la pantalla: se definen aquí, se publican con la API
de n8n y se exportan a n8n/workflows/ para que queden versionados (CLAUDE.md, apartado Git).

    uv run python -m radar.n8n --publicar
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

from radar.errores import FaltaConfiguracion

CARPETA = Path("n8n/workflows")
CREDENCIAL = CARPETA / "credencial_postgres.json"
API_APAGADA = (
    "La API de n8n está apagada a propósito, para que su clave no sirva de nada si se filtra "
    "(docs/DECISIONES.md D32). Para publicar un workflow, enciéndela un momento:\n"
    "  1. En .env, pon N8N_PUBLIC_API_DISABLED=false\n"
    "  2. docker compose up -d n8n\n"
    "  3. uv run python -m radar.n8n --publicar\n"
    "  4. Vuelve a poner N8N_PUBLIC_API_DISABLED=true y repite el paso 2"
)
# Dentro de la red de Docker, el servicio se llama por su nombre; no hace falta salir al host.
URL_AGENTE = "http://agente:8000"

# El correo. La contraseña de aplicación **no** está aquí ni en .env: vive cifrada dentro de
# n8n, en una credencial SMTP que se crea una vez a mano (docs/ENTORNO.md §6). Aquí solo va su
# nombre, que es lo que hay que elegir al importar el workflow.
CREDENCIAL_SMTP = "SMTP del radar"
FICHA_SMTP = CARPETA / "credencial_smtp.json"


def credencial_smtp() -> dict:
    """El id y el nombre de la credencial de correo. La contraseña vive dentro de n8n.

    Si el fichero no está, se referencia solo por el nombre: al importar el workflow habrá que
    elegirla a mano una vez. La contraseña de aplicación no pasa por aquí nunca.
    """
    if FICHA_SMTP.exists():
        return json.loads(FICHA_SMTP.read_text(encoding="utf-8"))
    return {"name": CREDENCIAL_SMTP}


def correo_de(variable: str, por_defecto: str = "") -> str:
    load_dotenv()
    return os.getenv(variable, por_defecto)


def nodo_correo(
    nombre: str,
    identificador: str,
    posicion: list[int],
    asunto: str,
    cuerpo: str,
    destino: str | None = None,
) -> dict:
    """Un nodo de envío. El asunto, el cuerpo y el destinatario son expresiones, no texto fijo.

    `destino` se deja pasar porque desde que hay más de un cliente la dirección no puede estar
    en el `.env`: la trae el propio correo que compone el agente, que sabe de quién es.
    """
    return {
        "parameters": {
            "fromEmail": correo_de("CORREO_REMITENTE"),
            "toEmail": destino or correo_de("CORREO_DESTINO"),
            "subject": asunto,
            "emailFormat": "both",
            "html": cuerpo,
            "text": cuerpo.replace(".html", ".texto") if ".html" in cuerpo else cuerpo,
            "options": {},
        },
        "id": identificador,
        "name": nombre,
        "type": "n8n-nodes-base.emailSend",
        "typeVersion": 2.1,
        "position": posicion,
        "credentials": {"smtp": credencial_smtp()},
    }


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
            nodo_correo(
                "Avisar por correo",
                "avisar",
                [480, 0],
                "=Radar de licitaciones: algo ha fallado esta noche",
                # El texto que se envía es el mismo que se guardó en incidencias: en castellano
                # y sin trazas. Si el mensaje no llegara, la incidencia sigue en la tabla.
                "={{ $json.mensaje }}",
            ),
        ],
        "connections": {
            "Cuando falla un workflow del radar": {
                "main": [[{"node": "Anotar la incidencia", "type": "main", "index": 0}]]
            },
            "Anotar la incidencia": {"main": [[{"node": "Avisar por correo", "type": "main", "index": 0}]]},
        },
    }


def workflow_diario(errores_id: str | None = None) -> dict:
    """07:00 de lunes a viernes: feed, pliegos y, para cada cliente, su trabajo y su correo.

    La lista de empresas no está escrita en el workflow: se le pregunta al agente. Dar de alta
    una empresa nueva no puede obligar a tocar n8n, porque entonces el formulario de alta no
    daría de alta a nadie.
    """
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
            {
                "parameters": {"url": f"{URL_AGENTE}/clientes", "options": {"timeout": 30000}},
                "id": "clientes",
                "name": "Preguntar que empresas hay",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [880, 0],
            },
            {
                "parameters": {"fieldToSplitOut": "empresas", "options": {}},
                "id": "una_a_una",
                "name": "Una empresa por vez",
                "type": "n8n-nodes-base.splitOut",
                "typeVersion": 1,
                "position": [1100, 0],
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{URL_AGENTE}/diario",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": ("={{ JSON.stringify({ empresa: $json.alias, gastar: true }) }}"),
                    "options": {"timeout": 1800000},
                },
                "id": "trabajo",
                "name": "Triar y leer para esa empresa",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1320, 0],
            },
            {
                "parameters": {
                    "url": f"{URL_AGENTE}/correo/hoy",
                    "sendQuery": True,
                    "queryParameters": {
                        "parameters": [
                            {
                                "name": "empresa",
                                "value": "={{ $('Una empresa por vez').item.json.alias }}",
                            }
                        ]
                    },
                    "options": {"timeout": 60000},
                },
                "id": "componer",
                "name": "Pedir el correo del dia",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1540, 0],
            },
            nodo_correo(
                "Enviar el correo del dia",
                "enviar",
                [1760, 0],
                "={{ $json.asunto }}",
                "={{ $json.html }}",
                destino="={{ $json.destinatario }}",
            ),
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
            "Bajar los pliegos pendientes": {
                "main": [[{"node": "Preguntar que empresas hay", "type": "main", "index": 0}]]
            },
            "Preguntar que empresas hay": {
                "main": [[{"node": "Una empresa por vez", "type": "main", "index": 0}]]
            },
            "Una empresa por vez": {
                "main": [[{"node": "Triar y leer para esa empresa", "type": "main", "index": 0}]]
            },
            "Triar y leer para esa empresa": {
                "main": [[{"node": "Pedir el correo del dia", "type": "main", "index": 0}]]
            },
            "Pedir el correo del dia": {
                "main": [[{"node": "Enviar el correo del dia", "type": "main", "index": 0}]]
            },
        },
    }


def workflow_prueba_correo() -> dict:
    """Un workflow de una sola tirada para comprobar que el correo sale de verdad.

    Existe porque la alternativa era lanzar el trabajo diario entero —ingesta incluida— solo para
    ver si el SMTP funciona. Se dispara con:

        curl -X POST http://localhost:5679/webhook/radar-prueba-correo

    El webhook escucha solo en el ordenador, igual que el resto del radar (SPEC §9). Aun así,
    después de comprobarlo se desactiva: un webhook que manda correos y que nadie vigila no tiene
    por qué quedarse encendido.
    """
    return {
        "name": "radar_prueba_correo",
        "settings": {"executionOrder": "v1", "timezone": "Europe/Madrid"},
        "nodes": [
            {
                "parameters": {"httpMethod": "POST", "path": "radar-prueba-correo", "options": {}},
                "id": "disparo",
                "name": "Prueba de correo",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [0, 0],
            },
            {
                "parameters": {
                    "url": f"{URL_AGENTE}/correo/hoy",
                    "sendQuery": True,
                    "queryParameters": {
                        "parameters": [
                            {"name": "empresa", "value": correo_de("CORREO_EMPRESA", "Empresa A")},
                            # Con una fecha en el cuerpo del webhook se manda el correo de ese
                            # día; sin ella, el de hoy. Sirve para enseñar un día con contenido
                            # sin tener que esperar a que lo haya.
                            {"name": "fecha", "value": "={{ $json.body?.fecha || '' }}"},
                        ]
                    },
                    "options": {"timeout": 60000},
                },
                "id": "componer",
                "name": "Pedir el correo del dia",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [220, 0],
            },
            nodo_correo(
                "Enviar la prueba",
                "enviar",
                [440, 0],
                "={{ $json.asunto }}",
                "={{ $json.html }}",
            ),
        ],
        "connections": {
            "Prueba de correo": {"main": [[{"node": "Pedir el correo del dia", "type": "main", "index": 0}]]},
            "Pedir el correo del dia": {"main": [[{"node": "Enviar la prueba", "type": "main", "index": 0}]]},
        },
    }


def comprobar_api(api: httpx.Client) -> None:
    """Distingue "la API está apagada" de "la clave no vale", que dan el mismo código.

    Con la API apagada, n8n responde 401 tanto si mandas la clave como si no: ahí está la
    prueba de que, apagada, la clave no abre nada.
    """
    respuesta = api.get("/workflows")
    if respuesta.status_code in (401, 404):
        raise FaltaConfiguracion(API_APAGADA)
    respuesta.raise_for_status()


def publicar(definicion: dict, activar: bool = True) -> dict:
    with cliente() as api:
        comprobar_api(api)
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


# Lo que se exporta se versiona, así que no puede llevar la dirección de correo de nadie. Es la
# misma regla que ya se aplicaba a la contraseña de Postgres, que nunca sale de .env: aquí se
# había quedado fuera, y la dirección apareció en los tres workflows al revisar el repositorio
# antes de hacerlo público (03-10-2026).
CORREO_OCULTO = "correo@oculto.invalid"
CORREOS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def sin_correos(valor):
    """La misma definición con cualquier dirección sustituida, sin tocar el original."""
    if isinstance(valor, str):
        return CORREOS.sub(CORREO_OCULTO, valor)
    if isinstance(valor, dict):
        return {c: sin_correos(v) for c, v in valor.items()}
    if isinstance(valor, list):
        return [sin_correos(v) for v in valor]
    return valor


def exportar(definicion: dict) -> Path:
    CARPETA.mkdir(parents=True, exist_ok=True)
    destino = CARPETA / f"{definicion['name']}.json"
    publico = sin_correos(definicion)
    destino.write_text(json.dumps(publico, indent=2, ensure_ascii=False), encoding="utf-8")
    return destino


def main() -> int:
    parser = argparse.ArgumentParser(description="Workflows de n8n")
    parser.add_argument("--publicar", action="store_true", help="crear o actualizar en n8n")
    args = parser.parse_args()

    if not args.publicar:
        # Sin conexión con n8n solo se pueden exportar los que no necesitan el identificador de
        # la credencial de Postgres; el de errores sí lo necesita.
        for definicion in (workflow_diario(), workflow_prueba_correo()):
            print(f"Exportado a {exportar(definicion)}")
        return 0

    try:
        with cliente() as api:
            credencial = credencial_postgres(api)
        errores = publicar(workflow_errores(credencial), activar=True)
        diario = publicar(workflow_diario(errores["id"]), activar=True)
        # La prueba de correo se publica activa porque su webhook solo responde si lo está;
        # se apaga en cuanto se ha comprobado que el correo sale (--apagar-prueba).
        prueba = publicar(workflow_prueba_correo(), activar=True)
    except FaltaConfiguracion as e:
        print(e)
        return 1

    for definicion in (
        workflow_errores(credencial),
        workflow_diario(errores["id"]),
        workflow_prueba_correo(),
    ):
        print(f"Exportado a {exportar(definicion)}")
    print(f"Publicado en n8n: {errores['name']} (id {errores['id']})")
    print(f"Publicado en n8n: {diario['name']} (id {diario['id']}), avisos a {errores['name']}")
    print(f"Publicado en n8n: {prueba['name']} (id {prueba['id']})")
    print("\nPara comprobar que el correo sale:")
    print("  curl -X POST http://localhost:5679/webhook/radar-prueba-correo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
