"""Lectura del feed de sindicación de la Plataforma de Contratación (formato CODICE sobre Atom).

Las rutas de cada campo están en la especificación oficial de sindicación; las referencias
concretas, en docs/DATOS.md §2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

FEED_PERFILES = (
    "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
    "licitacionesPerfilesContratanteCompleto3.atom"
)

_ENTRADA = re.compile(r"<entry>.*?</entry>", re.S)
_SIGUIENTE = re.compile(r'<link href="([^"]+)" rel="next"')
_BAJA = re.compile(r"<at:deleted-entry\s([^>]*)>(.*?)</at:deleted-entry>", re.S)
_LOTE = re.compile(r"<cac:ProcurementProjectLot>(.*?)</cac:ProcurementProjectLot>", re.S)


def _uno(bloque: str, etiqueta: str) -> str | None:
    # Dos detalles del formato real: el prefijo puede llevar guion
    # (cbc-place-ext:ContractFolderStatusCode), así que \w no basta; y la etiqueta tiene que
    # terminar ahí, o "ID" acabaría casando con <cbc:IdentificationCode>.
    m = re.search(rf"<(?:[\w-]+:)?{etiqueta}(?=[\s/>])[^>]*>\s*([^<]+?)\s*<", bloque)
    return m.group(1) if m else None


def _dentro(bloque: str, contenedor: str) -> str | None:
    m = re.search(rf"<cac:{contenedor}>(.*?)</cac:{contenedor}>", bloque, re.S)
    return m.group(1) if m else None


@dataclass
class Lote:
    numero: int | None
    objeto: str | None
    importe: float | None
    cpv: list[str] = field(default_factory=list)


@dataclass
class Baja:
    """Una licitación que la Plataforma retira del feed (anulada, cerrada o archivada)."""

    entry_id: str
    cuando: str | None
    motivo: str | None


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
    adjudicatario_nombre: str | None = None
    adjudicatario_pyme: str | None = None
    lotes: list[Lote] = field(default_factory=list)
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


def _entero(texto: str | None) -> int | None:
    try:
        return int(texto) if texto else None
    except ValueError:
        return None


def momento(texto: str | None) -> datetime | None:
    """Convierte la fecha del feed a un instante.

    Comparar estas fechas como texto falla en el cambio de hora: el mismo día conviven
    +02:00 y +01:00, y entonces el orden alfabético no es el orden real.
    """
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.strip())
    except ValueError:
        return None


def lotes_de(bloque: str) -> list[Lote]:
    lotes = []
    for trozo in _LOTE.findall(bloque):
        lotes.append(
            Lote(
                numero=_entero(_uno(trozo, "ID")),
                objeto=_uno(trozo, "Name"),
                importe=_numero(_uno(trozo, "TaxExclusiveAmount")),
                cpv=re.findall(r"<cbc:ItemClassificationCode[^>]*>\s*(\d+)", trozo),
            )
        )
    return lotes


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
        adjudicatario_nombre=_uno(ganador, "Name") if ganador else None,
        adjudicatario_pyme=_uno(bloque, "SMEAwardedIndicator"),
        lotes=lotes_de(bloque),
        ficha=(re.search(r'<link href="([^"]+)"', bloque) or [None, None])[1],
    )


def entradas(xml: str) -> list[str]:
    """Los bloques <entry> de una página, cada uno completo y sin nada detrás.

    Partir el texto por "<entry>" dejaba en el último bloque todo lo que venía después
    (el cierre del feed y las bajas), y eso acababa guardado en staging como si fuera parte
    de la entrada.
    """
    return _ENTRADA.findall(xml)


def siguiente_pagina(xml: str) -> str | None:
    m = _SIGUIENTE.search(xml)
    return m.group(1) if m else None


def bajas(xml: str) -> list[Baja]:
    """Licitaciones que la Plataforma retira: <at:deleted-entry ref=... when=...>."""
    retiradas = []
    for atributos, cuerpo in _BAJA.findall(xml):
        ref = re.search(r'ref="([^"]+)"', atributos)
        cuando = re.search(r'when="([^"]+)"', atributos)
        motivo = re.search(r'<at:comment type="([^"]+)"', cuerpo)
        if ref:
            retiradas.append(
                Baja(
                    entry_id=ref.group(1),
                    cuando=cuando.group(1) if cuando else None,
                    motivo=motivo.group(1) if motivo else None,
                )
            )
    return retiradas


def parsear_pagina(xml: str) -> tuple[list[Licitacion], str | None]:
    """Devuelve las licitaciones de una página del feed y la URL de la página anterior en el tiempo."""
    return [parsear_entrada(b) for b in entradas(xml)], siguiente_pagina(xml)


def es_informatica(lic: Licitacion) -> bool:
    return any(c.startswith(("72", "48")) for c in lic.cpv)


def fecha(texto: str | None) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        return None
