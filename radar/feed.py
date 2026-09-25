"""Lectura del feed de sindicación de la Plataforma de Contratación (formato CODICE sobre Atom).

Las rutas de cada campo están en la especificación oficial de sindicación; las referencias
concretas, en docs/DATOS.md §2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

FEED_PERFILES = (
    "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
    "licitacionesPerfilesContratanteCompleto3.atom"
)

_ENTRADA = re.compile(r"<entry>(.*?)</entry>", re.S)
_SIGUIENTE = re.compile(r'<link href="([^"]+)" rel="next"')


def _uno(bloque: str, etiqueta: str) -> str | None:
    # El prefijo puede llevar guion (cbc-place-ext:ContractFolderStatusCode), así que \w no basta.
    m = re.search(rf"<(?:[\w-]+:)?{etiqueta}[^>]*>\s*([^<]+?)\s*<", bloque)
    return m.group(1) if m else None


def _dentro(bloque: str, contenedor: str) -> str | None:
    m = re.search(rf"<cac:{contenedor}>(.*?)</cac:{contenedor}>", bloque, re.S)
    return m.group(1) if m else None


@dataclass
class Licitacion:
    entry_id: str | None
    actualizada: str | None
    expediente: str | None
    organo: str | None
    objeto: str | None
    estado: str | None
    cpv: list[str] = field(default_factory=list)
    importe_sin_iva: float | None = None
    valor_estimado: float | None = None
    plazo_presentacion: str | None = None
    tipo_contrato: str | None = None
    pcap: str | None = None
    ppt: str | None = None
    anexos: list[str] = field(default_factory=list)
    solvencia_feed: str | None = None
    adjudicatario_nif: str | None = None
    adjudicatario_pyme: str | None = None
    lotes: int = 0
    ficha: str | None = None

    @property
    def solvencia_con_cifras(self) -> bool:
        if not self.solvencia_feed:
            return False
        return bool(
            re.search(r"\d[\d.,]*\s*(€|euros|EUR)|\d+(,\d+)?\s*(veces|x)\b", self.solvencia_feed, re.I)
        )

    @property
    def solvencia_remite_al_pliego(self) -> bool:
        if not self.solvencia_feed:
            return False
        return bool(re.search(r"pliego|PCAP|cláusul|clausul|cuadro resumen|anexo", self.solvencia_feed, re.I))


def _numero(texto: str | None) -> float | None:
    try:
        return float(texto) if texto else None
    except ValueError:
        return None


def parsear_entrada(bloque: str) -> Licitacion:
    proyecto = _dentro(bloque, "ProcurementProject") or bloque
    plazo = re.search(r"<cac:TenderSubmissionDeadlinePeriod>\s*<cbc:EndDate>\s*([\d-]+)", bloque)
    cualificacion = _dentro(bloque, "TendererQualificationRequest")
    solvencia = None
    if cualificacion:
        solvencia = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cualificacion)).strip() or None

    ganador = _dentro(bloque, "WinningParty")
    documento = lambda etiqueta: (  # noqa: E731
        re.search(rf"<cac:{etiqueta}>.*?<cbc:URI>\s*([^<]+?)\s*</cbc:URI>", bloque, re.S)
    )

    pcap = documento("LegalDocumentReference")
    ppt = documento("TechnicalDocumentReference")

    return Licitacion(
        entry_id=_uno(bloque, "id"),
        actualizada=_uno(bloque, "updated"),
        expediente=_uno(bloque, "ContractFolderID"),
        organo=_uno(bloque, "Name"),
        objeto=re.sub(r"\s+", " ", (_uno(bloque, "title") or "")) or None,
        estado=_uno(bloque, "ContractFolderStatusCode"),
        cpv=re.findall(r"<cbc:ItemClassificationCode[^>]*>\s*(\d+)", proyecto),
        importe_sin_iva=_numero(_uno(bloque, "TaxExclusiveAmount")),
        valor_estimado=_numero(_uno(bloque, "EstimatedOverallContractAmount")),
        plazo_presentacion=plazo.group(1) if plazo else None,
        tipo_contrato=_uno(bloque, "TypeCode"),
        pcap=pcap.group(1) if pcap else None,
        ppt=ppt.group(1) if ppt else None,
        anexos=re.findall(
            r"<cac:AdditionalDocumentReference>.*?<cbc:URI>\s*([^<]+?)\s*</cbc:URI>", bloque, re.S
        ),
        solvencia_feed=solvencia,
        adjudicatario_nif=_uno(ganador, "ID") if ganador else None,
        adjudicatario_pyme=_uno(bloque, "SMEAwardedIndicator"),
        lotes=len(re.findall(r"<cac:ProcurementProjectLot>", bloque)),
        ficha=(re.search(r'<link href="([^"]+)"', bloque) or [None, None])[1],
    )


def parsear_pagina(xml: str) -> tuple[list[Licitacion], str | None]:
    """Devuelve las licitaciones de una página del feed y la URL de la página anterior en el tiempo."""
    licitaciones = [parsear_entrada(b) for b in _ENTRADA.findall(xml)]
    siguiente = _SIGUIENTE.search(xml)
    return licitaciones, (siguiente.group(1) if siguiente else None)


def es_informatica(lic: Licitacion) -> bool:
    return any(c.startswith(("72", "48")) for c in lic.cpv)


def fecha(texto: str | None) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        return None
