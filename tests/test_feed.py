"""Lectura del feed, comprobada contra una entrada real descargada de la Plataforma.

La entrada de tests/fixtures/entrada_real.xml es un expediente público de verdad, no un
ejemplo inventado (CLAUDE.md, innegociable 2).
"""

from pathlib import Path

import pytest
from conftest import BAJA_REAL, entrada, pagina

from radar import feed

FIXTURE = Path(__file__).parent / "fixtures" / "entrada_real.xml"


@pytest.fixture(scope="module")
def licitacion() -> feed.Licitacion:
    return feed.parsear_entrada(FIXTURE.read_text(encoding="utf-8"))


def test_identifica_el_expediente_y_el_organo(licitacion):
    assert licitacion.entry_id.startswith("https://contrataciondelestado.es/sindicacion/")
    assert licitacion.expediente == "2026-07-SG-SEGURO SALUD"
    assert "Sociedad" in licitacion.organo


def test_lee_el_estado_aunque_la_etiqueta_lleve_prefijo_con_guion(licitacion):
    # La etiqueta real es <cbc-place-ext:ContractFolderStatusCode>. Con un prefijo sin guion
    # el campo salia vacio y toda la Fase 1 contaba mal los estados.
    assert licitacion.estado in {"PUB", "EV", "ADJ", "RES", "PRE", "ANUL"}


def test_lee_importes_cpv_y_plazo(licitacion):
    assert licitacion.importe_sin_iva == 69360.0
    assert licitacion.valor_estimado == 138720.0
    assert licitacion.cpv[0].startswith("66")
    assert licitacion.plazo_presentacion == "2026-07-16"


def test_lee_los_enlaces_a_los_documentos(licitacion):
    assert licitacion.pcap.startswith("https://contrataciondelestado.es/FileSystem/servlet/")
    assert "DocumentIdParam" in licitacion.pcap


def test_lee_el_adjudicatario(licitacion):
    assert licitacion.adjudicatario_nif == "A08169294"


def test_clasifica_la_solvencia_del_feed(licitacion):
    assert licitacion.solvencia_feed
    assert licitacion.solvencia_con_cifras is True


def test_distingue_las_licitaciones_de_informatica():
    informatica = feed.Licitacion(None, None, None, None, None, None, cpv=["72253200"])
    seguros = feed.Licitacion(None, None, None, None, None, None, cpv=["66512200"])
    assert feed.es_informatica(informatica)
    assert not feed.es_informatica(seguros)


def test_una_pagina_trae_licitaciones_y_enlace_a_la_siguiente():
    xml = (
        '<feed><link href="https://ejemplo.es/pagina2.atom" rel="next"/>'
        + FIXTURE.read_text(encoding="utf-8")
        + "</feed>"
    )
    licitaciones, siguiente = feed.parsear_pagina(xml)
    assert len(licitaciones) == 1
    assert siguiente == "https://ejemplo.es/pagina2.atom"


def test_las_entradas_no_arrastran_el_cierre_del_feed():
    # Partir el XML por "<entry>" deja en el ultimo bloque todo lo que viene detras: el
    # cierre del feed y las bajas. Ese bloque se guardaba tal cual en staging.
    xml = pagina(
        [entrada("uno", "2026-09-05T10:00:00.000+02:00"), entrada("dos", "2026-09-04T10:00:00.000+02:00")],
        bajas=BAJA_REAL,
    ).decode("utf-8")
    bloques = feed.entradas(xml)
    assert len(bloques) == 2
    assert "</feed>" not in bloques[-1]
    assert "deleted-entry" not in bloques[-1]


def test_reconoce_las_licitaciones_anuladas():
    xml = pagina([entrada("uno", "2026-09-05T10:00:00.000+02:00")], bajas=BAJA_REAL).decode("utf-8")
    bajas = feed.bajas(xml)
    assert len(bajas) == 1
    assert bajas[0].entry_id.endswith("/20499474")
    assert bajas[0].motivo == "ANULADA"
    assert bajas[0].cuando.startswith("2026-09-04")


def test_lee_los_lotes_con_su_objeto_su_importe_y_su_cpv():
    bloque = (FIXTURE.parent / "entrada_con_lotes.xml").read_text(encoding="utf-8")
    licitacion = feed.parsear_entrada(bloque)
    assert len(licitacion.lotes) == 2
    assert licitacion.lotes[0].numero == 1
    assert licitacion.lotes[0].objeto == "Fiesta de la Vendimia"
    assert licitacion.lotes[1].importe == 16550.0
    assert "79952000" in licitacion.lotes[0].cpv


def test_una_licitacion_sin_lotes_no_inventa_ninguno(licitacion):
    assert licitacion.lotes == []


def test_ordena_las_fechas_aunque_cambie_el_huso():
    # El 25-10-2026 el horario pasa de +02:00 a +01:00.
    antes = feed.momento("2026-10-25T03:00:00.000+02:00")  # 01:00 UTC
    despues = feed.momento("2026-10-25T02:30:00.000+01:00")  # 01:30 UTC
    assert despues > antes
