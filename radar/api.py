"""Servicio HTTP del radar. Es la frontera con n8n: n8n no sabe cómo se decide, solo a qué
endpoint llamar (docs/DECISIONES.md D11).

    uv run uvicorn radar.api:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from radar import ingesta, pliegos
from radar.bd import conectar
from radar.errores import ErrorRadar

app = FastAPI(title="Radar de licitaciones", version="0.1.0")


@app.exception_handler(ErrorRadar)
def error_legible(peticion: Request, error: ErrorRadar) -> JSONResponse:
    """Un solo sitio donde los fallos previstos se convierten en respuesta.

    El mensaje sale tal cual en el correo de aviso de n8n, así que lo lee una persona:
    nunca una traza (CLAUDE.md, innegociable 3). El detalle técnico va al log.
    """
    return JSONResponse(status_code=503, content={"estado": "error", "mensaje": error.mensaje})


class PeticionIngesta(BaseModel):
    paginas: int = Field(default=5, ge=1, le=60, description="páginas del feed como máximo")
    tipo: str = Field(default="diaria", pattern="^(diaria|manual|historica)$")
    n8n_execution_id: str | None = Field(default=None, description="ejecución de n8n que lo dispara")


@app.get("/salud")
def salud() -> dict:
    """Comprueba que la base de datos responde. n8n lo usa antes de disparar nada."""
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        licitaciones = cur.fetchone()[0]
    return {"estado": "ok", "licitaciones": licitaciones}


@app.post("/ingesta")
def lanzar_ingesta(peticion: PeticionIngesta) -> dict:
    """Descarga el feed desde el último punto procesado y lo carga en la base de datos."""
    return ingesta.ingerir(peticion.paginas, peticion.tipo, peticion.n8n_execution_id)


class PeticionPliegos(BaseModel):
    limite: int = Field(default=20, ge=1, le=200, description="pliegos como máximo en esta pasada")
    documento: str = Field(default="PCAP", pattern="^(PCAP|PPT|anexo)$")
    tipo: str = Field(default="diaria", pattern="^(diaria|manual|historica)$")
    n8n_execution_id: str | None = None


@app.post("/pliegos")
def bajar_pliegos(peticion: PeticionPliegos) -> dict:
    """Baja los pliegos pendientes de las licitaciones candidatas."""
    return pliegos.descargar_pendientes(
        limite=peticion.limite,
        tipo=peticion.documento,
        tipo_ejecucion=peticion.tipo,
        n8n_execution_id=peticion.n8n_execution_id,
    )


@app.get("/resumen/hoy")
def resumen_hoy() -> dict:
    """Lo ingerido en la última ejecución correcta, para el informe diario."""
    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(
            "SELECT run_id, inicio, fin, estado FROM ejecuciones"
            " WHERE estado = 'ok' ORDER BY inicio DESC LIMIT 1"
        )
        fila = cur.fetchone()
        if not fila:
            return {"estado": "sin_ejecuciones"}
        cur.execute(
            "SELECT count(*) FROM licitaciones l JOIN stg_entradas s ON s.id = l.stg_entrada"
            " JOIN raw_ficheros r ON r.sha256 = s.raw_fichero WHERE r.ejecucion_id = %s",
            (fila[0],),
        )
        nuevas = cur.fetchone()[0]
    return {
        "run_id": str(fila[0]),
        "inicio": fila[1].isoformat(),
        "fin": fila[2].isoformat() if fila[2] else None,
        "licitaciones_ingeridas": nuevas,
    }
